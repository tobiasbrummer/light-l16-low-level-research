// SPDX-License-Identifier: MIT
/*
 * Clean-room LD_PRELOAD prototype that raises LCC's capture-completion
 * timeout so exposures beyond roughly five seconds can finish.
 *
 * LccInterface::openCamera() derives a per-run timeout from its third
 * argument and stores it in the instance:
 *
 *     openCamera @0x97f40:  cmp   r7, #9
 *                           addhi r3, r7, #5
 *                           movls r3, #15
 *                           str   r3, [r4, #0x24]
 *
 * The value is read only by closeCamera(), which adds it to the current time
 * and waits for the pipeline to finish:
 *
 *     closeCamera @0x97b78: ldr r2, [r4, #0x24]
 *                           add r1, r3, r2        ; deadline = now + timeout
 *
 * The budget is therefore constant at 15 s for every exposure up to 9 s,
 * while the work per capture grows with the exposure.  Past about five
 * seconds the wait expires, closeCamera tears the pipeline down, and the
 * artifact is left truncated: a 6 s all-16 request produced 34,631,680 of
 * 259,999,993 bytes.
 *
 * This preload calls the real openCamera and then replaces that one field.
 * It does not change the exposure, the module mask, the gain, or any other
 * capture parameter, and it touches nothing else in the instance.
 *
 * Before writing it verifies that the field holds exactly what the
 * disassembled formula predicts for the argument it just saw.  A different
 * value means the offset assumption no longer holds -- a changed build, a
 * different overload -- and the shim then refuses to write rather than
 * corrupting an unknown member.
 */

#if defined(L16_ANDROID_FREESTANDING)
typedef unsigned long l16_size_t;

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
extern long write(int fd, const void *buffer, l16_size_t length);

#define L16_RTLD_NOW 2
#define L16_RTLD_LOCAL 0
#else
#include <dlfcn.h>
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

#define L16_OPEN_SYMBOL "_ZN7qcamera12LccInterface10openCameraEjhj"

#ifndef L16_TARGET_LIBRARY
#define L16_TARGET_LIBRARY "/system/lib/hw/camera.msm8996.so"
#endif

/* Byte offset of mThreadTimeout inside LccInterface, from the store at
 * 0x97f54.  Written only by the constructor and by openCamera; read only by
 * closeCamera. */
#ifndef L16_TIMEOUT_OFFSET
#define L16_TIMEOUT_OFFSET 0x24
#endif

/* Seconds granted to the capture-completion wait.  Chosen to cover the
 * longest exposure the sensor accepts plus readout and the LRI write, with
 * margin.  This is an upper bound on waiting, not a target: the wrapper's own
 * outer timeout still bounds the whole invocation, so a genuinely hung
 * pipeline is still cut short from outside. */
#ifndef L16_TIMEOUT_SECONDS
#define L16_TIMEOUT_SECONDS 120u
#endif

#ifndef L16_SHELL_PATH
#define L16_SHELL_PATH "/system/bin/sh"
#endif

#define L16_MAX_ENVIRONMENT_ENTRIES 128

#define L16_LOG(literal)                                                       \
    do {                                                                       \
        static const char message[] = "L16_TIMEOUT_SHIM " literal "\n";        \
        long write_result =                                                    \
            write(2, message, (l16_size_t)(sizeof(message) - 1));              \
        (void)write_result;                                                    \
    } while (0)

typedef int (*l16_open_camera_fn)(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
);

static int l16_protocol_error;
static int l16_open_calls;
static int l16_helper_calls;
static int l16_helper_failures;
static int l16_clean_environment_ready;
static void *l16_target_handle;
static l16_open_camera_fn l16_real_open_camera;
static char *l16_clean_environment[L16_MAX_ENVIRONMENT_ENTRIES];

__attribute__((visibility("default")))
int l16_interposed_open_camera(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
) __asm__(L16_OPEN_SYMBOL);

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


/* lcc forks shell helpers.  They must not inherit this 32-bit preload, so a
 * copy of the environment without LD_PRELOAD is prepared once at load time
 * and used for every child. */
static int l16_prepare_clean_environment(void)
{
    l16_size_t source = 0;
    l16_size_t target = 0;

    if (environ == (char **)0) {
        L16_LOG("environment_missing");
        return 1;
    }
    while (environ[source] != (char *)0) {
        if (!l16_is_preload_entry(environ[source])) {
            if (target >= (l16_size_t)(L16_MAX_ENVIRONMENT_ENTRIES - 1)) {
                L16_LOG("environment_too_large");
                return 1;
            }
            l16_clean_environment[target] = environ[source];
            ++target;
        }
        ++source;
    }
    l16_clean_environment[target] = (char *)0;
    l16_clean_environment_ready = 1;
    return 0;
}


