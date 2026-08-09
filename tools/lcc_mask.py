#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Encode or decode the Light L16 factory CLI's 24-bit module mask."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Iterable, Sequence


MODULE_LAYOUT = (
    ("A1", 1, 1),
    ("A2", 2, 2),
    ("A3", 3, 2),
    ("A4", 4, 2),
    ("A5", 5, 1),
    ("B1", 6, 2),
    ("B2", 7, 1),
    ("B3", 8, 2),
    ("B4", 9, 1),
    ("B5", 10, 1),
    ("C1", 11, 3),
    ("C2", 12, 2),
    ("C3", 13, 3),
    ("C4", 14, 3),
    ("C5", 15, 1),
    ("C6", 16, 3),
)

MODULE_ORDER = tuple(name for name, _bit, _asic in MODULE_LAYOUT)
MODULE_BITS = {name: bit for name, bit, _asic in MODULE_LAYOUT}
MODULE_ASICS = {name: asic for name, _bit, asic in MODULE_LAYOUT}
GLOBAL_SELECTION_BIT = 1
EXPLICIT_MODULE_MASK = sum(1 << bit for _name, bit, _asic in MODULE_LAYOUT)
KNOWN_MASK = GLOBAL_SELECTION_BIT | EXPLICIT_MODULE_MASK


@dataclass(frozen=True)
class MaskSelection:
    """Decoded mask plus its effective camera and ASIC selections."""

    mask: int
    modules: tuple[str, ...]
    global_selection: bool

    @property
    def cli_bytes(self) -> tuple[int, int, int]:
        return tuple((self.mask >> shift) & 0xFF for shift in (0, 8, 16))

    def modules_for_asic(self, asic: int) -> tuple[str, ...]:
        return tuple(module for module in self.modules if MODULE_ASICS[module] == asic)


def _selection_from_mask(mask: int) -> MaskSelection:
    unknown = mask & ~KNOWN_MASK
    if unknown:
        raise ValueError(f"mask contains unknown bits: 0x{unknown:06x}")

    global_selection = bool(mask & GLOBAL_SELECTION_BIT)
    if global_selection and mask != GLOBAL_SELECTION_BIT:
        raise ValueError("global-selection bit cannot be mixed with module bits")
    if mask == 0:
        raise ValueError("mask selects no camera modules")

    if global_selection:
        modules = MODULE_ORDER
    else:
        modules = tuple(
            name for name, bit, _asic in MODULE_LAYOUT if mask & (1 << bit)
        )
    return MaskSelection(mask, modules, global_selection)


def encode_modules(modules: Iterable[str]) -> MaskSelection:
    """Encode named modules using explicit bits 1 through 16."""

    normalized = tuple(module.upper() for module in modules)
    if not normalized:
        raise ValueError("at least one camera module is required")
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate camera module")

    unknown = tuple(module for module in normalized if module not in MODULE_BITS)
    if unknown:
        raise ValueError(f"unknown camera module: {', '.join(unknown)}")

    mask = sum(1 << MODULE_BITS[module] for module in normalized)
    return _selection_from_mask(mask)


def decode_cli_bytes(values: Sequence[int]) -> MaskSelection:
    """Decode the three little-endian bytes consumed by the factory CLI."""

    if len(values) != 3:
        raise ValueError("exactly three mask bytes are required")
    if any(value < 0 or value > 0xFF for value in values):
        raise ValueError("mask bytes must be in the range 00..ff")

    mask = values[0] | values[1] << 8 | values[2] << 16
    return _selection_from_mask(mask)


def parse_hex_byte(value: str) -> int:
    text = value.removeprefix("0x").removeprefix("0X")
    if not text or len(text) > 2:
        raise ValueError(f"invalid hexadecimal byte: {value}")
    try:
        parsed = int(text, 16)
    except ValueError as error:
        raise ValueError(f"invalid hexadecimal byte: {value}") from error
    if parsed > 0xFF:
        raise ValueError(f"invalid hexadecimal byte: {value}")
    return parsed


def format_selection(selection: MaskSelection) -> str:
    byte_text = " ".join(f"{value:02X}" for value in selection.cli_bytes)
    kind = "global" if selection.global_selection else "explicit"
    lines = [
        f"mask=0x{selection.mask:06x}",
        f"bytes={byte_text}",
        f"selection={kind}:{','.join(selection.modules)}",
    ]
    for asic in (1, 2, 3):
        lines.append(f"asic{asic}={','.join(selection.modules_for_asic(asic))}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--decode",
        nargs=3,
        metavar=("BYTE0", "BYTE1", "BYTE2"),
        help="decode three little-endian hexadecimal bytes",
    )
    parser.add_argument("modules", nargs="*", help="module names such as A1 B3 C6")
    args = parser.parse_args(argv)

    try:
        if args.decode is not None:
            if args.modules:
                raise ValueError("module names cannot be combined with --decode")
            selection = decode_cli_bytes(
                tuple(parse_hex_byte(value) for value in args.decode)
            )
        else:
            selection = encode_modules(args.modules)
    except ValueError as error:
        parser.error(str(error))

    print(format_selection(selection))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
