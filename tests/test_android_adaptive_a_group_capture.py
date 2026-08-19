from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "adaptive-a-group-capture"
PACKAGE = APP / "src/io/github/tobiasbrummer/lightl16/adaptiveagroupcapture"
METER = PACKAGE / "MainActivity.java"
CAPTURE = PACKAGE / "CaptureActivity.java"
MATH = PACKAGE / "HdrMath.java"
SUPERVISOR = ROOT / "device" / "a_group_adaptive_hostless_capture_supervisor.sh"
CHILD = ROOT / "device" / "a_group_adaptive_capture_once.sh"


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def test_app_has_private_capture_activity_and_no_parameter_editor() -> None:
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert 'package="io.github.tobiasbrummer.lightl16.adaptiveagroupcapture"' in manifest
    assert manifest.count("uses-permission") == 1
    assert "android.permission.CAMERA" in manifest
    assert 'android:name=".CaptureActivity"' in manifest
    assert 'android:exported="false"' in manifest
    combined = METER.read_text() + CAPTURE.read_text()
    assert "EditText" not in combined
    assert "Runtime.getRuntime" not in combined
    assert "ProcessBuilder" not in combined


def test_meter_gates_root_launch_on_resolved_stable_bounded_plan() -> None:
    source = METER.read_text()
    for required in (
        "highlightResolved",
        "shadowStable && highlightStable && highlightResolved",
        "rootValuesBoundedAndOrdered(capturePlan)",
        "validRootCapturePlan(values)",
        "ROOT_MIN_EXPOSURE_NS = 10000L",
        "PROVEN_PILOT_MAX_EXPOSURE_NS",
        "CAPTURE_PLAN_WINDOW_MS = 60000L",
        "highlight_estimator_percentile=p99.9",
        "highlightStats.p999 < highlightStats.whiteCode",
        "MIN_USEFUL_PILOT_SPAN_EV = 0.5",
        "pilot_hdr_ladder_collapsed_by_20ms_cap",
        "root_capture_plan_status=ARMED_NOT_YET_EXECUTED",
        "camera_closed=yes",
        "3. A1-A5 MIT DIESEN WERTEN AUFNEHMEN",
    ):
        assert required in source
    assert source.index("closeCameraResources();") < source.index(
        "root_capture_plan_status=ARMED_NOT_YET_EXECUTED"
    )


def test_spent_installation_recovers_private_supervisor_result_without_root() -> None:
    source = METER.read_text()
    assert "showSpentCaptureResult()" in source
    assert 'privateFile("r.txt")' in source
    assert "readBoundedAscii(result)" in source
    assert "MAX_RECOVERY_RESULT_SIZE = 16384L" in source
    assert "probe=RECOVERY_DISPLAY_ONLY" in source
    assert "camera_touched_by_recovery=no" in source
    assert "root_or_lcc_invoked_by_recovery=no" in source
    assert "persistRecoveryCaptureReport(text)" in source


def test_plan_handoff_is_canonical_private_and_not_an_intent_extra() -> None:
    meter = METER.read_text()
    capture = CAPTURE.read_text()
    version = "L16_ADAPTIVE_A_GROUP_PLAN_V1"
    launch_arm = "L16_ADAPTIVE_A_GROUP_CAPTURE_UI_LAUNCH_V1"
    assert version in meter and version in capture and version in SUPERVISOR.read_text()
    assert launch_arm in meter and launch_arm in capture
    assert 'PLAN_NAME = "p.txt"' in meter
    assert 'PLAN_NAME = "p.txt"' in capture
    assert "putExtra" not in meter
    assert "getIntent" not in capture
    assert "readAndValidatePlan" in capture
    assert 'text.equals(rebuilt + "\\n")' in capture
    assert "consumeUiLaunchArm" in capture


