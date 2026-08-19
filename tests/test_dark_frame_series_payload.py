from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / "device" / "dark_frame_series_once.sh"

EXPOSURE_AXIS = ["10000", "1250000", "5000000", "20000000"]
GAIN_AXIS = ["2.0", "3.75", "4.0", "7.5"]
LONG_AXIS = ["100000000", "1000000000", "6000000000", "29000000000"]

SHORT_PATH = "/data/local/tmp/light_l16_dark_frame_series_once.sh"
LONG_PATH = "/data/local/tmp/light_l16_dark_frame_long_series_once.sh"


def expected_plan() -> list[str]:
    entries = []
    for exposure in EXPOSURE_AXIS:
        entries.extend([f"{exposure}:1.0"] * 3)
    for gain in GAIN_AXIS:
        entries.extend([f"1250000:{gain}"] * 3)
    return entries


def expected_long_plan() -> list[str]:
    """Ascending exposures, then the first cell repeated as a drift anchor."""
    entries = []
    for exposure in LONG_AXIS:
        entries.extend([f"{exposure}:1.0"] * 3)
    entries.extend([f"{LONG_AXIS[0]}:1.0"] * 3)
    return entries


def plan_lines() -> list[str]:
    return [
        line.strip()
        for line in CHILD.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("CAPTURE_PLAN=")
    ]


def plan_for(path: str) -> list[str]:
    """The CAPTURE_PLAN of the profile selected by an invocation path."""
    text = CHILD.read_text(encoding="utf-8")
    start = text.index(f"    {path})")
    end = text.index("        ;;", start)
    line = next(
        l.strip() for l in text[start:end].splitlines()
        if l.strip().startswith("CAPTURE_PLAN=")
    )
    return line.split("=", 1)[1].strip().strip("'").split()


def test_child_has_valid_shell_syntax() -> None:
    shell = shutil.which("sh")
    assert shell is not None
    subprocess.run([shell, "-n", str(CHILD)], check=True)


def test_plan_is_exactly_the_specified_twenty_four_captures() -> None:
    entries = plan_for(SHORT_PATH)
    assert len(entries) == 24
    assert entries == expected_plan()


def test_long_plan_ends_with_a_repeat_of_its_first_cell() -> None:
    """The anchor is what makes the slope interpretable.

    The 20 ms series could not separate a dark current from drift over the
    run.  Repeating the opening cell at the end measures that drift directly.
    """
    entries = plan_for(LONG_PATH)
    assert len(entries) == 15
    assert entries == expected_long_plan()
    assert entries[:3] == entries[-3:]
    assert all(e.endswith(":1.0") for e in entries)


def test_long_plan_stays_below_the_sensor_ceiling() -> None:
    ceiling = 29981853000  # Camera2 reports this as the exposure maximum
    for entry in plan_for(LONG_PATH):
        assert int(entry.split(":")[0]) <= ceiling


def test_both_profiles_are_selected_by_their_invocation_path() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert f"    {SHORT_PATH})" in text
    assert f"    {LONG_PATH})" in text
    assert "refusing unexpected invocation path" in text
    assert "CAPTURE_TIMEOUT_SECONDS=120" in text  # the long profile needs it


def test_exposure_axis_runs_first_and_holds_gain_one() -> None:
    entries = expected_plan()
    assert all(entry.endswith(":1.0") for entry in entries[:12])
    assert all(entry.startswith("1250000:") for entry in entries[12:])


def test_child_refuses_unexpected_invocation_path() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "/data/local/tmp/light_l16_dark_frame_series_once.sh" in text
    assert "refusing unexpected invocation path" in text


def test_child_pins_the_fixed_all16_selection_and_no_autofocus() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "MASK0=FE" in text
    assert "MASK1=FF" in text
    assert "MASK2=01" in text
    assert "TUPLE0=11" in text
    assert "TUPLE1=F1" in text
    assert "TUPLE2=00" in text
    assert "RUN_AUTOFOCUS=no" in text
    assert "USE_A1_AF_SHIM=no" in text
    assert "USE_ASYNC_SHIM=yes" in text
    assert "RUN_FACTORY_ASIC_RESET=no" in text
    assert "MIN_DATA_FREE_KB=8388608" in text
    assert "CAPTURE_TIMEOUT_SECONDS=60" in text


