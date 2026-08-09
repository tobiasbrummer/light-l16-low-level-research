"""Tests for the narrow ADRP/ADD/load/store reference scanner."""

from __future__ import annotations

import struct

from tools.arm64_page_refs import (
    Reference,
    containing_symbol,
    decode_add_immediate,
    decode_adrp,
    decode_unsigned_memory,
    find_references,
)


BASE = 0xFFFFFFC000080000
TARGET_PAGE = 0xFFFFFFC001E39000


def _adrp(*, pc: int, page: int, destination: int) -> int:
    delta = (page - (pc & ~0xFFF)) >> 12
    immediate = delta & ((1 << 21) - 1)
    return (
        0x90000000 | ((immediate & 0x3) << 29) | ((immediate >> 2) << 5) | destination
    )


def _add_x(*, destination: int, base: int, immediate: int) -> int:
    return 0x91000000 | (immediate << 10) | (base << 5) | destination


def _str_w(*, source: int, base: int, byte_offset: int) -> int:
    return 0xB9000000 | ((byte_offset >> 2) << 10) | (base << 5) | source


def _ldr_x(*, destination: int, base: int, byte_offset: int) -> int:
    return 0xF9400000 | ((byte_offset >> 3) << 10) | (base << 5) | destination


def _words(*values: int) -> bytes:
    return struct.pack(f"<{len(values)}I", *values)


def test_decoders_recognize_adrp_add_and_unsigned_memory() -> None:
    adrp = _adrp(pc=BASE, page=TARGET_PAGE, destination=20)
    assert decode_adrp(adrp, BASE) == (TARGET_PAGE, 20)
    assert decode_add_immediate(_add_x(destination=0, base=20, immediate=0x428)) == (
        0,
        20,
        0x428,
    )
    assert decode_unsigned_memory(_ldr_x(destination=19, base=0, byte_offset=8)) == (
        0,
        8,
    )


def test_find_references_recognizes_direct_store() -> None:
    target = TARGET_PAGE + 0x428
    image = _words(
        _adrp(pc=BASE, page=TARGET_PAGE, destination=0),
        _str_w(source=1, base=0, byte_offset=0x428),
    )
    assert find_references(image, base=BASE, target=target) == [Reference(0, 4, target)]
    assert find_references(image, base=BASE, target=target + 4) == []


def test_find_references_follows_add_to_later_load() -> None:
    target = TARGET_PAGE + 0x430
    image = _words(
        _adrp(pc=BASE, page=TARGET_PAGE, destination=20),
        _add_x(destination=0, base=20, immediate=0x428),
        _ldr_x(destination=19, base=0, byte_offset=8),
    )
    assert find_references(image, base=BASE, target=target) == [Reference(0, 8, target)]


def test_containing_symbol_uses_nearest_predecessor() -> None:
    assert containing_symbol(BASE + 0x14, [BASE, BASE + 0x20], ["first", "second"]) == (
        "first+0x14"
    )
    assert containing_symbol(BASE - 4, [BASE], ["first"]) == "<no text symbol>"
