// SPDX-License-Identifier: MIT
/*
 * Fixed A1 center-focus gate for the identified Light L16 LCC capture path.
 *
 * LccInterface::reqThreadRun() submits preview requests through the exported
 * QCamera3HardwareInterface::processCaptureRequest() PLT entry.  The matching
 * static camera3 callback forwards results through the exported
 * LccInterface::processCaptureResult() PLT entry.  This preload interposes both
 * calls: after startCapture() arms the gate, exactly one preview request gets
 * AF_MODE_AUTO, the fixed center ROI, and AF_TRIGGER_START.  Later requests
 * keep AF_MODE_AUTO and the ROI with AF_TRIGGER_IDLE.  The real lcc capture is
 * released only after result metadata for that frame or a later frame reports
 * AF_STATE_FOCUSED_LOCKED.
 *
 * No raw CCB/I2C autofocus request is sent.  This is intentionally fixed to
 * the verified A1 profile and exact production HAL.  A live wrapper must still
 * hash-gate lcc, the HAL, and this shim, and reboot after every attempt.
 */

#if defined(L16_ANDROID_FREESTANDING)
typedef unsigned char l16_u8;
typedef signed int l16_i32;
typedef unsigned int l16_u32;
typedef unsigned long l16_size_t;

extern void *dlsym(void *handle, const char *symbol);
extern void *dlopen(const char *filename, int flags);
extern char *getenv(const char *name);
extern int unsetenv(const char *name);
extern int fork(void);
extern int execve(
    const char *filename,
    char *const arguments[],
    char *const environment[]
);
extern int waitpid(int pid, int *status, int options);
extern void _exit(int status);
extern long write(int fd, const void *buffer, l16_size_t length);
extern int usleep(unsigned int microseconds);

#define L16_RTLD_NOW 2
#define L16_RTLD_LOCAL 0
#else
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef uint8_t l16_u8;
typedef int32_t l16_i32;
typedef uint32_t l16_u32;
typedef size_t l16_size_t;
#define L16_RTLD_NOW RTLD_NOW
#define L16_RTLD_LOCAL RTLD_LOCAL
#endif

#if !defined(L16_ANDROID_FREESTANDING)
extern int unsetenv(const char *name);
extern int usleep(unsigned int microseconds);
#endif

extern char **environ;


#define L16_START_SYMBOL "_ZN7qcamera12LccInterface12startCaptureEv"
#define L16_CLOSE_CAMERA_SYMBOL "_ZN7qcamera12LccInterface11closeCameraEv"
#define L16_CLOSE_SYMBOL "_ZN7qcamera12LccInterface5closeEv"
#define L16_PROCESS_REQUEST_SYMBOL                                           \
    "_ZN7qcamera25QCamera3HardwareInterface21processCaptureRequest"         \
    "EP23camera3_capture_request"
#define L16_PROCESS_RESULT_SYMBOL                                            \
    "_ZN7qcamera12LccInterface20processCaptureResult"                       \
    "EPK22camera3_capture_result"

#ifndef L16_TARGET_LIBRARY
#define L16_TARGET_LIBRARY "/system/lib/hw/camera.msm8996.so"
#endif

#ifndef L16_METADATA_LIBRARY
#define L16_METADATA_LIBRARY "libcamera_metadata.so"
#endif

#ifndef L16_SHELL_PATH
#define L16_SHELL_PATH "/system/bin/sh"
#endif

#ifndef L16_AF_WAIT_TIMEOUT_MILLISECONDS
#define L16_AF_WAIT_TIMEOUT_MILLISECONDS 5000
#endif

#ifndef L16_AF_WAIT_POLL_MICROSECONDS
#define L16_AF_WAIT_POLL_MICROSECONDS 10000
#endif

#ifndef L16_EXPECTED_HELPER_COMMANDS
/* The identified A1 lcc path runs seven helpers.  The constructor self-test is
 * deliberately reset before lcc starts and is not included here. */
