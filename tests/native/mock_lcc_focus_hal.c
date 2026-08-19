// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L

#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>


#define L16_START_SYMBOL "_ZN7qcamera12LccInterface12startCaptureEv"
#define L16_CLOSE_CAMERA_SYMBOL "_ZN7qcamera12LccInterface11closeCameraEv"
#define L16_CLOSE_SYMBOL "_ZN7qcamera12LccInterface5closeEv"
#define L16_PROCESS_REQUEST_SYMBOL                                           \
    "_ZN7qcamera25QCamera3HardwareInterface21processCaptureRequest"         \
    "EP23camera3_capture_request"
#define L16_PROCESS_RESULT_SYMBOL                                            \
    "_ZN7qcamera12LccInterface20processCaptureResult"                       \
    "EPK22camera3_capture_result"

#define MOCK_MAX_ENTRIES 16
#define MOCK_MAX_DATA 32
#define MOCK_AF_MODE (0x10000U + 7U)
#define MOCK_AF_REGIONS (0x10000U + 8U)
#define MOCK_AF_TRIGGER (0x10000U + 9U)
#define MOCK_AF_STATE (0x10000U + 32U)
#define MOCK_TYPE_BYTE 0
#define MOCK_TYPE_INT32 1
#define MOCK_AF_MODE_AUTO 1
#define MOCK_AF_TRIGGER_IDLE 0
#define MOCK_AF_TRIGGER_START 1
#define MOCK_AF_STATE_ACTIVE_SCAN 3

union mock_metadata_data {
    uint8_t *u8;
    int32_t *i32;
    void *generic;
};

struct camera_metadata_entry {
    size_t index;
    uint32_t tag;
    uint8_t type;
    size_t count;
    union mock_metadata_data data;
};

struct mock_entry {
    uint32_t tag;
    uint8_t type;
    size_t count;
    uint8_t data[MOCK_MAX_DATA];
};

struct camera_metadata {
    size_t entry_capacity;
    size_t data_capacity;
    size_t entry_count;
    struct mock_entry entries[MOCK_MAX_ENTRIES];
};

struct camera3_capture_request {
    uint32_t frame_number;
    const struct camera_metadata *settings;
    const void *input_buffer;
    uint32_t num_output_buffers;
    const void *output_buffers;
};

struct camera3_capture_result {
    uint32_t frame_number;
    const struct camera_metadata *result;
    uint32_t num_output_buffers;
    const void *output_buffers;
    const void *input_buffer;
    uint32_t partial_result;
};

static int real_start_calls;
static int real_close_camera_calls;
static int direct_close_calls;
static int real_process_request_calls;
static int real_process_result_calls;
static int af_trigger_calls;
static int af_hold_calls;
static int invalid_af_requests;
static int requested_final_state;
static int trigger_seen;
static int final_result_sent;
static int request_thread_stop;
static pthread_t request_thread;
static struct camera_metadata base_metadata;
static int fake_hal_object;
static int fake_lcc_object;


static size_t mock_type_size(uint8_t type)
{
    if (type == MOCK_TYPE_BYTE) {
        return 1;
    }
    if (type == MOCK_TYPE_INT32) {
        return 4;
    }
    return 0;
}


static uint8_t mock_tag_type(uint32_t tag)
{
    return tag == MOCK_AF_REGIONS ? MOCK_TYPE_INT32 : MOCK_TYPE_BYTE;
}


__attribute__((visibility("default")))
struct camera_metadata *allocate_camera_metadata(
    size_t entry_capacity,
    size_t data_capacity
)
{
    struct camera_metadata *metadata;

    if (entry_capacity > MOCK_MAX_ENTRIES) {
        return NULL;
    }
    metadata = calloc(1, sizeof(*metadata));
    if (metadata != NULL) {
        metadata->entry_capacity = entry_capacity;
        metadata->data_capacity = data_capacity;
    }
    return metadata;
}


__attribute__((visibility("default")))
void free_camera_metadata(struct camera_metadata *metadata)
{
    free(metadata);
}


__attribute__((visibility("default")))
size_t get_camera_metadata_entry_count(const struct camera_metadata *metadata)
{
    return metadata == NULL ? 0 : metadata->entry_count;
}


__attribute__((visibility("default")))
size_t get_camera_metadata_data_count(const struct camera_metadata *metadata)
{
    size_t count = 0;
    size_t index;

    if (metadata == NULL) {
        return 0;
    }
    for (index = 0; index < metadata->entry_count; ++index) {
        count += metadata->entries[index].count *
            mock_type_size(metadata->entries[index].type);
    }
    return count;
}


