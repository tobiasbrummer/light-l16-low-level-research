# All-16 dark frame series implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hostless Android app that records 24 all-16 dark frames across
four integration times and five gains in one root session, plus a host tool that
reduces the result to per-module black level, dark current, read noise, and the
requested-versus-recorded gain mapping.

**Architecture:** The app follows the established two-button pattern of
`android/a1-capture`: a read-only preflight arms a single capture trigger, which
hands a hash-pinned supervisor to the vendor `fihop` root runner, which stages
and invokes a hash-pinned child script. The child is new rather than a ninth
profile of `device/a1_capture_once.sh`, because a capture series changes the
control flow of that file and its hash is pinned by three shipping apps. The
child iterates a compiled-in 24-entry plan, running the existing settle checks
between captures instead of the existing reboot-after-every-attempt policy.

**Tech Stack:** POSIX shell for the device payloads (Android 6 toybox, no
bashisms), Java 8 without support libraries for the app, `aapt`/`d8`/`apksigner`
from the Android SDK build tools, pytest for host tests, NumPy for the analysis
tool only.

**Spec:** `docs/dark-frame-series.md`. Read it before starting. Every value
below is taken from it.

## Status: complete, not yet run on a camera

All eight tasks are implemented and committed on branch `dark-frame-series`.
The full test suite passes and the APK builds and verifies.

Three things turned out differently from the plan as written:

- The plan's verification of the RAW10 bit order (`max() <= 1023`) cannot
  distinguish the two candidate orderings, because they differ by at most
  3 DN. The order is therefore documented as an assumption that follows MIPI
  CSI-2, not as a measurement. It affects no reported statistic.
- Task 8's first step had to find where the pixels live. They sit before the
  protobuf message, and each surface carries its own offset in surface field 5,
  which `verify_stock_capture.py` does not read.
- The device payloads and the supervisor verdict are tested by execution
  rather than only by string assertions: the plan's static checks could not
  reach the loop's abort arithmetic or the PASS/PARTIAL selection.

What remains is physical: cover the lens, run the series, pull the frames, and
decode them with `tools/analyze_dark_frame_series.py` before any radiometric
claim enters the documentation.

## Global Constraints

- Target build `00WW_1_351`, LightOS 1.3.5.1, kernel `3.18.20-perf-g32d1d1c`, SELinux permissive.
- Module mask `FE FF 01`, factory tuple `11 F1 00`, resolution `4160,3120`, one capture frame.
- Exactly 24 captures, compiled in, in fixed order. No parameter is editable from the app.
- Integration times, in ns: `10000`, `1250000`, `5000000`, `20000000`.
- Gains: `1.0`, `2.0`, `3.75`, `4.0`, `7.5`.
- Exposure axis: the four times, three repeats each, all at gain `1.0`. Runs first, ascending.
- Gain axis: gains `2.0`, `3.75`, `4.0`, `7.5`, three repeats each, all at `1250000` ns. Runs second, ascending.
- No autofocus. `USE_A1_AF_SHIM` and `RUN_AUTOFOCUS` stay `no`; the async LRI writer shim stays `yes`.
- Per-capture timeout 60 s; supervisor bounds the whole child at 2400 s.
- `MIN_DATA_FREE_KB=8388608` (8 GiB) checked against `/data`.
- Package `io.github.tobiasbrummer.lightl16.darkframe`, app label `L16 Dark Frame Series`.
- One normal reboot after the series ends, whether it completed or aborted.
- Payload hashes are pinned at three layers: child in supervisor, supervisor and child in the Java source, all of them in the build script.
- Device scripts must pass `sh -n`. No bashisms, no arrays, no `local`.
- Python tests: `ROOT = Path(__file__).resolve().parents[1]`, no dependencies beyond pytest.
- Repository markdown carries no emoji and no YAML frontmatter.

## Terminology

A **capture** is one `lcc` invocation producing one LRI. A **cell** is one
(integration time, gain) pair; each cell has three captures. The **series** is
all 24 captures.

---

### Task 1: Child script skeleton and plan validation

Builds the new child script up to but not including any `lcc` invocation: the
compiled-in plan, its independent validation, and the refusal paths. At the end
of this task the script can be armed and will run its preflight, but it cannot
capture.

**Files:**
- Create: `device/dark_frame_series_once.sh`
- Create: `tests/test_dark_frame_series_payload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the invocation path `/data/local/tmp/light_l16_dark_frame_series_once.sh`, the arm file `/data/local/tmp/light_l16_dark_frame_series.armed` with value `DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE`, the result file `/data/local/tmp/light_l16_dark_frame_series.result`, and the shell variable `CAPTURE_PLAN` holding 24 `<exposure_ns>:<gain>` tokens.

- [x] **Step 1: Write the failing test**

Create `tests/test_dark_frame_series_payload.py`:

```python
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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dark_frame_series_payload.py -v`
Expected: all tests FAIL, because `device/dark_frame_series_once.sh` does not exist.

- [x] **Step 3: Create the child script header, plan, and constants**

Create `device/dark_frame_series_once.sh` starting with:

```sh
#!/system/bin/sh
# SPDX-License-Identifier: MIT
# DANGER: after all fixed preconditions pass, this executes a fixed series of
# 24 lcc captures with the lens covered.  It is intentionally not a general
# camera or root wrapper.  The plan below is compiled in; the script accepts no
# arguments and no parameter is reachable from the app.

PATH=/sbin:/vendor/bin:/system/sbin:/system/bin:/system/xbin
export PATH

[ "$0" = /data/local/tmp/light_l16_dark_frame_series_once.sh ] || {
    printf 'refusing unexpected invocation path: %s\n' "$0" >&2
    exit 2
}
[ "$#" -eq 0 ] || {
    printf 'refusing unexpected arguments\n' >&2
    exit 2
}

# Exposure axis first at gain 1.0, ascending time; then the gain axis at
# 1.25 ms, ascending gain.  Three repeats per cell.  The exposure axis uses the
# already exercised gain 1.0, so a refusal on the untested gain axis cannot
# cost the exposure measurement.
CAPTURE_PLAN='10000:1.0 10000:1.0 10000:1.0 1250000:1.0 1250000:1.0 1250000:1.0 5000000:1.0 5000000:1.0 5000000:1.0 20000000:1.0 20000000:1.0 20000000:1.0 1250000:2.0 1250000:2.0 1250000:2.0 1250000:3.75 1250000:3.75 1250000:3.75 1250000:4.0 1250000:4.0 1250000:4.0 1250000:7.5 1250000:7.5 1250000:7.5'
EXPECTED_PLAN_COUNT=24
EXPOSURE_AXIS_COUNT=12

RUN_AUTOFOCUS=no
RUN_FACTORY_ASIC_RESET=no
USE_A1_AF_SHIM=no
USE_ASYNC_SHIM=yes
GAIN_AXIS_EXPOSURE=1250000

