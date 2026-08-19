// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L

#include <pthread.h>
#include <stdint.h>
#include <time.h>


#define L16_WRITE_SYMBOL "_ZN7qcamera12LccInterface9writeFileEv"
#define L16_CLOSE_SYMBOL "_ZN7qcamera12LccInterface11closeCameraEv"

static pthread_t caller_thread;
static pthread_t writer_thread;
static int write_finished;
static int close_observed_finished;
/* On the device the descriptors writeFile maps belong to the pipeline that
 * closeCamera tears down.  Writing after that returns EBADF on every buffer,
 * so the model records the ordering violation rather than the symptom. */
static int teardown_finished;
static int wrote_after_teardown;
static int close_invokes_write;
static int write_return;
static int close_return;
static int64_t callback_microseconds;
static int64_t total_microseconds;


static int64_t elapsed_microseconds(struct timespec start, struct timespec end)
{
    int64_t seconds = (int64_t)end.tv_sec - (int64_t)start.tv_sec;
    int64_t nanoseconds = (int64_t)end.tv_nsec - (int64_t)start.tv_nsec;
    return seconds * 1000000 + nanoseconds / 1000;
}


__attribute__((noinline, visibility("default")))
int mock_write_file(void *self) __asm__(L16_WRITE_SYMBOL);

int mock_write_file(void *self)
{
    const struct timespec delay = {0, 250000000};

    (void)self;
    writer_thread = pthread_self();
    (void)nanosleep(&delay, 0);
    if (teardown_finished) {
        wrote_after_teardown = 1;
    }
    write_finished = 1;
    return 0;
}


__attribute__((noinline, visibility("default")))
int mock_close_camera(void *self) __asm__(L16_CLOSE_SYMBOL);

int mock_close_camera(void *self)
{
    (void)self;
    close_observed_finished = write_finished;
    if (close_invokes_write) {
        /* The real closeCamera is still inside the pipeline when the result
         * callback fires, and the descriptors stay valid until it returns.
         * A write that runs here is safe; one that runs on a worker is still
         * going when the teardown below completes. */
        write_return = mock_write_file(self);
    }
    teardown_finished = 1;
    return 1;
}


__attribute__((visibility("default")))
int mock_run_capture(void)
{
    struct timespec start;
    struct timespec after_callback;
    struct timespec after_close;
    int fake_lcc_object;

    write_finished = 0;
    close_observed_finished = 0;
    caller_thread = pthread_self();
    (void)clock_gettime(CLOCK_MONOTONIC, &start);
    write_return = mock_write_file(&fake_lcc_object);
    (void)clock_gettime(CLOCK_MONOTONIC, &after_callback);
    close_return = mock_close_camera(&fake_lcc_object);
    (void)clock_gettime(CLOCK_MONOTONIC, &after_close);
    callback_microseconds = elapsed_microseconds(start, after_callback);
    total_microseconds = elapsed_microseconds(start, after_close);
    return close_return;
}


/* lcc reaches closeCamera on its own schedule -- thread_time_out, derived
 * from the exposure -- so for a long exposure it gets there before the result
 * callback has fired.  This is that order. */
__attribute__((visibility("default")))
int mock_run_capture_close_first(void)
{
    struct timespec start;
    struct timespec after_close;
    struct timespec after_write;
    int fake_lcc_object;

    write_finished = 0;
    close_observed_finished = 0;
    teardown_finished = 0;
    wrote_after_teardown = 0;
    close_invokes_write = 1;
    caller_thread = pthread_self();
    (void)clock_gettime(CLOCK_MONOTONIC, &start);
    close_return = mock_close_camera(&fake_lcc_object);
    (void)clock_gettime(CLOCK_MONOTONIC, &after_close);
    close_invokes_write = 0;
    /* Give a worker, if one was started, the time it needs to finish, so the
     * ordering it produced is observable rather than a race in the test. */
    {
        const struct timespec settle = {1, 0};
        (void)nanosleep(&settle, 0);
    }
    (void)clock_gettime(CLOCK_MONOTONIC, &after_write);
    callback_microseconds = elapsed_microseconds(start, after_close);
    total_microseconds = elapsed_microseconds(start, after_write);
    return close_return;
}


__attribute__((visibility("default")))
int mock_wrote_after_teardown(void)
{
    return wrote_after_teardown;
}


__attribute__((visibility("default")))
int64_t mock_callback_microseconds(void)
{
    return callback_microseconds;
}


__attribute__((visibility("default")))
int64_t mock_total_microseconds(void)
{
    return total_microseconds;
}


__attribute__((visibility("default")))
int mock_writer_used_other_thread(void)
{
    return !pthread_equal(caller_thread, writer_thread);
}


__attribute__((visibility("default")))
int mock_close_observed_finished(void)
{
    return close_observed_finished;
}


__attribute__((visibility("default")))
int mock_write_return(void)
{
    return write_return;
}


__attribute__((visibility("default")))
int mock_close_return(void)
{
    return close_return;
}