__attribute__((visibility("default")))
int append_camera_metadata(
    struct camera_metadata *destination,
    const struct camera_metadata *source
)
{
    if (destination == NULL || source == NULL ||
        destination->entry_capacity < source->entry_count ||
        destination->data_capacity < get_camera_metadata_data_count(source)) {
        return -1;
    }
    memcpy(
        destination->entries,
        source->entries,
        source->entry_count * sizeof(source->entries[0]));
    destination->entry_count = source->entry_count;
    return 0;
}


__attribute__((visibility("default")))
int find_camera_metadata_entry(
    const struct camera_metadata *metadata,
    uint32_t tag,
    struct camera_metadata_entry *entry
)
{
    size_t index;

    if (metadata == NULL || entry == NULL) {
        return -1;
    }
    for (index = 0; index < metadata->entry_count; ++index) {
        if (metadata->entries[index].tag == tag) {
            entry->index = index;
            entry->tag = tag;
            entry->type = metadata->entries[index].type;
            entry->count = metadata->entries[index].count;
            entry->data.u8 = (uint8_t *)metadata->entries[index].data;
            return 0;
        }
    }
    return -2;
}


__attribute__((visibility("default")))
int update_camera_metadata_entry(
    struct camera_metadata *metadata,
    size_t index,
    const void *data,
    size_t data_count,
    struct camera_metadata_entry *updated_entry
)
{
    struct mock_entry *entry;
    size_t byte_count;

    if (metadata == NULL || index >= metadata->entry_count || data == NULL) {
        return -1;
    }
    entry = &metadata->entries[index];
    byte_count = mock_type_size(entry->type) * data_count;
    if (byte_count > sizeof(entry->data)) {
        return -1;
    }
    memcpy(entry->data, data, byte_count);
    entry->count = data_count;
    if (updated_entry != NULL) {
        return find_camera_metadata_entry(metadata, entry->tag, updated_entry);
    }
    return 0;
}


__attribute__((visibility("default")))
int add_camera_metadata_entry(
    struct camera_metadata *metadata,
    uint32_t tag,
    const void *data,
    size_t data_count
)
{
    struct mock_entry *entry;
    size_t byte_count;

    if (metadata == NULL || data == NULL ||
        metadata->entry_count >= metadata->entry_capacity) {
        return -1;
    }
    entry = &metadata->entries[metadata->entry_count];
    entry->tag = tag;
    entry->type = mock_tag_type(tag);
    byte_count = mock_type_size(entry->type) * data_count;
    if (byte_count > sizeof(entry->data)) {
        return -1;
    }
    memcpy(entry->data, data, byte_count);
    entry->count = data_count;
    metadata->entry_count += 1;
    return 0;
}


static int mock_read_u8(
    const struct camera_metadata *metadata,
    uint32_t tag,
    uint8_t *value
)
{
    struct camera_metadata_entry entry;

    if (find_camera_metadata_entry(metadata, tag, &entry) != 0 ||
        entry.type != MOCK_TYPE_BYTE || entry.count != 1) {
        return -1;
    }
    *value = entry.data.u8[0];
    return 0;
}


static int mock_valid_center_roi(const struct camera_metadata *metadata)
{
    static const int32_t expected[5] = {1040, 780, 3120, 2340, 1000};
    struct camera_metadata_entry entry;

    return find_camera_metadata_entry(metadata, MOCK_AF_REGIONS, &entry) == 0 &&
        entry.type == MOCK_TYPE_INT32 && entry.count == 5 &&
        memcmp(entry.data.i32, expected, sizeof(expected)) == 0;
}


__attribute__((noinline, visibility("default")))
void mock_process_capture_result(
    void *self,
    const struct camera3_capture_result *result
) __asm__(L16_PROCESS_RESULT_SYMBOL);

void mock_process_capture_result(
    void *self,
    const struct camera3_capture_result *result
)
{
    (void)self;
    if (result != NULL) {
        real_process_result_calls += 1;
    }
}


static void mock_send_af_result(uint32_t frame_number, uint8_t state)
{
    struct camera3_capture_result result;
    struct camera_metadata metadata;

    memset(&metadata, 0, sizeof(metadata));
    metadata.entry_capacity = MOCK_MAX_ENTRIES;
    metadata.data_capacity = MOCK_MAX_DATA;
    (void)add_camera_metadata_entry(&metadata, MOCK_AF_STATE, &state, 1);
    memset(&result, 0, sizeof(result));
    result.frame_number = frame_number;
    result.result = &metadata;
    result.partial_result = 1;
    mock_process_capture_result(&fake_lcc_object, &result);
}


__attribute__((noinline, visibility("default")))
int mock_process_capture_request(
    void *self,
    struct camera3_capture_request *request
) __asm__(L16_PROCESS_REQUEST_SYMBOL);

