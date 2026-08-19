// SPDX-License-Identifier: MIT
/*
 * Stand-in for the LCC HAL used to exercise the capture-timeout preload
 * without a camera.
 *
 * It reproduces exactly the part of openCamera the shim reasons about: the
 * timeout derived from the third argument and stored at instance offset
 * 0x24.  A test can ask it to store a different value instead, which is how
 * the shim's refusal path is exercised.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>

#define L16_OPEN_SYMBOL "_ZN7qcamera12LccInterface10openCameraEjhj"
#define L16_TIMEOUT_OFFSET 0x24

int mock_open_calls;
int mock_open_return;
unsigned int mock_stored_timeout;
/* When set, store this instead of the derived value, so the shim sees a
 * field that does not match its expectation. */
int mock_store_wrong_value;
unsigned int mock_wrong_value;


__attribute__((noinline, visibility("default")))
int mock_open_camera(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
) __asm__(L16_OPEN_SYMBOL);

int mock_open_camera(
    void *self,
    unsigned int first,
    unsigned char second,
    unsigned int third
)
{
    unsigned int derived;

    (void)first;
    (void)second;
    ++mock_open_calls;
    if (self == 0) {
        return -1;
    }
    if (mock_open_return != 0) {
        return mock_open_return;
    }

    /* cmp r7,#9 / addhi r3,r7,#5 / movls r3,#15 / str r3,[r4,#0x24] */
    derived = third > 9u ? third + 5u : 15u;
    if (mock_store_wrong_value) {
        derived = mock_wrong_value;
    }
    mock_stored_timeout = derived;
    *(unsigned int *)((char *)self + L16_TIMEOUT_OFFSET) = derived;
    return 0;
}
