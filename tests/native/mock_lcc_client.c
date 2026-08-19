// SPDX-License-Identifier: MIT

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>


extern int mock_run_capture(void);
extern int64_t mock_callback_microseconds(void);
extern int64_t mock_total_microseconds(void);
extern int mock_writer_used_other_thread(void);
extern int mock_close_observed_finished(void);
extern int mock_write_return(void);
extern int mock_close_return(void);


int main(void)
{
    int result = mock_run_capture();

    printf("result=%d\n", result);
    printf("callback_us=%" PRId64 "\n", mock_callback_microseconds());
    printf("total_us=%" PRId64 "\n", mock_total_microseconds());
    printf("writer_other_thread=%d\n", mock_writer_used_other_thread());
    printf("close_observed_finished=%d\n", mock_close_observed_finished());
    printf("write_return=%d\n", mock_write_return());
    printf("close_return=%d\n", mock_close_return());
    printf("ld_preload_present=%d\n", getenv("LD_PRELOAD") != NULL);
    return result == 1 ? 0 : 1;
}
