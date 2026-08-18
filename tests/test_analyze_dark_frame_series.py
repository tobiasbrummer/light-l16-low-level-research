from __future__ import annotations

import sys
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_dark_frame_series import (  # noqa: E402
    CellKey,
    group_into_cells,
    read_noise_from_pair,
    surface_statistics,
    unpack_raw10,
)

RETAINED = (
    ROOT / "output" / "all16-capture-20260809T192149Z" / "pixels"
    / "RDI_20260809_212153_985.lri"
)


def pack_raw10(values: list[int]) -> bytes:
    """Reference packer: four pixels per five bytes, low bits ascending."""
    assert len(values) % 4 == 0
    out = bytearray()
    for index in range(0, len(values), 4):
        quad = values[index:index + 4]
        low = 0
        for position, sample in enumerate(quad):
            out.append((sample >> 2) & 0xFF)
            low |= (sample & 0x03) << (2 * position)
        out.append(low)
    return bytes(out)


def test_unpack_raw10_round_trips_known_samples() -> None:
    values = [0, 1, 2, 3, 512, 1023, 640, 64]
    packed = pack_raw10(values)
    assert len(packed) == 10
    result = unpack_raw10(packed, width=8, height=1, row_stride=10)
    assert result.shape == (1, 8)
    assert list(result[0]) == values


def test_unpack_raw10_honours_row_stride_padding() -> None:
    packed = pack_raw10([64] * 4) + b"\x00\x00" + pack_raw10([320] * 4) + b"\x00\x00"
    result = unpack_raw10(packed, width=4, height=2, row_stride=7)
    assert result.shape == (2, 4)
    assert list(result[0]) == [64] * 4
    assert list(result[1]) == [320] * 4


def test_unpack_raw10_rejects_short_input() -> None:
    with pytest.raises(ValueError):
        unpack_raw10(b"\x00" * 4, width=4, height=1, row_stride=5)


def test_unpack_raw10_rejects_a_width_that_is_not_a_quad_multiple() -> None:
    with pytest.raises(ValueError):
        unpack_raw10(b"\x00" * 10, width=6, height=1, row_stride=10)


def test_unpack_raw10_rejects_a_stride_shorter_than_the_packed_row() -> None:
    with pytest.raises(ValueError):
        unpack_raw10(b"\x00" * 10, width=8, height=1, row_stride=9)


def test_surface_statistics_reports_level_and_spatial_noise() -> None:
    samples = numpy.full((16, 16), 64, dtype=numpy.uint16)
    samples[0, 0] = 1023
    stats = surface_statistics(samples, hot_threshold=512)
    assert stats.mean == pytest.approx(67.746, abs=0.01)
    assert stats.hot_count == 1
    assert stats.spatial_std > 0.0
    assert stats.maximum == 1023
    assert stats.minimum == 64


def test_read_noise_divides_the_pair_difference_by_root_two() -> None:
    """Two independent frames each carry sigma, so their difference carries
    sigma*sqrt(2).  The estimator must divide it back out."""
    generator = numpy.random.default_rng(7)
    level = 64.0
    sigma = 3.0
    first = generator.normal(level, sigma, size=(256, 256))
    second = generator.normal(level, sigma, size=(256, 256))
    estimate = read_noise_from_pair(first, second)
    assert estimate == pytest.approx(sigma, rel=0.05)


def test_cells_group_by_exposure_and_gain() -> None:
    entries = [
        ("a.lri", 10000, 1.0),
        ("b.lri", 10000, 1.0),
        ("c.lri", 1250000, 1.0),
        ("d.lri", 1250000, 7.5),
    ]
    cells = group_into_cells(entries)
    assert cells[CellKey(10000, 1.0)] == ["a.lri", "b.lri"]
    assert cells[CellKey(1250000, 1.0)] == ["c.lri"]
    assert cells[CellKey(1250000, 7.5)] == ["d.lri"]


@pytest.mark.skipif(not RETAINED.exists(), reason="retained all-16 LRI not present")
def test_real_capture_decodes_into_sixteen_named_surfaces() -> None:
    from analyze_dark_frame_series import iter_module_surfaces

    seen = {}
    for record, samples in iter_module_surfaces(RETAINED):
        seen[record.name] = samples.shape
        assert samples.dtype == numpy.uint16
        assert samples.max() <= 1023, f"{record.name} exceeds the 10-bit range"
        assert samples.min() >= 0
    assert len(seen) == 16
    assert seen["A1"] == (3120, 4160)
    assert set(seen) == {
        "A1", "A2", "A3", "A4", "A5",
        "B1", "B2", "B3", "B4", "B5",
        "C1", "C2", "C3", "C4", "C5", "C6",
    }


@pytest.mark.skipif(not RETAINED.exists(), reason="retained all-16 LRI not present")
def test_real_capture_reports_its_recorded_exposure_and_gains() -> None:
    from analyze_dark_frame_series import iter_module_surfaces

    for record, _ in iter_module_surfaces(RETAINED):
        # The retained control capture was 20 ms at gain 1.0 on every module.
        assert record.exposure_ns == 19999956
        assert record.analog_gain == pytest.approx(1.0)
        assert record.digital_gain == pytest.approx(1.0)
        assert record.row_stride == 5200
        assert record.raw_format == 7
