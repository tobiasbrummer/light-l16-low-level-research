// SPDX-License-Identifier: MIT
/*
 * Minimal clean-room LD_PRELOAD prototype for the identified LCC HAL path.
 *
 * It deliberately supports one in-flight write, matching the repository's
 * fixed n_burst=1 profiles.  The real writeFile() runs on a worker while the
 * interposed closeCamera() joins that worker before allowing HAL teardown.
 */

#if defined(L16_ANDROID_FREESTANDING)
typedef unsigned long l16_size_t;
typedef unsigned long pthread_t;

extern void *dlsym(void *handle, const char *symbol);
extern void *dlopen(const char *filename, int flags);
extern char *getenv(const char *name);
extern int fork(void);
extern int execve(
    const char *filename,
    char *const arguments[],
    char *const environment[]
);
extern int waitpid(int pid, int *status, int options);
extern void _exit(int status);
extern int pthread_create(
    pthread_t *thread,
    const void *attributes,
    void *(*start_routine)(void *),
    void *argument
);
extern int pthread_join(pthread_t thread, void **return_value);
extern long write(int fd, const void *buffer, l16_size_t length);

#define L16_RTLD_NOW 2
#define L16_RTLD_LOCAL 0
#else
#include <dlfcn.h>
#include <pthread.h>
#include <stddef.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef size_t l16_size_t;
#define L16_RTLD_NOW RTLD_NOW
#define L16_RTLD_LOCAL RTLD_LOCAL
#endif

extern int unsetenv(const char *name);
extern char **environ;


#define L16_WRITE_SYMBOL "_ZN7qcamera12LccInterface9writeFileEv"
#ifdef L16_TIMEOUT_PATCH_SECONDS
/* Optional second job: raise the capture-completion budget.
 *
 * openCamera derives it from its third argument and stores it at instance
 * offset 0x24 (str r3, [r4, #0x24] at 0x97f54); only closeCamera reads it,
 * as the deadline for the pipeline to finish.  The budget is flat at 15 s
 * below 9 s and grows slower than the work above it.
 *
 * That was expected to explain the roughly six-second exposure ceiling.  It
 * does not.  A 6 s all-16 capture with this patch active -- verified applied,
 * 180 s instead of 15 s -- failed exactly as it does without it, and produced
 * no more data.  The real failure is seventeen of twenty buffers failing to
 * mmap in writeFile; see docs/lcc-control.md.  The patch is kept because the
 * offset and the formula are confirmed on hardware and it reproduces that
 * negative result, not because it lifts the ceiling.
 *
 * This lives here rather than in a second preload because two preloads each
 * run their own child self-test, and the extra system() call breaks the
 * helper-command count this shim verifies.
 */
#define L16_OPEN_SYMBOL "_ZN7qcamera12LccInterface10openCameraEjhj"
#define L16_TIMEOUT_OFFSET 0x24
#endif
#define L16_CLOSE_SYMBOL "_ZN7qcamera12LccInterface11closeCameraEv"

#ifndef L16_TARGET_LIBRARY
#define L16_TARGET_LIBRARY "/system/lib/hw/camera.msm8996.so"
#endif

#ifndef L16_EXPECTED_HELPER_COMMANDS
#define L16_EXPECTED_HELPER_COMMANDS 7
#endif

#ifndef L16_SHELL_PATH
#define L16_SHELL_PATH "/system/bin/sh"
#endif

#define L16_MAX_ENVIRONMENT_ENTRIES 128

#define L16_LOG(literal)                                                       \
    do {                                                                       \
        static const char message[] = "L16_ASYNC_SHIM " literal "\n";          \
        long write_result =                                                    \
            write(2, message, (l16_size_t)(sizeof(message) - 1));              \
        (void)write_result;                                                     \
    } while (0)

enum l16_writer_state {
    L16_IDLE = 0,
    L16_RUNNING = 1,
    L16_DONE = 2,
};

