from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_known_build_hashes_have_expected_shape() -> None:
    manifest = json.loads(
        (ROOT / "artifacts" / "known-builds.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    artifacts = manifest["targets"][0]["artifacts"]
    assert artifacts
    for identity in artifacts.values():
        assert re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
        if "sha1" in identity:
            assert re.fullmatch(r"[0-9a-f]{40}", identity["sha1"])
        if "size" in identity:
            assert isinstance(identity["size"], int)
            assert identity["size"] > 0
        if "gnu_build_id" in identity:
            build_id = identity["gnu_build_id"]
            assert re.fullmatch(r"[0-9a-f]+", build_id)
            assert 16 <= len(build_id) <= 64
            assert len(build_id) % 2 == 0


def test_root_probe_is_syntax_valid_and_bounded() -> None:
    payload = ROOT / "device" / "root_probe_payload.sh"
    text = payload.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    if shell is not None:
        subprocess.run([shell, "-n", str(payload)], check=True)

    assert text.index("setprop persist.sys.fihop 0") < text.index("id\n")
    for argument in range(1, 6):
        assert f'setprop persist.sys.fihop{argument} ""' in text
    for forbidden in ("/dev/block", "reboot", "mount ", "camera_enable", "eeprom"):
        assert forbidden not in text


def test_a1_dry_run_is_syntax_valid_and_cannot_capture() -> None:
    payload = ROOT / "device" / "a1_capture_dry_run.sh"
    text = payload.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    if shell is not None:
        subprocess.run([shell, "-n", str(payload)], check=True)

    assert text.index("setprop persist.sys.fihop 0") < text.index("IDENTITY=$(id)")
    assert "02 00 00 11 F1 00" in text
    planned = next(line for line in text.splitlines() if "planned_argv=" in line)
    assert (
        "planned_argv=<lcc-copy> -m 0 -s 0 -f 1 02 00 00 11 F1 00 "
        "-R 4160,3120 -e 2609592 -g 1.0"
    ) in planned
    assert " -F " not in planned
    assert "<reference-" not in planned
    assert "ACTIVE_CLIENTS=$(" in text
    assert '[ "$ACTIVE_CLIENTS" = "[]" ]' in text
    assert "capture_executed=no" in text
    for forbidden in (
        "--execute",
        "prog_app_p2",
        "start fwupgrade",
        "echo 1 >",
        "reboot",
        "/system/bin/timeout -",
    ):
        assert forbidden not in text


def test_fixed_capture_payload_profiles_are_armed_and_cleanup_bounded() -> None:
    payload = ROOT / "device" / "a1_capture_once.sh"
    text = payload.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    if shell is not None:
        subprocess.run([shell, "-n", str(payload)], check=True)

    control_doc = (ROOT / "docs" / "lcc-control.md").read_text(encoding="utf-8")
    # The count is spelled out so adding a profile forces the doc to be read,
    # not just the byte size bumped.
    assert (
        f"current {len(payload.read_bytes()):,}-byte thirteen-profile payload"
        in control_doc
    )
    assert hashlib.sha1(payload.read_bytes()).hexdigest() in control_doc

    clear = "setprop persist.sys.fihop 0"
    armed = '[ "$ARMED" = "$ARM_VALUE" ]'
    attempted = "CAPTURE_ATTEMPTED=yes"
    assert text.index(clear) < text.index(': > "$OUT"')
    assert text.index(armed) < text.index(attempted)
    assert 'rm -f "$ARM_FILE"' in text
    assert "/data/local/tmp/light_l16_a1_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_a1_center_af_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_a1_inline_af_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_a_group_inline_af_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_a1_async_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_all16_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_all16_async_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_all16_hdr_async_capture_once.sh" in text
    assert "/data/local/tmp/light_l16_timeout_probe_once.sh" in text
    assert "/data/local/tmp/light_l16_timeout_probe_6s_once.sh" in text
    assert "/data/local/tmp/light_l16_mmap_probe_6s_once.sh" in text
    assert "/data/local/tmp/light_l16_bare_6s_once.sh" in text
    assert "/data/local/tmp/light_l16_timeout_probe_29s_once.sh" in text

    def profile_block(path: str) -> str:
        start = text.index(f"    {path})")
        end = text.index("        ;;", start)
        return text[start:end]

    a1_profile = profile_block("/data/local/tmp/light_l16_a1_capture_once.sh")
    a1_center_af_profile = profile_block(
        "/data/local/tmp/light_l16_a1_center_af_capture_once.sh"
    )
    a1_async_profile = profile_block(
        "/data/local/tmp/light_l16_a1_async_capture_once.sh"
    )
    a1_inline_af_profile = profile_block(
        "/data/local/tmp/light_l16_a1_inline_af_capture_once.sh"
    )
    a_group_inline_af_profile = profile_block(
        "/data/local/tmp/light_l16_a_group_inline_af_capture_once.sh"
    )
    all16_profile = profile_block(
        "/data/local/tmp/light_l16_all16_capture_once.sh"
    )
    all16_async_profile = profile_block(
        "/data/local/tmp/light_l16_all16_async_capture_once.sh"
    )
    all16_hdr_async_profile = profile_block(
        "/data/local/tmp/light_l16_all16_hdr_async_capture_once.sh"
    )
    timeout_probe_profile = profile_block(
        "/data/local/tmp/light_l16_timeout_probe_once.sh"
    )
    timeout_probe_6s_profile = profile_block(
        "/data/local/tmp/light_l16_timeout_probe_6s_once.sh"
    )
    mmap_probe_6s_profile = profile_block(
        "/data/local/tmp/light_l16_mmap_probe_6s_once.sh"
    )
    bare_6s_profile = profile_block(
        "/data/local/tmp/light_l16_bare_6s_once.sh"
    )
    timeout_probe_29s_profile = profile_block(
        "/data/local/tmp/light_l16_timeout_probe_29s_once.sh"
    )
    for profile in (a1_profile, a1_center_af_profile, a1_async_profile):
        assert "MASK0=02\n        MASK1=00\n        MASK2=00" in profile
        assert "CAPTURE_TIMEOUT_SECONDS=30" in profile
        assert "MIN_DATA_FREE_KB=262144" in profile
    assert "MASK0=02\n        MASK1=00\n        MASK2=00" in a1_inline_af_profile
    assert "CAPTURE_TIMEOUT_SECONDS=45" in a1_inline_af_profile
    assert "MIN_DATA_FREE_KB=262144" in a1_inline_af_profile
    assert "USE_A1_AF_SHIM=yes" in a1_inline_af_profile
    assert "MASK0=3E\n        MASK1=00\n        MASK2=00" in a_group_inline_af_profile
    assert "CAPTURE_TIMEOUT_SECONDS=60" in a_group_inline_af_profile
    assert "MIN_DATA_FREE_KB=524288" in a_group_inline_af_profile
    assert "ALLOW_CLEAN_NO_REBOOT=no" in a_group_inline_af_profile
    assert "USE_A1_AF_SHIM=yes" in a_group_inline_af_profile
    for profile in (all16_profile, all16_async_profile, all16_hdr_async_profile):
        assert "MASK0=FE\n        MASK1=FF\n        MASK2=01" in profile
        assert "CAPTURE_TIMEOUT_SECONDS=60" in profile
        assert "MIN_DATA_FREE_KB=1048576" in profile
        assert "ALLOW_CLEAN_NO_REBOOT=no" in profile
    assert "USE_ASYNC_SHIM=no" in a1_profile
    assert "RUN_AUTOFOCUS=yes" in a1_center_af_profile
    assert "RUN_FACTORY_ASIC_RESET=yes" in a1_center_af_profile
    assert "AUTOFOCUS_X=1040" in text
    assert "AUTOFOCUS_Y=780" in text
    assert "AUTOFOCUS_WIDTH=2080" in text
    assert "AUTOFOCUS_HEIGHT=1560" in text
    assert '"$LCC_COPY" -m 0 -s 0 -V -C -H -f 0' in text
    assert "autofocus_interrupt_not_received_once" in text
    assert "AUTOFOCUS_RESPONSE=interrupt_not_received" in text
    assert "autofocus_response_path_already_exists" in text
    assert "USE_ASYNC_SHIM=yes" in a1_async_profile
    assert "USE_ASYNC_SHIM=no" in all16_profile
    assert "USE_ASYNC_SHIM=yes" in all16_async_profile
    assert "USE_ASYNC_SHIM=yes" in all16_hdr_async_profile
    # The probe raises the completion budget rather than any capture
    # parameter: all sixteen modules, one exposure, gain unchanged.
    # Both probes differ from each other in the exposure alone.
    for profile in (timeout_probe_profile, timeout_probe_6s_profile):
        assert "MASK0=FE\n        MASK1=FF\n        MASK2=01" in profile
        # One combined preload does both jobs, so the plain async shim is off.
        assert "USE_ASYNC_SHIM=no" in profile
        assert "USE_TIMEOUT_SHIM=yes" in profile
        assert "ALLOW_CLEAN_NO_REBOOT=no" in profile
        assert "EXPOSURE_COUNT=1" in profile
        assert "CAPTURE_TIMEOUT_SECONDS=180" in profile
    assert "EXPOSURE_ARGS=8000000000" in timeout_probe_profile
    assert "EXPOSURE_PLAN=selected:8000000000" in timeout_probe_profile
    # 6 s sits just past the 15 s stock budget once ~14 s of readout is added,
    # while 1 s still completes.  It is the narrowest test of the shim.
    assert "EXPOSURE_ARGS=6000000000" in timeout_probe_6s_profile
    assert "EXPOSURE_PLAN=selected:6000000000" in timeout_probe_6s_profile
    # Distinct result, arm and work paths, so one probe cannot read the other.
    # The mmap probe repeats the 6 s capture with the diagnostic preload in
    # the extra-preload slot; the capture parameters must be identical or the
    # two runs are not comparable.
    assert "MASK0=FE\n        MASK1=FF\n        MASK2=01" in mmap_probe_6s_profile
    assert "EXPOSURE_ARGS=6000000000" in mmap_probe_6s_profile
    assert "EXPOSURE_PLAN=selected:6000000000" in mmap_probe_6s_profile
    assert "USE_TIMEOUT_SHIM=yes" in mmap_probe_6s_profile
    assert "ALLOW_CLEAN_NO_REBOOT=no" in mmap_probe_6s_profile
    # 29 s is the firmware's stated ceiling and the first exposure past the
    # flat part of the HAL formula, where it derives T+5 instead of 15.
    assert "EXPOSURE_ARGS=29000000000" in timeout_probe_29s_profile
    assert "EXPOSURE_PLAN=selected:29000000000" in timeout_probe_29s_profile
    assert "USE_TIMEOUT_SHIM=yes" in timeout_probe_29s_profile
    assert "CAPTURE_TIMEOUT_SECONDS=180" in timeout_probe_29s_profile
    # The control profile must load nothing: the point is to see the capture
    # without our own instrumentation in the path.
    assert "USE_ASYNC_SHIM=no" in bare_6s_profile
    assert "USE_TIMEOUT_SHIM=no" in bare_6s_profile
    assert "EXPOSURE_ARGS=6000000000" in bare_6s_profile
    assert "MASK0=FE\n        MASK1=FF\n        MASK2=01" in bare_6s_profile
    for marker in ("light_l16_mmap_probe_6s.result",
                   "light_l16_mmap_probe_6s.armed",
                   "light_l16_mmap_probe_6s_run"):
        assert marker in mmap_probe_6s_profile
        assert marker not in timeout_probe_6s_profile
    for marker in ("light_l16_timeout_probe_6s.result",
                   "light_l16_timeout_probe_6s.armed",
                   "light_l16_timeout_probe_6s_run"):
        assert marker in timeout_probe_6s_profile
        assert marker not in timeout_probe_profile
    # Second-scale exposures overflow a 32-bit shell, so the payload must not
    # compare them numerically.
    assert '[ "${#EXPOSURE_VALUE}" -le 11 ]' in text
    assert '"$EXPOSURE_VALUE" -gt 0' not in text

    assert "EXPOSURE_COUNT=16" in all16_hdr_async_profile
    assert (
        "EXPOSURE_ARGS='1250000 20000000 5000000 5000000 20000000 "
        "20000000 5000000 5000000 1250000 20000000 20000000 5000000 "
        "5000000 20000000 1250000 20000000'" in all16_hdr_async_profile
    )
    assert (
        "EXPOSURE_ORDER=A1,A2,A3,A4,A5,B1,B2,B3,B4,B5,C1,C2,C3,C4,C5,C6"
        in all16_hdr_async_profile
    )

    assert "ARM_VALUE=A1_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    assert (
        "ARM_VALUE=A1_CENTER_AF_THEN_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    )
    assert (
        "ARM_VALUE=A1_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    )
    assert "ARM_VALUE=A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    assert (
        "ARM_VALUE=A_GROUP_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    )
    assert "ARM_VALUE=ALL16_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    assert (
        "ARM_VALUE=ALL16_ASYNC_SHIM_CAPTURE_20000000NS_GAIN_1.0_ONCE" in text
    )
    assert (
        "ARM_VALUE=ALL16_HDR_ASYNC_SHIM_CAPTURE_1250000_5000000_20000000NS_"
        "GAIN_1.0_ONCE" in text
    )
    assert "MODE=A1_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=A1_CENTER_AF_THEN_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=A1_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=A_GROUP_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=ALL16_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=ALL16_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE" in text
    assert "MODE=ALL16_HDR_ASYNC_SHIM_SINGLE_REQUEST_1P25_5_20MS_ONCE" in text
    assert "MASK0=02\n        MASK1=00\n        MASK2=00" in text
    assert "MASK0=FE\n        MASK1=FF\n        MASK2=01" in text
    assert "EXPOSURE_COUNT=1" in text
    assert "EXPOSURE_ARGS=20000000" in text
    assert "EXPOSURE_ORDER=common_for_selected_modules" in text
    assert "EXPOSURE_PLAN=selected:20000000" in text
    assert "GAIN=1.0" in text
    assert "TUPLE0=11\nTUPLE1=F1\nTUPLE2=00" in text
    assert "CAPTURE_TIMEOUT_SECONDS=30" in text
    assert "CAPTURE_TIMEOUT_SECONDS=60" in text
    assert "MIN_DATA_FREE_KB=262144" in text
    assert "MIN_DATA_FREE_KB=1048576" in text
    assert text.count("DIAGNOSTIC_LOG_LINES=2000") == 13
    assert "DIAGNOSTIC_LOG_LINES=500" not in text
    assert "ALLOW_CLEAN_NO_REBOOT=yes" in text
    assert "ALLOW_CLEAN_NO_REBOOT=no" in text
    assert '/system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s"' in text
    assert 'set -- -m 0 -s 0 -f 1 "$MASK0" "$MASK1" "$MASK2"' in text
    assert '"$TUPLE0" "$TUPLE1" "$TUPLE2" -R 4160,3120 -e' in text
    assert 'set -- "$@" "$EXPOSURE_VALUE"' in text
    assert 'set -- "$@" -g "$GAIN"' in text
    assert '"$LCC_COPY" "$@"' in text
    assert "a comma-separated or" in text
    capture_plan = next(
        line
        for line in text.splitlines()
        if "printf 'executed_argv=<verified-lcc-copy>" in line
    )
    assert " -C " not in capture_plan
    assert " -F " not in capture_plan
    assert (
        "autofocus_executed_argv=<verified-lcc-copy> "
        "-m 0 -s 0 -V -C -H -f 0" in text
    )
    assert "PROG_APP_SOURCE=/system/etc/prog_app_p2" in text
    assert "EXPECTED_PROG_APP_SIZE=159664" in text
    assert "EXPECTED_PROG_APP_SHA1=d6d74641759f2e208beac4318507ea1b71923db4" in text
    assert "asic_reset_executed_argv=<verified-prog-app-copy> -q" in text
    assert '"$PROG_APP_COPY" -F' in text
    assert "asic_reset_scope=all_three_asics_normal_mode_nonflashing" in text
    assert "-m 0 -s 0 -r -p 12 34 15 02" in text
    assert "autofocus_response_status_nonzero" in text
    assert "autofocus_response_file_status_nonzero" in text
    assert "lcc_response_files=disabled" in text
    assert "hal_lri_output=expected_automatically" in text
    assert "HAL_SOURCE=/system/lib/hw/camera.msm8996.so" in text
    assert "EXPECTED_HAL_SIZE=1338100" in text
    assert "EXPECTED_HAL_SHA1=016602174e0635e79cda5566d5e850c1294a9300" in text
    assert "EXPECTED_SHIM_SIZE=9080" in text
    assert "EXPECTED_SHIM_SHA1=0b93dc17a2c4219943293d96b7edda39be61613d" in text
    assert "LD_PRELOAD=$1; export LD_PRELOAD; shift; exec \"$@\"" in text
    for marker in (
        "loaded",
        "preload_cleared",
        "resolve_targets_ok",
        "preload_child_selftest_ok",
        "enqueue_ok",
        "worker_start",
        "worker_done_ok",
        "close_wait",
        "close_continue",
        "helper_commands_ok",
        "close_reports_ok",
    ):
        assert marker in text
    assert "LRI_DIR=/sdcard/DCIM/camera" in text
    assert 'snapshot_lri_paths "$WORKDIR/lri.before.txt"' in text
    assert 'snapshot_lri_paths "$WORKDIR/lri.after.txt"' in text
    assert "lri_artifact_missing_or_ambiguous" in text
    assert "capture_output_file=disabled" not in text
    assert "persistent_pixel_output=not_requested_by_this_command" not in text
    assert "printf '0\\n' > \"$MANUAL_CONTROL\"" in text
    assert "NORMAL_REBOOT_REQUIRED=yes" in text
    assert 'rm -f "$LCC_COPY"' in text
    for forbidden in (
        "/dev/block",
        "start fwupgrade",
        "camera_enable",
        "eeprom",
        " -m program",
        "/sys/class/light_ccb/spi/firmware",
        "/system/bin/reboot",
    ):
        assert forbidden not in text


def test_host_capture_supervisor_enforces_profile_specific_reboot_policy(
    tmp_path: Path,
) -> None:
    supervisor = ROOT / "host" / "run_a1_capture_once.sh"
    shell = shutil.which("sh")
    assert shell is not None
    subprocess.run([shell, "-n", str(supervisor)], check=True)
    supervisor_text = supervisor.read_text(encoding="utf-8")
    assert (
        "--execute-fixed-a1-center-af-then-20ms-capture-once-and-reboot"
        in supervisor_text
    )
    assert (
        "--execute-fixed-a1-inline-af-then-20ms-capture-once-and-reboot"
        in supervisor_text
    )
    assert "EXPECTED_MODE=A1_CENTER_AF_THEN_FIXED_CAPTURE_20MS_ONCE" in supervisor_text
    assert "EXPECTED_MODE=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in supervisor_text
    assert "--execute-fixed-a1-async-shim-20ms-once-and-reboot" in supervisor_text
    assert "--execute-fixed-all16-async-shim-20ms-once-and-reboot" in supervisor_text
    assert "EXPECTED_MODE=A1_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE" in supervisor_text
    assert "EXPECTED_MODE=ALL16_ASYNC_SHIM_FIXED_CAPTURE_20MS_ONCE" in supervisor_text
    assert (
        "--execute-fixed-all16-hdr-async-shim-1p25-5-20ms-once-and-reboot"
        in supervisor_text
    )
    assert (
        "EXPECTED_MODE=ALL16_HDR_ASYNC_SHIM_SINGLE_REQUEST_1P25_5_20MS_ONCE"
        in supervisor_text
    )
    assert "completed result has unexpected exposure manifest" in supervisor_text
    assert "PASS_REBOOT_REQUIRED=yes" in supervisor_text
    assert "LIGHT_L16_ASYNC_SHIM" in supervisor_text
    assert "LIGHT_L16_A1_AF_SHIM" in supervisor_text
    assert "EXPECTED_SHIM_SIZE=9080" in supervisor_text
    assert (
        "EXPECTED_SHIM_SHA1=0b93dc17a2c4219943293d96b7edda39be61613d"
        in supervisor_text
    )
    assert "async PASS lacks verified shim runtime markers" in supervisor_text
    assert "inline-AF PASS lacks a focused-locked same-session result" in supervisor_text
    assert (
        "center-AF PASS lacks verified reset, readiness, status-zero response, "
        "or power-off" in supervisor_text
    )

    without_confirmation = subprocess.run(
        [shell, str(supervisor)], capture_output=True, text=True
    )
    assert without_confirmation.returncode == 2

    state = tmp_path / "fake-adb-state"
    state.mkdir()
    fake_adb = tmp_path / "adb"
    fake_adb.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import hashlib
            import os
            import shlex
            import struct
            import sys
            from pathlib import Path

            state = Path(os.environ["FAKE_ADB_STATE"])
            args = sys.argv[1:]
            with (state / "calls.log").open("a", encoding="utf-8") as log:
                log.write(repr(args) + "\\n")

            def prop_path(name):
                return state / ("prop-" + name.replace(".", "_"))

            def set_prop(name, value):
                prop_path(name).write_text(value, encoding="utf-8")

            def get_prop(name):
                path = prop_path(name)
                if path.exists():
                    return path.read_text(encoding="utf-8")
                return {
                    "ro.build.version.incremental": "00WW_1_351",
                    "ro.product.model": "L16",
                    "ro.product.name": "LFC_0002_FIH01",
                }.get(name, "")

            profile = os.environ.get("FAKE_PROFILE", "a1")
            if profile == "all16-hdr-async":
                mode = "ALL16_HDR_ASYNC_SHIM_SINGLE_REQUEST_1P25_5_20MS_ONCE"
                workdir = "/data/local/tmp/light_l16_all16_hdr_async_capture_run.1234"
                arm_value = "ALL16_HDR_ASYNC_SHIM_CAPTURE_1250000_5000000_20000000NS_GAIN_1.0_ONCE"
                exposure_count = "16"
                exposure_order = "A1,A2,A3,A4,A5,B1,B2,B3,B4,B5,C1,C2,C3,C4,C5,C6"
                exposure_plan = "A1:1250000,A2:20000000,A3:5000000,A4:5000000,A5:20000000,B1:20000000,B2:5000000,B3:5000000,B4:1250000,B5:20000000,C1:20000000,C2:5000000,C3:5000000,C4:20000000,C5:1250000,C6:20000000"
                async_shim = "verified"
            elif profile == "all16":
                mode = "ALL16_FIXED_CAPTURE_20MS_ONCE"
                workdir = "/data/local/tmp/light_l16_all16_capture_run.1234"
                arm_value = "ALL16_CAPTURE_20000000NS_GAIN_1.0_ONCE"
            elif profile == "a1-center-af":
                mode = "A1_CENTER_AF_THEN_FIXED_CAPTURE_20MS_ONCE"
                workdir = "/data/local/tmp/light_l16_a1_center_af_capture_run.1234"
                arm_value = "A1_CENTER_AF_THEN_CAPTURE_20000000NS_GAIN_1.0_ONCE"
            elif profile == "a1-inline-af":
                mode = "A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE"
                workdir = "/data/local/tmp/light_l16_a1_inline_af_capture_run.1234"
                arm_value = "A1_INLINE_AF_CAPTURE_20000000NS_GAIN_1.0_ONCE"
            else:
                mode = "A1_FIXED_CAPTURE_20MS_ONCE"
                workdir = "/data/local/tmp/light_l16_a1_capture_run.1234"
                arm_value = "A1_CAPTURE_20000000NS_GAIN_1.0_ONCE"
            if profile != "all16-hdr-async":
                exposure_count = "1"
                exposure_order = "common_for_selected_modules"
                exposure_plan = "selected:20000000"
                async_shim = "disabled"

            capture_attempted = os.environ.get("FAKE_CAPTURE_ATTEMPTED", "yes")
            final_status = os.environ.get("FAKE_FINAL_STATUS", "PASS")
            cleanup_ok = os.environ.get("FAKE_CLEANUP_OK", "yes")
            autofocus_attempted = (
                os.environ.get("FAKE_AUTOFOCUS_ATTEMPTED", "yes")
                if profile in ("a1-center-af", "a1-inline-af")
                else os.environ.get("FAKE_AUTOFOCUS_ATTEMPTED", "no")
            )
            asic_reset_attempted = (
                os.environ.get("FAKE_ASIC_RESET_ATTEMPTED", "yes")
                if profile == "a1-center-af"
                else os.environ.get("FAKE_ASIC_RESET_ATTEMPTED", "no")
            )
            pixel = (
                struct.pack("<4sQQIB7x", b"LELR", 43, 35, 8, 0)
                + b"raw"
                + b"protobuf"
            )
            pixel_sha1 = hashlib.sha1(pixel).hexdigest()
            reboot_required = (
                "yes"
                if asic_reset_attempted == "yes"
                or autofocus_attempted == "yes"
                or (
                    capture_attempted == "yes"
                    and (profile.startswith("all16") or final_status != "PASS")
                )
                else "no"
            )
            result = (
                f"mode={mode}\\n"
                f"exposure_argument_count={exposure_count}\\n"
                f"exposure_argument_module_order={exposure_order}\\n"
                f"exposure_plan_module_order={exposure_plan}\\n"
                f"capture_attempted={capture_attempted}\\n"
                f"asic_reset_attempted={asic_reset_attempted}\\n"
                f"asic_reset_exit_status={'0' if asic_reset_attempted == 'yes' else 'not_run'}\\n"
                f"asic_ready_exit_status={'0' if asic_reset_attempted == 'yes' else 'not_run'}\\n"
                f"asic_ready_response={'ready_01' if asic_reset_attempted == 'yes' else 'not_run'}\\n"
                f"asic_power_off_exit_status={'0' if asic_reset_attempted == 'yes' else 'not_run'}\\n"
                f"autofocus_attempted={autofocus_attempted}\\n"
                f"autofocus_exit_status={'0' if autofocus_attempted == 'yes' else 'not_run'}\\n"
                f"autofocus_response={('camera3_af_state_focused_locked_inline_hal_session' if profile == 'a1-inline-af' else 'interrupt_received_status_zero') if autofocus_attempted == 'yes' else 'not_run'}\\n"
                "lcc_exit_status=0\\n"
                "manual_control_after=manual_control mode is 0x0\\n"
                "lcc_process_after=no\\n"
                f"cleanup_ok={cleanup_ok}\\n"
                "settled_camera_clients=none\\n"
                "media_after=running\\n"
                "lightsvr_after=running\\n"
                f"async_shim={async_shim}\\n"
                f"a1_af_shim={'verified' if profile == 'a1-inline-af' else 'disabled'}\\n"
                f"normal_reboot_required={reboot_required}\\n"
                f"workdir={workdir}\\n"
                "lri_output_count=1\\n"
                "lri_output_path=/sdcard/DCIM/camera/RDI_20260809_123456_789.lri\\n"
                f"lri_output_size={len(pixel)}\\n"
                f"lri_output_sha1={pixel_sha1}\\n"
                f"final_status={final_status}\\n"
                "final_reason=simulated\\n"
            )

            if not args:
                raise SystemExit(1)
            if args[0] == "devices":
                print("List of devices attached")
                print("FAKE123\\tdevice")
                raise SystemExit(0)
            if args[0] == "push":
                raise SystemExit(0)
            if args[0] == "reboot":
                (state / "rebooted").touch()
                raise SystemExit(0)
            if args[0] == "pull":
                source, target = args[1], Path(args[2])
                if source.endswith(
                    (
                        "light_l16_a1_capture.result",
                        "light_l16_a1_center_af_capture.result",
                        "light_l16_a1_inline_af_capture.result",
                        "light_l16_all16_capture.result",
                        "light_l16_all16_hdr_async_capture.result",
                    )
                ):
                    if os.environ.get("FAKE_PULL_RESULT_FAIL") == "1":
                        raise SystemExit(1)
                    if (
                        os.environ.get("FAKE_LEGACY_SHELL_STATUS") == "1"
                        and not (state / "result-ready").exists()
                    ):
                        raise SystemExit(1)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(result, encoding="utf-8")
                elif source.endswith(".lri"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(pixel)
                else:
                    target.mkdir(parents=True, exist_ok=True)
                    (target / "lcc.txt").write_text("simulated\\n", encoding="utf-8")
                raise SystemExit(0)
            if args[0] != "shell":
                raise SystemExit(1)

            command = args[1]
            if "wc -c < '/data/local/tmp/liblcc_async_writer_shim.so'" in command:
                print("9080")
                raise SystemExit(0)
            if "sha1sum '/data/local/tmp/liblcc_async_writer_shim.so'" in command:
                print("0b93dc17a2c4219943293d96b7edda39be61613d  shim")
                raise SystemExit(0)
            if "wc -c < '/data/local/tmp/liblcc_a1_focus_capture_shim.so'" in command:
                print("13764")
                raise SystemExit(0)
            if "sha1sum '/data/local/tmp/liblcc_a1_focus_capture_shim.so'" in command:
                print("67647b71767ab2b68a214fae87578e24eb3433b2  shim")
                raise SystemExit(0)
            if "sha1sum" in command:
                print(os.environ["EXPECTED_PAYLOAD_SHA1"] + "  payload")
                raise SystemExit(0)
            if command.startswith("cat '/data/local/tmp/light_l16_") and command.endswith(
                "_capture.armed'"
            ):
                print(arm_value)
                raise SystemExit(0)
            if command.startswith("getprop "):
                print(get_prop(shlex.split(command)[1]))
                raise SystemExit(0)
            if command == "setprop persist.sys.fihop 8":
                set_prop("persist.sys.fihop", "8")
                (state / "triggered").touch()
                raise SystemExit(int(os.environ.get("FAKE_TRIGGER_STATUS", "0")))
            if command.startswith("setprop persist.sys.fihop ") and ";" not in command:
                parts = shlex.split(command)
                set_prop(parts[1], parts[2])
                raise SystemExit(0)
            if command.startswith("setprop persist.sys.fihop1 "):
                parts = shlex.split(command)
                set_prop(parts[1], parts[2])
                raise SystemExit(0)
            if command.startswith("setprop persist.sys.fihop2 "):
                parts = shlex.split(command)
                set_prop(parts[1], parts[2])
                raise SystemExit(0)
            if "setprop persist.sys.fihop 0;" in command:
                set_prop("persist.sys.fihop", "0")
                for number in range(1, 6):
                    set_prop(f"persist.sys.fihop{number}", "")
                raise SystemExit(0)
            if command.startswith("setprop persist.sys.fihop3 "):
                for number in range(3, 6):
                    set_prop(f"persist.sys.fihop{number}", "")
                raise SystemExit(0)
            if "grep -q '^final_status='" in command:
                poll_count_path = state / "poll-count"
                poll_count = (
                    int(poll_count_path.read_text(encoding="utf-8"))
                    if poll_count_path.exists()
                    else 0
                )
                poll_count += 1
                poll_count_path.write_text(str(poll_count), encoding="utf-8")
                pending_polls = int(os.environ.get("FAKE_RESULT_PENDING_POLLS", "0"))
                ready = (state / "triggered").exists() and poll_count > pending_polls
                if ready:
                    (state / "result-ready").touch()
                if "LIGHT_L16_RESULT_COMPLETE" in command:
                    print(
                        "LIGHT_L16_RESULT_COMPLETE"
                        if ready
                        else "LIGHT_L16_RESULT_PENDING"
                    )
                    raise SystemExit(0)
                if os.environ.get("FAKE_LEGACY_SHELL_STATUS") == "1":
                    raise SystemExit(0)
                raise SystemExit(0 if ready else 1)
            raise SystemExit(0)
            """
        ),
        encoding="utf-8",
    )
    fake_adb.chmod(0o755)

    fake_shim = tmp_path / "liblcc_async_writer_shim.so"
    fake_shim.write_bytes(bytes(9080))
    fake_af_shim = tmp_path / "liblcc_a1_focus_capture_shim.so"
    fake_af_shim.write_bytes(bytes(13764))
    fake_sha1sum = tmp_path / "sha1sum"
    fake_sha1sum.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import hashlib
            import os
            import sys
            from pathlib import Path

            target = os.path.realpath(sys.argv[1])
            shim = os.path.realpath(os.environ.get("FAKE_SHIM_PATH", ""))
            af_shim = os.path.realpath(os.environ.get("FAKE_AF_SHIM_PATH", ""))
            if target == shim:
                digest = "0b93dc17a2c4219943293d96b7edda39be61613d"
            elif target == af_shim:
                digest = "67647b71767ab2b68a214fae87578e24eb3433b2"
            else:
                digest = hashlib.sha1(Path(sys.argv[1]).read_bytes()).hexdigest()
            print(f"{digest}  {sys.argv[1]}")
            """
        ),
        encoding="utf-8",
    )
    fake_sha1sum.chmod(0o755)

    payload = ROOT / "device" / "a1_capture_once.sh"
    env = os.environ.copy()
    env.update(
        {
            "LIGHT_L16_ADB": str(fake_adb),
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "output"),
            "FAKE_ADB_STATE": str(state),
            "EXPECTED_PAYLOAD_SHA1": hashlib.sha1(payload.read_bytes()).hexdigest(),
            "FAKE_SHIM_PATH": str(fake_shim),
            "FAKE_AF_SHIM_PATH": str(fake_af_shim),
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        }
    )
    completed = subprocess.run(
        [shell, str(supervisor), "--execute-fixed-a1-20ms-once-with-failure-reboot"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (state / "triggered").exists()
    assert not (state / "rebooted").exists()
    results = list((tmp_path / "output").glob("*/result.txt"))
    assert len(results) == 1
    assert "final_status=PASS" in results[0].read_text(encoding="utf-8")
    pixels = list((tmp_path / "output").glob("*/pixels/*.lri"))
    assert len(pixels) == 1
    assert pixels[0].read_bytes().startswith(b"LELR")

    all16_state = tmp_path / "fake-adb-all16-state"
    all16_state.mkdir()
    all16_env = env.copy()
    all16_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "all16-output"),
            "FAKE_ADB_STATE": str(all16_state),
            "FAKE_PROFILE": "all16",
        }
    )
    all16 = subprocess.run(
        [
            shell,
            str(supervisor),
            "--execute-fixed-all16-20ms-once-and-reboot",
        ],
        cwd=ROOT,
        env=all16_env,
        capture_output=True,
        text=True,
    )
    assert all16.returncode == 0, all16.stderr
    assert (all16_state / "triggered").exists()
    assert (all16_state / "rebooted").exists()
    assert "mandatory normal reboot" in all16.stderr
    all16_results = list((tmp_path / "all16-output").glob("*/result.txt"))
    assert len(all16_results) == 1
    assert "mode=ALL16_FIXED_CAPTURE_20MS_ONCE" in all16_results[0].read_text(
        encoding="utf-8"
    )

    center_af_state = tmp_path / "fake-adb-center-af-state"
    center_af_state.mkdir()
    center_af_env = env.copy()
    center_af_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "center-af-output"),
            "FAKE_ADB_STATE": str(center_af_state),
            "FAKE_PROFILE": "a1-center-af",
        }
    )
    center_af = subprocess.run(
        [
            shell,
            str(supervisor),
            "--execute-fixed-a1-center-af-then-20ms-capture-once-and-reboot",
        ],
        cwd=ROOT,
        env=center_af_env,
        capture_output=True,
        text=True,
    )
    assert center_af.returncode == 0, center_af.stderr
    assert (center_af_state / "triggered").exists()
    assert (center_af_state / "rebooted").exists()
    assert "mandatory normal reboot" in center_af.stderr
    center_af_results = list((tmp_path / "center-af-output").glob("*/result.txt"))
    assert len(center_af_results) == 1
    center_af_result = center_af_results[0].read_text(encoding="utf-8")
    assert "mode=A1_CENTER_AF_THEN_FIXED_CAPTURE_20MS_ONCE" in center_af_result
    assert "asic_reset_attempted=yes" in center_af_result
    assert "asic_ready_response=ready_01" in center_af_result
    assert "autofocus_attempted=yes" in center_af_result
    assert "autofocus_response=interrupt_received_status_zero" in center_af_result

    inline_af_state = tmp_path / "fake-adb-inline-af-state"
    inline_af_state.mkdir()
    inline_af_env = env.copy()
    inline_af_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "inline-af-output"),
            "LIGHT_L16_A1_AF_SHIM": str(fake_af_shim),
            "FAKE_ADB_STATE": str(inline_af_state),
            "FAKE_PROFILE": "a1-inline-af",
        }
    )
    inline_af = subprocess.run(
        [
            shell,
            str(supervisor),
            "--execute-fixed-a1-inline-af-then-20ms-capture-once-and-reboot",
        ],
        cwd=ROOT,
        env=inline_af_env,
        capture_output=True,
        text=True,
    )
    assert inline_af.returncode == 0, inline_af.stderr
    assert (inline_af_state / "triggered").exists()
    assert (inline_af_state / "rebooted").exists()
    inline_af_results = list((tmp_path / "inline-af-output").glob("*/result.txt"))
    assert len(inline_af_results) == 1
    inline_af_result = inline_af_results[0].read_text(encoding="utf-8")
    assert "mode=A1_INLINE_CENTER_AF_FIXED_CAPTURE_20MS_ONCE" in inline_af_result
    assert "asic_reset_attempted=no" in inline_af_result
    assert "autofocus_attempted=yes" in inline_af_result
    assert (
        "autofocus_response=camera3_af_state_focused_locked_inline_hal_session"
        in inline_af_result
    )
    assert "a1_af_shim=verified" in inline_af_result

    all16_wrapper = ROOT / "host" / "run_all16_capture_once.sh"
    subprocess.run([shell, "-n", str(all16_wrapper)], check=True)
    wrapper_without_confirmation = subprocess.run(
        [shell, str(all16_wrapper)], capture_output=True, text=True
    )
    assert wrapper_without_confirmation.returncode == 2

    hdr_wrapper = ROOT / "host" / "run_all16_hdr_capture_once.sh"
    subprocess.run([shell, "-n", str(hdr_wrapper)], check=True)
    hdr_description = subprocess.run(
        [shell, str(hdr_wrapper), "--describe"],
        env={**os.environ, "LIGHT_L16_ADB": "/definitely/not/adb"},
        capture_output=True,
        text=True,
    )
    assert hdr_description.returncode == 0
    assert "A1   1.25ms" in hdr_description.stdout
    assert "C6   20ms" in hdr_description.stdout
    assert "one lcc request" in hdr_description.stdout
    assert "not run on a camera yet" in hdr_description.stdout
    hdr_without_confirmation = subprocess.run(
        [shell, str(hdr_wrapper)], capture_output=True, text=True
    )
    assert hdr_without_confirmation.returncode == 2
    assert "No ADB or camera action was attempted." in hdr_without_confirmation.stderr

    hdr_state = tmp_path / "fake-adb-hdr-state"
    hdr_state.mkdir()
    hdr_env = env.copy()
    hdr_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "hdr-output"),
            "LIGHT_L16_ASYNC_SHIM": str(fake_shim),
            "FAKE_ADB_STATE": str(hdr_state),
            "FAKE_PROFILE": "all16-hdr-async",
        }
    )
    hdr = subprocess.run(
        [
            shell,
            str(hdr_wrapper),
            "--execute-fixed-all16-hdr-async-shim-1p25-5-20ms-once-and-reboot",
        ],
        cwd=ROOT,
        env=hdr_env,
        capture_output=True,
        text=True,
    )
    assert hdr.returncode == 0, hdr.stderr
    assert (hdr_state / "triggered").exists()
    assert (hdr_state / "rebooted").exists()
    assert "mandatory normal reboot" in hdr.stderr
    hdr_results = list((tmp_path / "hdr-output").glob("*/result.txt"))
    assert len(hdr_results) == 1
    hdr_result = hdr_results[0].read_text(encoding="utf-8")
    assert "mode=ALL16_HDR_ASYNC_SHIM_SINGLE_REQUEST_1P25_5_20MS_ONCE" in hdr_result
    assert "exposure_argument_count=16" in hdr_result
    assert "exposure_argument_module_order=A1,A2,A3,A4,A5,B1" in hdr_result
    hdr_manifests = list((tmp_path / "hdr-output").glob("*/pixels/manifest.txt"))
    assert len(hdr_manifests) == 1
    hdr_manifest = hdr_manifests[0].read_text(encoding="utf-8")
    assert "profile=all16-hdr-async" in hdr_manifest
    assert "exposure_plan_module_order=A1:1250000,A2:20000000" in hdr_manifest

    ambiguous_state = tmp_path / "fake-adb-ambiguous-trigger-state"
    ambiguous_state.mkdir()
    ambiguous_env = env.copy()
    ambiguous_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "ambiguous-trigger-output"),
            "FAKE_ADB_STATE": str(ambiguous_state),
            "FAKE_TRIGGER_STATUS": "1",
        }
    )
    ambiguous = subprocess.run(
        [shell, str(supervisor), "--execute-fixed-a1-20ms-once-with-failure-reboot"],
        cwd=ROOT,
        env=ambiguous_env,
        capture_output=True,
        text=True,
    )
    assert ambiguous.returncode == 0, ambiguous.stderr
    assert "delivery may have occurred" in ambiguous.stderr
    assert (ambiguous_state / "triggered").exists()
    assert not (ambiguous_state / "rebooted").exists()
    ambiguous_results = list(
        (tmp_path / "ambiguous-trigger-output").glob("*/result.txt")
    )
    assert len(ambiguous_results) == 1
    assert "final_status=PASS" in ambiguous_results[0].read_text(encoding="utf-8")

    legacy_state = tmp_path / "fake-adb-legacy-shell-state"
    legacy_state.mkdir()
    legacy_env = env.copy()
    legacy_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "legacy-shell-output"),
            "FAKE_ADB_STATE": str(legacy_state),
            "FAKE_LEGACY_SHELL_STATUS": "1",
            "FAKE_RESULT_PENDING_POLLS": "2",
        }
    )
    legacy = subprocess.run(
        [shell, str(supervisor), "--execute-fixed-a1-20ms-once-with-failure-reboot"],
        cwd=ROOT,
        env=legacy_env,
        capture_output=True,
        text=True,
    )
    assert legacy.returncode == 0, legacy.stderr
    assert int((legacy_state / "poll-count").read_text(encoding="utf-8")) == 3
    assert (legacy_state / "result-ready").exists()
    assert not (legacy_state / "rebooted").exists()
    legacy_results = list((tmp_path / "legacy-shell-output").glob("*/result.txt"))
    assert len(legacy_results) == 1
    assert "final_status=PASS" in legacy_results[0].read_text(encoding="utf-8")

    dirty_result_state = tmp_path / "fake-adb-dirty-result-state"
    dirty_result_state.mkdir()
    dirty_result_env = env.copy()
    dirty_result_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "dirty-result-output"),
            "FAKE_ADB_STATE": str(dirty_result_state),
            "FAKE_CLEANUP_OK": "no",
        }
    )
    dirty_result = subprocess.run(
        [
            shell,
            str(supervisor),
            "--execute-fixed-a1-20ms-once-with-failure-reboot",
        ],
        cwd=ROOT,
        env=dirty_result_env,
        capture_output=True,
        text=True,
    )
    assert dirty_result.returncode != 0
    assert (dirty_result_state / "triggered").exists()
    assert (dirty_result_state / "rebooted").exists()

    stopped_state = tmp_path / "fake-adb-stopped-state"
    stopped_state.mkdir()
    stopped_env = env.copy()
    stopped_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "stopped-output"),
            "FAKE_ADB_STATE": str(stopped_state),
            "FAKE_CAPTURE_ATTEMPTED": "no",
            "FAKE_FINAL_STATUS": "FAIL",
        }
    )
    stopped = subprocess.run(
        [shell, str(supervisor), "--execute-fixed-a1-20ms-once-with-failure-reboot"],
        cwd=ROOT,
        env=stopped_env,
        capture_output=True,
        text=True,
    )
    assert stopped.returncode == 1
    assert (stopped_state / "triggered").exists()
    assert not (stopped_state / "rebooted").exists()

    failed_pull_state = tmp_path / "fake-adb-failed-pull-state"
    failed_pull_state.mkdir()
    failed_pull_env = env.copy()
    failed_pull_env.update(
        {
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "failed-pull-output"),
            "FAKE_ADB_STATE": str(failed_pull_state),
            "FAKE_PULL_RESULT_FAIL": "1",
        }
    )
    failed_pull = subprocess.run(
        [shell, str(supervisor), "--execute-fixed-a1-20ms-once-with-failure-reboot"],
        cwd=ROOT,
        env=failed_pull_env,
        capture_output=True,
        text=True,
    )
    assert failed_pull.returncode != 0
    assert (failed_pull_state / "triggered").exists()
    assert (failed_pull_state / "rebooted").exists()
    failed_pull_calls = (failed_pull_state / "calls.log").read_text(encoding="utf-8")
    staging_cleanup = (
        "rm -f '/data/local/tmp/light_l16_a1_capture_once.sh' "
        "'/data/local/tmp/light_l16_a1_capture.armed'"
    )
    assert failed_pull_calls.count(staging_cleanup) == 1
    assert failed_pull_calls.index(staging_cleanup) < failed_pull_calls.index(
        "['push',"
    )