def test_child_validates_every_plan_entry_independently() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "invalid_plan_entry_count" in text
    assert "invalid_plan_exposure_value" in text
    assert "invalid_plan_gain_value" in text
    assert "exposure_axis_gain_not_one" in text
    assert "gain_axis_exposure_not_1250000" in text
    assert "plan_exposure_below_10000ns" in text
    assert "plan_exposure_above_sensor_ceiling" in text


def test_child_consumes_the_arm_token_before_any_device_state() -> None:
    text = CHILD.read_text(encoding="utf-8")
    armed = '[ "$ARMED" = "$ARM_VALUE" ]'
    assert armed in text
    assert 'rm -f "$ARM_FILE"' in text
    assert text.index(armed) < text.index("validate_plan\n")
    assert text.index("setprop persist.sys.fihop 0") < text.index(': > "$OUT"')


def extract_validator(overrides: str = "") -> str:
    """Build a runnable fragment: the plan, validate_plan, and a fail() stub.

    The device script cannot run on a host, but validate_plan is plain POSIX
    shell.  Extracting it lets the test exercise the logic instead of only
    asserting that its error strings appear in the file.
    """
    text = CHILD.read_text(encoding="utf-8")
    plan_line = plan_lines()[0]
    start = text.index("validate_plan() {")
    end = text.index("\n}\n", start) + len("\n}\n")
    validator = text[start:end]
    stub = (
        "fail() {\n"
        "    printf 'failure=%s\\n' \"$1\"\n"
        "    exit 1\n"
        "}\n"
    )
    constants = "\n".join([
        "EXPECTED_PLAN_COUNT=24",
        "EXPOSURE_AXIS_COUNT=12",
        "GAIN_AXIS_EXPOSURE=1250000",
        "ALLOWED_EXPOSURES='10000 1250000 5000000 20000000'",
        "ALLOWED_GAINS='1.0 2.0 3.75 4.0 7.5'",
    ])
    return "\n".join(
        [
            stub,
            plan_line,
            constants,
            overrides,
            validator,
            "validate_plan",
            'printf "captures_requested=%s\\n" "$CAPTURES_REQUESTED"',
        ]
    )


def run_validator(overrides: str = "") -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh")
    assert shell is not None
    return subprocess.run(
        [shell, "-c", extract_validator(overrides)],
        capture_output=True,
        text=True,
    )


def test_compiled_plan_passes_its_own_validator() -> None:
    result = run_validator()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "captures_requested=24" in result.stdout


def test_validator_rejects_a_short_plan() -> None:
    result = run_validator("CAPTURE_PLAN='10000:1.0 10000:1.0'")
    assert result.returncode == 1
    assert "failure=invalid_plan_entry_count" in result.stdout


def test_validator_rejects_an_unlisted_gain() -> None:
    plan = " ".join(["10000:1.0"] * 11 + ["10000:9.0"] + ["1250000:2.0"] * 12)
    result = run_validator(f"CAPTURE_PLAN='{plan}'")
    assert result.returncode == 1
    assert "failure=invalid_plan_gain_value" in result.stdout


def test_validator_rejects_an_unlisted_exposure() -> None:
    plan = " ".join(["10000:1.0"] * 11 + ["7000:1.0"] + ["1250000:2.0"] * 12)
    result = run_validator(f"CAPTURE_PLAN='{plan}'")
    assert result.returncode == 1
    assert "failure=plan_exposure_below_10000ns" in result.stdout


def test_validator_rejects_gain_on_the_exposure_axis() -> None:
    plan = " ".join(["10000:1.0"] * 11 + ["10000:2.0"] + ["1250000:2.0"] * 12)
    result = run_validator(f"CAPTURE_PLAN='{plan}'")
    assert result.returncode == 1
    assert "failure=exposure_axis_gain_not_one" in result.stdout


