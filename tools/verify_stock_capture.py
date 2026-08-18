#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify one no-root stock-path LRI/JPEG/report bundle.

The verifier is deliberately dependency-free.  It validates the public LELR
framing, the app report and hashes, JPEG framing/dimensions, and the small
subset of the reconstructed LightHeader protobuf schema needed to identify
the fired modules and their capture metadata.  It never interprets the RAW10
pixels or claims image-quality validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

try:
    from tools.analyze_a1_capture import parse_key_values, validate_lri_container
except ModuleNotFoundError:  # Direct execution as tools/verify_stock_capture.py.
    from analyze_a1_capture import parse_key_values, validate_lri_container


MIN_LRI_BYTES = 1024 * 1024
LRI_HEADER = struct.Struct("<4sQQIB7x")
CAMERA_NAMES = (
    "A1", "A2", "A3", "A4", "A5",
    "B1", "B2", "B3", "B4", "B5",
    "C1", "C2", "C3", "C4", "C5", "C6",
)
AF_TRIGGER_NAMES = {
    0: "LEGACY_UNKNOWN",
    1: "START_UP",
    2: "FACE_DETECT",
    3: "MOTION_DETECT",
    4: "ZOOM_MODE_CHANGE",
    5: "USER_TAP",
    6: "HW_SHORT_PRESS",
    7: "TEST",
    8: "USER_TAP_N_HOLD",
    9: "HW_LONG_PRESS",
    10: "PRE_CAPTURE",
}
RAW_FORMAT_NAMES = {
    0: "RAW_BAYER_JPEG",
    7: "RAW_PACKED_10BPP",
    8: "RAW_PACKED_12BPP",
    9: "RAW_PACKED_14BPP",
}
EXPECTED_GROUPS = {
    "AB": frozenset(CAMERA_NAMES[:10]),
    "BC": frozenset(CAMERA_NAMES[5:]),
    "all16": frozenset(CAMERA_NAMES),
    "A1": frozenset(("A1",)),
}
SOF_MARKERS = frozenset(
    (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)
)
SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")


class DecodeError(ValueError):
    """A bounded protobuf or JPEG structure could not be decoded."""


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class ModuleRecord:
    name: str
    enabled: bool
    exposure_ns: int | None
    analog_gain: float | None
    digital_gain: float | None
    lens_position: int | None
    mirror_position: int
    width: int | None
    height: int | None
    raw_format: int | None
    row_stride: int | None
    frame_index: int | None


@dataclass(frozen=True)
class CaptureHeader:
    block_index: int
    focal_length_35mm: int | None
    af_trigger_source: int | None
    modules: tuple[ModuleRecord, ...]


@dataclass(frozen=True)
class LriInspection:
    block_count: int
    capture_headers: tuple[CaptureHeader, ...]

    @property
    def modules(self) -> tuple[ModuleRecord, ...]:
        return tuple(module for header in self.capture_headers for module in header.modules)