def test_repository_contains_no_proprietary_binary_extensions() -> None:
    forbidden_suffixes = {".apk", ".bin", ".elf", ".img", ".so", ".zip"}
    offenders = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(ROOT).parts)
        and path.suffix.lower() in forbidden_suffixes
    ]
    assert offenders == []


def test_android_shim_build_script_is_bounded_and_syntax_valid() -> None:
    build_script = ROOT / "host" / "build_lcc_async_shim.sh"
    text = build_script.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    assert shell is not None
    subprocess.run([shell, "-n", str(build_script)], check=True)

    assert "--target=armv7a-linux-androideabi23" in text
    assert "-DL16_ANDROID_FREESTANDING" in text
    assert "-mfloat-abi=softfp" in text
    assert "-nostdlib" in text
    assert "--hash-style=sysv" in text
    assert "-z,noexecstack" in text
    assert "--build-id=sha1" in text
    assert "refusing to place a generated binary inside the repository" in text


def test_relative_markdown_links_resolve() -> None:
    pattern = re.compile(r"]\((?!https?://|mailto:|#)([^)#]+)(?:#[^)]+)?\)")
    missing: list[str] = []
    for document in ROOT.rglob("*.md"):
        text = document.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            target = document.parent / match.group(1)
            if not target.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {match.group(1)}")
    assert missing == []