def test_validator_rejects_a_wrong_exposure_on_the_gain_axis() -> None:
    plan = " ".join(["10000:1.0"] * 12 + ["5000000:2.0"] + ["1250000:2.0"] * 11)
    result = run_validator(f"CAPTURE_PLAN='{plan}'")
    assert result.returncode == 1
    assert "failure=gain_axis_exposure_not_1250000" in result.stdout


def test_validator_rejects_a_non_numeric_exposure() -> None:
    plan = " ".join(["abc:1.0"] + ["10000:1.0"] * 11 + ["1250000:2.0"] * 12)
    result = run_validator(f"CAPTURE_PLAN='{plan}'")
    assert result.returncode == 1
    assert "failure=invalid_plan_exposure_value" in result.stdout


def test_settle_gate_runs_between_captures_not_a_reboot() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "settle_after_capture" in text
    assert "force_manual_zero" in text
    assert "lcc_process_survived_capture" in text
    assert "camera_client_after_capture_or_state_unknown" in text
    assert "media_stopped_after_capture" in text
    assert "lightsvr_stopped_after_capture" in text
    # The child must never reboot; only the supervisor does, once, at the end.
    assert "/system/bin/reboot" not in text
    assert "sys.powerctl" not in text


def test_each_capture_requires_exactly_one_new_lri() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "capture_lri_count_not_one" in text
    assert "valid_generated_lri_path" in text
    assert "capture_lri_path_invalid" in text


def test_partial_series_is_reported_separately_from_failure() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "FINAL_STATUS=PARTIAL" in text
    assert "series_aborted_after_completed_captures" in text
    assert "series_produced_no_verified_capture" in text
    assert "SERIES_ABORTED_AT=" in text


def test_a_dirty_cleanup_downgrades_a_partial_series_to_failure() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "post_series_cleanup_failed" in text
    assert text.index("CLEANUP_OK=yes") < text.index("post_series_cleanup_failed")


def test_every_capture_is_bounded_and_uses_the_async_shim() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert '/system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s"' in text
    assert "'LD_PRELOAD=$1; export LD_PRELOAD; shift; exec \"$@\"'" in text
    assert "l16-dark-frame-launch" in text
    assert '"$WORKDIR/lcc.$CAPTURE_INDEX.txt"' in text


def test_lcc_argv_is_built_per_capture_with_one_exposure_and_one_gain() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert 'set -- -m 0 -s 0 -f 1 "$MASK0" "$MASK1" "$MASK2" \\' in text
    assert '-R 4160,3120 -e "$CAPTURE_EXPOSURE" -g "$CAPTURE_GAIN"' in text
    # One -e value per capture, never the 16-value HDR form.
    assert "EXPOSURE_ARGS" not in text


def test_capture_attempt_forces_a_reboot_request() -> None:
    text = CHILD.read_text(encoding="utf-8")
    armed = '[ "$ARMED" = "$ARM_VALUE" ]'
    assert text.index(armed) < text.index("CAPTURE_ATTEMPTED=yes")
    assert text.index("CAPTURE_ATTEMPTED=yes") < text.index('"$LCC_COPY" "$@"')
    assert "NORMAL_REBOOT_REQUIRED=yes" in text


def test_preflight_verifies_every_binary_it_copies() -> None:
    text = CHILD.read_text(encoding="utf-8")
    for reason in (
        "unexpected_lcc_hash",
        "copied_lcc_hash_mismatch",
        "unexpected_async_shim_hash",
        "copied_async_shim_hash_mismatch",
        "unexpected_camera_hal_hash",
        "unexpected_build",
        "unexpected_kernel",
        "unexpected_asic_firmware",
        "manual_control_not_zero",
        "lcc_already_running",
        "insufficient_data_free_space",
    ):
        assert reason in text