#ifdef L16_TIMEOUT_PATCH_SECONDS
typedef int (*l16_open_camera_fn)(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
);
#endif

typedef int (*l16_write_file_fn)(void *self);
typedef int (*l16_close_camera_fn)(void *self);

static int l16_state = L16_IDLE;
static int l16_thread_valid;
static int l16_join_claimed;
static int l16_protocol_error;
static int l16_writer_result = 1;
static int l16_helper_calls;
static int l16_helper_failures;
static int l16_clean_environment_ready;
static pthread_t l16_thread;
static void *l16_job_self;
static void *l16_target_handle;
#ifdef L16_TIMEOUT_PATCH_SECONDS
static l16_open_camera_fn l16_real_open_camera;
static int l16_timeout_patched;
#endif
static l16_write_file_fn l16_real_write;
static l16_close_camera_fn l16_real_close;
static char *l16_clean_environment[L16_MAX_ENVIRONMENT_ENTRIES];


#ifdef L16_TIMEOUT_PATCH_SECONDS
__attribute__((visibility("default")))
int l16_interposed_open_camera(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
) __asm__(L16_OPEN_SYMBOL);
#endif

__attribute__((visibility("default")))
int l16_interposed_write_file(void *self)
    __asm__(L16_WRITE_SYMBOL);

__attribute__((visibility("default")))
int l16_interposed_close_camera(void *self)
    __asm__(L16_CLOSE_SYMBOL);

__attribute__((visibility("default")))
int l16_interposed_system(const char *command)
    __asm__("system");


static int l16_is_preload_entry(const char *entry)
{
    static const char prefix[] = "LD_PRELOAD=";
    l16_size_t index;

    if (entry == (const char *)0) {
        return 0;
    }
    for (index = 0; index < (l16_size_t)(sizeof(prefix) - 1); ++index) {
        if (entry[index] != prefix[index]) {
            return 0;
        }
    }
    return 1;
}


static int l16_prepare_clean_environment(void)
{
    l16_size_t source = 0;
    l16_size_t destination = 0;

    if (environ != (char **)0) {
        while (environ[source] != (char *)0) {
            if (!l16_is_preload_entry(environ[source])) {
                if (destination + 1 >= L16_MAX_ENVIRONMENT_ENTRIES) {
                    L16_LOG("environment_too_large_error");
                    return 1;
                }
                l16_clean_environment[destination++] = environ[source];
            }
            ++source;
        }
    }
    l16_clean_environment[destination] = (char *)0;
    __atomic_store_n(&l16_clean_environment_ready, 1, __ATOMIC_RELEASE);
    return 0;
}


int l16_interposed_system(const char *command)
{
    char *arguments[4];
    int pid;
    int waited;
    int status = -1;

    if (command == (const char *)0) {
        return 1;
    }
    __atomic_add_fetch(&l16_helper_calls, 1, __ATOMIC_ACQ_REL);
    if (__atomic_load_n(&l16_clean_environment_ready, __ATOMIC_ACQUIRE) == 0) {
        __atomic_add_fetch(&l16_helper_failures, 1, __ATOMIC_ACQ_REL);
        L16_LOG("helper_environment_not_ready_error");
        return -1;
    }

    arguments[0] = (char *)"sh";
    arguments[1] = (char *)"-c";
    arguments[2] = (char *)command;
    arguments[3] = (char *)0;
    pid = fork();
    if (pid == 0) {
        (void)execve(
            L16_SHELL_PATH,
            arguments,
            l16_clean_environment
        );
        _exit(127);
    }
    if (pid < 0) {
        __atomic_add_fetch(&l16_helper_failures, 1, __ATOMIC_ACQ_REL);
        L16_LOG("helper_fork_failed");
        return -1;
    }
    waited = waitpid(pid, &status, 0);
    if (waited != pid || status != 0) {
        __atomic_add_fetch(&l16_helper_failures, 1, __ATOMIC_ACQ_REL);
        L16_LOG("helper_command_failed");
    }
    return waited == pid ? status : -1;
}


