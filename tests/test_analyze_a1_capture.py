from __future__ import annotations

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
)


PASS_RESULT = """\
mode=A1_FIXED_CAPTURE_ONCE
capture_attempted=yes
lcc_exit_status=0
manual_control_after=manual control mode is 0x0
lcc_process_after=no
cleanup_ok=yes
normal_reboot_required=yes
workdir=/data/local/tmp/light_l16_a1_capture_run.1234
final_reason=lcc_exit_zero_cleanup_verified_capture_not_yet_validated
final_status=PASS
"""


def _write_bundle(root: Path, *, lcc: str | None = None) -> Path:
    root.mkdir()
    (root / "result.txt").write_text(PASS_RESULT, encoding="utf-8")
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
        "manual_control=manual control mode is 0x0\n"
        "media=running\n"
        "lightsvr=running\n",
        encoding="utf-8",
    )
    (device / "camera.after_immediate.txt").write_text(
        "Active Camera Clients:\n[]\nAllowed users:\n0\n", encoding="utf-8"
    )
    return root


def test_complete_control_path_pass_keeps_pixel_boundary(tmp_path: Path) -> None:
    analysis = analyze_capture(_write_bundle(tmp_path / "capture"))
    assert analysis.verdict == PASS_VERDICT
    assert analysis.exit_code == 0
    assert analysis.pixel_validation == "not_available_no_pixel_artifact_requested"
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
        finding.code == "camera_stack_error_review"
        for finding in analysis.findings
    )


def test_zero_error_counter_does_not_downgrade(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "capture")
    after = root / "device" / "logcat.after.txt"
    after.write_text("light_ccb error count: 0\n", encoding="utf-8")
    assert analyze_capture(root).verdict == PASS_VERDICT


def test_cli_emits_stable_verdict_and_exit_code(
    tmp_path: Path, capsys
) -> None:
    root = _write_bundle(tmp_path / "capture")
    assert main([str(root)]) == 0
    output = capsys.readouterr().out
    assert output.startswith(f"verdict={PASS_VERDICT}\n")
    assert "pixel_validation=not_available_no_pixel_artifact_requested\n" in output
    assert "post_reboot_validation=not_in_capture_bundle\n" in output


def test_multiset_delta_handles_non_prefix_overlap() -> None:
    assert new_lines("a\nb\na\n", "b\na\nc\na\nd\n") == ["c", "d"]