#define L16_EXPECTED_HELPER_COMMANDS 7
#endif

#define L16_MAX_ENVIRONMENT_ENTRIES 128
#define L16_METADATA_EXTRA_ENTRIES 3
#define L16_METADATA_EXTRA_DATA_BYTES 64
#define L16_AF_ROI_COUNT 5

#define L16_METADATA_TYPE_BYTE 0
#define L16_METADATA_TYPE_INT32 1

#define L16_ANDROID_CONTROL_START (1U << 16)
#define L16_ANDROID_CONTROL_AF_MODE (L16_ANDROID_CONTROL_START + 7U)
#define L16_ANDROID_CONTROL_AF_REGIONS (L16_ANDROID_CONTROL_START + 8U)
#define L16_ANDROID_CONTROL_AF_TRIGGER (L16_ANDROID_CONTROL_START + 9U)
#define L16_ANDROID_CONTROL_AF_STATE (L16_ANDROID_CONTROL_START + 32U)

#define L16_AF_MODE_AUTO 1
#define L16_AF_TRIGGER_IDLE 0
#define L16_AF_TRIGGER_START 1
#define L16_AF_STATE_ACTIVE_SCAN 3
#define L16_AF_STATE_FOCUSED_LOCKED 4
#define L16_AF_STATE_NOT_FOCUSED_LOCKED 5

#define L16_LOG(literal)                                                       \
    do {                                                                       \
        static const char message[] = "L16_A1_AF_SHIM " literal "\n";         \
        long write_result =                                                    \
            write(2, message, (l16_size_t)(sizeof(message) - 1));              \
        (void)write_result;                                                     \
    } while (0)

enum l16_af_gate_state {
    L16_AF_NOT_ATTEMPTED = 0,
    L16_AF_REQUESTED = 1,
    L16_AF_WAITING = 2,
    L16_AF_FOCUSED_LOCKED = 3,
    L16_AF_FAILED = 4,
};

struct l16_camera_metadata;

union l16_metadata_data {
    l16_u8 *u8;
    l16_i32 *i32;
    void *generic;
};

struct l16_camera_metadata_entry {
    l16_size_t index;
    l16_u32 tag;
    l16_u8 type;
    l16_size_t count;
    union l16_metadata_data data;
};

struct l16_camera3_capture_request {
    l16_u32 frame_number;
    const struct l16_camera_metadata *settings;
    const void *input_buffer;
    l16_u32 num_output_buffers;
    const void *output_buffers;
};

struct l16_camera3_capture_result {
    l16_u32 frame_number;
    const struct l16_camera_metadata *result;
    l16_u32 num_output_buffers;
    const void *output_buffers;
    const void *input_buffer;
    l16_u32 partial_result;
};

typedef int (*l16_method_fn)(void *self);
typedef int (*l16_process_request_fn)(
    void *self,
    struct l16_camera3_capture_request *request
);
typedef void (*l16_process_result_fn)(
    void *self,
    const struct l16_camera3_capture_result *result
);
typedef struct l16_camera_metadata *(*l16_allocate_metadata_fn)(
    l16_size_t entry_capacity,
    l16_size_t data_capacity
);
typedef void (*l16_free_metadata_fn)(struct l16_camera_metadata *metadata);
typedef l16_size_t (*l16_get_metadata_count_fn)(
    const struct l16_camera_metadata *metadata
);
typedef int (*l16_append_metadata_fn)(
    struct l16_camera_metadata *destination,
    const struct l16_camera_metadata *source
);
typedef int (*l16_find_metadata_fn)(
    const struct l16_camera_metadata *metadata,
    l16_u32 tag,
    struct l16_camera_metadata_entry *entry
);
typedef int (*l16_update_metadata_fn)(
    struct l16_camera_metadata *metadata,
    l16_size_t index,
    const void *data,
    l16_size_t data_count,
    struct l16_camera_metadata_entry *updated_entry
);
typedef int (*l16_add_metadata_fn)(
    struct l16_camera_metadata *metadata,
    l16_u32 tag,
    const void *data,
    l16_size_t data_count
);

