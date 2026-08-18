import hashlib
import struct
from pathlib import Path

from tools.verify_stock_capture import inspect_lri, verify_bundle


HEADER = struct.Struct("<4sQQIB7x")


def varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def field_varint(number: int, value: int) -> bytes:
    return varint((number << 3) | 0) + varint(value)


def field_message(number: int, value: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(value)) + value


def field_float(number: int, value: float) -> bytes:
    return varint((number << 3) | 5) + struct.pack("<f", value)


def module_message(camera_id: int, frame_index: int = 0) -> bytes:
    point = field_varint(1, 4160) + field_varint(2, 3120)
    surface = (
        field_message(1, field_varint(1, 0) + field_varint(2, 0))
        + field_message(2, point)
        + field_varint(3, 7)
        + field_varint(4, 5200)
        + field_varint(5, 32)
    )
    return (
        field_varint(2, camera_id)
        + field_varint(3, 1)
        + field_varint(4, 0)
        + field_varint(5, 1000 + camera_id)
        + field_float(7, 1.0)
        + field_varint(8, 2_000_000 + camera_id)
        + field_message(9, surface)
        + field_float(14, 1.0)
        + field_varint(15, frame_index)
    )


def light_header(camera_ids=range(10), af_source: int = 6, focal: int = 28) -> bytes:
    af_info = field_varint(1, 1) + field_varint(2, focal) + field_varint(3, af_source)
    return (
        field_varint(4, focal)
        + b"".join(field_message(12, module_message(camera_id)) for camera_id in camera_ids)
        + field_message(24, af_info)
    )


def lri_block(message: bytes, payload_size: int = 0) -> bytes:
    message_offset = HEADER.size + payload_size
    block_length = message_offset + len(message)
    return (
        HEADER.pack(b"LELR", block_length, message_offset, len(message), 0)
        + bytes(payload_size)
        + message
    )


def jpeg(width: int = 4160, height: int = 3120) -> bytes:
    components = b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    sof_payload = b"\x08" + struct.pack(">HH", height, width) + components
    sof = b"\xff\xc0" + struct.pack(">H", len(sof_payload) + 2) + sof_payload
    return b"\xff\xd8" + sof + bytes(1024) + b"\xff\xd9"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bundle(tmp_path: Path, *, af_source: int = 6, camera_ids=range(10)):
    stamp = "20260814_120000_123"
    report = tmp_path / f"RDI_STOCK_{stamp}.txt"
    lri = tmp_path / f"RDI_STOCK_{stamp}.lri"
    image = tmp_path / f"IMG_STOCK_{stamp}.jpg"
    lri.write_bytes(lri_block(light_header(camera_ids, af_source), 1024 * 1024))
    image.write_bytes(jpeg())
    report.write_text(
        "\n".join((
            "pipeline=RUNNING",
            "hardware_level=1",
            "active_array=0 0 4160 3120",
            "selected_raw_size=3840x2160",
            "selected_jpeg_size=4160x3120",
            "session_surface_count=3",
            "session_configured=yes",
            "metering=PASS",
            "focus_type=6",
            "focus=PASS",
            "pipeline=ARMED",
            "stacked_capture=false",
            "still_started=yes",
            "still_capture_result=PASS",
            "still_af_state=4",
            "still_exposure_time_ns=2000005",
            "still_sensitivity=100",
            "raw_image_available=yes",
            "jpeg_image_available=yes",
            f"lri_path=/sdcard/DCIM/camera/{lri.name}",
            f"lri_size={lri.stat().st_size}",
            f"lri_sha256={sha256(lri)}",
            f"jpeg_path=/sdcard/DCIM/camera/{image.name}",
            f"jpeg_size={image.stat().st_size}",
            f"jpeg_sha256={sha256(image)}",
            "result=PASS",
            "reason=focused_same_session_lri_and_jpeg_saved",
            "camera_closed=yes",
            "",
        )),
        encoding="utf-8",
    )
    return report, lri, image


def test_valid_ab_bundle_passes_and_decodes_capture_metadata(tmp_path: Path):
    report, lri, _ = write_bundle(tmp_path)

    result = verify_bundle(report)
    inspection = inspect_lri(lri)

    assert result.verdict == "PASS"
    assert result.exit_code == 0
    assert result.lri_blocks == 1
    assert result.capture_headers == 1
    assert result.focal_lengths_35mm == (28,)
    assert result.af_trigger_sources == (6,)
    assert set(result.modules) == {
        "A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"
    }
    assert inspection.modules[0].width == 4160
    assert inspection.modules[0].height == 3120
    assert inspection.modules[0].raw_format == 7


def test_report_hash_mismatch_fails(tmp_path: Path):
    report, _, _ = write_bundle(tmp_path)
    report.write_text(
        report.read_text().replace("lri_sha256=", "lri_sha256=bad"),
        encoding="utf-8",
    )

    result = verify_bundle(report)

    assert result.verdict == "FAIL"
    assert any(finding.code == "lri_sha256_mismatch" for finding in result.findings)


def test_af_source_and_module_group_must_match_fixed_profile(tmp_path: Path):
    report, _, _ = write_bundle(tmp_path, af_source=0, camera_ids=range(5, 16))

    result = verify_bundle(report)

    assert result.verdict == "FAIL"
    codes = {finding.code for finding in result.findings}
    assert "af_trigger_mismatch" in codes
    assert "module_group_mismatch" in codes


def test_bad_lri_framing_is_reported_without_metadata_claim(tmp_path: Path):
    report, lri, _ = write_bundle(tmp_path)
    data = bytearray(lri.read_bytes())
    data[0:4] = b"NOPE"
    lri.write_bytes(data)
    report.write_text(
        report.read_text()
        .replace(next(line for line in report.read_text().splitlines()
                      if line.startswith("lri_sha256=")), f"lri_sha256={sha256(lri)}"),
        encoding="utf-8",
    )

    result = verify_bundle(report)

    assert result.verdict == "FAIL"
    assert any(finding.code == "lri_framing" for finding in result.findings)
    assert result.capture_headers is None


def test_firmware_stacked_result_must_match_non_stacked_request(tmp_path: Path):
    report, _, _ = write_bundle(tmp_path)
    report.write_text(
        report.read_text() + "vendor_stacked_capture_fw=1\n",
        encoding="utf-8",
    )

    result = verify_bundle(report)

    assert result.verdict == "FAIL"
    assert any(finding.code == "stacked_result_mismatch" for finding in result.findings)
