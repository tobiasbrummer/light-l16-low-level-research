// SPDX-License-Identifier: MIT

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>


extern int mock_run_capture(void);
extern int mock_run_capture_close_first(void);
extern int mock_wrote_after_teardown(void);
extern int64_t mock_callback_microseconds(void);
extern int64_t mock_total_microseconds(void);
extern int mock_writer_used_other_thread(void);
extern int mock_close_observed_finished(void);
extern int mock_write_return(void);
extern int mock_close_return(void);


int main(int argc, char **argv)
{
    /* "close-first" runs closeCamera before writeFile, the order lcc uses
     * once the exposure outlasts its own timeout. */
    int close_first = argc > 1 && argv[1][0] == 'c';
    int result = close_first ? mock_run_capture_close_first()
                             : mock_run_capture();

    printf("result=%d\n", result);
    printf("callback_us=%" PRId64 "\n", mock_callback_microseconds());
    printf("total_us=%" PRId64 "\n", mock_total_microseconds());
    printf("writer_other_thread=%d\n", mock_writer_used_other_thread());
    printf("close_observed_finished=%d\n", mock_close_observed_finished());
    printf("write_return=%d\n", mock_write_return());
    printf("close_return=%d\n", mock_close_return());
    printf("wrote_after_teardown=%d\n", mock_wrote_after_teardown());
    printf("ld_preload_present=%d\n", getenv("LD_PRELOAD") != NULL);
    return result == 1 ? 0 : 1;
}