static int l16_protocol_error;
static int l16_af_state = L16_AF_NOT_ATTEMPTED;
static l16_u32 l16_af_trigger_frame;
static int l16_af_trigger_frame_valid;
static int l16_af_hold_logged;
static int l16_af_active_scan_logged;
static int l16_helper_calls;
static int l16_helper_failures;
static int l16_clean_environment_ready;
static void *l16_target_handle;
static void *l16_metadata_handle;
static l16_method_fn l16_real_start;
static l16_method_fn l16_real_close_camera;
static l16_method_fn l16_real_close;
static l16_process_request_fn l16_real_process_request;
static l16_process_result_fn l16_real_process_result;
static l16_allocate_metadata_fn l16_allocate_metadata;
static l16_free_metadata_fn l16_free_metadata;
static l16_get_metadata_count_fn l16_get_entry_count;
static l16_get_metadata_count_fn l16_get_data_count;
static l16_append_metadata_fn l16_append_metadata;
static l16_find_metadata_fn l16_find_metadata;
static l16_update_metadata_fn l16_update_metadata;
static l16_add_metadata_fn l16_add_metadata;
static char *l16_clean_environment[L16_MAX_ENVIRONMENT_ENTRIES];


__attribute__((visibility("default")))
int l16_interposed_start_capture(void *self)
    __asm__(L16_START_SYMBOL);

__attribute__((visibility("default")))
int l16_interposed_close_camera(void *self)
    __asm__(L16_CLOSE_CAMERA_SYMBOL);

__attribute__((visibility("default")))
int l16_interposed_process_capture_request(
    void *self,
    struct l16_camera3_capture_request *request
) __asm__(L16_PROCESS_REQUEST_SYMBOL);

__attribute__((visibility("default")))
void l16_interposed_process_capture_result(
    void *self,
    const struct l16_camera3_capture_result *result
) __asm__(L16_PROCESS_RESULT_SYMBOL);

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
        (void)execve(L16_SHELL_PATH, arguments, l16_clean_environment);
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


static l16_size_t l16_type_size(l16_u8 type)
{
    if (type == L16_METADATA_TYPE_BYTE) {
        return 1;
    }
    if (type == L16_METADATA_TYPE_INT32) {
        return 4;
    }
    return 0;
}


static int l16_bytes_equal(
    const l16_u8 *left,
    const l16_u8 *right,
    l16_size_t count
)
{
    l16_size_t index;

    if (left == (const l16_u8 *)0 || right == (const l16_u8 *)0) {
        return 0;
    }
    for (index = 0; index < count; ++index) {
        if (left[index] != right[index]) {
            return 0;
        }
    }
    return 1;
}


static int l16_set_and_verify_metadata(
    struct l16_camera_metadata *metadata,
    l16_u32 tag,
    l16_u8 expected_type,
    const void *data,
    l16_size_t count
)
{
    struct l16_camera_metadata_entry entry;
    l16_size_t type_size;
    l16_size_t byte_count;
    int found;
    int result;

    type_size = l16_type_size(expected_type);
    if (metadata == (struct l16_camera_metadata *)0 || type_size == 0 ||
        count > ((l16_size_t)-1) / type_size) {
        return 1;
    }
    byte_count = count * type_size;
    found = l16_find_metadata(metadata, tag, &entry);
    if (found == 0) {
        if (entry.type != expected_type) {
            return 1;
        }
        result = l16_update_metadata(
            metadata,
            entry.index,
            data,
            count,
            (struct l16_camera_metadata_entry *)0
        );
    }
    else {
        result = l16_add_metadata(metadata, tag, data, count);
    }
    if (result != 0 || l16_find_metadata(metadata, tag, &entry) != 0 ||
        entry.type != expected_type || entry.count != count ||
        !l16_bytes_equal(
            entry.data.u8,
            (const l16_u8 *)data,
            byte_count)) {
        return 1;
    }
    return 0;
}