def test_every_wrapper_profile_sets_the_variables_the_report_prints() -> None:
    """A branch that omits one only fails after the capture has been taken.

    The bare 6 s profile reached the report with PROFILE unset, aborting the
    wrapper after a successful 260 MB capture.  Nothing was lost, but the run
    was a physical capture and a reboot, so the check belongs here.
    """
    wrapper = (ROOT / "host" / "run_a1_capture_once.sh").read_text(encoding="utf-8")
    head, _, _ = wrapper.partition("\nRUN_STAMP=")
    parts = re.split(r'\n(?:el)?if \[ "\$#" -eq 1 \] && \[ "\$1" = ', head)
    preamble, branches = parts[0], parts[1:]
    assert len(branches) >= 12
    # A variable initialised before the branches has a safe default, so a
    # branch may leave it alone.  PROFILE and PROFILE_LABEL have no default,
    # which is exactly why omitting them aborted the wrapper.
    defaulted = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", preamble, re.M))
    assigned = {}
    for branch in branches:
        # The branch text starts at the opening quote of the confirm variable.
        name = branch.split("\"")[1]
        assigned[name] = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)=", branch, re.M))

    # Rather than list the variables by hand -- the list is what was wrong --
    # take anything most branches set as required of all of them.  Genuinely
    # profile-specific settings appear in only a few and stay out of it.
    counts = {}
    for names in assigned.values():
        for variable in names:
            counts[variable] = counts.get(variable, 0) + 1
    common = {v for v, n in counts.items()
              if n > len(branches) // 2 and v not in defaulted}
    assert "PROFILE_LABEL" in common and "PROFILE" in common
    for name, names in assigned.items():
        missing = sorted(common - names)
        assert not missing, f"{name} does not set {', '.join(missing)}"
