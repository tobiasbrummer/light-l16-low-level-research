from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "a1-capture"
SOURCE = (
    APP / "src/io/github/tobiasbrummer/lightl16/a1capture/MainActivity.java"
)
SUPERVISOR = ROOT / "device" / "a1_hostless_capture_supervisor.sh"
CHILD = ROOT / "device" / "a1_capture_once.sh"
AF_SHIM_BUILDER = ROOT / "host" / "build_lcc_a1_focus_capture_shim.sh"
EXPECTED_AF_SHIM_SIZE = 13764
EXPECTED_AF_SHIM_SHA1 = "67647b71767ab2b68a214fae87578e24eb3433b2"
EXPECTED_AF_SHIM_SHA256 = (
    "72d1d05a6966cafbf92b7b5b45b82243d24da1a35a18b734097196357dc59ad6"
)


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def test_manifest_requests_no_permissions_and_disables_debug_access() -> None:
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert "<uses-permission" not in manifest
    assert "<uses-feature" not in manifest
    assert 'android:allowBackup="false"' in manifest
    assert 'android:debuggable="false"' in manifest


def test_app_uses_the_same_session_inline_focus_profile_without_camera2() -> None:
    source = SOURCE.read_text()
    supervisor = SUPERVISOR.read_text()
    assert "MeterFocusController" not in source
    assert "TextureView" not in source
    assert "android.hardware.camera2" not in source
    assert "A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in supervisor
    assert "A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE" in supervisor
    assert "camera3_af_state_focused_locked_inline_hal_session" in supervisor
    assert "child_a1_af_shim_not_verified" in supervisor


def test_build_generates_and_packages_only_the_reviewed_fixed_payloads() -> None:
    build = (APP / "build_debug_apk.sh").read_text()
    assert 'SUPERVISOR="$PROJECT_ROOT/device/a1_hostless_capture_supervisor.sh"' in build
    assert 'CHILD="$PROJECT_ROOT/device/a1_capture_once.sh"' in build
    assert 'AF_SHIM_BUILDER="$PROJECT_ROOT/host/build_lcc_a1_focus_capture_shim.sh"' in build
    assert 'cp "$SUPERVISOR" "$TEMP_DIR/assets/a1_hostless_capture_supervisor.sh"' in build
    assert 'cp "$CHILD" "$TEMP_DIR/assets/a1_capture_once.sh"' in build
    assert 'AF_SHIM="$TEMP_DIR/assets/liblcc_a1_focus_capture_shim.so"' in build
    assert '"$AF_SHIM_BUILDER" "$AF_SHIM"' in build
    assert 'sh -n "$FILE"' in build


def test_all_three_layers_pin_current_payload_sizes_and_hashes() -> None:
    source = SOURCE.read_text()
    supervisor = SUPERVISOR.read_text()
    build = (APP / "build_debug_apk.sh").read_text()

    supervisor_size = SUPERVISOR.stat().st_size
    supervisor_sha256 = digest(SUPERVISOR, "sha256")
    child_size = CHILD.stat().st_size
    child_sha256 = digest(CHILD, "sha256")
    child_sha1 = digest(CHILD, "sha1")

    assert f"EXPECTED_SUPERVISOR_SIZE={supervisor_size}" in build
    assert f"EXPECTED_SUPERVISOR_SHA256={supervisor_sha256}" in build
    assert f"EXPECTED_SUPERVISOR_SIZE = {supervisor_size}L" in source
    assert supervisor_sha256 in source
    assert f"EXPECTED_CHILD_SIZE={child_size}" in build
    assert f"EXPECTED_CHILD_SHA256={child_sha256}" in build
    assert f"EXPECTED_CHILD_SIZE = {child_size}L" in source
    assert child_sha256 in source
    assert f"EXPECTED_CHILD_SIZE={child_size}" in supervisor
    assert f"EXPECTED_CHILD_SHA1={child_sha1}" in supervisor
    assert f"EXPECTED_AF_SHIM_SIZE={EXPECTED_AF_SHIM_SIZE}" in build
    assert f"EXPECTED_AF_SHIM_SHA256={EXPECTED_AF_SHIM_SHA256}" in build
    assert f"EXPECTED_AF_SHIM_SIZE = {EXPECTED_AF_SHIM_SIZE}L" in source
    assert EXPECTED_AF_SHIM_SHA256 in source
    assert f"EXPECTED_AF_SHIM_SIZE={EXPECTED_AF_SHIM_SIZE}" in supervisor
    assert f"EXPECTED_AF_SHIM_SHA1={EXPECTED_AF_SHIM_SHA1}" in supervisor


def test_both_device_scripts_have_valid_shell_syntax() -> None:
    for path in (SUPERVISOR, CHILD):
        subprocess.run(["sh", "-n", str(path)], check=True)