def test_supervisor_revalidates_plan_and_passes_five_quoted_values_once() -> None:
    text = SUPERVISOR.read_text()
    for required in (
        "APP_PLAN=$APP_DIR/p.txt",
        "app_plan_must_be_one_line",
        "app_plan_not_canonical",
        "app_plan_exposure_below_10000ns",
        "app_plan_exposure_above_20000000ns",
        "app_plan_a2_must_equal_a1",
        "app_plan_a5_below_a4",
        "app_plan_hdr_ladder_collapsed",
        "EXPECTED_EXPOSURE_COUNT=5",
        "EXPECTED_EXPOSURE_ORDER=A1,A2,A3,A4,A5",
        "EXPECTED_MODE=A_GROUP_ADAPTIVE_INLINE_CENTER_AF_CAPTURE_ONCE",
    ):
        assert required in text
    invocation = (
        '/system/bin/timeout -k 10s 120s /system/bin/sh "$CHILD" \\\n'
        '    "$EXPOSURE_A1" "$EXPOSURE_A2" "$EXPOSURE_A3" '
        '"$EXPOSURE_A4" "$EXPOSURE_A5"'
    )
    assert invocation in text
    assert text.count('/system/bin/sh "$CHILD"') == 1
    assert "eval " not in text


def test_supervisor_mirrors_complete_manifest_before_delayed_reboot() -> None:
    text = SUPERVISOR.read_text()
    external = (
        "/sdcard/Android/data/io.github.tobiasbrummer.lightl16."
        "adaptiveagroupcapture/files/"
        "light-l16-adaptive-a-group-capture-last-display.txt"
    )
    assert f"APP_EXTERNAL_RESULT={external}" in text
    complete = text.index("printf 'supervisor_complete=%s")
    copy = text.index('cp "$APP_RESULT" "$APP_EXTERNAL_RESULT"')
    reboot_delay = text.index('/system/bin/sleep 5')
    assert complete < copy < reboot_delay
    assert "Reporting must never change capture or reboot policy" in text


def test_child_has_one_adaptive_profile_and_independent_bounds() -> None:
    text = CHILD.read_text()
    for required in (
        'DYNAMIC_ARGUMENT_COUNT=$#',
        'EXPOSURE_COUNT=5',
        'EXPOSURE_ORDER=A1,A2,A3,A4,A5',
        'MODE=A_GROUP_ADAPTIVE_INLINE_CENTER_AF_CAPTURE_ONCE',
        'MASK0=3E\nMASK1=00\nMASK2=00',
        'USE_A1_AF_SHIM=yes',
        'dynamic_exposure_below_10000ns',
        'dynamic_exposure_above_20000000ns',
        'provisional_a2_must_equal_highlight_safe_a1',
        'adaptive_plan_validation=PASS',
        'adaptive_hdr_ladder_collapsed',
    ):
        assert required in text
    assert "case \"$0\" in" not in text
    assert "ALL16" not in text
    assert "eval " not in text


def test_all_payload_pin_layers_match() -> None:
    java = CAPTURE.read_text()
    supervisor = SUPERVISOR.read_text()
    build = (APP / "build_debug_apk.sh").read_text()
    supervisor_size = SUPERVISOR.stat().st_size
    supervisor_sha256 = digest(SUPERVISOR, "sha256")
    child_size = CHILD.stat().st_size
    child_sha1 = digest(CHILD, "sha1")
    child_sha256 = digest(CHILD, "sha256")
    assert f"EXPECTED_SUPERVISOR_SIZE={supervisor_size}" in build
    assert f"EXPECTED_SUPERVISOR_SHA256={supervisor_sha256}" in build
    assert f"EXPECTED_SUPERVISOR_SIZE = {supervisor_size}L" in java
    assert supervisor_sha256 in java
    assert f"EXPECTED_CHILD_SIZE={child_size}" in supervisor
    assert f"EXPECTED_CHILD_SHA1={child_sha1}" in supervisor
    assert f"EXPECTED_CHILD_SIZE={child_size}" in build
    assert f"EXPECTED_CHILD_SHA256={child_sha256}" in build
    assert f"EXPECTED_CHILD_SIZE = {child_size}L" in java
    assert child_sha256 in java


def test_new_shell_payloads_parse() -> None:
    for path in (SUPERVISOR, CHILD, APP / "build_debug_apk.sh"):
        subprocess.run(["sh", "-n", str(path)], check=True)


def test_original_fixed_group_payload_is_not_reused_or_modified_by_build() -> None:
    build = (APP / "build_debug_apk.sh").read_text()
    assert "a_group_adaptive_hostless_capture_supervisor.sh" in build
    assert "a_group_adaptive_capture_once.sh" in build
    assert 'device/a_group_hostless_capture_supervisor.sh' not in build
    assert 'device/a1_capture_once.sh' not in build
