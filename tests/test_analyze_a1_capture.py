from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from tools.analyze_a1_capture import (
    FAILED_VERDICT,
    INCOMPLETE_VERDICT,
    PASS_VERDICT,
    PREFLIGHT_VERDICT,
    WRAPPER_FAILED_VERDICT,
    analyze_capture,
    main,
    new_lines,
    validate_lri_container,
)


PASS_RESULT_BASE = """\
mode=A1_FIXED_CAPTURE_ONCE
capture_attempted=yes
lcc_exit_status=0
manual_control_after=manual control mode is 0x0
lcc_process_after=no
cleanup_ok=yes
normal_reboot_required=yes
workdir=/data/local/tmp/light_l16_a1_capture_run.1234
final_reason=lcc_exit_zero_lri_captured_cleanup_verified_content_not_validated
final_status=PASS
"""


def _valid_lri_bytes() -> bytes:
    raw = b"raw-pixels"
    message = b"protobuf"
    message_offset = 32 + len(raw)
    block_length = message_offset + len(message)
    return (
        struct.pack("<4sQQIB7x", b"LELR", block_length, message_offset, len(message), 0)
        + raw
        + message
    )


def _write_bundle(root: Path, *, lcc: str | None = None) -> Path:
    root.mkdir()
    pixels = root / "pixels"
    pixels.mkdir()
    lri_name = "RDI_20260809_123456_789.lri"
    lri_data = _valid_lri_bytes()
    (pixels / lri_name).write_bytes(lri_data)
    result = (
        PASS_RESULT_BASE
        + "lri_output_count=1\n"
        + f"lri_output_path=/sdcard/DCIM/camera/{lri_name}\n"
        + f"lri_output_size={len(lri_data)}\n"
        + f"lri_output_sha1={hashlib.sha1(lri_data).hexdigest()}\n"
    )
    (root / "result.txt").write_text(result, encoding="utf-8")
    device = root / "device"
    device.mkdir()
    (device / "lcc.txt").write_text(
        lcc
        if lcc is not None
        else "Open camera pipeline\nStart Capture\nClosed camera pipeline, 1\n",
        encoding="utf-8",
    )
    (device / "dmesg.before.txt").write_text("old line\n", encoding="utf-8")
    (device / "dmesg.after.txt").write_text(
        "old line\nbenign new line\n", encoding="utf-8"
    )
    (device / "logcat.before.txt").write_text("old log\n", encoding="utf-8")
    (device / "logcat.after.txt").write_text("old log\n", encoding="utf-8")
    (device / "state.after.txt").write_text(
        "manual_control=manual control mode is 0x0\nmedia=running\nlightsvr=running\n",
        encoding="utf-8",
    )
    (device / "camera.after_immediate.txt").write_text(
        "Active Camera Clients:\n[]\nAllowed users:\n0\n", encoding="utf-8"
    )
    return root


def test_complete_bundle_passes_lri_framing_but_keeps_content_boundary(
    tmp_path: Path,
) -> None:
    analysis = analyze_capture(_write_bundle(tmp_path / "capture"))
    assert analysis.verdict == PASS_VERDICT
    assert analysis.exit_code == 0
    assert analysis.pixel_validation == (
        "lri_transfer_and_container_framing_valid_protobuf_and_pixels_unverified"
    )
    assert analysis.post_reboot_validation == "not_in_capture_bundle"


def test_preflight_stop_is_distinct_from_capture_failure(tmp_path: Path) -> None:
    root = tmp_path / "capture"
    root.mkdir()
    (root / "result.txt").write_text(
        "capture_attempted=no\n"
        "failure=camera_client_present_or_state_unknown\n"
        "final_reason=camera_client_present_or_state_unknown\n"
        "final_status=FAIL\n",
        encoding="utf-8",
    )
    analysis = analyze_capture(root)
    assert analysis.verdict == PREFLIGHT_VERDICT
    assert analysis.exit_code == 2