def test_runner_command_is_fixed_short_and_triggered_once() -> None:
    source = SOURCE.read_text()
    assert 'RUNNER_PROGRAM = "/system/bin/sh"' in source
    assert 'SUPERVISOR_PATH = PRIVATE_DIR + "/s.sh"' in source
    private_dir = "/data/data/io.github.tobiasbrummer.lightl16.a1capture/files"
    assert len(private_dir + "/s.sh") <= 91
    assert source.count('setRunnerProperty(TRIGGER, "8")') == 1
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source


def test_only_fixed_runner_properties_and_values_can_be_written() -> None:
    source = SOURCE.read_text()
    for expected in (
        "refusing non-runner property write",
        "refusing unexpected runner trigger",
        "refusing unexpected runner program",
        "refusing unexpected runner payload",
        "refusing nonempty extra runner argument",
    ):
        assert expected in source
    assert '!("0".equals(value) || "8".equals(value))' in source
    assert "SUPERVISOR_PATH.equals(value)" in source


def test_app_checks_exact_target_runner_and_assets_before_arming() -> None:
    source = SOURCE.read_text()
    for expected in (
        "00WW_1_351",
        "L16",
        "LFC_0002_FIH01",
        "3.18.20-perf-g32d1d1c",
        'EXPECTED_BUILD_TYPE = "user"',
        'EXPECTED_DEBUGGABLE = "0"',
        'EXPECTED_SELINUX_ENFORCE = "0"',
        "6550cce118492e43c5285d469f7dc383e4d6c14c7cf766de1c82cb57fbaebe4f",
        "EXPECTED_FIHOP_SIZE = 1649L",
        "runnerNeutral()",
        "inspectAsset(SUPERVISOR_ASSET)",
        "inspectAsset(CHILD_ASSET)",
        "inspectAsset(AF_SHIM_ASSET)",
    ):
        assert expected in source


def test_ui_requires_read_only_preflight_then_time_limited_second_tap() -> None:
    source = SOURCE.read_text()
    assert 'preflightButton.setText("1. VORPRÜFUNG & SCHARFSCHALTEN")' in source
    assert 'captureButton.setText("2. A1 CENTER-AF + 20 MS AUSLÖSEN")' in source
    assert "captureButton.setEnabled(false)" in source
    assert "runReadOnlyPreflight()" in source
    assert "ARM_WINDOW_MS = 60000L" in source
    assert "uiArmDeadline = SystemClock.elapsedRealtime() + ARM_WINDOW_MS" in source
    assert "SystemClock.elapsedRealtime() > uiArmDeadline" in source


def test_every_display_update_is_mirrored_to_permissionless_external_text() -> None:
    source = SOURCE.read_text()
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert 'DISPLAY_REPORT_NAME =\n        "light-l16-a1-inline-af-last-display.txt"' in source
    assert "getExternalFilesDir(null)" in source
    assert "persistDisplayedReport(text)" in source
    assert "StandardCharsets.UTF_8" in source
    assert source.count("output.setText(") == 1
    assert "The diagnostic copy must never change capture or recovery policy" in source
    assert "android.permission.WRITE_EXTERNAL_STORAGE" not in manifest


def test_installation_is_spent_before_the_single_trigger() -> None:
    source = SOURCE.read_text()
    spent_write = source.index("writePrivateFile(spent,")
    spent_verify = source.index("SPENT_VALUE.equals(readFirstLine(spent))")
    trigger = source.index('setRunnerProperty(TRIGGER, "8")')
    assert spent_write < spent_verify < trigger
    assert "installation_already_spent" in source
    assert 'SPENT_NAME = "spent"' in source
    assert "adb install -r" in (APP / "README.md").read_text()


def test_supervisor_clears_runner_then_consumes_two_fixed_inline_arm_tokens() -> None:
    text = SUPERVISOR.read_text()
    first_clear = text.index("# Clear the persistent runner")
    arm_check = text.index('[ -f "$APP_ARM" ]')
    identity = text.index("IDENTITY=$(id)")
    assert first_clear < arm_check < identity
    assert "L16_HOSTLESS_A1_INLINE_AF_CAPTURE_SUPERVISOR_ONCE_V1" in text
    assert "A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    assert 'rm -f "$APP_ARM"' in text
    assert 'rm -f "$CHILD_ARM" "$CHILD" "$AF_SHIM"' in text
    for number in range(1, 6):
        assert f'setprop persist.sys.fihop{number} ""' in text


