// SPDX-License-Identifier: MIT
/*
 * Drives the capture-timeout preload against the mock HAL.
 *
 * The preload interposes openCamera, so calling it here goes through the
 * shim, which forwards to the mock and then patches the timeout field.  The
 * client reports what actually ended up in the instance.
 *
 * Argument: the third openCamera parameter, i.e. the exposure in seconds
 * that the stock formula derives its budget from.  A second argument, when
 * present, makes the mock store that value instead of the derived one, which
 * must make the shim refuse to write.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define L16_TIMEOUT_OFFSET 0x24
#define L16_INSTANCE_BYTES 512

extern int mock_open_calls;
extern unsigned int mock_stored_timeout;
extern int mock_store_wrong_value;
extern unsigned int mock_wrong_value;

extern int open_camera_entry(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
) __asm__("_ZN7qcamera12LccInterface10openCameraEjhj");


int main(int argc, char **argv)
{
    unsigned char instance[L16_INSTANCE_BYTES];
    unsigned int exposure_seconds;
    unsigned int observed;
    int result;

    if (argc < 2) {
        fprintf(stderr, "usage: %s <exposure_seconds> [wrong_value]\n", argv[0]);
        return 2;
    }
    exposure_seconds = (unsigned int)strtoul(argv[1], 0, 10);
    if (argc > 2) {
        mock_store_wrong_value = 1;
        mock_wrong_value = (unsigned int)strtoul(argv[2], 0, 10);
    }

    memset(instance, 0, sizeof(instance));
    result = open_camera_entry(instance, 0u, (unsigned char)0, exposure_seconds);
    observed = *(unsigned int *)(instance + L16_TIMEOUT_OFFSET);

    printf("open_result=%d\n", result);
    printf("mock_open_calls=%d\n", mock_open_calls);
    printf("mock_stored_timeout=%u\n", mock_stored_timeout);
    printf("observed_timeout=%u\n", observed);
    return 0;
}
