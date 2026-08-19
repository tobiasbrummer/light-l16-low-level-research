// SPDX-License-Identifier: MIT

#include <stdio.h>
#include <stdlib.h>


extern int mock_run_focus_capture(int final_af_state);
extern int mock_real_start_calls(void);
extern int mock_real_close_camera_calls(void);
extern int mock_direct_close_calls(void);
extern int mock_real_process_request_calls(void);
extern int mock_real_process_result_calls(void);
extern int mock_af_trigger_calls(void);
extern int mock_af_hold_calls(void);
extern int mock_invalid_af_requests(void);


int main(int argc, char **argv)
{
    int final_af_state;
    int result;

    if (argc != 2) {
        return 2;
    }
    final_af_state = atoi(argv[1]);
    result = mock_run_focus_capture(final_af_state);
    printf("result=%d\n", result);
    printf("real_start_calls=%d\n", mock_real_start_calls());
    printf("real_close_camera_calls=%d\n", mock_real_close_camera_calls());
    printf("direct_close_calls=%d\n", mock_direct_close_calls());
    printf("real_process_request_calls=%d\n", mock_real_process_request_calls());
    printf("real_process_result_calls=%d\n", mock_real_process_result_calls());
    printf("af_trigger_calls=%d\n", mock_af_trigger_calls());
    printf("af_hold_calls=%d\n", mock_af_hold_calls());
    printf("invalid_af_requests=%d\n", mock_invalid_af_requests());
    printf("ld_preload_present=%d\n", getenv("LD_PRELOAD") != NULL);
    return 0;
}
