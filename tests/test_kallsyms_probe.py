"""Tests for the read-only ARM64 kallsyms candidate finder."""

from __future__ import annotations

import struct

from tools.kallsyms_probe import has_matching_num_syms, main, pointer_runs


BASE = 0xFFFFFFC000080000


def _candidate(*, count: int = 5, valid_count: bool = True) -> bytes:
    values = [BASE, BASE + 4, BASE + 4, BASE + 0x20, BASE + 0x80][:count]
    stored_count = len(values) if valid_count else len(values) + 1
    return (
        b"abc"
        + struct.pack(f"<{len(values)}Q", *values)
        + struct.pack("<I", stored_count)
    )


def test_pointer_runs_finds_unaligned_monotonic_table() -> None:
    image = _candidate()
    assert pointer_runs(
        image,
        lower=BASE,
        upper=BASE + 0x1000,
        minimum=5,
    ) == [(3, 5, BASE, BASE + 0x80)]


def test_num_syms_must_follow_table() -> None:
    assert has_matching_num_syms(_candidate(), 3, 5)
    assert not has_matching_num_syms(_candidate(valid_count=False), 3, 5)
    assert not has_matching_num_syms(b"short", 3, 5)


def test_descending_address_ends_run() -> None:
    image = struct.pack("<4Q", BASE, BASE + 8, BASE + 4, BASE + 12)
    assert (
        pointer_runs(
            image,
            lower=BASE,
            upper=BASE + 0x1000,
            minimum=3,
        )
        == []
    )


def test_cli_validated_only_filters_decoy(tmp_path, capsys) -> None:
    image = tmp_path / "kernel.raw"
    image.write_bytes(_candidate(valid_count=False))
    assert (
        main(
            [
                str(image),
                "--base",
                hex(BASE),
                "--span",
                "0x1000",
                "--minimum",
                "5",
                "--validated-only",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == ""