int l16_interposed_system(const char *command)
{
    char *arguments[4];
    int pid;
    int status = -1;
    int waited;

    if (command == (const char *)0) {
        return 1;
    }
    if (!l16_clean_environment_ready) {
        L16_LOG("helper_without_clean_environment");
        return -1;
    }
    ++l16_helper_calls;

    arguments[0] = (char *)"sh";
    arguments[1] = (char *)"-c";
    arguments[2] = (char *)command;
    arguments[3] = (char *)0;

    pid = fork();
    if (pid < 0) {
        ++l16_helper_failures;
        L16_LOG("helper_fork_failed");
        return -1;
    }
    if (pid == 0) {
        execve(L16_SHELL_PATH, arguments, l16_clean_environment);
        _exit(127);
    }
    waited = waitpid(pid, &status, 0);
    if (waited != pid || status != 0) {
        ++l16_helper_failures;
        L16_LOG("helper_command_failed");
    }
    return waited == pid ? status : -1;
}


static int l16_resolve_targets(void)
{
    union l16_open_cast {
        void *object;
        l16_open_camera_fn function;
    } open_symbol;

    l16_target_handle = dlopen(
        L16_TARGET_LIBRARY,
        L16_RTLD_NOW | L16_RTLD_LOCAL
    );
    if (l16_target_handle == (void *)0) {
        L16_LOG("target_dlopen_failed");
        return 1;
    }

    open_symbol.object = dlsym(l16_target_handle, L16_OPEN_SYMBOL);
    l16_real_open_camera = open_symbol.function;
    if (l16_real_open_camera == (l16_open_camera_fn)0) {
        L16_LOG("target_dlsym_failed");
        return 1;
    }
    if (l16_real_open_camera == l16_interposed_open_camera) {
        L16_LOG("target_resolved_to_shim_error");
        return 1;
    }

    L16_LOG("resolve_targets_ok");
    return 0;
}


/* The value openCamera is known to store, reproduced from the disassembly so
 * the shim can tell whether it is looking at the field it thinks it is. */
static unsigned int l16_expected_timeout(unsigned int third)
{
    return third > 9u ? third + 5u : 15u;
}


int l16_interposed_open_camera(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
)
{
    volatile unsigned int *field;
    unsigned int found;
    unsigned int expected;
    int result;

    if (l16_protocol_error) {
        L16_LOG("open_refused_after_protocol_error");
        return -1;
    }
    if (l16_real_open_camera == (l16_open_camera_fn)0) {
        L16_LOG("open_without_resolved_target");
        return -1;
    }
    if (self == (void *)0) {
        L16_LOG("open_without_instance");
        return -1;
    }

    ++l16_open_calls;
    if (l16_open_calls != 1) {
        /* The fixed profiles open the camera exactly once.  A second open
         * would mean the run is not what this shim was reasoned about. */
        L16_LOG("open_called_more_than_once");
        l16_protocol_error = 1;
        return -1;
    }

    result = l16_real_open_camera(self, first, second, third);
    if (result != 0) {
        L16_LOG("real_open_camera_failed");
        return result;
    }
    L16_LOG("real_open_camera_ok");

    field = (volatile unsigned int *)((char *)self + L16_TIMEOUT_OFFSET);
    found = *field;
    expected = l16_expected_timeout(third);
    if (found != expected) {
        /* Either the offset moved or openCamera no longer derives the value
         * this way.  Writing anyway would clobber an unknown member, so the
         * capture proceeds with the stock timeout instead. */
        L16_LOG("timeout_field_unexpected_not_patched");
        l16_protocol_error = 1;
        return result;
    }

    *field = (unsigned int)L16_TIMEOUT_SECONDS;
    if (*field != (unsigned int)L16_TIMEOUT_SECONDS) {
        L16_LOG("timeout_write_did_not_stick");
        l16_protocol_error = 1;
        return result;
    }

    L16_LOG("timeout_patched");
    return result;
}


__attribute__((constructor))
static void l16_shim_loaded(void)
{
    L16_LOG("loaded");
    if (unsetenv("LD_PRELOAD") != 0) {
        l16_protocol_error = 1;
        L16_LOG("unsetenv_failed");
        return;
    }
    if (getenv("LD_PRELOAD") != (char *)0) {
        l16_protocol_error = 1;
        L16_LOG("preload_still_present_error");
        return;
    }
    if (l16_prepare_clean_environment() != 0) {
        l16_protocol_error = 1;
        return;
    }
    L16_LOG("preload_cleared");
    if (l16_resolve_targets() != 0) {
        l16_protocol_error = 1;
        return;
    }
    if (l16_interposed_system(":") == 0) {
        L16_LOG("preload_child_selftest_ok");
    } else {
        l16_protocol_error = 1;
        L16_LOG("preload_child_selftest_failed");
    }
}


__attribute__((destructor))
static void l16_shim_unloaded(void)
{
    if (l16_helper_failures != 0) {
        L16_LOG("helper_commands_failed");
    } else {
        L16_LOG("helper_commands_ok");
    }
    if (l16_protocol_error) {
        L16_LOG("close_reports_error");
    } else {
        L16_LOG("close_reports_ok");
    }
}