@dataclass(frozen=True)
class Verification:
    verdict: str
    exit_code: int
    report: str
    lri: str | None
    jpeg: str | None
    lri_blocks: int | None
    capture_headers: int | None
    focal_lengths_35mm: tuple[int, ...]
    af_trigger_sources: tuple[int, ...]
    modules: tuple[str, ...]
    findings: tuple[Finding, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_varint(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if position >= len(data):
            raise DecodeError("truncated varint")
        byte = data[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, position
    raise DecodeError("varint exceeds 10 bytes")


def _wire_fields(data: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    position = 0
    while position < len(data):
        tag, position = _read_varint(data, position)
        field_number, wire_type = tag >> 3, tag & 7
        if field_number == 0:
            raise DecodeError("protobuf field zero")
        if wire_type == 0:
            value, position = _read_varint(data, position)
        elif wire_type == 1:
            end = position + 8
            if end > len(data):
                raise DecodeError("truncated fixed64")
            value, position = data[position:end], end
        elif wire_type == 2:
            length, position = _read_varint(data, position)
            end = position + length
            if end > len(data):
                raise DecodeError("truncated length-delimited field")
            value, position = data[position:end], end
        elif wire_type == 5:
            end = position + 4
            if end > len(data):
                raise DecodeError("truncated fixed32")
            value, position = data[position:end], end
        else:
            raise DecodeError(f"unsupported protobuf wire type {wire_type}")
        yield field_number, wire_type, value


def _values(data: bytes, number: int, wire_type: int) -> list[int | bytes]:
    return [value for field, wire, value in _wire_fields(data)
            if field == number and wire == wire_type]


def _optional_varint(data: bytes, number: int) -> int | None:
    values = _values(data, number, 0)
    return int(values[-1]) if values else None


def _optional_message(data: bytes, number: int) -> bytes | None:
    values = _values(data, number, 2)
    return bytes(values[-1]) if values else None


def _optional_float(data: bytes, number: int) -> float | None:
    values = _values(data, number, 5)
    return struct.unpack("<f", bytes(values[-1]))[0] if values else None


def _signed_int32(value: int | None) -> int | None:
    if value is None:
        return None
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _decode_point(data: bytes | None) -> tuple[int | None, int | None]:
    if data is None:
        return None, None
    return (_signed_int32(_optional_varint(data, 1)),
            _signed_int32(_optional_varint(data, 2)))


def _decode_module(data: bytes) -> ModuleRecord:
    camera_id = _optional_varint(data, 2)
    if camera_id is None or not 0 <= camera_id < len(CAMERA_NAMES):
        raise DecodeError(f"invalid or missing camera ID {camera_id}")
    enabled_value = _optional_varint(data, 3)
    surface = _optional_message(data, 9)
    size = _optional_message(surface, 2) if surface is not None else None
    width, height = _decode_point(size)
    return ModuleRecord(
        name=CAMERA_NAMES[camera_id],
        enabled=True if enabled_value is None else bool(enabled_value),
        exposure_ns=_optional_varint(data, 8),
        analog_gain=_optional_float(data, 7),
        digital_gain=_optional_float(data, 14),
        lens_position=_signed_int32(_optional_varint(data, 5)),
        mirror_position=_signed_int32(_optional_varint(data, 4)) or 0,
        width=width,
        height=height,
        raw_format=_optional_varint(surface, 3) if surface is not None else None,
        row_stride=_optional_varint(surface, 4) if surface is not None else None,
        frame_index=_optional_varint(data, 15),
    )


def _decode_capture_header(block_index: int, data: bytes) -> CaptureHeader | None:
    module_payloads = [bytes(value) for value in _values(data, 12, 2)]
    if not module_payloads:
        return None
    af_info = _optional_message(data, 24)
    return CaptureHeader(
        block_index=block_index,
        focal_length_35mm=_signed_int32(_optional_varint(data, 4)),
        af_trigger_source=(
            _optional_varint(af_info, 3) if af_info is not None else None
        ),
        modules=tuple(_decode_module(payload) for payload in module_payloads),
    )


def inspect_lri(path: Path) -> LriInspection:
    """Stream only LELR headers and protobuf messages, not the RAW surfaces."""

    size = path.stat().st_size
    offset = 0
    index = 0
    capture_headers: list[CaptureHeader] = []
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
            if message_type == 0:
                stream.seek(offset + message_offset)
                message = stream.read(message_length)
                if len(message) != message_length:
                    raise DecodeError(f"short message in block {index}")
                capture = _decode_capture_header(index, message)
                if capture is not None:
                    capture_headers.append(capture)
            offset += block_length
            index += 1
    return LriInspection(index, tuple(capture_headers))


def jpeg_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise DecodeError("JPEG SOI/EOI markers are missing")
    position = 2
    while position + 1 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in (0x00, 0x01, 0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(data):
            raise DecodeError("truncated JPEG segment length")
        length = int.from_bytes(data[position:position + 2], "big")
        if length < 2 or position + length > len(data):
            raise DecodeError("invalid JPEG segment length")
        if marker in SOF_MARKERS:
            if length < 7:
                raise DecodeError("short JPEG SOF segment")
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            return width, height
        if marker == 0xDA:  # Entropy-coded scan; SOF must precede it.
            break
        position += length
    return None


def _derive_artifact(report: Path, values: dict[str, str], kind: str) -> Path:
    key = f"{kind}_path"
    if key in values:
        return report.parent / Path(values[key]).name
    if kind == "lri":
        return report.with_suffix(".lri")
    stamp = report.stem.removeprefix("RDI_STOCK_")
    return report.with_name(f"IMG_STOCK_{stamp}.jpg")


def _expect_value(
    findings: list[Finding], values: dict[str, str], key: str, expected: str
) -> None:
    actual = values.get(key)
    if actual != expected:
        findings.append(Finding(
            "FAIL", f"report_{key}", f"{key}={actual!r}, expected {expected!r}"
        ))


def _check_recorded_file(
    findings: list[Finding], values: dict[str, str], kind: str, path: Path
) -> None:
    actual_size = path.stat().st_size
    try:
        recorded_size = int(values.get(f"{kind}_size", ""))
    except ValueError:
        findings.append(Finding(
            "FAIL", f"{kind}_size_missing", f"valid {kind}_size is missing from report"
        ))
    else:
        if recorded_size != actual_size:
            findings.append(Finding(
                "FAIL", f"{kind}_size_mismatch",
                f"report={recorded_size}, local={actual_size}"
            ))
    actual_hash = _sha256(path)
    recorded_hash = values.get(f"{kind}_sha256", "").lower()
    if recorded_hash != actual_hash:
        findings.append(Finding(
            "FAIL", f"{kind}_sha256_mismatch",
            f"report={recorded_hash or '<missing>'}, local={actual_hash}"
        ))


def _check_capture_metadata(
    findings: list[Finding], inspection: LriInspection, expected_group: str,
    expected_af: int | None, reported_exposure_ns: int | None,
) -> None:
    if not inspection.capture_headers:
        findings.append(Finding("FAIL", "capture_headers_missing", "no module-bearing LightHeader"))
        return
    modules = inspection.modules
    names = [module.name for module in modules]
    if len(names) != len(set(names)):
        findings.append(Finding(
            "FAIL", "duplicate_modules", f"non-stacked capture contains duplicates: {names}"
        ))
    if expected_group != "any":
        expected = EXPECTED_GROUPS[expected_group]
        actual = frozenset(names)
        if actual != expected:
            findings.append(Finding(
                "FAIL", "module_group_mismatch",
                f"expected {expected_group}={sorted(expected)}, got {sorted(actual)}"
            ))
    focal_lengths = {
        header.focal_length_35mm for header in inspection.capture_headers
        if header.focal_length_35mm is not None
    }
    if len(focal_lengths) != 1:
        findings.append(Finding(
            "FAIL", "focal_length_inconsistent", f"capture headers contain {sorted(focal_lengths)}"
        ))
    elif expected_group == "AB" and next(iter(focal_lengths)) >= 70:
        findings.append(Finding(
            "FAIL", "focal_group_inconsistent", f"AB capture reports {next(iter(focal_lengths))} mm"
        ))
    elif expected_group == "BC" and next(iter(focal_lengths)) < 70:
        findings.append(Finding(
            "FAIL", "focal_group_inconsistent", f"BC capture reports {next(iter(focal_lengths))} mm"
        ))
    af_sources = [header.af_trigger_source for header in inspection.capture_headers]
    if expected_af is not None and any(value != expected_af for value in af_sources):
        findings.append(Finding(
            "FAIL", "af_trigger_mismatch",
            f"expected {AF_TRIGGER_NAMES.get(expected_af, expected_af)}, got {af_sources}"
        ))
    exposures = sorted(
        module.exposure_ns for module in modules
        if module.exposure_ns is not None and module.exposure_ns > 0
    )
    if reported_exposure_ns is not None and exposures:
        median = exposures[len(exposures) // 2]
        relative_error = abs(median - reported_exposure_ns) / reported_exposure_ns
        if relative_error > 0.10:
            findings.append(Finding(
                "FAIL", "reported_exposure_mismatch",
                f"Camera2={reported_exposure_ns} ns, module median={median} ns"
            ))
    for module in modules:
        prefix = f"module_{module.name.lower()}"
        if not module.enabled:
            findings.append(Finding("FAIL", f"{prefix}_disabled", "module is not enabled"))
        if module.exposure_ns is None or module.exposure_ns <= 0:
            findings.append(Finding("FAIL", f"{prefix}_exposure", "exposure is absent or non-positive"))
        if module.analog_gain is None or module.analog_gain <= 0:
            findings.append(Finding("FAIL", f"{prefix}_analog_gain", "analog gain is absent or non-positive"))
        if module.digital_gain is None or module.digital_gain <= 0:
            findings.append(Finding("FAIL", f"{prefix}_digital_gain", "digital gain is absent or non-positive"))
        if module.lens_position is None or module.lens_position <= 0:
            findings.append(Finding("FAIL", f"{prefix}_lens_position", "lens position is absent or zero"))
        if (module.width, module.height) != (4160, 3120):
            findings.append(Finding(
                "FAIL", f"{prefix}_surface_size",
                f"expected 4160x3120, got {module.width}x{module.height}"
            ))
        if module.raw_format != 7:
            findings.append(Finding(
                "FAIL", f"{prefix}_raw_format",
                f"expected RAW_PACKED_10BPP (7), got {module.raw_format}"
            ))


def _compare_reference(
    findings: list[Finding], actual: LriInspection, reference: LriInspection,
) -> None:
    actual_names = frozenset(module.name for module in actual.modules)
    reference_names = frozenset(module.name for module in reference.modules)
    if actual_names != reference_names:
        findings.append(Finding(
            "WARN", "reference_module_difference",
            f"capture={sorted(actual_names)}, reference={sorted(reference_names)}"
        ))
    actual_headers = len(actual.capture_headers)
    reference_headers = len(reference.capture_headers)
    if actual_headers != reference_headers:
        findings.append(Finding(
            "WARN", "reference_header_count_difference",
            f"capture={actual_headers}, reference={reference_headers}"
        ))


def verify_bundle(
    report: Path, *, lri: Path | None = None, jpeg: Path | None = None,
    expected_group: str = "AB", reference: Path | None = None,
) -> Verification:
    report = report.resolve()
    findings: list[Finding] = []
    if not report.is_file():
        return Verification(
            "FAIL", 2, str(report), None, None, None, None, (), (), (),
            (Finding("FAIL", "report_missing", "report file does not exist"),),
        )
    values = parse_key_values(report.read_text(encoding="utf-8", errors="replace"))
    for key, expected in (
        ("hardware_level", "1"),
        ("active_array", "0 0 4160 3120"),
        ("selected_raw_size", "3840x2160"),
        ("session_surface_count", "3"),
        ("session_configured", "yes"),
        ("metering", "PASS"),
        ("focus_type", "6"),
        ("focus", "PASS"),
        ("pipeline", "ARMED"),
        ("stacked_capture", "false"),
        ("still_started", "yes"),
        ("still_capture_result", "PASS"),
        ("still_af_state", "4"),
        ("raw_image_available", "yes"),
        ("jpeg_image_available", "yes"),
        ("result", "PASS"),
        ("reason", "focused_same_session_lri_and_jpeg_saved"),
        ("camera_closed", "yes"),
    ):
        _expect_value(findings, values, key, expected)
    for key, expected in (
        ("requested_lens_focal_length", "2.8"),
        ("requested_zoom_factor", "1.0"),
    ):
        if key in values:
            _expect_value(findings, values, key, expected)
    try:
        reported_exposure_ns = int(values.get("still_exposure_time_ns", ""))
        reported_sensitivity = int(values.get("still_sensitivity", ""))
        if reported_exposure_ns <= 0 or reported_sensitivity <= 0:
            raise ValueError
    except ValueError:
        reported_exposure_ns = None
        findings.append(Finding(
            "FAIL", "reported_still_exposure", "still exposure/sensitivity is absent or invalid"
        ))
    stacked_result = values.get("vendor_stacked_capture_fw")
    if stacked_result is not None:
        if stacked_result.startswith("unavailable_") or stacked_result == "null":
            findings.append(Finding(
                "WARN", "stacked_result_unavailable", stacked_result
            ))
        elif stacked_result != "0":
            findings.append(Finding(
                "FAIL", "stacked_result_mismatch",
                f"non-stacked request returned firmware state {stacked_result}"
            ))

    lri = (lri.resolve() if lri is not None else _derive_artifact(report, values, "lri"))
    jpeg = (jpeg.resolve() if jpeg is not None else _derive_artifact(report, values, "jpeg"))
    inspection: LriInspection | None = None
    lri_blocks: int | None = None
    if not lri.is_file():
        findings.append(Finding("FAIL", "lri_missing", str(lri)))
    else:
        _check_recorded_file(findings, values, "lri", lri)
        if lri.stat().st_size < MIN_LRI_BYTES:
            findings.append(Finding("FAIL", "lri_too_small", str(lri.stat().st_size)))
        lri_blocks, framing_error = validate_lri_container(lri)
        if framing_error is not None:
            findings.append(Finding("FAIL", "lri_framing", framing_error))
        else:
            try:
                inspection = inspect_lri(lri)
                _check_capture_metadata(
                    findings, inspection, expected_group,
                    int(values["focus_type"]) if values.get("focus_type", "").isdigit() else None,
                    reported_exposure_ns,
                )
            except (DecodeError, OSError, struct.error) as error:
                findings.append(Finding("FAIL", "lri_metadata_decode", str(error)))

    if not jpeg.is_file():
        findings.append(Finding("FAIL", "jpeg_missing", str(jpeg)))
    else:
        _check_recorded_file(findings, values, "jpeg", jpeg)
        if jpeg.stat().st_size < 1024:
            findings.append(Finding("FAIL", "jpeg_too_small", str(jpeg.stat().st_size)))
        try:
            dimensions = jpeg_dimensions(jpeg)
            expected_size = SIZE_PATTERN.fullmatch(values.get("selected_jpeg_size", ""))
            if dimensions is None:
                findings.append(Finding("FAIL", "jpeg_dimensions_missing", "no SOF marker"))
            elif expected_size is None:
                findings.append(Finding(
                    "FAIL", "jpeg_report_dimensions_missing", "selected_jpeg_size is invalid"
                ))
            else:
                expected_dimensions = tuple(map(int, expected_size.groups()))
                if dimensions != expected_dimensions:
                    findings.append(Finding(
                        "FAIL", "jpeg_dimensions_mismatch",
                        f"report={expected_dimensions}, JPEG={dimensions}"
                    ))
        except (DecodeError, OSError) as error:
            findings.append(Finding("FAIL", "jpeg_structure", str(error)))

    if reference is not None and inspection is not None:
        reference = reference.resolve()
        try:
            reference_blocks, reference_error = validate_lri_container(reference)
            if reference_error is not None:
                raise DecodeError(reference_error)
            if reference_blocks == 0:
                raise DecodeError("reference has no blocks")
            _compare_reference(findings, inspection, inspect_lri(reference))
        except (DecodeError, OSError, struct.error) as error:
            findings.append(Finding("FAIL", "reference_decode", str(error)))

    failed = any(finding.level == "FAIL" for finding in findings)
    warned = any(finding.level == "WARN" for finding in findings)
    verdict = "FAIL" if failed else ("PASS_WITH_WARNINGS" if warned else "PASS")
    focal_lengths = tuple(sorted({
        header.focal_length_35mm for header in inspection.capture_headers
        if header.focal_length_35mm is not None
    })) if inspection is not None else ()
    af_sources = tuple(
        header.af_trigger_source for header in inspection.capture_headers
        if header.af_trigger_source is not None
    ) if inspection is not None else ()
    module_names = tuple(module.name for module in inspection.modules) if inspection else ()
    return Verification(
        verdict=verdict,
        exit_code=2 if failed else 0,
        report=str(report),
        lri=str(lri),
        jpeg=str(jpeg),
        lri_blocks=lri_blocks,
        capture_headers=len(inspection.capture_headers) if inspection else None,
        focal_lengths_35mm=focal_lengths,
        af_trigger_sources=af_sources,
        modules=module_names,
        findings=tuple(findings),
    )


def _human_report(result: Verification) -> Iterable[str]:
    yield f"verdict={result.verdict}"
    yield f"report={result.report}"
    yield f"lri={result.lri}"
    yield f"jpeg={result.jpeg}"
    yield f"lri_blocks={result.lri_blocks}"
    yield f"capture_headers={result.capture_headers}"
    yield f"focal_lengths_35mm={list(result.focal_lengths_35mm)}"
    yield "af_trigger_sources=" + str([
        f"{AF_TRIGGER_NAMES.get(value, 'UNKNOWN')}({value})"
        for value in result.af_trigger_sources
    ])
    yield f"modules={list(result.modules)}"
    yield "pixel_validation=NOT_PERFORMED"
    for finding in result.findings:
        yield f"{finding.level}:{finding.code}: {finding.message}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="RDI_STOCK_*.txt report")
    parser.add_argument("--lri", type=Path, help="local LRI path; otherwise derive from report")
    parser.add_argument("--jpeg", type=Path, help="local JPEG path; otherwise derive from report")
    parser.add_argument(
        "--expect-group", choices=("AB", "BC", "all16", "A1", "any"),
        default="AB", help="expected unique module set (default: AB for this fixed 2.8 mm app)",
    )
    parser.add_argument("--reference", type=Path, help="optional decoded LRI comparison")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = verify_bundle(
        args.report, lri=args.lri, jpeg=args.jpeg,
        expected_group=args.expect_group, reference=args.reference,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print("\n".join(_human_report(result)))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