static struct l16_camera_metadata *l16_build_af_metadata(
    const struct l16_camera_metadata *source,
    int start_trigger
)
{
    static const l16_i32 center_roi[L16_AF_ROI_COUNT] = {
        1040, 780, 3120, 2340, 1000
    };
    const l16_u8 mode = L16_AF_MODE_AUTO;
    const l16_u8 trigger = start_trigger
        ? L16_AF_TRIGGER_START
        : L16_AF_TRIGGER_IDLE;
    struct l16_camera_metadata *metadata;
    l16_size_t entry_count;
    l16_size_t data_count;

    if (source == (const struct l16_camera_metadata *)0) {
        L16_LOG("request_settings_missing_error");
        return (struct l16_camera_metadata *)0;
    }
    entry_count = l16_get_entry_count(source);
    data_count = l16_get_data_count(source);
    if (entry_count > (l16_size_t)-1 - L16_METADATA_EXTRA_ENTRIES ||
        data_count > (l16_size_t)-1 - L16_METADATA_EXTRA_DATA_BYTES) {
        L16_LOG("metadata_capacity_overflow_error");
        return (struct l16_camera_metadata *)0;
    }
    metadata = l16_allocate_metadata(
        entry_count + L16_METADATA_EXTRA_ENTRIES,
        data_count + L16_METADATA_EXTRA_DATA_BYTES
    );
    if (metadata == (struct l16_camera_metadata *)0 ||
        l16_append_metadata(metadata, source) != 0 ||
        l16_set_and_verify_metadata(
            metadata,
            L16_ANDROID_CONTROL_AF_MODE,
            L16_METADATA_TYPE_BYTE,
            &mode,
            1) != 0 ||
        l16_set_and_verify_metadata(
            metadata,
            L16_ANDROID_CONTROL_AF_REGIONS,
            L16_METADATA_TYPE_INT32,
            center_roi,
            L16_AF_ROI_COUNT) != 0 ||
        l16_set_and_verify_metadata(
            metadata,
            L16_ANDROID_CONTROL_AF_TRIGGER,
            L16_METADATA_TYPE_BYTE,
            &trigger,
            1) != 0) {
        if (metadata != (struct l16_camera_metadata *)0) {
            l16_free_metadata(metadata);
        }
        L16_LOG("metadata_build_or_verify_error");
        return (struct l16_camera_metadata *)0;
    }
    return metadata;
}


