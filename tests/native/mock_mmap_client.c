// SPDX-License-Identifier: MIT
/*
 * Drives the mmap-failure probe in the preload.
 *
 * The probe exists because the HAL prints "mmap failed on ion fd: %d" without
 * the errno that would say why.  It must report failures and stay out of the
 * way otherwise, so this client exercises both paths and prints what the
 * caller actually observed.
 *
 * Arguments: none.  It performs one mapping that must succeed, one that must
 * fail with EBADF, and one that must fail with EINVAL, then reports the
 * return values and errno each call left behind.
 */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>


int main(void)
{
    void *ok;
    void *bad_fd;
    void *bad_len;
    int bad_fd_errno;
    int bad_len_errno;
    int ok_errno;

    /* Anonymous mapping: no descriptor involved, must be left alone. */
    errno = 0;
    ok = mmap(0, 4096, PROT_READ | PROT_WRITE,
              MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    ok_errno = errno;

    /* A descriptor that was never opened. */
    errno = 0;
    bad_fd = mmap(0, 4096, PROT_READ, MAP_SHARED, 999, 0);
    bad_fd_errno = errno;

    /* Zero length is rejected before the descriptor is even considered. */
    errno = 0;
    bad_len = mmap(0, 0, PROT_READ, MAP_SHARED, 0, 0);
    bad_len_errno = errno;

    printf("ok_failed=%d\n", ok == MAP_FAILED);
    printf("ok_errno=%d\n", ok_errno);
    printf("bad_fd_failed=%d\n", bad_fd == MAP_FAILED);
    printf("bad_fd_errno=%d\n", bad_fd_errno);
    printf("bad_len_failed=%d\n", bad_len == MAP_FAILED);
    printf("bad_len_errno=%d\n", bad_len_errno);
    printf("ebadf=%d\n", EBADF);
    printf("einval=%d\n", EINVAL);

    if (ok != MAP_FAILED) {
        munmap(ok, 4096);
    }
    return 0;
}
