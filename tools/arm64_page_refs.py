#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Find simple ARM64 ADRP-based references to one virtual address.

The scanner is deliberately narrow: it recognizes ADRP followed shortly by an
ADD-immediate or an unsigned-immediate load/store. That covers the usual
position-independent access pattern for built-in kernel globals without trying
to replace a disassembler. It only reads the supplied image.
"""

from __future__ import annotations

import argparse
import bisect
import mmap
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Reference:
    adrp_offset: int
    access_offset: int
    address: int


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def decode_adrp(word: int, pc: int) -> tuple[int, int] | None:
    """Return ``(page, destination_register)`` for an ADRP instruction."""
    if word & 0x9F000000 != 0x90000000:
        return None
    immediate = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 0x3)
    page = (pc & ~0xFFF) + (_sign_extend(immediate, 21) << 12)
    return page & 0xFFFFFFFFFFFFFFFF, word & 0x1F


def decode_add_immediate(word: int) -> tuple[int, int, int] | None:
    """Return ``(destination, base, immediate)`` for ADD (immediate)."""
    if word & 0x7F000000 != 0x11000000:
        return None
    immediate = (word >> 10) & 0xFFF
    if word & (1 << 22):
        immediate <<= 12
    return word & 0x1F, (word >> 5) & 0x1F, immediate


def decode_unsigned_memory(word: int) -> tuple[int, int] | None:
    """Return ``(base_register, byte_offset)`` for unsigned load/store."""
    if word & 0x3B000000 != 0x39000000:
        return None
    scale = (word >> 30) & 0x3
    return (word >> 5) & 0x1F, ((word >> 10) & 0xFFF) << scale


def find_references(
    image: bytes | bytearray | mmap.mmap,
    *,
    base: int,
    target: int,
    window: int = 8,
) -> list[Reference]:
    references: set[Reference] = set()
    target &= 0xFFFFFFFFFFFFFFFF
    target_page = target & ~0xFFF
    for offset in range(0, len(image) - 3, 4):
        word = struct.unpack_from("<I", image, offset)[0]
        decoded = decode_adrp(word, base + offset)
        if decoded is None or decoded[0] != target_page:
            continue
        registers = {decoded[1]: decoded[0]}
        end = min(len(image) - 3, offset + (window + 1) * 4)
        for access_offset in range(offset + 4, end, 4):
            following = struct.unpack_from("<I", image, access_offset)[0]
            add = decode_add_immediate(following)
            if add is not None and add[1] in registers:
                registers[add[0]] = (registers[add[1]] + add[2]) & 0xFFFFFFFFFFFFFFFF
            memory = decode_unsigned_memory(following)
            if memory is not None and memory[0] in registers:
                address = (registers[memory[0]] + memory[1]) & 0xFFFFFFFFFFFFFFFF
                if address == target:
                    references.add(Reference(offset, access_offset, address))
    return sorted(references, key=lambda item: (item.access_offset, item.adrp_offset))


def load_text_symbols(path: Path) -> tuple[list[int], list[str]]:
    entries: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.split(maxsplit=2)
            if len(fields) != 3 or fields[1] not in {"t", "T"}:
                continue
            try:
                entries.append((int(fields[0], 16), fields[2].strip()))
            except ValueError:
                continue
    entries.sort()
    return [entry[0] for entry in entries], [entry[1] for entry in entries]


def containing_symbol(address: int, starts: list[int], names: list[str]) -> str:
    index = bisect.bisect_right(starts, address) - 1
    if index < 0:
        return "<no text symbol>"
    return f"{names[index]}+0x{address - starts[index]:x}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--base", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--target", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--window", type=int, default=8)
    parser.add_argument("--kallsyms", type=Path)
    args = parser.parse_args(argv)

    starts: list[int] = []
    names: list[str] = []
    if args.kallsyms is not None:
        starts, names = load_text_symbols(args.kallsyms)
    with args.image.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as image:
            references = find_references(
                image,
                base=args.base,
                target=args.target,
                window=args.window,
            )
    for reference in references:
        pc = args.base + reference.access_offset
        owner = containing_symbol(pc, starts, names) if starts else ""
        suffix = f" {owner}" if owner else ""
        print(
            f"adrp=0x{args.base + reference.adrp_offset:016x} "
            f"access=0x{pc:016x}{suffix}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