static int l16_resolve_targets(void)
{
#define L16_RESOLVE(handle, symbol, target, type)                              \
    do {                                                                       \
        union {                                                                \
            void *object;                                                      \
            type function;                                                     \
        } resolved;                                                            \
        resolved.object = dlsym((handle), (symbol));                           \
        (target) = resolved.function;                                           \
    } while (0)

    l16_target_handle = dlopen(
        L16_TARGET_LIBRARY,
        L16_RTLD_NOW | L16_RTLD_LOCAL
    );
    if (l16_target_handle == (void *)0) {
        L16_LOG("target_dlopen_error");
        return 1;
    }
    l16_metadata_handle = dlopen(
        L16_METADATA_LIBRARY,
        L16_RTLD_NOW | L16_RTLD_LOCAL
    );
    if (l16_metadata_handle == (void *)0) {
        L16_LOG("metadata_dlopen_error");
        return 1;
    }

    L16_RESOLVE(
        l16_target_handle,
        L16_START_SYMBOL,
        l16_real_start,
        l16_method_fn);
    L16_RESOLVE(
        l16_target_handle,
        L16_CLOSE_CAMERA_SYMBOL,
        l16_real_close_camera,
        l16_method_fn);
    L16_RESOLVE(
        l16_target_handle,
        L16_CLOSE_SYMBOL,
        l16_real_close,
        l16_method_fn);
    L16_RESOLVE(
        l16_target_handle,
        L16_PROCESS_REQUEST_SYMBOL,
        l16_real_process_request,
        l16_process_request_fn);
    L16_RESOLVE(
        l16_target_handle,
        L16_PROCESS_RESULT_SYMBOL,
        l16_real_process_result,
        l16_process_result_fn);
    if (l16_real_start == (l16_method_fn)0 ||
        l16_real_close_camera == (l16_method_fn)0 ||
        l16_real_close == (l16_method_fn)0 ||
        l16_real_process_request == (l16_process_request_fn)0 ||
        l16_real_process_result == (l16_process_result_fn)0 ||
        l16_real_start == l16_interposed_start_capture ||
        l16_real_close_camera == l16_interposed_close_camera ||
        l16_real_process_request == l16_interposed_process_capture_request ||
        l16_real_process_result == l16_interposed_process_capture_result) {
        L16_LOG("target_dlsym_error");
        return 1;
    }
    L16_LOG("resolve_targets_ok");

    L16_RESOLVE(
        l16_metadata_handle,
        "allocate_camera_metadata",
        l16_allocate_metadata,
        l16_allocate_metadata_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "free_camera_metadata",
        l16_free_metadata,
        l16_free_metadata_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "get_camera_metadata_entry_count",
        l16_get_entry_count,
        l16_get_metadata_count_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "get_camera_metadata_data_count",
        l16_get_data_count,
        l16_get_metadata_count_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "append_camera_metadata",
        l16_append_metadata,
        l16_append_metadata_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "find_camera_metadata_entry",
        l16_find_metadata,
        l16_find_metadata_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "update_camera_metadata_entry",
        l16_update_metadata,
        l16_update_metadata_fn);
    L16_RESOLVE(
        l16_metadata_handle,
        "add_camera_metadata_entry",
        l16_add_metadata,
        l16_add_metadata_fn);
    if (l16_allocate_metadata == (l16_allocate_metadata_fn)0 ||
        l16_free_metadata == (l16_free_metadata_fn)0 ||
        l16_get_entry_count == (l16_get_metadata_count_fn)0 ||
        l16_get_data_count == (l16_get_metadata_count_fn)0 ||
        l16_append_metadata == (l16_append_metadata_fn)0 ||
        l16_find_metadata == (l16_find_metadata_fn)0 ||
        l16_update_metadata == (l16_update_metadata_fn)0 ||
        l16_add_metadata == (l16_add_metadata_fn)0) {
        L16_LOG("metadata_dlsym_error");
        return 1;
    }
    L16_LOG("metadata_resolve_ok");
#undef L16_RESOLVE
    return 0;
}


__attribute__((constructor))
static void l16_shim_loaded(void)
{
    L16_LOG("loaded");
    if (unsetenv("LD_PRELOAD") != 0 ||
        getenv("LD_PRELOAD") != (char *)0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("preload_clear_error");
        return;
    }
    if (l16_prepare_clean_environment() != 0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        return;
    }
    L16_LOG("preload_cleared");
    if (l16_resolve_targets() != 0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        return;
    }
    if (l16_interposed_system(":") != 0) {
        L16_LOG("preload_child_selftest_failed");
        _exit(125);
    }
    L16_LOG("preload_child_selftest_ok");
    __atomic_store_n(&l16_helper_calls, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&l16_helper_failures, 0, __ATOMIC_RELEASE);
}


