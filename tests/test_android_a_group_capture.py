from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "a-group-capture"
SOURCE = (
    APP / "src/io/github/tobiasbrummer/lightl16/agroupcapture/MainActivity.java"
)
SUPERVISOR = ROOT / "device" / "a_group_hostless_capture_supervisor.sh"
CHILD = ROOT / "device" / "a1_capture_once.sh"
HOST_ENTRY = ROOT / "host" / "run_a_group_capture_once.sh"
AF_SHIM_SIZE = 13764
AF_SHIM_SHA1 = "67647b71767ab2b68a214fae87578e24eb3433b2"
AF_SHIM_SHA256 = (
    "72d1d05a6966cafbf92b7b5b45b82243d24da1a35a18b734097196357dc59ad6"
)


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def test_app_is_separate_permissionless_fixed_package() -> None:
    manifest = (APP / "AndroidManifest.xml").read_text()
    assert 'package="io.github.tobiasbrummer.lightl16.agroupcapture"' in manifest
    assert 'android:label="L16 A-Gruppe Inline AF"' in manifest
    assert "<uses-permission" not in manifest
    assert 'android:debuggable="false"' in manifest
    source = SOURCE.read_text()
    assert "EditText" not in source
    assert "android.hardware.camera" not in source
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source


def test_child_profile_is_exact_a1_a5_selection() -> None:
    text = CHILD.read_text()
    start = text.index(
        "    /data/local/tmp/light_l16_a_group_inline_af_capture_once.sh)"
    )
    block = text[start:text.index("        ;;", start)]
    for expected in (
        "MODE=A_GROUP_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE",
        "MASK0=3E\n        MASK1=00\n        MASK2=00",
        "modules=A1-A5 asics=1,2",
        "CAPTURE_TIMEOUT_SECONDS=60",
        "MIN_DATA_FREE_KB=524288",
        "ALLOW_CLEAN_NO_REBOOT=no",
        "USE_A1_AF_SHIM=yes",
    ):
        assert expected in block
    assert "USE_ASYNC_SHIM=no" in block


def test_supervisor_only_invokes_group_profile_and_reboots_attempts() -> None:
    text = SUPERVISOR.read_text()
    assert "L16_HOSTLESS_A_GROUP_INLINE_AF_CAPTURE_V1" in text
    assert "A_GROUP_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    assert "CHILD=/data/local/tmp/light_l16_a_group_inline_af_capture_once.sh" in text
    assert "EXPECTED_MODE=A_GROUP_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in text
    assert '/system/bin/timeout -k 10s 120s /system/bin/sh "$CHILD"' in text
    assert text.count('/system/bin/sh "$CHILD"') == 1
    assert "REBOOT_REQUIRED=yes" in text
    assert "/system/bin/reboot" in text
    assert "setprop sys.powerctl reboot" in text
    assert "liblcc_async_writer_shim" not in text


def test_all_pin_layers_match_current_payloads() -> None:
    source = SOURCE.read_text()
    supervisor = SUPERVISOR.read_text()
    build = (APP / "build_debug_apk.sh").read_text()
    supervisor_size = SUPERVISOR.stat().st_size
    supervisor_sha256 = digest(SUPERVISOR, "sha256")
    child_size = CHILD.stat().st_size
    child_sha1 = digest(CHILD, "sha1")
    child_sha256 = digest(CHILD, "sha256")
    assert f"EXPECTED_SUPERVISOR_SIZE={supervisor_size}" in build
    assert f"EXPECTED_SUPERVISOR_SHA256={supervisor_sha256}" in build
    assert f"EXPECTED_SUPERVISOR_SIZE = {supervisor_size}L" in source
    assert supervisor_sha256 in source
    assert f"EXPECTED_CHILD_SIZE={child_size}" in supervisor
    assert f"EXPECTED_CHILD_SHA1={child_sha1}" in supervisor
    assert f"EXPECTED_CHILD_SIZE={child_size}" in build
    assert f"EXPECTED_CHILD_SHA256={child_sha256}" in build
    assert f"EXPECTED_CHILD_SIZE = {child_size}L" in source
    assert child_sha256 in source
    assert f"EXPECTED_AF_SHIM_SIZE={AF_SHIM_SIZE}" in supervisor
    assert f"EXPECTED_AF_SHIM_SHA1={AF_SHIM_SHA1}" in supervisor
    assert f"EXPECTED_AF_SHIM_SIZE={AF_SHIM_SIZE}" in build
    assert AF_SHIM_SHA256 in build
    assert f"EXPECTED_AF_SHIM_SIZE = {AF_SHIM_SIZE}L" in source
    assert AF_SHIM_SHA256 in source


def test_ui_and_report_name_describe_five_module_attempt() -> None:
    source = SOURCE.read_text()
    assert "A1-A5 CENTER-AF + 20 MS AUSLÖSEN" in source
    assert "FOCUSED_LOCKED werden die fünf A-Module" in source
    assert '"light-l16-a-group-inline-af-last-display.txt"' in source
    assert "getExternalFilesDir(null)" in source
    assert "persistDisplayedReport(text)" in source
    assert source.count('setRunnerProperty(TRIGGER, "8")') == 1


def test_build_packages_only_reviewed_group_assets() -> None:
    text = (APP / "build_debug_apk.sh").read_text()
    assert 'SUPERVISOR="$PROJECT_ROOT/device/a_group_hostless_capture_supervisor.sh"' in text
    assert 'CHILD="$PROJECT_ROOT/device/a1_capture_once.sh"' in text
    assert 'AF_SHIM_BUILDER="$PROJECT_ROOT/host/build_lcc_a1_focus_capture_shim.sh"' in text
    assert 'a_group_hostless_capture_supervisor.sh' in text
    assert 'liblcc_a1_focus_capture_shim.so' in text
    assert 'light-l16-a-group-inline-focus-capture-debug.apk' in text


def test_shell_entry_points_parse_and_describe_without_adb() -> None:
    for path in (SUPERVISOR, CHILD, HOST_ENTRY):
        subprocess.run(["sh", "-n", str(path)], check=True)
    result = subprocess.run(
        [str(HOST_ENTRY), "--describe"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "mask: 3E 00 00" in result.stdout
    assert "physical A1-A5 LRI and matching hostless supervisor PASS verified" in result.stdout


def test_docs_do_not_overclaim_physical_group_focus() -> None:
    text = (APP / "README.md").read_text()
    assert "The first camera run on 2026-08-16" in text
    assert "verified at both artifact and supervisor levels" in text
    assert "not proof that every selected module" in text
    assert "exactly `A1,A2,A3,A4,A5`" in text
    assert "plausible nonzero `lens_position`" in text