static int l16_resolve_targets(void)
{
    union l16_write_cast {
        void *object;
        l16_write_file_fn function;
    } write_symbol;
    union l16_close_cast {
        void *object;
        l16_close_camera_fn function;
    } close_symbol;

    l16_target_handle = dlopen(
        L16_TARGET_LIBRARY,
        L16_RTLD_NOW | L16_RTLD_LOCAL
    );
    if (l16_target_handle == (void *)0) {
        L16_LOG("target_dlopen_failed");
        return 1;
    }

#ifdef L16_TIMEOUT_PATCH_SECONDS
    {
        union l16_open_cast {
            void *object;
            l16_open_camera_fn function;
        } open_symbol;

        open_symbol.object = dlsym(l16_target_handle, L16_OPEN_SYMBOL);
        l16_real_open_camera = open_symbol.function;
        if (l16_real_open_camera == (l16_open_camera_fn)0 ||
            l16_real_open_camera == l16_interposed_open_camera) {
            L16_LOG("open_camera_resolve_failed");
            return 1;
        }
    }
#endif
    write_symbol.object = dlsym(l16_target_handle, L16_WRITE_SYMBOL);
    close_symbol.object = dlsym(l16_target_handle, L16_CLOSE_SYMBOL);
    l16_real_write = write_symbol.function;
    l16_real_close = close_symbol.function;
    if (l16_real_write == (l16_write_file_fn)0 ||
        l16_real_close == (l16_close_camera_fn)0) {
        L16_LOG("target_dlsym_failed");
        return 1;
    }
    if (l16_real_write == l16_interposed_write_file ||
        l16_real_close == l16_interposed_close_camera) {
        L16_LOG("target_resolved_to_shim_error");
        return 1;
    }

    L16_LOG("resolve_targets_ok");
    return 0;
}


static void *l16_writer_main(void *unused)
{
    int result;

    (void)unused;
    L16_LOG("worker_start");
    result = l16_real_write(l16_job_self);
    __atomic_store_n(&l16_writer_result, result, __ATOMIC_RELEASE);
    __atomic_store_n(&l16_state, L16_DONE, __ATOMIC_RELEASE);
    if (result == 0) {
        L16_LOG("worker_done_ok");
    } else {
        L16_LOG("worker_done_error");
    }
    return (void *)0;
}


__attribute__((constructor))
static void l16_shim_loaded(void)
{
    L16_LOG("loaded");
    if (unsetenv("LD_PRELOAD") != 0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("unsetenv_failed");
        return;
    }
    if (getenv("LD_PRELOAD") != (char *)0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("preload_still_present_error");
        return;
    }
    if (l16_prepare_clean_environment() != 0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        return;
    }
    L16_LOG("preload_cleared");
    if (l16_resolve_targets() != 0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
    }
    if (l16_interposed_system(":") == 0) {
        L16_LOG("preload_child_selftest_ok");
    } else {
        L16_LOG("preload_child_selftest_failed");
        _exit(125);
    }
    __atomic_store_n(&l16_helper_calls, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&l16_helper_failures, 0, __ATOMIC_RELEASE);
}


#ifdef L16_TIMEOUT_PATCH_SECONDS
int l16_interposed_open_camera(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
)
{
    volatile unsigned int *field;
    unsigned int expected_timeout;
    int result;

    if (l16_real_open_camera == (l16_open_camera_fn)0 || self == (void *)0) {
        L16_LOG("open_camera_precondition_failed");
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        return -1;
    }

    /* The return value is not a success flag: lcc continues past a nonzero
     * result, so the field itself is the evidence that openCamera ran. */
    result = l16_real_open_camera(self, first, second, third);

    field = (volatile unsigned int *)((char *)self + L16_TIMEOUT_OFFSET);
    expected_timeout = third > 9u ? third + 5u : 15u;
    if (*field != expected_timeout) {
        /* Offset moved, or the value is no longer derived this way.  Writing
         * anyway would clobber an unknown member. */
        L16_LOG("timeout_field_unexpected_not_patched");
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        return result;
    }
    *field = (unsigned int)L16_TIMEOUT_PATCH_SECONDS;
    if (*field != (unsigned int)L16_TIMEOUT_PATCH_SECONDS) {
        L16_LOG("timeout_write_did_not_stick");
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        return result;
    }
    l16_timeout_patched = 1;
    L16_LOG("timeout_patched");
    return result;
}
#endif

