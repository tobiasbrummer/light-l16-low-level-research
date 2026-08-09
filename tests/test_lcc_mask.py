from __future__ import annotations

import pytest

from tools.lcc_mask import (
    MODULE_ORDER,
    decode_cli_bytes,
    encode_modules,
    main,
    parse_hex_byte,
)


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("A1", (0x02, 0x00, 0x00)),
        ("B3", (0x00, 0x01, 0x00)),
        ("C6", (0x00, 0x00, 0x01)),
    ],
)
def test_single_module_bits(module: str, expected: tuple[int, int, int]) -> None:
    assert encode_modules([module]).cli_bytes == expected


def test_known_multi_asic_example() -> None:
    selection = encode_modules(["A1", "B3", "C6"])
    assert selection.mask == 0x010102
    assert selection.cli_bytes == (0x02, 0x01, 0x01)
    assert selection.modules_for_asic(1) == ("A1",)
    assert selection.modules_for_asic(2) == ("B3",)
    assert selection.modules_for_asic(3) == ("C6",)


def test_all_explicit_module_bits_match_factory_mask() -> None:
    selection = encode_modules(MODULE_ORDER)
    assert selection.mask == 0x01FFFE
    assert selection.cli_bytes == (0xFE, 0xFF, 0x01)
    assert not selection.global_selection


def test_global_selection_bit_decodes_separately() -> None:
    selection = decode_cli_bytes((0x01, 0x00, 0x00))
    assert selection.global_selection
    assert selection.modules == MODULE_ORDER


@pytest.mark.parametrize(
    "values",
    [
        (0x00, 0x00, 0x00),
        (0x03, 0x00, 0x00),
        (0x00, 0x00, 0x02),
        (0x100, 0x00, 0x00),
    ],
)
def test_invalid_or_ambiguous_masks_are_rejected(values: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        decode_cli_bytes(values)


def test_unknown_and_duplicate_module_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        encode_modules(["D1"])
    with pytest.raises(ValueError, match="duplicate"):
        encode_modules(["A1", "a1"])


def test_hex_bytes_are_not_parsed_as_decimal() -> None:
    assert parse_hex_byte("10") == 0x10
    assert parse_hex_byte("0xF1") == 0xF1
    with pytest.raises(ValueError):
        parse_hex_byte("100")


def test_cli_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["A1", "B3", "C6"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "mask=0x010102",
        "bytes=02 01 01",
        "selection=explicit:A1,B3,C6",
        "asic1=A1",
        "asic2=B3",
        "asic3=C6",
    ]
