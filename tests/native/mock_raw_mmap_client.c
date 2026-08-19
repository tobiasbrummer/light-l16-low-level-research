// SPDX-License-Identifier: MIT
/*
 * Exercises the re-entrant mapping path of the preload directly.
 *
 * That path exists because resolving the real mmap can itself map memory, and
 * the first version recursed until the stack was gone.  It bypasses libc and
 * issues the system call, so the architecture's call number and offset unit
 * have to be right -- and nothing in the normal tests would notice if they
 * were not, because the normal tests never reach it.
 *
 * The shim's translation unit is included rather than linked so the static
 * helper is reachable.
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

#define L16_TARGET_LIBRARY "libmock_lcc_hal.so"
#define L16_EXPECTED_HELPER_COMMANDS 0
#define L16_SHELL_PATH "/bin/sh"
#define L16_LOG_MMAP_FAILURES 8u

#include "lcc_async_writer_shim.c"


int main(void)
{
    void *mapping;
    void *failure;
    char *bytes;

    mapping = l16_raw_mmap(0, 4096, PROT_READ | PROT_WRITE,
                           MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    printf("raw_mapped=%d\n", mapping != L16_MAP_FAILED
                              && (unsigned long)mapping < (unsigned long)-4096L);

    if (mapping != L16_MAP_FAILED) {
        /* A returned address that cannot be written to would mean the flags
         * were misinterpreted, which a pointer check alone would not catch. */
        bytes = (char *)mapping;
        memset(bytes, 0x5a, 4096);
        printf("raw_writable=%d\n", bytes[0] == 0x5a && bytes[4095] == 0x5a);
        munmap(mapping, 4096);
    } else {
        printf("raw_writable=0\n");
    }

    /* Errors come back as a small negative value, not as a valid address. */
    failure = l16_raw_mmap(0, 4096, PROT_READ, MAP_SHARED, 999, 0);
    printf("raw_rejects_bad_fd=%d\n",
           (long)failure < 0 && (long)failure > -4096L);
    return 0;
}