OUT=/data/local/tmp/light_l16_dark_frame_series.result
ARM_FILE=/data/local/tmp/light_l16_dark_frame_series.armed
ARM_VALUE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
WORK_PREFIX=/data/local/tmp/light_l16_dark_frame_series_run
MODE=DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE
MASK0=FE
MASK1=FF
MASK2=01
SELECTION_DESCRIPTION='mask=FE FF 01 modules=A1-A5,B1-B5,C1-C6 asics=1,2,3 async_shim=required dark_frame_series=24_captures'
CAPTURE_TIMEOUT_SECONDS=60
MIN_DATA_FREE_KB=8388608
DIAGNOSTIC_LOG_LINES=2000
TUPLE0=11
TUPLE1=F1
TUPLE2=00
```

Then copy the constant block from `device/a1_capture_once.sh` lines 170-192
verbatim (`LCC_SOURCE` through `EXPECTED_AF_SHIM_SHA1`), dropping the two
`AF_SHIM` lines and the four `AUTOFOCUS_*` geometry lines, which this profile
does not use.

Then add the series state variables, replacing the single-capture ones:

```sh
CAPTURE_ATTEMPTED=no
CAPTURES_REQUESTED=0
CAPTURES_COMPLETED=0
SERIES_ABORTED_AT=none
SERIES_ABORT_REASON=none
FINAL_STATUS=FAIL
FINAL_REASON=wrapper_did_not_finish
NORMAL_REBOOT_REQUIRED=no
CLEANUP_OK=no
WORKDIR=
LCC_COPY=
SHIM_COPY=
ASYNC_SHIM_STATUS=disabled
MANIFEST=
SETTLED_CAMERA_CLIENTS=unknown
MEDIA_AFTER=unknown
LIGHTSVR_AFTER=unknown
```

- [x] **Step 4: Copy the helper functions**

Copy `device/a1_capture_once.sh` lines 231-329 verbatim into the new script:
`clear_runner`, `manual_is_zero`, `force_manual_zero`, `camera_clients_none`,
`snapshot_lri_paths`, `path_in_snapshot`, `valid_generated_lri_path`,
`capture_diagnostics`, and `fail`. Omit `read_decimal_tid`, which only the
autofocus path uses.

- [x] **Step 5: Add the plan validation**

Insert after the helper functions:

```sh
validate_plan() {
    PLAN_INDEX=0
    for PLAN_ENTRY in $CAPTURE_PLAN; do
        PLAN_INDEX=$((PLAN_INDEX + 1))
        PLAN_EXPOSURE=${PLAN_ENTRY%%:*}
        PLAN_GAIN=${PLAN_ENTRY##*:}
        case "$PLAN_EXPOSURE" in
            ""|*[!0-9]*) fail invalid_plan_exposure_value ;;
        esac
        [ "$PLAN_EXPOSURE" -ge 10000 ] || fail plan_exposure_below_10000ns
        [ "$PLAN_EXPOSURE" -le 20000000 ] || fail plan_exposure_above_20000000ns
        case "$PLAN_EXPOSURE" in
            10000|1250000|5000000|20000000) ;;
            *) fail invalid_plan_exposure_value ;;
        esac
        case "$PLAN_GAIN" in
            1.0|2.0|3.75|4.0|7.5) ;;
            *) fail invalid_plan_gain_value ;;
        esac
        if [ "$PLAN_INDEX" -le "$EXPOSURE_AXIS_COUNT" ]; then
            [ "$PLAN_GAIN" = "1.0" ] || fail exposure_axis_gain_not_one
        else
            [ "$PLAN_EXPOSURE" = "$GAIN_AXIS_EXPOSURE" ] || \
                fail gain_axis_exposure_not_1250000
        fi
    done
    [ "$PLAN_INDEX" -eq "$EXPECTED_PLAN_COUNT" ] || fail invalid_plan_entry_count
    CAPTURES_REQUESTED=$PLAN_INDEX
}
```

- [x] **Step 6: Add the setup, traps, and arm consumption**

Copy `device/a1_capture_once.sh` lines 500-528 verbatim (from the
`clear_runner` call through `printf 'workdir_created=%s\n' "$WORKDIR"`), then
call `validate_plan` immediately after the arm token is consumed, so a malformed
plan is refused before any device state is touched:

```sh
validate_plan
printf 'captures_requested=%s\n' "$CAPTURES_REQUESTED"
printf 'capture_plan=%s\n' "$CAPTURE_PLAN"
```

Leave `finish()` unimplemented for now; add a placeholder that exits so the file
parses:

```sh
finish() {
    ORIGINAL_STATUS=$?
    trap - EXIT HUP INT TERM
    clear_runner
    return "$ORIGINAL_STATUS"
}
```

- [x] **Step 7: Add behavioural tests for the validator**

The assertions above only prove that the error strings appear in the file.
`validate_plan` is plain POSIX shell with no Android dependency, so extract it
and run it. Add `extract_validator(overrides)`, which pulls `CAPTURE_PLAN`, the
three plan constants, and the `validate_plan` body out of the script, prepends a
`fail()` stub that prints `failure=<reason>` and exits 1, and appends a call.
Then assert one case per refusal path: the compiled plan passes and reports
`captures_requested=24`; a two-entry plan gives `invalid_plan_entry_count`; gain
`9.0` gives `invalid_plan_gain_value`; a 7000 ns entry gives
`plan_exposure_below_10000ns`; gain `2.0` in the first twelve gives
`exposure_axis_gain_not_one`; a 5 ms entry in the last twelve gives
`gain_axis_exposure_not_1250000`; and a non-numeric exposure gives
`invalid_plan_exposure_value`.

- [x] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dark_frame_series_payload.py -v`
Expected: all 14 tests PASS.

- [x] **Step 9: Commit**

```bash
git add device/dark_frame_series_once.sh tests/test_dark_frame_series_payload.py
git commit -m "Add dark frame series plan and validation"
```

---

### Task 2: Child script preflight and capture series

Completes the child: preflight, the 24-capture loop with a settle gate between
captures, the per-capture LRI attribution, the manifest, and the PARTIAL
semantics.

**Files:**
- Modify: `device/dark_frame_series_once.sh`
- Modify: `tests/test_dark_frame_series_payload.py`

**Interfaces:**
- Consumes: `CAPTURE_PLAN`, `validate_plan`, and the helper functions from Task 1.
- Produces: the result file keys `mode`, `captures_requested`, `captures_completed`, `capture_plan`, `series_aborted_at`, `series_abort_reason`, `capture_<index>_exposure_ns`, `capture_<index>_gain`, `capture_<index>_lri_path`, `capture_<index>_lri_size`, `capture_<index>_lri_sha1`, `cleanup_ok`, `capture_attempted`, `normal_reboot_required`, `workdir`, `final_status`, `final_reason`. `final_status` is one of `PASS`, `PARTIAL`, `FAIL`.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_dark_frame_series_payload.py`:

```python
def test_settle_gate_runs_between_captures_not_a_reboot() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert "settle_after_capture" in text
    assert "force_manual_zero" in text
    assert "lcc_process_survived_capture" in text
    assert "camera_client_after_capture_or_state_unknown" in text
    assert "media_stopped_after_capture" in text
    assert "lightsvr_stopped_after_capture" in text
    # The series must not reboot between captures; only the supervisor reboots.
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
    assert "captures_completed=" in text
    assert "SERIES_ABORTED_AT=" in text


def test_every_capture_is_bounded_and_uses_the_async_shim() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert '/system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s"' in text
    assert "LD_PRELOAD=$1; export LD_PRELOAD; shift; exec \"$@\"" in text
    assert "l16-dark-frame-launch" in text
    assert 'lcc.$CAPTURE_INDEX.txt' in text or 'lcc.${CAPTURE_INDEX}.txt' in text


def test_lcc_argv_is_built_per_capture_with_one_exposure_and_one_gain() -> None:
    text = CHILD.read_text(encoding="utf-8")
    assert 'set -- -m 0 -s 0 -f 1 "$MASK0" "$MASK1" "$MASK2" \\' in text
    assert '-R 4160,3120 -e "$CAPTURE_EXPOSURE" -g "$CAPTURE_GAIN"' in text


def test_capture_attempt_forces_a_reboot_request() -> None:
    text = CHILD.read_text(encoding="utf-8")
    armed = '[ "$ARMED" = "$ARM_VALUE" ]'
    assert text.index(armed) < text.index("CAPTURE_ATTEMPTED=yes")
    assert text.index("CAPTURE_ATTEMPTED=yes") < text.index("$LCC_COPY \"$@\"")
    assert "NORMAL_REBOOT_REQUIRED=yes" in text
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dark_frame_series_payload.py -v`
Expected: the six new tests FAIL; the seven from Task 1 still PASS.

- [x] **Step 3: Add the preflight**

Copy `device/a1_capture_once.sh` lines 529-664 into the new script, after the
`validate_plan` call. This is the identity, build, kernel, SELinux, service,
ASIC firmware, `manual_control`, UDP port, free space, and LRI directory block.
Drop the `RUN_FACTORY_ASIC_RESET` and autofocus branches, which are `no` here.
Then copy lines 666-690: diagnostics, the pre-capture camera client check, the
`lcc` copy with its hash check, and the async shim copy with its hash check.

- [x] **Step 4: Add the capture series loop**

Insert after the preflight:

```sh
MANIFEST="$WORKDIR/series.manifest"
: > "$MANIFEST" || fail cannot_create_manifest