def test_wrapper_postcondition_failure_wins(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    result = (root / "result.txt").read_text(encoding="utf-8")
    (root / "result.txt").write_text(
        result.replace("cleanup_ok=yes", "cleanup_ok=no").replace(
            "final_status=PASS", "final_status=FAIL"
        ),
        encoding="utf-8",
    )
    analysis = analyze_capture(root)
    assert analysis.verdict == WRAPPER_FAILED_VERDICT
    assert analysis.exit_code == 1


def test_new_mipi_error_fails_even_when_wrapper_returned_pass(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    after = root / "device" / "dmesg.after.txt"
    after.write_text(
        after.read_text(encoding="utf-8") + "MIPI RX[A1]: lane error\n",
        encoding="utf-8",
    )
    analysis = analyze_capture(root)
    assert analysis.verdict == FAILED_VERDICT
    assert any(finding.code == "mipi_rx_error" for finding in analysis.findings)


def test_preexisting_identical_mipi_line_is_subtracted(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    before = root / "device" / "dmesg.before.txt"
    after = root / "device" / "dmesg.after.txt"
    before.write_text("MIPI RX[A1]: historical error\n", encoding="utf-8")
    after.write_text("MIPI RX[A1]: historical error\n", encoding="utf-8")
    analysis = analyze_capture(root)
    assert analysis.verdict == PASS_VERDICT


def test_missing_lcc_success_marker_is_inconclusive(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture", lcc="Open camera pipeline\n")
    analysis = analyze_capture(root)
    assert analysis.verdict == INCOMPLETE_VERDICT
    assert analysis.exit_code == 2


def test_ambiguous_new_camera_error_requires_review(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    after = root / "device" / "logcat.after.txt"
    after.write_text("QCamera reported an error state\n", encoding="utf-8")
    analysis = analyze_capture(root)
    assert analysis.verdict == INCOMPLETE_VERDICT
    assert any(
        finding.code == "camera_stack_error_review" for finding in analysis.findings
    )


def test_zero_error_counter_does_not_downgrade(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    after = root / "device" / "logcat.after.txt"
    after.write_text("light_ccb error count: 0\n", encoding="utf-8")
    assert analyze_capture(root).verdict == PASS_VERDICT


def test_cli_emits_stable_verdict_and_exit_code(tmp_path: Path, capsys) -> None:
    root = _write_bundle(tmp_path / "capture")
    assert main([str(root)]) == 0
    output = capsys.readouterr().out
    assert output.startswith(f"verdict={PASS_VERDICT}\n")
    assert (
        "pixel_validation=lri_transfer_and_container_framing_valid_"
        "protobuf_and_pixels_unverified\n"
    ) in output
    assert "post_reboot_validation=not_in_capture_bundle\n" in output


def test_multiset_delta_handles_non_prefix_overlap() -> None:
    assert new_lines("a\nb\na\n", "b\na\nc\na\nd\n") == ["c", "d"]


def test_missing_reported_lri_is_incomplete(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    next((root / "pixels").glob("*.lri")).unlink()
    analysis = analyze_capture(root)
    assert analysis.verdict == INCOMPLETE_VERDICT
    assert analysis.pixel_validation == "lri_reported_but_not_in_capture_bundle"


def test_invalid_lri_framing_fails_after_matching_transfer_hash(
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "capture")
    lri = next((root / "pixels").glob("*.lri"))
    data = b"NOPE" + lri.read_bytes()[4:]
    lri.write_bytes(data)
    result = (root / "result.txt").read_text(encoding="utf-8")
    result = result.replace(
        next(
            line for line in result.splitlines() if line.startswith("lri_output_sha1=")
        ),
        f"lri_output_sha1={hashlib.sha1(data).hexdigest()}",
    )
    (root / "result.txt").write_text(result, encoding="utf-8")
    analysis = analyze_capture(root)
    assert analysis.verdict == FAILED_VERDICT
    assert analysis.pixel_validation == "lri_container_framing_invalid"


def test_lri_validator_rejects_message_past_block_end(tmp_path: Path) -> None:
    path = tmp_path / "bad.lri"
    path.write_bytes(struct.pack("<4sQQIB7x", b"LELR", 32, 32, 1, 0))
    blocks, error = validate_lri_container(path)
    assert blocks == 0
    assert error == "message extends beyond block 0"