def extract_series(stub_results: dict[int, str]) -> str:
    """Build a runnable fragment of the capture loop with a stubbed camera.

    The loop's own control flow -- when it breaks, what it counts, and which
    final status it reports -- is the part most likely to hold an off-by-one.
    String assertions cannot reach it, so the harness replaces only the three
    lines that invoke lcc with a scripted exit status and stubs the two gate
    functions.  Everything else, including the counting and the status
    selection, is the real code.
    """
    text = CHILD.read_text(encoding="utf-8")
    start = text.index("CAPTURE_INDEX=0\n")
    end = text.index("exit 0\n", start) + len("exit 0\n")
    loop = text[start:end]

    invocation_start = loop.index("    (\n        cd \"$WORKDIR\"")
    invocation_end = loop.index("CAPTURE_LCC_STATUS=$?\n") + len(
        "CAPTURE_LCC_STATUS=$?\n"
    )
    loop = (
        loop[:invocation_start]
        + '    CAPTURE_LCC_STATUS=$(lcc_status_stub "$CAPTURE_INDEX")\n'
        + loop[invocation_end:]
    )

    def stub_for(kind: str) -> str:
        return "\n".join(
            f'        {index}) if [ "{kind}" = "{outcome}" ]; then '
            f'abort_series "$1" stub_{kind}_failure; return 1; fi ;;'
            for index, outcome in stub_results.items()
        )

    lcc_cases = "\n".join(
        f"        {index}) printf '1\\n'; return 0 ;;"
        for index, outcome in stub_results.items()
        if outcome == "lcc"
    )
    harness = f'''
CAPTURE_PLAN='{" ".join("10000:1.0" for _ in range(24))}'
CAPTURES_REQUESTED=24
CAPTURES_COMPLETED=0
CAPTURE_ATTEMPTED=no
NORMAL_REBOOT_REQUIRED=no
SERIES_ABORTED_AT=none
SERIES_ABORT_REASON=none
FINAL_STATUS=FAIL
FINAL_REASON=harness_did_not_finish
SELECTION_DESCRIPTION=harness
TUPLE0=11
TUPLE1=F1
TUPLE2=00
CAPTURE_TIMEOUT_SECONDS=60
LRI_DIR=/harness
WORKDIR=$(mktemp -d)
MANIFEST=""
ASYNC_SHIM_STATUS=disabled

# The loop ends in `exit 0`; finish() is not part of the extracted fragment,
# so an EXIT trap is what surfaces the selected final status.
trap 'printf "final_status=%s\\nfinal_reason=%s\\n" "$FINAL_STATUS" "$FINAL_REASON"' EXIT

fail() {{
    printf 'failure=%s\\n' "$1"
    exit 1
}}

abort_series() {{
    SERIES_ABORTED_AT=$1
    SERIES_ABORT_REASON=$2
    printf 'series_aborted_at=%s\\n' "$SERIES_ABORTED_AT"
    printf 'series_abort_reason=%s\\n' "$SERIES_ABORT_REASON"
}}

snapshot_lri_paths() {{
    : > "$1"
}}

lcc_status_stub() {{
    case "$1" in
{lcc_cases}
    esac
    printf '0\\n'
    return 0
}}

settle_after_capture() {{
    case "$1" in
{stub_for("settle")}
    esac
    printf 'capture_%s_settled=yes\\n' "$1"
    return 0
}}

record_capture_lri() {{
    case "$1" in
{stub_for("record")}
    esac
    printf 'capture_%s_lri_recorded=yes\\n' "$1"
    return 0
}}
'''
    return harness + "\n" + loop


def run_series(stub_results: dict[int, str] | None = None) -> dict[str, str]:
    shell = shutil.which("sh")
    assert shell is not None
    result = subprocess.run(
        [shell, "-c", extract_series(stub_results or {})],
        capture_output=True,
        text=True,
    )
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_series_completes_all_twenty_four_captures() -> None:
    values = run_series()
    assert values["captures_completed"] == "24"
    assert values["capture_24"] == "ok"
    assert "capture_25_exposure_ns" not in values


def test_series_stops_at_a_failed_settle_gate_and_reports_partial() -> None:
    values = run_series({5: "settle"})
    assert values["captures_completed"] == "4"
    assert values["series_aborted_at"] == "5"
    assert values["series_abort_reason"] == "stub_settle_failure"
    assert "capture_6_exposure_ns" not in values


def test_series_failing_on_the_first_capture_completes_nothing() -> None:
    values = run_series({1: "settle"})
    assert values["captures_completed"] == "0"
    assert values["series_aborted_at"] == "1"