printf '%s\n' "$SELECTION_DESCRIPTION"
printf 'factory_tuple=%s %s %s\n' "$TUPLE0" "$TUPLE1" "$TUPLE2"
printf 'series_policy=settle_gate_between_captures_single_reboot_after_series\n'

CAPTURE_INDEX=0
for PLAN_ENTRY in $CAPTURE_PLAN; do
    CAPTURE_INDEX=$((CAPTURE_INDEX + 1))
    CAPTURE_EXPOSURE=${PLAN_ENTRY%%:*}
    CAPTURE_GAIN=${PLAN_ENTRY##*:}
    printf 'capture_%s_exposure_ns=%s\n' "$CAPTURE_INDEX" "$CAPTURE_EXPOSURE"
    printf 'capture_%s_gain=%s\n' "$CAPTURE_INDEX" "$CAPTURE_GAIN"

    snapshot_lri_paths "$WORKDIR/lri.before.$CAPTURE_INDEX.txt" || \
        abort_series "$CAPTURE_INDEX" cannot_snapshot_lri_before

    # From this assignment onward a camera attempt has happened, so the
    # supervisor must reboot regardless of how the series ends.
    CAPTURE_ATTEMPTED=yes
    NORMAL_REBOOT_REQUIRED=yes

    set -- -m 0 -s 0 -f 1 "$MASK0" "$MASK1" "$MASK2" \
        "$TUPLE0" "$TUPLE1" "$TUPLE2" \
        -R 4160,3120 -e "$CAPTURE_EXPOSURE" -g "$CAPTURE_GAIN"
    (
        cd "$WORKDIR" || exit 126
        /system/bin/timeout -k 5s "${CAPTURE_TIMEOUT_SECONDS}s" \
            /system/bin/sh -c \
            'LD_PRELOAD=$1; export LD_PRELOAD; shift; exec "$@"' \
            l16-dark-frame-launch "$SHIM_COPY" "$LCC_COPY" "$@"
    ) > "$WORKDIR/lcc.$CAPTURE_INDEX.txt" 2>&1
    CAPTURE_LCC_STATUS=$?
    printf 'capture_%s_lcc_returned=%s\n' "$CAPTURE_INDEX" "$CAPTURE_LCC_STATUS"

    settle_after_capture "$CAPTURE_INDEX" || break
    record_capture_lri "$CAPTURE_INDEX" || break
    [ "$CAPTURE_LCC_STATUS" = "0" ] || {
        abort_series "$CAPTURE_INDEX" capture_lcc_nonzero_or_timeout
        break
    }
    CAPTURES_COMPLETED=$CAPTURE_INDEX
    printf 'capture_%s=ok\n' "$CAPTURE_INDEX"
done
```

- [x] **Step 5: Add the settle, record, and abort helpers**

Insert these before the loop, after `validate_plan`:

```sh
abort_series() {
    SERIES_ABORTED_AT=$1
    SERIES_ABORT_REASON=$2
    printf 'series_aborted_at=%s\n' "$SERIES_ABORTED_AT"
    printf 'series_abort_reason=%s\n' "$SERIES_ABORT_REASON"
    return 1
}

settle_after_capture() {
    SETTLE_INDEX=$1
    force_manual_zero || {
        abort_series "$SETTLE_INDEX" manual_control_cleanup_failed
        return 1
    }
    if /system/bin/toybox pgrep -x lcc >/dev/null 2>&1; then
        abort_series "$SETTLE_INDEX" lcc_process_survived_capture
        return 1
    fi
    camera_clients_none "$WORKDIR/camera.after.$SETTLE_INDEX.txt" || {
        abort_series "$SETTLE_INDEX" camera_client_after_capture_or_state_unknown
        return 1
    }
    [ "$(getprop init.svc.media)" = "running" ] || {
        abort_series "$SETTLE_INDEX" media_stopped_after_capture
        return 1
    }
    [ "$(getprop init.svc.lightsvr)" = "running" ] || {
        abort_series "$SETTLE_INDEX" lightsvr_stopped_after_capture
        return 1
    }
    printf 'capture_%s_settled=yes\n' "$SETTLE_INDEX"
    return 0
}

record_capture_lri() {
    RECORD_INDEX=$1
    snapshot_lri_paths "$WORKDIR/lri.after.$RECORD_INDEX.txt" || {
        abort_series "$RECORD_INDEX" cannot_snapshot_lri_after
        return 1
    }
    : > "$WORKDIR/lri.new.$RECORD_INDEX.txt" || {
        abort_series "$RECORD_INDEX" cannot_create_lri_delta
        return 1
    }
    while IFS= read -r FILE; do
        [ -n "$FILE" ] || continue
        if ! path_in_snapshot "$FILE" "$WORKDIR/lri.before.$RECORD_INDEX.txt"
        then
            printf '%s\n' "$FILE" >> "$WORKDIR/lri.new.$RECORD_INDEX.txt" || {
                abort_series "$RECORD_INDEX" cannot_record_new_lri
                return 1
            }
        fi
    done < "$WORKDIR/lri.after.$RECORD_INDEX.txt"
    RECORD_COUNT=$(
        /system/bin/toybox wc -l < "$WORKDIR/lri.new.$RECORD_INDEX.txt"
    ) || {
        abort_series "$RECORD_INDEX" cannot_count_new_lri
        return 1
    }
    [ "$RECORD_COUNT" = "1" ] || {
        abort_series "$RECORD_INDEX" capture_lri_count_not_one
        return 1
    }
    RECORD_PATH=$(
        /system/bin/toybox sed -n '1p' "$WORKDIR/lri.new.$RECORD_INDEX.txt"
    ) || {
        abort_series "$RECORD_INDEX" cannot_read_new_lri_path
        return 1
    }
    valid_generated_lri_path "$RECORD_PATH" || {
        abort_series "$RECORD_INDEX" capture_lri_path_invalid
        return 1
    }
    RECORD_SIZE=$(/system/bin/toybox wc -c < "$RECORD_PATH") || {
        abort_series "$RECORD_INDEX" cannot_size_new_lri
        return 1
    }
    [ "$RECORD_SIZE" -ge 32 ] || {
        abort_series "$RECORD_INDEX" new_lri_too_small
        return 1
    }
    RECORD_SHA1=$(/system/bin/toybox sha1sum "$RECORD_PATH") || {
        abort_series "$RECORD_INDEX" cannot_hash_new_lri
        return 1
    }
    RECORD_SHA1=${RECORD_SHA1%% *}
    printf 'capture_%s_lri_path=%s\n' "$RECORD_INDEX" "$RECORD_PATH"
    printf 'capture_%s_lri_size=%s\n' "$RECORD_INDEX" "$RECORD_SIZE"
    printf 'capture_%s_lri_sha1=%s\n' "$RECORD_INDEX" "$RECORD_SHA1"
    printf '%s %s %s %s %s\n' "$RECORD_INDEX" "$CAPTURE_EXPOSURE" \
        "$CAPTURE_GAIN" "$RECORD_SIZE" "$RECORD_SHA1" >> "$MANIFEST"
    printf '%s\n' "$RECORD_PATH" >> "$MANIFEST.paths"
    return 0
}
```

`abort_series` prints the reason to stdout, which the script has already
redirected into the result file, and the caller returns 1 on the next line.
Do not write `return $(abort_series ...)`: command substitution would swallow
the printed reason and hand `return` a string instead of a status.

- [x] **Step 6: Add the final status and finish handler**

After the loop:

```sh
CLEANUP_OK=yes
MANUAL_AFTER=$(cat "$MANUAL_CONTROL" 2>/dev/null)
SETTLED_CAMERA_CLIENTS=none
MEDIA_AFTER=$(getprop init.svc.media)
LIGHTSVR_AFTER=$(getprop init.svc.lightsvr)
printf 'captures_completed=%s\n' "$CAPTURES_COMPLETED"

if [ "$CAPTURES_COMPLETED" -eq "$CAPTURES_REQUESTED" ]; then
    FINAL_STATUS=PASS
    FINAL_REASON=full_dark_frame_series_completed_settled_cleanup_content_not_validated
elif [ "$CAPTURES_COMPLETED" -gt 0 ]; then
    FINAL_STATUS=PARTIAL
    FINAL_REASON=series_aborted_after_completed_captures
else
    FINAL_STATUS=FAIL
    FINAL_REASON=series_produced_no_verified_capture
fi
exit 0
```

Replace the placeholder `finish()` from Task 1 with the real one, modelled on
`device/a1_capture_once.sh` lines 331-498 but reporting the series keys:

```sh
finish() {
    ORIGINAL_STATUS=$?
    trap - EXIT HUP INT TERM

    clear_runner
    if [ "$CAPTURE_ATTEMPTED" = "yes" ]; then
        NORMAL_REBOOT_REQUIRED=yes
        force_manual_zero || CLEANUP_OK=no
    fi
    capture_diagnostics after

    printf 'captures_requested=%s\n' "$CAPTURES_REQUESTED"
    printf 'captures_completed=%s\n' "$CAPTURES_COMPLETED"
    printf 'series_aborted_at=%s\n' "$SERIES_ABORTED_AT"
    printf 'series_abort_reason=%s\n' "$SERIES_ABORT_REASON"
    printf 'capture_attempted=%s\n' "$CAPTURE_ATTEMPTED"
    printf 'normal_reboot_required=%s\n' "$NORMAL_REBOOT_REQUIRED"
    printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
    printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
    printf 'settled_camera_clients=%s\n' "$SETTLED_CAMERA_CLIENTS"
    printf 'media_after=%s\n' "$MEDIA_AFTER"
    printf 'lightsvr_after=%s\n' "$LIGHTSVR_AFTER"
    printf 'workdir=%s\n' "$WORKDIR"
    printf 'final_reason=%s\n' "$FINAL_REASON"
    printf 'final_status=%s\n' "$FINAL_STATUS"
    return "$ORIGINAL_STATUS"
}
```

- [x] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dark_frame_series_payload.py -v`
Expected: all 13 tests PASS.

Also run: `sh -n device/dark_frame_series_once.sh`
Expected: no output, exit 0.

- [x] **Step 8: Commit**

```bash
git add device/dark_frame_series_once.sh tests/test_dark_frame_series_payload.py
git commit -m "Add bounded dark frame capture series with settle gate"
```

---

### Task 3: Root supervisor

The supervisor is what the vendor `fihop` runner executes as UID 0. It accepts
no arguments, verifies and stages the child and the async shim, bounds the child
at 2400 s, mirrors the child's manifest into the app-readable result, and
reboots after any possible camera attempt.

**Files:**
- Create: `device/dark_frame_series_hostless_supervisor.sh`
- Create: `tests/test_dark_frame_series_supervisor.py`

**Interfaces:**
- Consumes: the child result keys from Task 2.
- Produces: the app-visible result at `/data/data/io.github.tobiasbrummer.lightl16.darkframe/files/r.txt`, containing `supervisor=L16_HOSTLESS_DARK_FRAME_SERIES_V1`, `supervisor_complete` (`PASS`, `PARTIAL`, `PREFLIGHT_FAIL`, or `FAIL`), `supervisor_decision`, `captures_completed`, `captures_requested`, and the mirrored per-capture lines.
- App arm token: `L16_HOSTLESS_DARK_FRAME_SERIES_SUPERVISOR_ONCE_V1` at `<private>/a`.

- [x] **Step 1: Write the failing test**

Create `tests/test_dark_frame_series_supervisor.py`:

```python
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
    assert "EXPECTED_ASYNC_SHIM_SIZE=8904" in text
    assert (
        "EXPECTED_ASYNC_SHIM_SHA1=150e53a736624010dc7fb741490ea8dca7afbfb8"
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
    assert 'CHILD_FINAL_STATUS" = "PASS"' in text
    assert 'CHILD_FINAL_STATUS" = "PARTIAL"' in text
    assert "SUPERVISOR_STATUS=PARTIAL" in text
    assert "child_series_produced_no_verified_capture" in text


def test_supervisor_reboots_after_any_possible_camera_attempt() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "REBOOT_REQUIRED=yes" in text
    assert "/system/bin/reboot" in text
    assert "normal_reboot_after_dark_frame_series" in text
    assert "no_reboot_after_proven_preflight_failure" in text


def test_supervisor_mirrors_the_child_manifest_before_rebooting() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert "series.manifest" in text
    assert text.index("series.manifest") < text.index("/system/bin/reboot")


def test_supervisor_clears_the_runner_before_any_other_action() -> None:
    text = SUPERVISOR.read_text(encoding="utf-8")
    assert text.index("clear_runner") < text.index("IDENTITY=$(id)")
    assert PRIVATE_DIR in text
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dark_frame_series_supervisor.py -v`
Expected: all 9 tests FAIL, because the supervisor does not exist.

- [x] **Step 3: Create the supervisor from the established pattern**

Copy `device/a1_hostless_capture_supervisor.sh` to
`device/dark_frame_series_hostless_supervisor.sh` and apply these changes:

- `APP_DIR` becomes `/data/data/io.github.tobiasbrummer.lightl16.darkframe/files`.
- `APP_ARM_VALUE` becomes `L16_HOSTLESS_DARK_FRAME_SERIES_SUPERVISOR_ONCE_V1`.
- `CHILD` becomes `/data/local/tmp/light_l16_dark_frame_series_once.sh`.
- `CHILD_RESULT` becomes `/data/local/tmp/light_l16_dark_frame_series.result`.
- `CHILD_ARM` becomes `/data/local/tmp/light_l16_dark_frame_series.armed`.
- `CHILD_ARM_VALUE` becomes `DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE`.
- `EXPECTED_MODE` becomes `DARK_FRAME_SERIES_ALL16_24_CAPTURES_ONCE`.
- The `APP_AF_SHIM` / `AF_SHIM` pair becomes `APP_ASYNC_SHIM=$APP_DIR/n.so` and `ASYNC_SHIM=/data/local/tmp/liblcc_async_writer_shim.so`, with `EXPECTED_ASYNC_SHIM_SIZE=8904` and `EXPECTED_ASYNC_SHIM_SHA1=150e53a736624010dc7fb741490ea8dca7afbfb8`. The staged shim is `chmod 0400`, matching the AF shim handling.
- Delete the `EXPECTED_AUTOFOCUS_RESPONSE` constant and every `autofocus_*` and `a1_af_shim` field check; this profile has no autofocus.
- Replace `EXPECTED_EXPOSURE_*` with the series fields: `EXPECTED_CAPTURES_REQUESTED=24`.
- The child invocation becomes:

```sh
/system/bin/timeout -k 10s 2400s /system/bin/sh "$CHILD"
```

- [x] **Step 4: Replace the single-capture result checks with series checks**

Replace the block from `RESULT_MODE=$(result_field mode)` to the end with:

```sh
RESULT_MODE=$(result_field mode)
CAPTURES_REQUESTED=$(result_field captures_requested)
CAPTURES_COMPLETED=$(result_field captures_completed)
SERIES_ABORTED_AT=$(result_field series_aborted_at)
SERIES_ABORT_REASON=$(result_field series_abort_reason)
CLEANUP_OK=$(result_field cleanup_ok)
MANUAL_AFTER=$(result_field manual_control_after)
MEDIA_AFTER=$(result_field media_after)
LIGHTSVR_AFTER=$(result_field lightsvr_after)
WORKDIR=$(result_field workdir)

printf 'mode=%s\n' "$RESULT_MODE"
printf 'captures_requested=%s\n' "$CAPTURES_REQUESTED"
printf 'captures_completed=%s\n' "$CAPTURES_COMPLETED"
printf 'series_aborted_at=%s\n' "$SERIES_ABORTED_AT"
printf 'series_abort_reason=%s\n' "$SERIES_ABORT_REASON"
printf 'cleanup_ok=%s\n' "$CLEANUP_OK"
printf 'manual_control_after=%s\n' "$MANUAL_AFTER"
printf 'media_after=%s\n' "$MEDIA_AFTER"
printf 'lightsvr_after=%s\n' "$LIGHTSVR_AFTER"
printf 'workdir=%s\n' "$WORKDIR"

[ "$RESULT_MODE" = "$EXPECTED_MODE" ] || fail unexpected_child_mode
[ "$CAPTURES_REQUESTED" = "$EXPECTED_CAPTURES_REQUESTED" ] || \
    fail unexpected_captures_requested
valid_decimal "$CAPTURES_COMPLETED" || fail invalid_captures_completed
[ "$CAPTURES_COMPLETED" -ge 1 ] || \
    fail child_series_produced_no_verified_capture
[ "$CLEANUP_OK" = "yes" ] || fail child_cleanup_not_verified
case "$MANUAL_AFTER" in
    *0x0) ;;
    *) fail child_manual_control_not_zero ;;
esac
[ "$MEDIA_AFTER" = "running" ] || fail child_media_not_running
[ "$LIGHTSVR_AFTER" = "running" ] || fail child_lightsvr_not_running

# Mirror the child's per-capture manifest so the app can report the retained
# frames without re-entering the camera path.  A copy failure must not change
# capture or reboot policy.
if [ -f "$WORKDIR/series.manifest" ]; then
    printf 'manifest_begin\n'
    /system/bin/toybox cat "$WORKDIR/series.manifest" 2>/dev/null
    printf 'manifest_end\n'
fi

if [ "$CHILD_FINAL_STATUS" = "PASS" ] && \
    [ "$CAPTURES_COMPLETED" = "$EXPECTED_CAPTURES_REQUESTED" ]
then
    SUPERVISOR_STATUS=PASS
    SUPERVISOR_REASON=full_dark_frame_series_recorded_and_child_cleanup_verified
else
    SUPERVISOR_STATUS=PARTIAL
    SUPERVISOR_REASON=partial_dark_frame_series_recorded_and_child_cleanup_verified
fi
SUPERVISOR_DECISION=normal_reboot_after_dark_frame_series
exit 0
```

Adjust the earlier gate so `PARTIAL` is not rejected: change
`[ "$CHILD_FINAL_STATUS" = "PASS" ] || fail child_capture_failed` to

```sh
case "$CHILD_FINAL_STATUS" in
    PASS|PARTIAL) ;;
    *) fail child_series_failed ;;
esac
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_dark_frame_series_supervisor.py -v`
Expected: all 9 tests PASS.

- [x] **Step 6: Commit**

```bash
git add device/dark_frame_series_hostless_supervisor.sh tests/test_dark_frame_series_supervisor.py
git commit -m "Add dark frame series root supervisor"
```

---

### Task 4: Android app shell and payload staging

The app: manifest, three-button flow, preflight, payload staging with hash
verification, arm token, runner trigger, and result polling. The darkness check
is a separate task; here the middle button exists but only records that the
check has not run.

**Files:**
- Create: `android/dark-frame-series/AndroidManifest.xml`
- Create: `android/dark-frame-series/src/io/github/tobiasbrummer/lightl16/darkframe/MainActivity.java`
- Create: `tests/test_android_dark_frame_series.py`

**Interfaces:**
- Consumes: the supervisor arm token and result keys from Task 3.
- Produces: the private payload paths `<private>/s.sh` (supervisor), `<private>/c.sh` (child), `<private>/n.so` (async shim), `<private>/r.txt` (result), `<private>/a` (arm token); the external mirror `/sdcard/Android/data/io.github.tobiasbrummer.lightl16.darkframe/files/light-l16-dark-frame-series-last-display.txt`; and the Java method `void onDarknessCheckResult(boolean dark, String report)`, which Task 5 calls.

- [x] **Step 1: Write the failing test**

Create `tests/test_android_dark_frame_series.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "android" / "dark-frame-series"
PACKAGE_DIR = "src/io/github/tobiasbrummer/lightl16/darkframe"
SOURCE = APP / PACKAGE_DIR / "MainActivity.java"
SUPERVISOR = ROOT / "device" / "dark_frame_series_hostless_supervisor.sh"
CHILD = ROOT / "device" / "dark_frame_series_once.sh"


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
    assert "android:label=\"L16 Dark Frame Series\"" in manifest


def test_app_pins_supervisor_and_child_sizes_and_hashes() -> None:
    source = SOURCE.read_text()
    assert f"EXPECTED_SUPERVISOR_SIZE = {SUPERVISOR.stat().st_size}L" in source
    assert digest(SUPERVISOR, "sha256") in source
    assert f"EXPECTED_CHILD_SIZE = {CHILD.stat().st_size}L" in source
    assert digest(CHILD, "sha256") in source
    assert "EXPECTED_ASYNC_SHIM_SIZE = 8904L" in source


def test_app_uses_only_the_fixed_runner_trigger_once() -> None:
    source = SOURCE.read_text()
    assert 'RUNNER_PROGRAM = "/system/bin/sh"' in source
    private_dir = (
        "/data/data/io.github.tobiasbrummer.lightl16.darkframe/files"
    )
    assert f'PRIVATE_DIR =\n        "{private_dir}"' in source or (
        private_dir in source
    )
    assert len(private_dir + "/s.sh") <= 91
    assert source.count('setRunnerProperty(TRIGGER, "8")') == 1
    assert "Runtime.getRuntime" not in source
    assert "ProcessBuilder" not in source


def test_app_locks_itself_to_one_series_per_installation() -> None:
    source = SOURCE.read_text()
    assert "SPENT_NAME" in source
    assert "SPENT_VALUE" in source
    assert "already_spent" in source


def test_app_requires_preflight_and_darkness_before_arming() -> None:
    source = SOURCE.read_text()
    assert "onDarknessCheckResult" in source
    assert "darknessConfirmed" in source
    assert "refusing capture without preflight" in source
    assert "refusing capture without darkness check" in source


def test_app_reports_partial_series_distinctly() -> None:
    source = SOURCE.read_text()
    assert "PARTIAL" in source
    assert "captures_completed" in source
    assert "PASS_MANIFEST_REBOOT_REQUESTED" in source
    assert "PARTIAL_MANIFEST_REBOOT_REQUESTED" in source


def test_app_mirrors_its_report_without_extra_storage_permission() -> None:
    source = SOURCE.read_text()
    assert "light-l16-dark-frame-series-last-display.txt" in source
    assert "getExternalFilesDir" in source
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_android_dark_frame_series.py -v`
Expected: all 7 tests FAIL, because the app does not exist.

- [x] **Step 3: Write the manifest**

Create `android/dark-frame-series/AndroidManifest.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="io.github.tobiasbrummer.lightl16.darkframe">

    <uses-sdk
        android:minSdkVersion="21"
        android:targetSdkVersion="23" />
    <uses-permission android:name="android.permission.CAMERA" />
    <application
        android:allowBackup="false"
        android:debuggable="false"
        android:label="L16 Dark Frame Series"
        android:theme="@android:style/Theme.Material.Light">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:screenOrientation="portrait">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
```

The camera permission is required because the darkness check in Task 5 opens
Camera2. It is the only permission; the report mirror uses
`getExternalFilesDir`, which needs none on this API level.

- [x] **Step 4: Write MainActivity**

Copy `android/a1-capture/src/io/github/tobiasbrummer/lightl16/a1capture/MainActivity.java`
as the base and apply these changes:

- Package and `PRIVATE_DIR` move to `io.github.tobiasbrummer.lightl16.darkframe`.
- `SUPERVISOR_ASSET` becomes `dark_frame_series_hostless_supervisor.sh`, `CHILD_ASSET` becomes `dark_frame_series_once.sh`.
- The AF shim asset and `AF_SHIM_PATH` become the async shim: asset `liblcc_async_writer_shim.so`, private path `PRIVATE_DIR + "/n.so"`, `EXPECTED_ASYNC_SHIM_SIZE = 8904L` and its SHA-256 from the build.
- `ARM_VALUE` becomes `L16_HOSTLESS_DARK_FRAME_SERIES_SUPERVISOR_ONCE_V1`.
- `DISPLAY_REPORT_NAME` becomes `light-l16-dark-frame-series-last-display.txt`.
- `POLL_TIMEOUT_MS` becomes `2460000L`: the supervisor's 2400 s child bound plus the 60 s it needs to write its manifest and reboot. `ARM_WINDOW_MS` stays `60000L`.
- Add a third button between preflight and capture, labelled `2. DUNKELHEIT PRÜFEN`, and renumber the capture button to `3. DUNKELBILDSERIE STARTEN (24 AUFNAHMEN)`.
- Add the fields `private boolean preflightPassed;` and `private boolean darknessConfirmed;`, and the method:

```java
    void onDarknessCheckResult(boolean dark, String report) {
        darknessConfirmed = dark;
        line(report);
        captureButton.setEnabled(preflightPassed && darknessConfirmed);
    }
```

- In the capture handler, refuse with the exact strings the test requires:

```java
        if (!preflightPassed) {
            line("refusing capture without preflight");
            return;
        }
        if (!darknessConfirmed) {
            line("refusing capture without darkness check");
            return;
        }
```

- In the result interpretation, map the supervisor status to three outcomes
  instead of two:

```java
        String status = values.get("supervisor_complete");
        String completed = values.get("captures_completed");
        if ("PASS".equals(status)) {
            interpretation = "PASS_MANIFEST_REBOOT_REQUESTED";
        } else if ("PARTIAL".equals(status)) {
            interpretation = "PARTIAL_MANIFEST_REBOOT_REQUESTED";
        } else if ("PREFLIGHT_FAIL".equals(status)) {
            interpretation = "PREFLIGHT_FAIL_NO_REBOOT";
        } else {
            interpretation = "FAIL_AMBIGUOUS_DO_NOT_RETRY";
        }
        line("captures_completed=" + completed);
```

- Raise `MAX_RESULT_SIZE` from `16384L` to `65536L`: the mirrored manifest adds
  24 capture lines plus the per-capture keys, which do not fit the old bound.

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_android_dark_frame_series.py -v`
Expected: all 7 tests PASS.

- [x] **Step 6: Commit**

```bash
git add android/dark-frame-series tests/test_android_dark_frame_series.py
git commit -m "Add dark frame series app shell and payload staging"
```

---

### Task 5: Camera2 darkness check

Confirms the lens is covered before a 25-minute series starts. Opens a preview,
lets AE converge, and requires the scene to stay dark at the maximum
sensitivity the device reports. Camera2 is fully closed before the root trigger
can fire.

**Files:**
- Create: `android/dark-frame-series/src/io/github/tobiasbrummer/lightl16/darkframe/DarknessCheck.java`
- Modify: `android/dark-frame-series/src/io/github/tobiasbrummer/lightl16/darkframe/MainActivity.java`
- Modify: `tests/test_android_dark_frame_series.py`

**Interfaces:**
- Consumes: `MainActivity.onDarknessCheckResult(boolean, String)` from Task 4.
- Produces: `DarknessCheck.start(Activity, Callback)` and `DarknessCheck.close()`, where `Callback` is `void onResult(boolean dark, String report)`.

- [x] **Step 1: Write the failing test**

Append to `tests/test_android_dark_frame_series.py`:

```python
DARKNESS = APP / PACKAGE_DIR / "DarknessCheck.java"


def test_darkness_check_measures_yuv_luma_at_maximum_sensitivity() -> None:
    source = DARKNESS.read_text()
    assert "ImageFormat.YUV_420_888" in source
    assert "SENSOR_INFO_SENSITIVITY_RANGE" in source
    assert "CONTROL_AE_MODE_OFF" in source
    assert "SENSOR_SENSITIVITY" in source
    assert "SENSOR_EXPOSURE_TIME" in source


def test_darkness_check_uses_a_fixed_threshold_and_frame_count() -> None:
    source = DARKNESS.read_text()
    assert "DARK_MEAN_MAX_LUMA" in source
    assert "DARK_P999_MAX_LUMA" in source
    assert "REQUIRED_FRAMES" in source


def test_darkness_check_always_closes_camera2_before_reporting() -> None:
    source = DARKNESS.read_text()
    assert source.count("close()") >= 1
    assert "finally" in source
    assert "onResult" in source


def test_main_activity_closes_camera_before_arming_the_runner() -> None:
    source = SOURCE.read_text()
    assert "DarknessCheck" in source
    assert source.index("darknessCheck.close()") < source.index(
        'setRunnerProperty(TRIGGER, "8")'
    )
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_android_dark_frame_series.py -v`
Expected: the four new tests FAIL.

- [x] **Step 3: Write DarknessCheck**

Base it on the Camera2 pipeline in
`android/hdr-meter-probe/src/io/github/tobiasbrummer/lightl16/hdrmeterprobe/MainActivity.java`:
reuse `configureStreams` (lines 495-514), the `CameraDevice.StateCallback`
(lines 516-529), `createSession` (lines 531-547), and the `LumaAccumulator`
class (lines 175-230). Do not reuse `applyAutoPreviewSettings`; this check needs
manual exposure, not AE.

The measurement differs from the meter probe: instead of letting AE choose,
force the worst case for darkness. Set `CONTROL_AE_MODE_OFF`, `SENSOR_SENSITIVITY`
to the upper bound of `SENSOR_INFO_SENSITIVITY_RANGE`, and `SENSOR_EXPOSURE_TIME`
to 100 ms. If the scene is still dark under maximum amplification, the lens is
covered.

```java
    private static final int DARK_MEAN_MAX_LUMA = 24;
    private static final int DARK_P999_MAX_LUMA = 64;
    private static final int REQUIRED_FRAMES = 8;
    private static final long PROBE_EXPOSURE_NS = 100000000L;
```

Accumulate luma over `REQUIRED_FRAMES` frames. Report dark when the mean luma
is at or below `DARK_MEAN_MAX_LUMA` and the 99.9th percentile is at or below
`DARK_P999_MAX_LUMA`. The percentile bound catches a light leak at one edge
that a mean would average away.

These two thresholds are starting values on an 8-bit luma scale, not calibrated
constants. The report prints the measured mean and p99.9 next to the bounds, so
the first physical run shows how much margin the cover actually has, and the
values can be tightened afterwards.

Close the camera in a `finally` block before invoking `onResult`, so no path
leaves a Camera2 client open when the root trigger fires.

- [x] **Step 4: Wire it into MainActivity**

The middle button calls `darknessCheck.start(this, callback)`; the callback
calls `onDarknessCheckResult`. In the capture handler, close the camera and
prove it is closed before arming the runner:

```java
        darknessCheck.close();
        darknessCheck = null;
        if (!DarknessCheck.isClosed()) {
            line("refusing capture with camera2 still open");
            return;
        }
        setRunnerProperty(TRIGGER, "8");
```

`DarknessCheck.isClosed()` is a static method returning whether the single
`CameraDevice` and `ImageReader` references are both null. The child script
independently re-checks this through `dumpsys media.camera` before it touches
`lcc`, so this is the app-side half of a two-sided check, not the only one.

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_android_dark_frame_series.py -v`
Expected: all 11 tests PASS.

- [x] **Step 6: Commit**

```bash
git add android/dark-frame-series tests/test_android_dark_frame_series.py
git commit -m "Add Camera2 darkness check before dark frame series"
```

---

### Task 6: Build script and the hash chain

Wires the three payloads into a signed APK and closes the pin chain. This task
must run after Tasks 1-5, because every pinned hash covers a finished file.

**Files:**
- Create: `android/dark-frame-series/build_debug_apk.sh`
- Modify: `android/dark-frame-series/src/io/github/tobiasbrummer/lightl16/darkframe/MainActivity.java`
- Modify: `device/dark_frame_series_hostless_supervisor.sh`
- Modify: `tests/test_android_dark_frame_series.py`

**Interfaces:**
- Consumes: all files from Tasks 1-5.
- Produces: `.build/dark-frame-series/light-l16-dark-frame-series-debug.apk`.

- [x] **Step 1: Write the failing test**

Append to `tests/test_android_dark_frame_series.py`:

```python
BUILD = APP / "build_debug_apk.sh"
ASYNC_SHIM_BUILDER = ROOT / "host" / "build_lcc_async_shim.sh"
EXPECTED_ASYNC_SHIM_SIZE = 8904
EXPECTED_ASYNC_SHIM_SHA1 = "150e53a736624010dc7fb741490ea8dca7afbfb8"


def test_build_packages_only_the_three_reviewed_payloads() -> None:
    build = BUILD.read_text()
    assert 'SUPERVISOR="$PROJECT_ROOT/device/dark_frame_series_hostless_supervisor.sh"' in build
    assert 'CHILD="$PROJECT_ROOT/device/dark_frame_series_once.sh"' in build
    assert 'ASYNC_SHIM_BUILDER="$PROJECT_ROOT/host/build_lcc_async_shim.sh"' in build
    assert 'sh -n "$FILE"' in build
    assert "apksigner" in build


def test_build_refuses_changed_payloads() -> None:
    build = BUILD.read_text()
    assert f"EXPECTED_SUPERVISOR_SIZE={SUPERVISOR.stat().st_size}" in build
    assert f"EXPECTED_SUPERVISOR_SHA256={digest(SUPERVISOR, 'sha256')}" in build
    assert f"EXPECTED_CHILD_SIZE={CHILD.stat().st_size}" in build
    assert f"EXPECTED_CHILD_SHA256={digest(CHILD, 'sha256')}" in build
    assert f"EXPECTED_ASYNC_SHIM_SIZE={EXPECTED_ASYNC_SHIM_SIZE}" in build
    assert "refusing changed payload" in build


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
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_android_dark_frame_series.py -v`
Expected: the three new tests FAIL.

- [x] **Step 3: Write the build script**

Copy `android/a1-capture/build_debug_apk.sh` and change:

- `OUTPUT_DIR` to `$PROJECT_ROOT/.build/dark-frame-series`, `APK` to `light-l16-dark-frame-series-debug.apk`.
- `SUPERVISOR` and `CHILD` to the new device scripts.
- `AF_SHIM_BUILDER` to `ASYNC_SHIM_BUILDER="$PROJECT_ROOT/host/build_lcc_async_shim.sh"`, producing `$TEMP_DIR/assets/liblcc_async_writer_shim.so`, pinned to size 8904 and its SHA-256.
- The `javac` invocation must compile both sources:

```sh
javac -source 8 -target 8 \
    -bootclasspath "$ANDROID_JAR" \
    -d "$TEMP_DIR/classes" \
    "$SCRIPT_DIR/src/io/github/tobiasbrummer/lightl16/darkframe/MainActivity.java" \
    "$SCRIPT_DIR/src/io/github/tobiasbrummer/lightl16/darkframe/DarknessCheck.java"
```

- [x] **Step 4: Fill in the real hashes**

Compute and paste the actual values, in this order, because each layer pins the
one before it:

```bash
sha256sum device/dark_frame_series_once.sh
sha1sum device/dark_frame_series_once.sh
wc -c device/dark_frame_series_once.sh
```

Put child size and SHA-1 into the supervisor. Then, because the supervisor file
just changed, recompute it:

```bash
sha256sum device/dark_frame_series_hostless_supervisor.sh
wc -c device/dark_frame_series_hostless_supervisor.sh
```

Put supervisor and child sizes and SHA-256 values into `MainActivity.java` and
into the build script. Changing the supervisor after pinning it invalidates the
pin, so this order is not optional.

- [x] **Step 5: Build the APK**

Run: `android/dark-frame-series/build_debug_apk.sh`
Expected: prints `apk=` and a SHA-256, exits 0. If it refuses a payload, a hash
in Step 4 is stale.

- [x] **Step 6: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests PASS, including the pre-existing ones.

- [x] **Step 7: Commit**

```bash
git add android/dark-frame-series device/dark_frame_series_hostless_supervisor.sh tests/test_android_dark_frame_series.py
git commit -m "Build dark frame series APK with pinned payloads"
```

---

### Task 7: Documentation

**Files:**
- Create: `android/dark-frame-series/README.md`
- Modify: `README.md`
- Modify: `docs/dark-frame-series.md`
- Modify: `tests/test_dark_frame_series_payload.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_dark_frame_series_payload.py`:

```python
import hashlib


def test_docs_pin_the_current_child_payload() -> None:
    doc = (ROOT / "docs" / "dark-frame-series.md").read_text(encoding="utf-8")
    payload = CHILD.read_bytes()
    assert f"{len(payload):,}-byte" in doc
    assert hashlib.sha1(payload).hexdigest() in doc


def test_repository_readme_links_the_dark_frame_series() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/dark-frame-series.md" in readme
    assert "dark frame" in readme.lower()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_dark_frame_series_payload.py -v`
Expected: the two new tests FAIL.

- [x] **Step 3: Write the app README**

Create `android/dark-frame-series/README.md` following the structure of
`android/a1-capture/README.md`: purpose, the compiled-in plan as a table, the
safety and recovery policy, build, one-time installation with the exact
`adb uninstall` and `adb install` commands, the three-button device test, the
expected success markers, and the validation status. State plainly that the
series has not run on a camera.

- [x] **Step 4: Add the payload pin to the spec**

Add to `docs/dark-frame-series.md`, in a new section after the measurement plan:

```markdown
## Payload identity

The current NN,NNN-byte child payload has SHA-1 `<hash>`. The supervisor, the
Java source, and the build script each refuse a payload that does not match.
```

Replace `NN,NNN` and `<hash>` with the real values from
`wc -c` and `sha1sum`, formatted with a thousands separator to match the test.

- [x] **Step 5: Link it from the repository README**

Add to the documentation list in `README.md`:

```markdown
- [All-16 dark frame series](docs/dark-frame-series.md)
```

Add a status bullet to the confirmed-results list stating that the dark frame
series app and analysis tool are built and host-tested, and that the series has
not yet run on a camera.

- [x] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest -v`
Expected: all tests PASS, including `test_relative_markdown_links_resolve`.

- [x] **Step 7: Commit**

```bash
git add README.md docs/dark-frame-series.md android/dark-frame-series/README.md tests/test_dark_frame_series_payload.py
git commit -m "Document the all-16 dark frame series"
```

---

### Task 8: Host analysis tool

Reduces a pulled series to a per-module report. This is the only part of the
repository that reads RAW10 pixels and the only one that needs NumPy.

**Files:**
- Create: `tools/analyze_dark_frame_series.py`
- Create: `requirements-analysis.txt`
- Create: `tests/test_analyze_dark_frame_series.py`

**Interfaces:**
- Consumes: `inspect_lri` and the module decoding from `tools/verify_stock_capture.py`.
- Produces: `unpack_raw10(data: bytes, width: int, height: int, row_stride: int) -> numpy.ndarray` returning a `(height, width)` array of `uint16`; `surface_statistics(samples) -> SurfaceStats`; `analyze_series(directory: Path) -> SeriesReport`; and a CLI writing a text report to stdout.

- [x] **Step 1: Determine where the pixel bytes live**

The container format is already decoded in `tools/verify_stock_capture.py`:
`LRI_HEADER = struct.Struct("<4sQQIB7x")` gives magic `LELR`, `block_length`,
`message_offset`, `message_length`, and `message_type` per 32-byte block header,
and `inspect_lri` walks the blocks but deliberately reads only the
`message_type == 0` protobuf metadata.

Dump the block table of the retained all-16 capture to find the pixel regions:

```bash
python3 - <<'PY'
import struct
from pathlib import Path
p = Path("output/all16-capture-20260809T192149Z/pixels/RDI_20260809_212153_985.lri")
header = struct.Struct("<4sQQIB7x")
offset = 0
size = p.stat().st_size
with p.open("rb") as fh:
    while offset < size:
        fh.seek(offset)
        magic, block_length, message_offset, message_length, message_type = (
            header.unpack(fh.read(header.size))
        )
        print(f"{offset=} {magic=} {block_length=} {message_offset=} "
              f"{message_length=} {message_type=}")
        offset += block_length
PY
```

Record which `message_type` carries the surfaces and where the pixel bytes start
relative to the block. Write that finding as a comment at the top of the new
tool. Do not guess it.

- [x] **Step 2: Write the failing unpacker test**

Create `tests/test_analyze_dark_frame_series.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_dark_frame_series import unpack_raw10, surface_statistics


def pack_raw10(values: list[int]) -> bytes:
    assert len(values) % 4 == 0
    out = bytearray()
    for index in range(0, len(values), 4):
        quad = values[index:index + 4]
        low = 0
        for position, sample in enumerate(quad):
            out.append((sample >> 2) & 0xFF)
            low |= (sample & 0x03) << (2 * position)
        out.append(low)
    return bytes(out)


def test_unpack_raw10_round_trips_known_samples() -> None:
    values = [0, 1, 2, 3, 512, 1023, 640, 64]
    packed = pack_raw10(values)
    assert len(packed) == 10
    result = unpack_raw10(packed, width=8, height=1, row_stride=10)
    assert result.shape == (1, 8)
    assert list(result[0]) == values


def test_unpack_raw10_honours_row_stride_padding() -> None:
    values = [64] * 8
    packed = pack_raw10(values[:4]) + b"\x00\x00" + pack_raw10(values[4:]) + b"\x00\x00"
    result = unpack_raw10(packed, width=4, height=2, row_stride=7)
    assert result.shape == (2, 4)
    assert result.max() == 64


def test_unpack_raw10_rejects_short_input() -> None:
    with pytest.raises(ValueError):
        unpack_raw10(b"\x00" * 4, width=4, height=1, row_stride=5)


def test_surface_statistics_reports_mean_and_spatial_noise() -> None:
    samples = numpy.full((16, 16), 64, dtype=numpy.uint16)
    samples[0, 0] = 1023
    stats = surface_statistics(samples, hot_threshold=512)
    assert stats.mean == pytest.approx(67.75, abs=0.01)
    assert stats.hot_count == 1
    assert stats.spatial_std > 0
    assert stats.maximum == 1023
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_analyze_dark_frame_series.py -v`
Expected: FAIL with an import error, or skip entirely if NumPy is absent.
Install it first: `python -m pip install -r requirements-analysis.txt` after
creating that file with the single line `numpy>=1.24`.

- [x] **Step 4: Write the unpacker and statistics**

Create `tools/analyze_dark_frame_series.py`:

```python
"""Reduce an all-16 dark frame series to a per-module noise report.

Unlike every other tool in this repository, this one reads RAW10 pixels.  It
requires NumPy; see requirements-analysis.txt.  Container decoding is imported
from verify_stock_capture rather than reimplemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import numpy
except ModuleNotFoundError:  # pragma: no cover - exercised by the CLI only.
    raise SystemExit(
        "analyze_dark_frame_series requires NumPy: "
        "python -m pip install -r requirements-analysis.txt"
    )


@dataclass(frozen=True)
class SurfaceStats:
    mean: float
    spatial_std: float
    minimum: int
    maximum: int
    hot_count: int


def unpack_raw10(
    data: bytes, width: int, height: int, row_stride: int
) -> numpy.ndarray:
    """Unpack MIPI RAW10: four pixels per five bytes, low bits in byte five."""

    if width % 4:
        raise ValueError(f"width {width} is not a multiple of four")
    packed_row_bytes = width // 4 * 5
    if row_stride < packed_row_bytes:
        raise ValueError(
            f"row_stride {row_stride} shorter than packed row {packed_row_bytes}"
        )
    if len(data) < row_stride * height:
        raise ValueError(
            f"need {row_stride * height} bytes, got {len(data)}"
        )
    raw = numpy.frombuffer(data, dtype=numpy.uint8, count=row_stride * height)
    rows = raw.reshape(height, row_stride)[:, :packed_row_bytes]
    quads = rows.reshape(height, width // 4, 5)
    high = quads[:, :, :4].astype(numpy.uint16)
    low = quads[:, :, 4].astype(numpy.uint16)
    out = numpy.empty((height, width // 4, 4), dtype=numpy.uint16)
    for position in range(4):
        out[:, :, position] = (
            (high[:, :, position] << 2) | ((low >> (2 * position)) & 0x03)
        )
    return out.reshape(height, width)


def surface_statistics(
    samples: numpy.ndarray, hot_threshold: int
) -> SurfaceStats:
    values = samples.astype(numpy.float64)
    return SurfaceStats(
        mean=float(values.mean()),
        spatial_std=float(values.std()),
        minimum=int(samples.min()),
        maximum=int(samples.max()),
        hot_count=int((samples > hot_threshold).sum()),
    )
```

If Step 1 showed a different bit order in the fifth byte, correct the shift and
say so in the docstring. The synthetic round-trip test passes either way, so it
cannot catch a wrong order on its own; Step 6 validates against real data.

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_analyze_dark_frame_series.py -v`
Expected: 4 tests PASS.

- [x] **Step 6: Write the series reduction and CLI**

Add to `tools/analyze_dark_frame_series.py`:

- `read_module_surfaces(path)` returning a dict of module name to array, using
  `inspect_lri` from `verify_stock_capture` for the per-module metadata and the
  block offsets found in Step 1.
- `analyze_series(directory)` grouping the LRIs into cells by their recorded
  `sensor_exposure` and gain, computing per cell: mean, spatial standard
  deviation, hot count, and, where a cell has at least two members, the read
  noise as the standard deviation of the difference of two repeats divided by
  the square root of two.
- Dark current per module as a least-squares slope of cell mean against
  integration time, restricted to the gain 1.0 cells, reported in DN per second.
- A gain table listing, per capture, the requested gain from the file order and
  the recorded `sensor_analog_gain` and `sensor_digital_gain`, so the
  quantization of the CCB sensitivity command is visible directly.
- A `main()` that takes a directory, prints the report as aligned text, and
  states plainly that values are in DN and that no electron conversion is
  claimed.

Memory stays bounded: reduce each surface to its statistics immediately after
unpacking, and hold at most two surfaces for a read-noise pair.

- [x] **Step 7: Validate the unpacker against the retained real capture**

Add this test, which skips when the local artifact is absent, matching the
optional full-size test pattern already described in `docs/async-lri-writer.md`:

```python
RETAINED = (
    ROOT / "output" / "all16-capture-20260809T192149Z" / "pixels"
    / "RDI_20260809_212153_985.lri"
)


@pytest.mark.skipif(not RETAINED.exists(), reason="retained LRI not present")
def test_unpacked_real_surface_has_plausible_ten_bit_range() -> None:
    from analyze_dark_frame_series import read_module_surfaces

    surfaces = read_module_surfaces(RETAINED)
    assert len(surfaces) == 16
    for name, samples in surfaces.items():
        assert samples.shape == (3120, 4160)
        assert samples.max() <= 1023, f"{name} exceeds the 10-bit range"
        assert samples.min() >= 0
```

A wrong bit order would push samples past 1023 or collapse the distribution, so
this is the check that actually constrains Step 4.

Run: `python -m pytest tests/test_analyze_dark_frame_series.py -v`
Expected: 5 PASS, or 4 PASS and 1 SKIP on a machine without the retained file.

- [x] **Step 8: Run the full suite and commit**

Run: `python -m pytest -v`
Expected: all tests PASS or SKIP.

```bash
git add tools/analyze_dark_frame_series.py tests/test_analyze_dark_frame_series.py requirements-analysis.txt
git commit -m "Add dark frame series analysis tool"
```

---

## Execution order and why it is fixed

Tasks 1-2 build the child, Task 3 pins the child, Tasks 4-5 pin the supervisor
and child, Task 6 pins all three and builds. Each layer hashes the finished
layer below it, so reordering means re-pinning. Tasks 7 and 8 are independent
of that chain: Task 8 can be built and tested at any point, including before the
camera ever runs, because the retained all-16 capture is enough to validate the
unpacker.

## What this plan does not do

It does not run the series on the camera. After Task 6 produces an APK, the
physical test is a manual step described in the app README, and its first result
must be decoded with Task 8's tool before any claim about dark current, read
noise, or gain quantization enters the documentation.
