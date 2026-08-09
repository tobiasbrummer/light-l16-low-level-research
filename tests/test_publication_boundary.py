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


def test_a1_capture_payload_is_fixed_armed_and_cleanup_bounded() -> None:
    payload = ROOT / "device" / "a1_capture_once.sh"
    text = payload.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    if shell is not None:
        subprocess.run([shell, "-n", str(payload)], check=True)

    clear = "setprop persist.sys.fihop 0"
    armed = '[ "$ARMED" = "$ARM_VALUE" ]'
    attempted = "CAPTURE_ATTEMPTED=yes"
    assert text.index(clear) < text.index(': > "$OUT"')
    assert text.index(armed) < text.index(attempted)
    assert 'rm -f "$ARM_FILE"' in text
    assert '/system/bin/timeout -k 5s 30s "$LCC_COPY"' in text
    assert "-m 0 -s 0 -f 1 02 00 00 11 F1 00" in text
    assert "-R 4160,3120 -e 20000000 -g 1.0" in text
    assert " -F " not in text
    assert " -C " not in text
    assert "lcc_response_files=disabled" in text
    assert "hal_lri_output=expected_automatically" in text
    assert "HAL_SOURCE=/system/lib/hw/camera.msm8996.so" in text
    assert "EXPECTED_HAL_SIZE=1338100" in text
    assert "EXPECTED_HAL_SHA1=016602174e0635e79cda5566d5e850c1294a9300" in text
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
        "prog_app_p2",
        "start fwupgrade",
        "camera_enable",
        "eeprom",
        " -m program",
        "/sys/class/light_ccb/spi/firmware",
        "/system/bin/reboot",
    ):
        assert forbidden not in text


def test_host_capture_supervisor_requires_confirmation_and_reboots_only_on_failure(
    tmp_path: Path,
) -> None:
    supervisor = ROOT / "host" / "run_a1_capture_once.sh"
    shell = shutil.which("sh")
    assert shell is not None
    subprocess.run([shell, "-n", str(supervisor)], check=True)

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

            capture_attempted = os.environ.get("FAKE_CAPTURE_ATTEMPTED", "yes")
            final_status = os.environ.get("FAKE_FINAL_STATUS", "PASS")
            cleanup_ok = os.environ.get("FAKE_CLEANUP_OK", "yes")
            pixel = (
                struct.pack("<4sQQIB7x", b"LELR", 43, 35, 8, 0)
                + b"raw"
                + b"protobuf"
            )
            pixel_sha1 = hashlib.sha1(pixel).hexdigest()
            result = (
                "mode=A1_FIXED_CAPTURE_20MS_ONCE\\n"
                f"capture_attempted={capture_attempted}\\n"
                "lcc_exit_status=0\\n"
                "manual_control_after=manual_control mode is 0x0\\n"
                "lcc_process_after=no\\n"
                f"cleanup_ok={cleanup_ok}\\n"
                "settled_camera_clients=none\\n"
                "media_after=running\\n"
                "lightsvr_after=running\\n"
                f"normal_reboot_required={'no' if capture_attempted == 'yes' and final_status == 'PASS' else 'yes' if capture_attempted == 'yes' else 'no'}\\n"
                "workdir=/data/local/tmp/light_l16_a1_capture_run.1234\\n"
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
                if source.endswith("light_l16_a1_capture.result"):
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
            if "sha1sum" in command:
                print(os.environ["EXPECTED_PAYLOAD_SHA1"] + "  payload")
                raise SystemExit(0)
            if command.startswith("cat '/data/local/tmp/light_l16_a1_capture.armed'"):
                print("A1_CAPTURE_20000000NS_GAIN_1.0_ONCE")
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

    payload = ROOT / "device" / "a1_capture_once.sh"
    env = os.environ.copy()
    env.update(
        {
            "LIGHT_L16_ADB": str(fake_adb),
            "LIGHT_L16_OUTPUT_ROOT": str(tmp_path / "output"),
            "FAKE_ADB_STATE": str(state),
            "EXPECTED_PAYLOAD_SHA1": hashlib.sha1(payload.read_bytes()).hexdigest(),
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
    assert (
        "rm -f '/data/local/tmp/light_l16_a1_capture_once.sh' "
        "'/data/local/tmp/light_l16_a1_capture.armed'"
    ) not in failed_pull_calls


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