int mock_process_capture_request(
    void *self,
    struct camera3_capture_request *request
)
{
    uint8_t mode;
    uint8_t trigger;

    (void)self;
    real_process_request_calls += 1;
    if (request == NULL || request->settings == NULL ||
        mock_read_u8(request->settings, MOCK_AF_MODE, &mode) != 0 ||
        mock_read_u8(request->settings, MOCK_AF_TRIGGER, &trigger) != 0) {
        return 0;
    }
    if (mode != MOCK_AF_MODE_AUTO ||
        !mock_valid_center_roi(request->settings)) {
        invalid_af_requests += 1;
        return 0;
    }
    if (trigger == MOCK_AF_TRIGGER_START) {
        af_trigger_calls += 1;
        trigger_seen = 1;
        mock_send_af_result(request->frame_number, MOCK_AF_STATE_ACTIVE_SCAN);
    }
    else if (trigger == MOCK_AF_TRIGGER_IDLE && trigger_seen) {
        af_hold_calls += 1;
        if (!final_result_sent) {
            final_result_sent = 1;
            mock_send_af_result(
                request->frame_number,
                (uint8_t)requested_final_state);
        }
    }
    else {
        invalid_af_requests += 1;
    }
    return 0;
}


__attribute__((noinline, visibility("default")))
int mock_start_capture(void *self) __asm__(L16_START_SYMBOL);

int mock_start_capture(void *self)
{
    (void)self;
    real_start_calls += 1;
    if (system("true") != 0) {
        return 0;
    }
    return 1;
}


__attribute__((noinline, visibility("default")))
int mock_close_camera(void *self) __asm__(L16_CLOSE_CAMERA_SYMBOL);

int mock_close_camera(void *self)
{
    (void)self;
    real_close_camera_calls += 1;
    return 1;
}


__attribute__((noinline, visibility("default")))
int mock_direct_close(void *self) __asm__(L16_CLOSE_SYMBOL);

int mock_direct_close(void *self)
{
    (void)self;
    direct_close_calls += 1;
    return 1;
}


static void *mock_request_loop(void *unused)
{
    const struct timespec delay = {0, 1000000};
    struct camera3_capture_request request;
    uint32_t frame = 1;

    (void)unused;
    while (!__atomic_load_n(&request_thread_stop, __ATOMIC_ACQUIRE)) {
        memset(&request, 0, sizeof(request));
        request.frame_number = frame++;
        request.settings = &base_metadata;
        request.num_output_buffers = 1;
        (void)mock_process_capture_request(&fake_hal_object, &request);
        (void)nanosleep(&delay, NULL);
    }
    return NULL;
}


__attribute__((visibility("default")))
int mock_run_focus_capture(int final_af_state)
{
    int start_result;
    int close_result;

    real_start_calls = 0;
    real_close_camera_calls = 0;
    direct_close_calls = 0;
    real_process_request_calls = 0;
    real_process_result_calls = 0;
    af_trigger_calls = 0;
    af_hold_calls = 0;
    invalid_af_requests = 0;
    requested_final_state = final_af_state;
    trigger_seen = 0;
    final_result_sent = 0;
    request_thread_stop = 0;
    memset(&base_metadata, 0, sizeof(base_metadata));
    base_metadata.entry_capacity = MOCK_MAX_ENTRIES;
    base_metadata.data_capacity = MOCK_MAX_DATA;
    if (pthread_create(&request_thread, NULL, mock_request_loop, NULL) != 0) {
        return -10;
    }
    start_result = mock_start_capture(&fake_lcc_object);
    close_result = mock_close_camera(&fake_lcc_object);
    __atomic_store_n(&request_thread_stop, 1, __ATOMIC_RELEASE);
    (void)pthread_join(request_thread, NULL);
    return start_result * 10 + close_result;
}


__attribute__((visibility("default")))
int mock_real_start_calls(void)
{
    return real_start_calls;
}


__attribute__((visibility("default")))
int mock_real_close_camera_calls(void)
{
    return real_close_camera_calls;
}


__attribute__((visibility("default")))
int mock_direct_close_calls(void)
{
    return direct_close_calls;
}


__attribute__((visibility("default")))
int mock_real_process_request_calls(void)
{
    return real_process_request_calls;
}


__attribute__((visibility("default")))
int mock_real_process_result_calls(void)
{
    return real_process_result_calls;
}


__attribute__((visibility("default")))
int mock_af_trigger_calls(void)
{
    return af_trigger_calls;
}


__attribute__((visibility("default")))
int mock_af_hold_calls(void)
{
    return af_hold_calls;
}


__attribute__((visibility("default")))
int mock_invalid_af_requests(void)
{
    return invalid_af_requests;
}
