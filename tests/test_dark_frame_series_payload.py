from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / "device" / "dark_frame_series_once.sh"

EXPOSURE_AXIS = ["10000", "1250000", "5000000", "20000000"]
GAIN_AXIS = ["2.0", "3.75", "4.0", "7.5"]


def expected_plan() -> list[str]:
    entries = []
    for exposure in EXPOSURE_AXIS:
        entries.extend([f"{exposure}:1.0"] * 3)
    for gain in GAIN_AXIS:
        entries.extend([f"1250000:{gain}"] * 3)
    return entries


def test_child_has_valid_shell_syntax() -> None:
    shell = shutil.which("sh")
    assert shell is not None
    subprocess.run([shell, "-n", str(CHILD)], check=True)


def test_plan_is_exactly_the_specified_twenty_four_captures() -> None:
    text = CHILD.read_text(encoding="utf-8")
    plan_line = next(
        line for line in text.splitlines() if line.startswith("CAPTURE_PLAN=")
    )
    value = plan_line.split("=", 1)[1].strip().strip("'")
    entries = value.split()
    assert len(entries) == 24
    assert entries == expected_plan()


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
    assert "plan_exposure_above_20000000ns" in text


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
    plan_line = next(
        line for line in text.splitlines() if line.startswith("CAPTURE_PLAN=")
    )
    start = text.index("validate_plan() {")
    end = text.index("\n}\n", start) + len("\n}\n")
    validator = text[start:end]
    stub = (
        "fail() {\n"
        "    printf 'failure=%s\\n' \"$1\"\n"
        "    exit 1\n"
        "}\n"
    )
    constants = "\n".join(
        line
        for line in text.splitlines()
        if line.startswith(
            ("EXPECTED_PLAN_COUNT=", "EXPOSURE_AXIS_COUNT=", "GAIN_AXIS_EXPOSURE=")
        )
    )
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