int l16_interposed_process_capture_request(
    void *self,
    struct l16_camera3_capture_request *request
)
{
    struct l16_camera3_capture_request modified;
    struct l16_camera_metadata *metadata;
    int expected;
    int result;
    int state;
    int start_trigger;

    if (l16_real_process_request == (l16_process_request_fn)0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("real_process_request_missing_error");
        return -1;
    }
    state = __atomic_load_n(&l16_af_state, __ATOMIC_ACQUIRE);
    if (state != L16_AF_REQUESTED && state != L16_AF_WAITING &&
        state != L16_AF_FOCUSED_LOCKED) {
        return l16_real_process_request(self, request);
    }
    if (request == (struct l16_camera3_capture_request *)0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
        L16_LOG("capture_request_missing_error");
        return l16_real_process_request(self, request);
    }

    start_trigger = state == L16_AF_REQUESTED;
    metadata = l16_build_af_metadata(request->settings, start_trigger);
    if (metadata == (struct l16_camera_metadata *)0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
        return l16_real_process_request(self, request);
    }
    if (start_trigger) {
        __atomic_store_n(
            &l16_af_trigger_frame,
            request->frame_number,
            __ATOMIC_RELEASE);
        __atomic_store_n(&l16_af_trigger_frame_valid, 1, __ATOMIC_RELEASE);
        expected = L16_AF_REQUESTED;
        if (!__atomic_compare_exchange_n(
                &l16_af_state,
                &expected,
                L16_AF_WAITING,
                0,
                __ATOMIC_ACQ_REL,
                __ATOMIC_ACQUIRE)) {
            l16_free_metadata(metadata);
            __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
            __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
            L16_LOG("af_trigger_state_race_error");
            return l16_real_process_request(self, request);
        }
        L16_LOG("af_metadata_trigger_injected");
    }
    else if (__atomic_exchange_n(
                 &l16_af_hold_logged,
                 1,
                 __ATOMIC_ACQ_REL) == 0) {
        L16_LOG("af_metadata_hold_injected");
    }

    modified.frame_number = request->frame_number;
    modified.settings = metadata;
    modified.input_buffer = request->input_buffer;
    modified.num_output_buffers = request->num_output_buffers;
    modified.output_buffers = request->output_buffers;
    result = l16_real_process_request(self, &modified);
    l16_free_metadata(metadata);
    if (result != 0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
        L16_LOG("real_process_request_error");
    }
    return result;
}


void l16_interposed_process_capture_result(
    void *self,
    const struct l16_camera3_capture_result *result
)
{
    struct l16_camera_metadata_entry entry;
    l16_u32 trigger_frame;
    l16_u8 af_state;
    int expected;

    if (result != (const struct l16_camera3_capture_result *)0 &&
        result->result != (const struct l16_camera_metadata *)0 &&
        __atomic_load_n(&l16_af_state, __ATOMIC_ACQUIRE) == L16_AF_WAITING &&
        __atomic_load_n(
            &l16_af_trigger_frame_valid,
            __ATOMIC_ACQUIRE) != 0) {
        trigger_frame = __atomic_load_n(
            &l16_af_trigger_frame,
            __ATOMIC_ACQUIRE);
        if (result->frame_number >= trigger_frame &&
            l16_find_metadata(
                result->result,
                L16_ANDROID_CONTROL_AF_STATE,
                &entry) == 0) {
            if (entry.type != L16_METADATA_TYPE_BYTE || entry.count != 1 ||
                entry.data.u8 == (l16_u8 *)0) {
                __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
                __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
                L16_LOG("af_state_metadata_invalid_error");
            }
            else {
                af_state = entry.data.u8[0];
                if (af_state == L16_AF_STATE_ACTIVE_SCAN &&
                    __atomic_exchange_n(
                        &l16_af_active_scan_logged,
                        1,
                        __ATOMIC_ACQ_REL) == 0) {
                    L16_LOG("af_state_active_scan");
                }
                else if (af_state == L16_AF_STATE_FOCUSED_LOCKED) {
                    expected = L16_AF_WAITING;
                    if (__atomic_compare_exchange_n(
                            &l16_af_state,
                            &expected,
                            L16_AF_FOCUSED_LOCKED,
                            0,
                            __ATOMIC_ACQ_REL,
                            __ATOMIC_ACQUIRE)) {
                        L16_LOG("af_state_focused_locked");
                    }
                }
                else if (af_state == L16_AF_STATE_NOT_FOCUSED_LOCKED) {
                    expected = L16_AF_WAITING;
                    if (__atomic_compare_exchange_n(
                            &l16_af_state,
                            &expected,
                            L16_AF_FAILED,
                            0,
                            __ATOMIC_ACQ_REL,
                            __ATOMIC_ACQUIRE)) {
                        L16_LOG("af_state_not_focused_locked");
                    }
                }
            }
        }
    }
    if (l16_real_process_result == (l16_process_result_fn)0) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
        L16_LOG("real_process_result_missing_error");
        return;
    }
    l16_real_process_result(self, result);
}