def test_supervisor_only_launches_fixed_inline_focus_a1_child_under_timeout() -> None:
    text = SUPERVISOR.read_text()
    assert "CHILD=/data/local/tmp/light_l16_a1_inline_af_capture_once.sh" in text
    assert "AF_SHIM=/data/local/tmp/liblcc_a1_focus_capture_shim.so" in text
    assert "EXPECTED_MODE=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in text
    assert "EXPECTED_EXPOSURE_COUNT=1" in text
    assert "EXPECTED_EXPOSURE_ORDER=common_for_selected_modules" in text
    assert "EXPECTED_EXPOSURE_PLAN=selected:20000000" in text
    assert '/system/bin/timeout -k 10s 120s /system/bin/sh "$CHILD"' in text
    assert text.count('/system/bin/sh "$CHILD"') == 1
    assert "liblcc_a1_focus_capture_shim" in text
    assert "liblcc_async_writer_shim" not in text
    assert "prog_app_p2" not in text
    assert "/data/local/tmp/light_l16_a1_inline_af_capture_run.*" in text
    assert "/data/local/tmp/light_l16_a1_capture_run.*" not in text


def test_device_runtime_uses_available_sha1_not_missing_sha256_applet() -> None:
    text = SUPERVISOR.read_text()
    assert "/system/bin/toybox sha1sum" in text
    assert "/system/bin/toybox sha256sum" not in text


def test_supervisor_reboots_possible_attempt_but_not_proven_preflight_fail() -> None:
    text = SUPERVISOR.read_text()
    child_started = text.index("CHILD_STARTED=yes")
    reboot_required = text.index("REBOOT_REQUIRED=yes", child_started)
    invoke = text.index('/system/bin/timeout -k 10s 120s /system/bin/sh "$CHILD"')
    assert child_started < reboot_required < invoke
    assert '[ "$CHILD_FINAL_STATUS" = "FAIL" ]' in text
    assert '[ "$CAPTURE_ATTEMPTED" = "no" ]' in text
    assert '[ "$CHILD_REBOOT_REQUIRED" = "no" ]' in text
    assert "REBOOT_REQUIRED=no" in text
    assert "no_reboot_after_proven_preflight_failure" in text
    assert "normal_reboot_after_hostless_capture_success" in text
    assert "/system/bin/reboot" in text
    assert "setprop sys.powerctl reboot" in text


def test_pass_requires_complete_cleanup_and_lri_manifest() -> None:
    text = SUPERVISOR.read_text()
    for expected in (
        '[ "$LCC_EXIT_STATUS" = "0" ]',
        '[ "$CLEANUP_OK" = "yes" ]',
        '[ "$LCC_PROCESS_AFTER" = "no" ]',
        '[ "$SETTLED_CAMERA_CLIENTS" = "none" ]',
        '[ "$MEDIA_AFTER" = "running" ]',
        '[ "$LIGHTSVR_AFTER" = "running" ]',
        '[ "$LRI_COUNT" = "1" ]',
        '[ "$AUTOFOCUS_ATTEMPTED" = "yes" ]',
        '[ "$AUTOFOCUS_EXIT_STATUS" = "0" ]',
        '[ "$A1_AF_SHIM_STATUS" = "verified" ]',
        'valid_lri_path "$LRI_PATH"',
        'valid_decimal "$LRI_SIZE"',
        'valid_sha1 "$LRI_SHA1"',
    ):
        assert expected in text
    success = text.index("SUPERVISOR_STATUS=PASS", text.index("# Unlike the adb wrapper"))
    assert success > text.index('valid_sha1 "$LRI_SHA1"')


def test_app_exposes_no_command_camera_network_or_partition_api() -> None:
    combined = "\n".join(
        [(APP / "AndroidManifest.xml").read_text(), SOURCE.read_text()]
    )
    forbidden = (
        "android.permission.INTERNET",
        "android.permission.CAMERA",
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
        "android.hardware.Camera",
        "android.hardware.camera2",
        "java.net.",
        "EditText",
        "getIntent()",
        "getStringExtra",
        "/dev/block",
        "/sys/class/light_ccb",
        "Runtime.getRuntime",
        "ProcessBuilder",
    )
    for value in forbidden:
        assert value not in combined


def test_app_parser_rejects_duplicate_fields_and_validates_lri_shape() -> None:
    source = SOURCE.read_text()
    field_parser = source[source.index("private static String field"):]
    assert "boolean seen = false" in field_parser
    assert "if (seen)" in field_parser
    assert "seen = true" in field_parser
    assert 'return "";' in field_parser
    assert "[0-9a-f]{40}" in source
    assert "validDecimalAtLeast" in source
    assert "RDI_[0-9]{8}_[0-9]{6}_[0-9]{3}" in source


def test_docs_state_real_capture_reboot_and_unvalidated_content() -> None:
    text = (APP / "README.md").read_text().lower()
    for expected in (
        "module `a1` only",
        "20,000,000 ns",
        "same-session",
        "normal android reboot after every possible camera attempt",
        "do not yet prove image",
        "silently retry",
    ):
        assert expected in text
