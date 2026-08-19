from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "android" / "root-runner-probe"
SOURCE = (
    PROBE
    / "src/io/github/tobiasbrummer/lightl16/runnerprobe/MainActivity.java"
)


def test_manifest_requests_no_permissions() -> None:
    manifest = (PROBE / "AndroidManifest.xml").read_text()
    assert "<uses-permission" not in manifest
    assert 'android:allowBackup="false"' in manifest
    assert 'android:debuggable="true"' in manifest


def test_runner_values_are_fixed_and_short() -> None:
    source = SOURCE.read_text()
    assert 'RUNNER_PROGRAM = "/system/bin/sh"' in source
    match = re.search(r'PAYLOAD_PATH = PRIVATE_DIR \+ "([^"]+)"', source)
    assert match is not None
    private_dir = "/data/data/io.github.tobiasbrummer.lightl16.runnerprobe/files"
    assert len(private_dir + match.group(1)) <= 91
    assert 'setRunnerProperty(TRIGGER, "8")' in source
    assert source.count('setRunnerProperty(TRIGGER, "8")') == 1


def test_only_the_two_android_user_zero_private_aliases_are_accepted() -> None:
    source = SOURCE.read_text()
    assert 'PRIVATE_DIR =\n        "/data/data/' in source
    assert 'USER_ZERO_PRIVATE_DIR =\n        "/data/user/0/' in source
    assert "!PRIVATE_DIR.equals(privateDirectory)" in source
    assert "!USER_ZERO_PRIVATE_DIR.equals(privateDirectory)" in source


def test_probe_checks_exact_target_and_vendor_script() -> None:
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
        'EXPECTED_FIHOP_STATE = "stopped"',
    ):
        assert expected in source


def test_payload_clears_runner_before_identity_and_is_one_use() -> None:
    source = SOURCE.read_text()
    payload_start = source.index('private static final String PAYLOAD =')
    payload_end = source.index('private TextView output;', payload_start)
    payload = source[payload_start:payload_end]
    assert payload.index('+ "rm -f') < payload.index('+ "clear_runner\\n"')
    assert payload.index('+ "clear_runner\\n"') < payload.index('+ "  id\\n"')
    for number in range(1, 6):
        assert f'setprop persist.sys.fihop{number} \\"\\"' in payload
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source


def test_app_precreates_result_and_polls_for_content() -> None:
    source = SOURCE.read_text()
    assert "writePrivateFile(result, new byte[0])" in source
    assert "result.length() > 0L" in source
    assert "validPayloadResult(resultText)" in source
    assert 'firstLineWithPrefix(resultText, "probe_error=")' in source


def test_probe_waits_for_runner_to_settle_and_disables_repeat_button() -> None:
    source = SOURCE.read_text()
    assert "waitForRunnerStoppedAndNeutral()" in source
    assert "SETTLE_TIMEOUT_MS = 3000L" in source
    assert "if (running || attempted)" in source
    assert 'runButton.setText("TEST BEENDET")' in source


def test_empty_service_state_is_allowed_only_before_first_trigger() -> None:
    source = SOURCE.read_text()
    assert "runnerIdleBeforeTrigger(serviceState)" in source
    assert "serviceState.isEmpty() || EXPECTED_FIHOP_STATE.equals(serviceState)" in source
    assert "EXPECTED_FIHOP_STATE.equals(serviceState)" in source
    assert "waitForRunnerStoppedAndNeutral()" in source
    assert "if (triggerAttempted)" in source


def test_refusal_continues_through_common_final_state_reporting() -> None:
    source = SOURCE.read_text()
    assert "throw refused(report" in source
    assert "return refused(report" not in source
    assert "catch (ProbeRefusedException ignored)" in source
    assert "return report.toString();" in source


def test_partial_private_file_creation_is_cleaned() -> None:
    source = SOURCE.read_text()
    assert "privateFilesTouched = true;" in source
    assert source.index("privateFilesTouched = true;") < source.index(
        "writePrivateFile(payload, payloadBytes)"
    )


def test_ambiguous_trigger_preserves_payload_until_runner_is_neutral() -> None:
    source = SOURCE.read_text()
    assert "if (!triggerAttempted || runnerFinalNeutral)" in source
    assert '"PRESERVED_CHECK_REQUIRED"' in source


def test_setter_rejects_every_unexpected_value() -> None:
    source = SOURCE.read_text()
    for expected in (
        "refusing non-runner property write",
        "refusing unexpected runner trigger",
        "refusing unexpected runner program",
        "refusing unexpected runner payload",
        "refusing nonempty extra runner argument",
    ):
        assert expected in source


def test_probe_has_no_camera_network_or_external_storage_api() -> None:
    combined = "\n".join(
        [(PROBE / "AndroidManifest.xml").read_text(), SOURCE.read_text()]
    )
    forbidden = (
        "android.permission.CAMERA",
        "android.permission.INTERNET",
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
        "android.hardware.Camera",
        "android.hardware.camera2",
        "java.net.",
        "/dev/block",
        "/sys/class/light_ccb",
        "/sdcard",
        "Runtime.getRuntime",
        "ProcessBuilder",
    )
    for value in forbidden:
        assert value not in combined


def test_final_report_exposes_both_cleanup_states() -> None:
    source = SOURCE.read_text()
    assert 'append("runner_final=")' in source
    assert 'append("files_final=")' in source
    assert '"NEUTRAL" : "CHECK_REQUIRED"' in source
    assert '"CLEAN" : "PRESERVED_CHECK_REQUIRED"' in source
