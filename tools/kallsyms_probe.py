#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find long monotonic ARM64 kernel-pointer runs in a raw Image.

This is an exploratory, read-only probe. A classic pre-base-relative kallsyms
address table is an array of sorted native-width kernel virtual addresses; long
runs are therefore useful candidates for a full decoder.
"""

from __future__ import annotations

import argparse
import mmap
import struct
from pathlib import Path


def pointer_runs(
    image: bytes | bytearray | mmap.mmap,
    *,
    lower: int,
    upper: int,
    minimum: int,
) -> list[tuple[int, int, int, int]]:
    runs: list[tuple[int, int, int, int]] = []
    for alignment in range(8):
        offset = alignment
        while offset + 8 <= len(image):
            value = struct.unpack_from("<Q", image, offset)[0]
            if lower <= value < upper:
                start = offset
                first = value
                previous = value
                offset += 8
                count = 1
                while offset + 8 <= len(image):
                    value = struct.unpack_from("<Q", image, offset)[0]
                    if not (lower <= value < upper):
                        break
                    if value < previous:
                        break
                    previous = value
                    count += 1
                    offset += 8
                if count >= minimum:
                    runs.append((start, count, first, previous))
            else:
                offset += 8
    return sorted(runs, key=lambda item: (-item[1], item[0]))


def has_matching_num_syms(
    image: bytes | bytearray | mmap.mmap,
    offset: int,
    count: int,
) -> bool:
    """Check the classic kallsyms count stored after an address table."""
    count_offset = offset + count * 8
    if count_offset + 4 > len(image):
        return False
    return struct.unpack_from("<I", image, count_offset)[0] == count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--base", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--span", type=lambda value: int(value, 0), default=0x4000000)
    parser.add_argument("--minimum", type=int, default=32)
    parser.add_argument(
        "--validated-only",
        action="store_true",
        help="only print runs followed by a matching 32-bit symbol count",
    )
    args = parser.parse_args(argv)
    with args.image.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as image:
            for offset, count, first, last in pointer_runs(
                image,
                lower=args.base,
                upper=args.base + args.span,
                minimum=args.minimum,
            ):
                validated = has_matching_num_syms(image, offset, count)
                if args.validated_only and not validated:
                    continue
                print(
                    f"offset=0x{offset:08x} count={count} "
                    f"first=0x{first:016x} last=0x{last:016x} "
                    f"num_syms={'match' if validated else 'mismatch'}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