int l16_interposed_write_file(void *self)
{
    int expected = L16_IDLE;
    int create_result;

    if (!__atomic_compare_exchange_n(
            &l16_state,
            &expected,
            L16_RUNNING,
            0,
            __ATOMIC_ACQ_REL,
            __ATOMIC_ACQUIRE)) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("unexpected_second_write");
        /* Let the fixed workflow reach closeCamera(), which reports failure. */
        return 0;
    }

    l16_job_self = self;
    if (l16_real_write == (l16_write_file_fn)0) {
        __atomic_store_n(&l16_writer_result, 1, __ATOMIC_RELEASE);
        __atomic_store_n(&l16_state, L16_DONE, __ATOMIC_RELEASE);
        L16_LOG("resolve_write_failed");
        return 0;
    }

    create_result = pthread_create(
        &l16_thread,
        (const void *)0,
        l16_writer_main,
        (void *)0
    );
    if (create_result != 0) {
        __atomic_store_n(&l16_writer_result, 1, __ATOMIC_RELEASE);
        __atomic_store_n(&l16_state, L16_DONE, __ATOMIC_RELEASE);
        L16_LOG("pthread_create_failed");
        return 0;
    }
    __atomic_store_n(&l16_thread_valid, 1, __ATOMIC_RELEASE);
    L16_LOG("enqueue_ok");
    return 0;
}


int l16_interposed_close_camera(void *self)
{
    l16_close_camera_fn real_close;
    int close_result;
    int join_result = 0;
    int writer_result;
    int helper_calls;
    int helper_failures;

    if (__atomic_load_n(&l16_thread_valid, __ATOMIC_ACQUIRE) != 0 &&
        __atomic_exchange_n(&l16_join_claimed, 1, __ATOMIC_ACQ_REL) == 0) {
        L16_LOG("close_wait");
        join_result = pthread_join(l16_thread, (void **)0);
        if (join_result != 0) {
            L16_LOG("pthread_join_failed");
        }
        __atomic_store_n(&l16_thread_valid, 0, __ATOMIC_RELEASE);
    }

    writer_result = __atomic_load_n(&l16_writer_result, __ATOMIC_ACQUIRE);
    if (join_result != 0) {
        /* Never tear down the HAL while worker completion is uncertain. */
        L16_LOG("close_reports_error");
        return 0;
    }

    real_close = l16_real_close;
    if (real_close == (l16_close_camera_fn)0) {
        L16_LOG("resolve_close_failed");
        return 0;
    }

    L16_LOG("close_continue");
    close_result = real_close(self);
    helper_calls = __atomic_load_n(&l16_helper_calls, __ATOMIC_ACQUIRE);
    helper_failures = __atomic_load_n(&l16_helper_failures, __ATOMIC_ACQUIRE);
    if (helper_calls == L16_EXPECTED_HELPER_COMMANDS && helper_failures == 0) {
        L16_LOG("helper_commands_ok");
    } else {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("helper_command_count_or_status_error");
    }
    if (writer_result != 0 ||
        __atomic_load_n(&l16_protocol_error, __ATOMIC_ACQUIRE) != 0) {
        L16_LOG("close_reports_error");
        return 0;
    }
    L16_LOG("close_reports_ok");
    return close_result;
}
