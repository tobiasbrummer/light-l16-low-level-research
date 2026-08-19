from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "device" / "dark_frame_series_hostless_supervisor.sh"
CHILD = ROOT / "device" / "dark_frame_series_once.sh"
PRIVATE_DIR = "/data/data/io.github.tobiasbrummer.lightl16.darkframe/files"


def test_supervisor_has_valid_shell_syntax() -> None:
    shell = shutil.which("sh")
    assert shell is not None
    subprocess.run([shell, "-n", str(SUPERVISOR)], check=True)


def test_supervisor_accepts_no_arguments_and_one_fixed_child_path() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "/data/local/tmp/light_l16_dark_frame_series_once.sh" in text
    assert "DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE" in text
    assert "unexpected_supervisor_path" in text
    assert "L16_HOSTLESS_DARK_FRAME_SERIES_SUPERVISOR_ONCE_V1" in text


def test_supervisor_pins_child_and_async_shim_sizes_and_hashes() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    child_size = CHILD.stat().st_size
    child_sha1 = hashlib.sha1(CHILD.read_bytes()).hexdigest()
    assert f"EXPECTED_CHILD_SIZE={child_size}" in text
    assert f"EXPECTED_CHILD_SHA1={child_sha1}" in text
    assert "EXPECTED_ASYNC_SHIM_SIZE=9080" in text
    assert (
        "EXPECTED_ASYNC_SHIM_SHA1=0b93dc17a2c4219943293d96b7edda39be61613d"
        in text
    )


def test_supervisor_verifies_payloads_before_and_after_staging() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    for reason in (
        "packaged_child_missing",
        "unexpected_packaged_child_size",
        "unexpected_packaged_child_hash",
        "staged_child_size_mismatch",
        "staged_child_hash_mismatch",
        "packaged_async_shim_missing",
        "unexpected_packaged_async_shim_size",
        "unexpected_packaged_async_shim_hash",
        "staged_async_shim_size_mismatch",
        "staged_async_shim_hash_mismatch",
    ):
        assert reason in text


def test_supervisor_bounds_the_child_at_forty_minutes() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "/system/bin/timeout -k 10s 2400s /system/bin/sh" in text


def test_supervisor_accepts_pass_and_partial_but_not_silent_failure() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "PASS|PARTIAL" in text
    assert "SUPERVISOR_STATUS=PARTIAL" in text
    assert "child_series_produced_no_verified_capture" in text
    assert "child_series_failed" in text


def test_supervisor_reboots_after_any_possible_camera_attempt() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "REBOOT_REQUIRED=yes" in text
    assert "/system/bin/reboot" in text
    assert "normal_reboot_after_dark_frame_series" in text
    assert "no_reboot_after_proven_preflight_failure" in text


def test_supervisor_mirrors_the_child_manifest_before_rebooting() -> None:
    """The mirror runs in the main flow; the reboot only in the EXIT handler.

    Comparing raw text positions would be wrong here: finish() is defined near
    the top of the file but runs last, after the main flow has already written
    the manifest into the app-readable result.
    """
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "series.manifest" in text
    assert text.index("series.manifest") < text.index("SUPERVISOR_STATUS=PASS")

    start = text.index("finish() {")
    end = text.index("\n}\n", start)
    finish_body = text[start:end]
    assert "/system/bin/reboot" in finish_body
    assert "series.manifest" not in finish_body
    assert "trap finish EXIT" in text


def test_supervisor_clears_the_runner_before_any_other_action() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert text.index("clear_runner") < text.index("IDENTITY=$(id)")
    assert PRIVATE_DIR in text


def test_supervisor_never_passes_a_camera_parameter_to_the_child() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    # The child takes no arguments at all; the plan is compiled into it.
    assert '/system/bin/sh "$CHILD"\n' in text
    for forbidden in ("-e ", "-g ", "MASK", "EXPOSURE_ARGS"):
        assert forbidden not in text


