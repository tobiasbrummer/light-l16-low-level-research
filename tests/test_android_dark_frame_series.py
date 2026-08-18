from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "dark-frame-series"
PACKAGE_DIR = "src/io/github/tobiasbrummer/lightl16/darkframe"
SOURCE = APP / PACKAGE_DIR / "MainActivity.java"
SUPERVISOR = ROOT / "device" / "dark_frame_series_hostless_supervisor.sh"
CHILD = ROOT / "device" / "dark_frame_series_once.sh"
PRIVATE_DIR = "/data/data/io.github.tobiasbrummer.lightl16.darkframe/files"


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def test_manifest_requests_only_the_camera_permission_it_needs() -> None:
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert 'android:allowBackup="false"' in manifest
    assert 'android:debuggable="false"' in manifest
    assert 'package="io.github.tobiasbrummer.lightl16.darkframe"' in manifest
    assert manifest.count("<uses-permission") == 1
    assert "android.permission.CAMERA" in manifest
    assert "WRITE_EXTERNAL_STORAGE" not in manifest
    assert 'android:label="L16 Dark Frame Series"' in manifest


def test_app_pins_supervisor_child_and_shim_sizes_and_hashes() -> None:
    source = SOURCE.read_text()
    assert f"EXPECTED_SUPERVISOR_SIZE = {SUPERVISOR.stat().st_size}L" in source
    assert digest(SUPERVISOR, "sha256") in source
    assert f"EXPECTED_CHILD_SIZE = {CHILD.stat().st_size}L" in source
    assert digest(CHILD, "sha256") in source
    assert "EXPECTED_ASYNC_SHIM_SIZE = 8904L" in source
    assert (
        "bbc6865374dfd7beb72d4a1cc30fad81414c6915052eb22e35c5205574ae9cb5"
        in source
    )


def test_app_uses_only_the_fixed_runner_trigger_once() -> None:
    source = SOURCE.read_text()
    assert 'RUNNER_PROGRAM = "/system/bin/sh"' in source
    assert PRIVATE_DIR in source
    # The vendor runner truncates its argument properties; keep the path short.
    assert len(PRIVATE_DIR + "/s.sh") <= 91
    assert source.count('setRunnerProperty(TRIGGER, "8")') == 1
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source


def test_app_locks_itself_to_one_series_per_installation() -> None:
    source = SOURCE.read_text()
    assert "SPENT_NAME" in source
    assert "SPENT_VALUE" in source
    assert "installation_already_spent" in source
    # The lock is written before the only trigger, so an ambiguous delivery
    # cannot be retried by accident.
    assert source.index("spent_marker_round_trip_failed") < source.index(
        'setRunnerProperty(TRIGGER, "8")'
    )


def test_app_requires_preflight_and_darkness_before_arming() -> None:
    source = SOURCE.read_text()
    assert "onDarknessCheckResult" in source
    assert "darknessConfirmed" in source
    assert "preflightPassed" in source
    assert "refusing capture without preflight" in source
    assert "refusing capture without darkness check" in source


def test_app_reports_partial_series_distinctly_from_pass_and_failure() -> None:
    source = SOURCE.read_text()
    assert "validPartialResult" in source
    assert "PASS_MANIFEST_REBOOT_REQUESTED" in source
    assert "PARTIAL_MANIFEST_REBOOT_REQUESTED" in source
    assert "captures_completed" in source
    # A PARTIAL supervisor result must still terminate the poll loop.
    assert '"PARTIAL".equals(value)' in source


def test_app_expects_a_poll_window_covering_the_whole_series() -> None:
    source = SOURCE.read_text()
    # 24 captures at 60 s plus the supervisor's own margin; the single-capture
    # app polled for 135 s, which would time out long before this series ends.
    assert "POLL_TIMEOUT_MS = 2460000L" in source
    assert "MAX_RESULT_SIZE = 65536L" in source


def test_app_stages_the_async_shim_not_the_focus_shim() -> None:
    source = SOURCE.read_text()
    assert "liblcc_async_writer_shim.so" in source
    assert "ASYNC_SHIM_PATH" in source
    assert "liblcc_a1_focus_capture_shim.so" not in source
    assert "AF_SHIM" not in source


def test_app_mirrors_its_report_without_extra_storage_permission() -> None:
    source = SOURCE.read_text()
    assert "light-l16-dark-frame-series-last-display.txt" in source
    assert "getExternalFilesDir" in source


def test_app_does_not_reference_autofocus() -> None:
    source = SOURCE.read_text()
    for forbidden in ("autofocus", "AF_STATE", "focused_locked", "lri_output_count"):
        assert forbidden not in source


DARKNESS = APP / PACKAGE_DIR / "DarknessCheck.java"


def test_darkness_check_forces_the_worst_case_for_darkness() -> None:
    source = DARKNESS.read_text()
    assert "ImageFormat.YUV_420_888" in source
    assert "SENSOR_INFO_SENSITIVITY_RANGE" in source
    assert "CONTROL_AE_MODE_OFF" in source
    assert "SENSOR_SENSITIVITY" in source
    assert "SENSOR_EXPOSURE_TIME" in source
    # Auto-exposure would adapt to darkness and hide a light leak; the check
    # must instead amplify as hard as the device allows.
    assert "CONTROL_AE_MODE_ON" not in source
    assert "sensitivityRange.getUpper()" in source


def test_darkness_check_uses_a_fixed_threshold_and_frame_count() -> None:
    source = DARKNESS.read_text()
    assert "DARK_MEAN_MAX_LUMA = 24" in source
    assert "DARK_P999_MAX_LUMA = 64" in source
    assert "REQUIRED_FRAMES = 8" in source
    assert "PROBE_EXPOSURE_NS = 100000000L" in source