int l16_interposed_start_capture(void *self)
{
    unsigned int waited = 0;
    int expected = L16_AF_NOT_ATTEMPTED;
    int result;
    int state;

    if (!__atomic_compare_exchange_n(
            &l16_af_state,
            &expected,
            L16_AF_REQUESTED,
            0,
            __ATOMIC_ACQ_REL,
            __ATOMIC_ACQUIRE)) {
        __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
        L16_LOG("unexpected_second_start_error");
        return 0;
    }
    L16_LOG("af_gate_enter");
    L16_LOG("af_trigger_request_armed");
    if (__atomic_load_n(&l16_protocol_error, __ATOMIC_ACQUIRE) != 0 ||
        l16_real_start == (l16_method_fn)0) {
        L16_LOG("af_precondition_error");
        goto failed;
    }

    while (waited < L16_AF_WAIT_TIMEOUT_MILLISECONDS) {
        state = __atomic_load_n(&l16_af_state, __ATOMIC_ACQUIRE);
        if (state == L16_AF_FOCUSED_LOCKED) {
            L16_LOG("af_gate_pass");
            result = l16_real_start(self);
            if (result == 0) {
                __atomic_store_n(&l16_protocol_error, 1, __ATOMIC_RELEASE);
                __atomic_store_n(
                    &l16_af_state,
                    L16_AF_FAILED,
                    __ATOMIC_RELEASE);
                L16_LOG("real_start_error");
                return 0;
            }
            L16_LOG("capture_released");
            return result;
        }
        if (state == L16_AF_FAILED) {
            goto failed;
        }
        if (usleep(L16_AF_WAIT_POLL_MICROSECONDS) != 0) {
            L16_LOG("af_wait_sleep_error");
            goto failed;
        }
        waited += L16_AF_WAIT_POLL_MICROSECONDS / 1000U;
    }
    L16_LOG("af_state_wait_timeout");

failed:
    __atomic_store_n(&l16_af_state, L16_AF_FAILED, __ATOMIC_RELEASE);
    L16_LOG("capture_suppressed");
    return 0;
}


int l16_interposed_close_camera(void *self)
{
    int state = __atomic_load_n(&l16_af_state, __ATOMIC_ACQUIRE);
    int helper_calls;
    int helper_failures;
    int result;

    if (state != L16_AF_FOCUSED_LOCKED ||
        __atomic_load_n(&l16_protocol_error, __ATOMIC_ACQUIRE) != 0) {
        if (l16_real_close == (l16_method_fn)0) {
            L16_LOG("direct_close_missing_error");
            return 0;
        }
        (void)l16_real_close(self);
        L16_LOG("close_without_capture");
        return 0;
    }
    if (l16_real_close_camera == (l16_method_fn)0) {
        L16_LOG("real_close_camera_missing_error");
        return 0;
    }
    result = l16_real_close_camera(self);
    helper_calls = __atomic_load_n(&l16_helper_calls, __ATOMIC_ACQUIRE);
    helper_failures = __atomic_load_n(&l16_helper_failures, __ATOMIC_ACQUIRE);
    if (helper_calls != L16_EXPECTED_HELPER_COMMANDS || helper_failures != 0) {
        L16_LOG("helper_command_count_or_status_error");
        return 0;
    }
    if (result == 0) {
        L16_LOG("real_close_camera_error");
        return 0;
    }
    L16_LOG("helper_commands_ok");
    L16_LOG("close_reports_ok");
    return result;
}