def extract_verdict(result_fields: dict[str, str], manifest: str | None) -> str:
    """Run the real verdict block against a synthetic child result file.

    Whether a stopped series is reported as PARTIAL rather than quietly as PASS
    is the supervisor's central claim, and no string assertion can establish it.
    This harness keeps the verdict block verbatim and supplies only the child
    result it reads.
    """
    text = SUPERVISOR.read_text(encoding="utf-8")

    def function(name: str) -> str:
        start = text.index(f"{name}() {{")
        end = text.index("\n}\n", start) + len("\n}\n")
        return text[start:end]

    verdict = text[text.index("RESULT_MODE=$(result_field mode)"):]
    verdict = verdict.replace("exit 0\n", "")

    lines = "\n".join(f"{key}={value}" for key, value in result_fields.items())
    setup = [
        "CHILD_RESULT=$(mktemp)",
        f"cat > \"$CHILD_RESULT\" <<'RESULT'\n{lines}\nRESULT",
        "EXPECTED_MODE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE",
        "EXPECTED_CAPTURES_REQUESTED=24",
        'WORKDIR_STUB=$(mktemp -d)',
        "CHILD_FINAL_STATUS=" + result_fields.get("final_status", "PASS"),
        "fail() {\n    printf 'failure=%s\\n' \"$1\"\n    exit 1\n}",
        function("result_field"),
        function("valid_decimal"),
    ]
    if manifest is not None:
        setup.append(f'printf \'{manifest}\' > "$WORKDIR_STUB/series.manifest"')
    setup.append(verdict)
    setup.append('printf "supervisor_status=%s\\n" "$SUPERVISOR_STATUS"')
    setup.append('printf "supervisor_reason=%s\\n" "$SUPERVISOR_REASON"')
    return "\n".join(setup)


def run_verdict(
    completed: str = "24",
    final_status: str = "PASS",
    cleanup_ok: str = "yes",
    manifest: str | None = "1 10000 1.0 260000000 abc\\n",
) -> dict[str, str]:
    fields = {
        "mode": "DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE",
        "captures_requested": "24",
        "captures_completed": completed,
        "series_aborted_at": "none",
        "series_abort_reason": "none",
        "async_shim_status": "exercised_per_capture",
        "cleanup_ok": cleanup_ok,
        "manual_control_after": "0x0",
        "lcc_process_after": "no",
        "settled_camera_clients": "none",
        "media_after": "running",
        "lightsvr_after": "running",
        "workdir": "/data/local/tmp/light_l16_dark_frame_series_run.4242",
        "final_status": final_status,
    }
    script = extract_verdict(fields, manifest)
    # The verdict validates the device workdir path, so point the manifest
    # lookup at the local stub directory instead.
    script = script.replace(
        '"$WORKDIR/series.manifest"', '"$WORKDIR_STUB/series.manifest"'
    )
    # The device calls sed/tail/cat through toybox at an absolute path that
    # does not exist on the host.  Dropping the prefix resolves them from PATH
    # and leaves the verdict logic itself untouched; the absolute paths are
    # covered by the static assertions above.
    script = script.replace("/system/bin/toybox ", "")
    shell = shutil.which("sh")
    assert shell is not None
    result = subprocess.run(
        [shell, "-c", script], capture_output=True, text=True
    )
    values = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    values["_returncode"] = str(result.returncode)
    values["_stdout"] = result.stdout
    return values


def test_verdict_reports_pass_only_for_a_complete_series() -> None:
    values = run_verdict(completed="24", final_status="PASS")
    assert values["_returncode"] == "0"
    assert values["supervisor_status"] == "PASS"


def test_verdict_reports_partial_for_a_stopped_series() -> None:
    values = run_verdict(completed="19", final_status="PARTIAL")
    assert values["_returncode"] == "0"
    assert values["supervisor_status"] == "PARTIAL"


def test_verdict_refuses_a_pass_that_did_not_complete_every_capture() -> None:
    """A child claiming PASS with 20 of 24 frames must not be reported as PASS."""
    values = run_verdict(completed="20", final_status="PASS")
    assert values["supervisor_status"] == "PARTIAL"


def test_verdict_fails_when_no_capture_was_verified() -> None:
    values = run_verdict(completed="0", final_status="FAIL")
    assert values["_returncode"] == "1"
    assert "failure=child_series_produced_no_verified_capture" in values["_stdout"]


def test_verdict_fails_on_a_dirty_cleanup() -> None:
    values = run_verdict(cleanup_ok="no")
    assert values["_returncode"] == "1"
    assert "failure=child_cleanup_not_verified" in values["_stdout"]


def test_verdict_refuses_more_completed_captures_than_requested() -> None:
    values = run_verdict(completed="25")
    assert values["_returncode"] == "1"
    assert "failure=more_captures_completed_than_requested" in values["_stdout"]


def test_verdict_mirrors_the_manifest_into_the_result() -> None:
    values = run_verdict(manifest="7 1250000 3.75 259999993 deadbeef\\n")
    assert "manifest_begin" in values["_stdout"]
    assert "7 1250000 3.75 259999993 deadbeef" in values["_stdout"]
    assert "manifest_end" in values["_stdout"]


def test_verdict_survives_a_missing_manifest() -> None:
    values = run_verdict(manifest=None)
    assert values["_returncode"] == "0"
    assert "manifest_absent" in values["_stdout"]
    assert values["supervisor_status"] == "PASS"
