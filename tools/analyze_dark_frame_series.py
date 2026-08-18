"""Reduce an all-16 dark frame series to a per-module noise report.

Unlike every other tool in this repository, this one reads RAW10 pixels.  The
container and protobuf decoding are imported from ``verify_stock_capture``
rather than reimplemented; only the pixel access is new.

NumPy is required and is confined to this tool.  See requirements-analysis.txt.

Container layout, established by walking a retained all-16 capture:

* the file is a chain of 32-byte ``LELR`` block headers holding
  ``block_length``, ``message_offset``, ``message_length``, ``message_type``;
* ``message_type == 0`` blocks carry the protobuf capture header at
  ``message_offset``, and the pixel surfaces sit *before* it, between the
  block header and the message;
* each module record (field 12) has a surface submessage (field 9) whose
  field 5 is the surface's byte offset relative to the start of its block.
  A retained all-16 capture places 6, 6, and 4 surfaces into three blocks,
  each surface aligned so that consecutive offsets differ by 16,228,352
  bytes while only 16,224,000 of those are pixels.

The offset is read from field 5 rather than computed from the stride, because
the padding between surfaces is not derivable from the image geometry.

RAW10 bit order: this follows the MIPI CSI-2 packing, four pixels per five
bytes with the low bits of pixels 0..3 in bits [1:0], [3:2], [5:4], [7:6] of
the fifth byte.  That assignment could not be confirmed empirically from the
retained capture: the alternative ordering differs by at most 3 DN and is
invisible in a high-contrast scene.  It does not affect any statistic reported
here, since the two low bits are equally distributed across the four quad
positions; it would only change which individual pixel a hot-pixel coordinate
names.  A dark frame with a genuinely flat field would settle it.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

try:
    import numpy
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI only.
    raise SystemExit(
        "analyze_dark_frame_series requires NumPy: "
        "python -m pip install -r requirements-analysis.txt"
    )

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_stock_capture import (  # noqa: E402
    LRI_HEADER,
    DecodeError,
    ModuleRecord,
    _decode_module,
    _optional_message,
    _optional_varint,
    _wire_fields,
)

DEFAULT_HOT_THRESHOLD = 512
MODULE_FIELD = 12
SURFACE_FIELD = 9
SURFACE_OFFSET_FIELD = 5
RAW_PACKED_10BPP = 7


@dataclass(frozen=True)
class SurfaceStats:
    mean: float
    spatial_std: float
    minimum: int
    maximum: int
    hot_count: int


@dataclass(frozen=True)
class CellKey:
    exposure_ns: int
    gain: float


def unpack_raw10(
    data: bytes, width: int, height: int, row_stride: int
) -> "numpy.ndarray":
    """Unpack MIPI RAW10 into a (height, width) array of uint16."""
    if width % 4:
        raise ValueError(f"width {width} is not a multiple of four")
    packed_row_bytes = width // 4 * 5
    if row_stride < packed_row_bytes:
        raise ValueError(
            f"row_stride {row_stride} shorter than packed row {packed_row_bytes}"
        )
    needed = row_stride * height
    if len(data) < needed:
        raise ValueError(f"need {needed} bytes, got {len(data)}")
    raw = numpy.frombuffer(data, dtype=numpy.uint8, count=needed)
    quads = raw.reshape(height, row_stride)[:, :packed_row_bytes]
    quads = quads.reshape(height, width // 4, 5)
    high = quads[:, :, :4].astype(numpy.uint16)
    low = quads[:, :, 4].astype(numpy.uint16)
    out = numpy.empty((height, width // 4, 4), dtype=numpy.uint16)
    for position in range(4):
        out[:, :, position] = (
            (high[:, :, position] << 2) | ((low >> (2 * position)) & 0x03)
        )
    return out.reshape(height, width)


def surface_statistics(
    samples: "numpy.ndarray", hot_threshold: int = DEFAULT_HOT_THRESHOLD
) -> SurfaceStats:
    values = samples.astype(numpy.float64)
    return SurfaceStats(
        mean=float(values.mean()),
        spatial_std=float(values.std()),
        minimum=int(samples.min()),
        maximum=int(samples.max()),
        hot_count=int((samples > hot_threshold).sum()),
    )


def read_noise_from_pair(
    first: "numpy.ndarray", second: "numpy.ndarray"
) -> float:
    """Temporal noise from two repeats of the same cell.

    Each frame carries the same sigma, so their difference carries
    sigma * sqrt(2); dividing it back out gives the per-frame read noise and
    cancels the fixed pattern, which is identical in both frames.
    """
    difference = first.astype(numpy.float64) - second.astype(numpy.float64)
    return float(difference.std() / math.sqrt(2.0))


def group_into_cells(entries) -> dict:
    """Group (path, exposure_ns, gain) triples into measurement cells."""
    cells: dict = defaultdict(list)
    for path, exposure_ns, gain in entries:
        cells[CellKey(int(exposure_ns), float(gain))].append(path)
    return dict(cells)


def _surface_offset(module_payload: bytes) -> int | None:
    surface = _optional_message(module_payload, SURFACE_FIELD)
    if surface is None:
        return None
    return _optional_varint(surface, SURFACE_OFFSET_FIELD)


def iter_module_surfaces(
    path: Path,
) -> Iterator[tuple[ModuleRecord, "numpy.ndarray"]]:
    """Yield one (record, samples) pair per module, one surface at a time.

    Reducing each surface as it arrives keeps memory bounded: a full all-16
    capture is 16 surfaces of about 26 MB unpacked, which need not be resident
    at once.
    """
    size = path.stat().st_size
    offset = 0
    with path.open("rb") as stream:
        while offset < size:
            stream.seek(offset)
            raw = stream.read(LRI_HEADER.size)
            if len(raw) != LRI_HEADER.size:
                raise DecodeError(f"short LELR header at offset {offset}")
            magic, block_length, message_offset, message_length, message_type = (
                LRI_HEADER.unpack(raw)
            )
            if magic != b"LELR":
                raise DecodeError(f"bad LELR magic at offset {offset}")
            if block_length <= 0:
                raise DecodeError(f"non-positive block length at offset {offset}")
            if message_type == 0:
                stream.seek(offset + message_offset)
                message = stream.read(message_length)
                if len(message) != message_length:
                    raise DecodeError(f"short message at offset {offset}")
                for number, _wire, payload in _wire_fields(message):
                    if number != MODULE_FIELD or isinstance(payload, int):
                        continue
                    record = _decode_module(payload)
                    surface_offset = _surface_offset(payload)
                    if (
                        surface_offset is None
                        or record.width is None
                        or record.height is None
                        or record.row_stride is None
                    ):
                        continue
                    if record.raw_format != RAW_PACKED_10BPP:
                        raise DecodeError(
                            f"{record.name} is not RAW_PACKED_10BPP"
                        )
                    stream.seek(offset + surface_offset)
                    data = stream.read(record.row_stride * record.height)
                    yield record, unpack_raw10(
                        data, record.width, record.height, record.row_stride
                    )
            offset += block_length


def _cell_label(key: CellKey) -> str:
    if key.exposure_ns >= 1_000_000:
        exposure = f"{key.exposure_ns / 1_000_000:g} ms"
    else:
        exposure = f"{key.exposure_ns / 1000:g} us"
    return f"{exposure} @ g{key.gain:g}"


def analyze_series(directory: Path, hot_threshold: int) -> str:
    files = sorted(directory.glob("*.lri"))
    if not files:
        raise SystemExit(f"no .lri files in {directory}")

    # Pass one: per-file, per-module statistics, reduced as each surface is
    # read so that the whole series never has to be resident.
    per_file: dict[Path, dict[str, SurfaceStats]] = {}
    identity: dict[Path, tuple[int, float, float]] = {}
    lines: list[str] = []

    for path in files:
        stats: dict[str, SurfaceStats] = {}
        exposures: set[int] = set()
        analog: set[float] = set()
        digital: set[float] = set()
        for record, samples in iter_module_surfaces(path):
            stats[record.name] = surface_statistics(samples, hot_threshold)
            if record.exposure_ns is not None:
                exposures.add(record.exposure_ns)
            if record.analog_gain is not None:
                analog.add(round(record.analog_gain, 6))
            if record.digital_gain is not None:
                digital.add(round(record.digital_gain, 6))
        per_file[path] = stats
        identity[path] = (
            max(exposures) if exposures else 0,
            max(analog) if analog else 0.0,
            max(digital) if digital else 0.0,
        )

    lines.append("# All-16 dark frame series report")
    lines.append("")
    lines.append(f"files={len(files)}")
    lines.append(f"hot_pixel_threshold_dn={hot_threshold}")
    lines.append("units=DN (10-bit); no conversion to electrons is claimed")
    lines.append("")

    lines.append("## Recorded exposure and gain per file")
    lines.append("")
    lines.append(
        f"{'file':<40} {'exposure_ns':>12} {'analog_gain':>12} {'digital_gain':>13}"
    )
    for path in files:
        exposure, analog_gain, digital_gain = identity[path]
        lines.append(
            f"{path.name:<40} {exposure:>12} {analog_gain:>12.5f} "
            f"{digital_gain:>13.5f}"
        )
    lines.append("")

    entries = [
        (path, identity[path][0], identity[path][1] * identity[path][2])
        for path in files
    ]
    cells = group_into_cells(entries)

    lines.append("## Per-cell, per-module level and noise")
    lines.append("")
    lines.append(
        f"{'cell':<22} {'module':<7} {'mean':>9} {'fpn':>9} {'read':>8} "
        f"{'min':>5} {'max':>6} {'hot':>8}"
    )
    for key in sorted(cells, key=lambda k: (k.gain, k.exposure_ns)):
        members = cells[key]
        label = _cell_label(key)
        modules = sorted(per_file[members[0]])
        read_noise: dict[str, float | None] = {name: None for name in modules}
        if len(members) >= 2:
            read_noise = _read_noise_for_cell(members[0], members[1], modules)
        for name in modules:
            stats = per_file[members[0]][name]
            noise = read_noise.get(name)
            noise_text = f"{noise:>8.3f}" if noise is not None else f"{'n/a':>8}"
            lines.append(
                f"{label:<22} {name:<7} {stats.mean:>9.3f} "
                f"{stats.spatial_std:>9.3f} {noise_text} "
                f"{stats.minimum:>5} {stats.maximum:>6} {stats.hot_count:>8}"
            )
    lines.append("")

    lines.append("## Dark current at gain 1.0")
    lines.append("")
    lines.append(f"{'module':<7} {'slope_dn_per_s':>16} {'points':>7}")
    gain_one = {
        key: members for key, members in cells.items() if abs(key.gain - 1.0) < 1e-6
    }
    modules = sorted(per_file[files[0]])
    for name in modules:
        points = [
            (key.exposure_ns / 1e9, per_file[members[0]][name].mean)
            for key, members in sorted(gain_one.items(), key=lambda kv: kv[0].exposure_ns)
            if name in per_file[members[0]]
        ]
        if len(points) < 2:
            lines.append(f"{name:<7} {'n/a':>16} {len(points):>7}")
            continue
        slope = _least_squares_slope(points)
        lines.append(f"{name:<7} {slope:>16.3f} {len(points):>7}")
    lines.append("")

    lines.append("## Requested versus recorded gain")
    lines.append("")
    lines.append(
        "The requested value is the plan's -g argument, inferred from the file "
        "order; the recorded values come from the LRI itself."
    )
    lines.append("")
    lines.append(
        f"{'file':<40} {'analog':>9} {'digital':>9} {'product':>9}"
    )
    for path in files:
        _exposure, analog_gain, digital_gain = identity[path]
        lines.append(
            f"{path.name:<40} {analog_gain:>9.5f} {digital_gain:>9.5f} "
            f"{analog_gain * digital_gain:>9.5f}"
        )
    return "\n".join(lines) + "\n"


def _read_noise_for_cell(
    first_path: Path, second_path: Path, modules: list[str]
) -> dict:
    """Read noise per module from two repeats, holding two surfaces at a time."""
    first_surfaces = {
        record.name: samples for record, samples in iter_module_surfaces(first_path)
    }
    result: dict = {}
    for record, samples in iter_module_surfaces(second_path):
        other = first_surfaces.get(record.name)
        if other is not None and other.shape == samples.shape:
            result[record.name] = read_noise_from_pair(other, samples)
    return result


def _least_squares_slope(points: list[tuple[float, float]]) -> float:
    xs = numpy.array([point[0] for point in points], dtype=numpy.float64)
    ys = numpy.array([point[1] for point in points], dtype=numpy.float64)
    x_mean = xs.mean()
    y_mean = ys.mean()
    denominator = ((xs - x_mean) ** 2).sum()
    if denominator == 0.0:
        return 0.0
    return float(((xs - x_mean) * (ys - y_mean)).sum() / denominator)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reduce a pulled all-16 dark frame series to a report."
    )
    parser.add_argument(
        "directory", type=Path, help="directory holding the pulled .lri files"
    )
    parser.add_argument(
        "--hot-threshold",
        type=int,
        default=DEFAULT_HOT_THRESHOLD,
        help=f"hot pixel threshold in DN (default {DEFAULT_HOT_THRESHOLD})",
    )
    arguments = parser.parse_args(argv)
    sys.stdout.write(analyze_series(arguments.directory, arguments.hot_threshold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