def test_series_stops_on_a_nonzero_lcc_status() -> None:
    values = run_series({10: "lcc"})
    assert values["captures_completed"] == "9"
    assert values["series_aborted_at"] == "10"
    assert values["series_abort_reason"] == "capture_lcc_nonzero_or_timeout"


def test_series_stops_when_a_capture_produces_no_attributable_lri() -> None:
    values = run_series({3: "record"})
    assert values["captures_completed"] == "2"
    assert values["series_aborted_at"] == "3"


def test_first_capture_marks_the_run_as_camera_touched() -> None:
    values = run_series({1: "settle"})
    assert values["capture_1_exposure_ns"] == "10000"


def test_complete_series_reports_pass() -> None:
    values = run_series()
    assert values["final_status"] == "PASS"
    assert values["final_reason"].startswith("full_dark_frame_series_completed")


def test_aborted_series_with_frames_reports_partial_not_failure() -> None:
    values = run_series({20: "settle"})
    assert values["final_status"] == "PARTIAL"
    assert values["final_reason"] == "series_aborted_after_completed_captures"
    assert values["captures_completed"] == "19"


def test_series_without_any_verified_capture_reports_failure() -> None:
    values = run_series({1: "settle"})
    assert values["final_status"] == "FAIL"
    assert values["final_reason"] == "series_produced_no_verified_capture"


def test_docs_pin_the_current_child_payload() -> None:
    import hashlib

    doc = (ROOT / "docs" / "dark-frame-series.md").read_text(encoding="utf-8")
    payload = CHILD.read_bytes()
    assert f"{len(payload):,}-byte" in doc
    assert hashlib.sha1(payload).hexdigest() in doc


def test_repository_readme_links_the_dark_frame_series() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/dark-frame-series.md" in readme
    assert "dark frame" in readme.lower()


def test_app_readme_states_the_plan_and_the_measured_status() -> None:
    """The README must carry the plan and a dated, concrete run status.

    This originally asserted the series had not run.  It has, so the check now
    requires the outcome to be stated rather than the absence of one -- and
    still requires the one thing the series could not measure to be named.
    """
    readme = (ROOT / "android" / "dark-frame-series" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "24" in readme
    assert "L16_LLD" in readme
    for exposure in ("10 us", "1.25 ms", "5 ms", "20 ms"):
        assert exposure in readme
    for gain in ("2.0", "3.75", "4.0", "7.5"):
        assert gain in readme
    assert "2026-08-18" in readme
    assert "24 of 24" in readme
    assert "could not measure" in readme


def test_no_numeric_comparison_exceeds_the_device_shell_word_size() -> None:
    """Android 6 on this camera is 32-bit; its shell overflows past ~2.1e9.

    The host test harness runs a 64-bit shell and therefore cannot reproduce
    this: the long-exposure profile passed every host check and was then
    refused on the device, because $((29000000000)) evaluates to -1064771072
    there and even a small left-hand value fails when the right-hand constant
    overflows.  This check reads the comparisons statically instead.
    """
    import re

    limit = 2**31 - 1
    offenders = []
    for path in (CHILD, ROOT / "device" / "dark_frame_series_hostless_supervisor.sh",
                 ROOT / "device" / "dark_frame_long_series_hostless_supervisor.sh"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # comments may quote the very example being guarded
            for match in re.finditer(r"-(?:eq|ne|lt|le|gt|ge)\s+\"?(\d+)", line):
                if int(match.group(1)) > limit:
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
            for match in re.finditer(r"\[\s+\"?(\d+)\"?\s+-(?:eq|ne|lt|le|gt|ge)", line):
                if int(match.group(1)) > limit:
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "32-bit overflow in shell arithmetic:\n" + "\n".join(offenders)


def test_exposure_bounds_are_checked_by_digit_count() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert '[ "${#PLAN_EXPOSURE}" -ge 5 ]' in text
    assert '[ "${#PLAN_EXPOSURE}" -le 11 ]' in text
    # The exact values remain enforced by the per-profile whitelist.
    assert "ALLOWED_EXPOSURES=" in text