def test_darkness_check_reports_measured_values_next_to_the_limits() -> None:
    source = DARKNESS.read_text()
    for key in ("mean_luma=", "p999_luma=", "mean_luma_limit=", "p999_luma_limit="):
        assert key in source


def test_darkness_check_always_closes_the_camera_before_reporting() -> None:
    source = DARKNESS.read_text()
    finish = source[source.index("private void finish("):]
    assert "close();" in finish
    assert "finally" in finish
    assert finish.index("close();") < finish.index("target.onResult(")
    assert "dark && isClosed()" in finish


def test_darkness_check_reports_exactly_once_and_bounds_itself() -> None:
    source = DARKNESS.read_text()
    assert "if (finished) {" in source
    assert "finished = true;" in source
    assert "OVERALL_TIMEOUT_MS" in source
    assert "measurement_timeout_after_" in source


def test_darkness_check_exposes_a_static_closed_state() -> None:
    source = DARKNESS.read_text()
    assert "public static boolean isClosed()" in source
    assert "cameraOpen = false;" in source


def test_main_activity_closes_camera_before_arming_the_runner() -> None:
    source = SOURCE.read_text()
    assert "DarknessCheck" in source
    assert source.index("darknessCheck.close()") < source.index(
        'setRunnerProperty(TRIGGER, "8")'
    )
    assert "camera2_still_open_before_trigger" in source


def test_main_activity_releases_the_camera_when_paused() -> None:
    source = SOURCE.read_text()
    assert "protected void onPause()" in source
    pause = source[source.index("protected void onPause()"):]
    assert "darknessCheck.close()" in pause[:400]
    # A cover removed while the activity was in the background must not stay
    # confirmed.
    assert "darknessConfirmed = false" in pause[:400]


def test_main_activity_requests_the_camera_permission_at_runtime() -> None:
    source = SOURCE.read_text()
    assert "checkSelfPermission(Manifest.permission.CAMERA)" in source
    assert "onRequestPermissionsResult" in source


BUILD = APP / "build_debug_apk.sh"
EXPECTED_ASYNC_SHIM_SIZE = 8904
EXPECTED_ASYNC_SHIM_SHA1 = "150e53a736624010dc7fb741490ea8dca7afbfb8"
EXPECTED_ASYNC_SHIM_SHA256 = (
    "bbc6865374dfd7beb72d4a1cc30fad81414c6915052eb22e35c5205574ae9cb5"
)


def test_build_packages_only_the_three_reviewed_payloads() -> None:
    build = BUILD.read_text()
    assert (
        'SUPERVISOR="$PROJECT_ROOT/device/dark_frame_series_hostless_supervisor.sh"'
        in build
    )
    assert 'CHILD="$PROJECT_ROOT/device/dark_frame_series_once.sh"' in build
    assert (
        'ASYNC_SHIM_BUILDER="$PROJECT_ROOT/host/build_lcc_async_shim.sh"' in build
    )
    assert 'sh -n "$FILE"' in build
    assert "apksigner" in build


def test_build_refuses_changed_payloads() -> None:
    build = BUILD.read_text()
    assert f"EXPECTED_SUPERVISOR_SIZE={SUPERVISOR.stat().st_size}" in build
    assert f"EXPECTED_SUPERVISOR_SHA256={digest(SUPERVISOR, 'sha256')}" in build
    assert f"EXPECTED_CHILD_SIZE={CHILD.stat().st_size}" in build
    assert f"EXPECTED_CHILD_SHA256={digest(CHILD, 'sha256')}" in build
    assert f"EXPECTED_ASYNC_SHIM_SIZE={EXPECTED_ASYNC_SHIM_SIZE}" in build
    assert f"EXPECTED_ASYNC_SHIM_SHA256={EXPECTED_ASYNC_SHIM_SHA256}" in build
    assert "refusing changed payload" in build
    assert "refusing unexpected generated async shim" in build


def test_build_compiles_both_java_sources() -> None:
    build = BUILD.read_text()
    assert "MainActivity.java" in build
    assert "DarknessCheck.java" in build


def test_build_prefers_the_reviewed_lld_over_an_unrelated_one() -> None:
    """The reviewed shim identity comes from LLD 20.1.8.

    A different LLD produces a different byte count, so the build must look for
    the versioned Ubuntu paths before falling back to whatever toolchain
    happens to ship one.
    """
    build = BUILD.read_text()
    assert "/usr/lib/llvm-20/bin/ld.lld" in build
    assert "ld.lld-20" in build
    assert build.index("llvm-20") < build.index("rustup")


def test_all_three_layers_pin_the_same_values() -> None:
    build = BUILD.read_text()
    source = SOURCE.read_text()
    supervisor = SUPERVISOR.read_text()
    child_size = CHILD.stat().st_size
    child_sha1 = digest(CHILD, "sha1")
    child_sha256 = digest(CHILD, "sha256")

    assert f"EXPECTED_CHILD_SIZE={child_size}" in build
    assert f"EXPECTED_CHILD_SIZE = {child_size}L" in source
    assert f"EXPECTED_CHILD_SIZE={child_size}" in supervisor
    assert child_sha256 in build
    assert child_sha256 in source
    assert f"EXPECTED_CHILD_SHA1={child_sha1}" in supervisor
    assert f"EXPECTED_ASYNC_SHIM_SHA1={EXPECTED_ASYNC_SHIM_SHA1}" in supervisor
    assert EXPECTED_ASYNC_SHIM_SHA256 in build
    assert EXPECTED_ASYNC_SHIM_SHA256 in source
