from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
START_SYMBOL = "_ZN7qcamera12LccInterface12startCaptureEv"
CLOSE_CAMERA_SYMBOL = "_ZN7qcamera12LccInterface11closeCameraEv"
CLOSE_SYMBOL = "_ZN7qcamera12LccInterface5closeEv"
PROCESS_REQUEST_SYMBOL = (
    "_ZN7qcamera25QCamera3HardwareInterface21processCaptureRequest"
    "EP23camera3_capture_request"
)
PROCESS_RESULT_SYMBOL = (
    "_ZN7qcamera12LccInterface20processCaptureResult"
    "EPK22camera3_capture_result"
)


def _values(stdout: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = int(value)
    return values


def test_shim_uses_same_session_camera3_metadata_not_raw_ccb_af() -> None:
    source = (ROOT / "shim" / "lcc_a1_focus_capture_shim.c").read_text()
    assert "QCamera3HardwareInterface21processCaptureRequest" in source
    assert "LccInterface20processCaptureResult" in source
    assert "EP23camera3_capture_request" in source
    assert "EPK22camera3_capture_result" in source
    assert "L16_ANDROID_CONTROL_AF_MODE" in source
    assert "L16_ANDROID_CONTROL_AF_REGIONS" in source
    assert "L16_ANDROID_CONTROL_AF_TRIGGER" in source
    assert "L16_ANDROID_CONTROL_AF_STATE" in source
    assert "L16_AF_STATE_FOCUSED_LOCKED" in source
    assert "L16_AF_WRITE_PATH" not in source
    assert "response_socket" not in source
    assert "recvfrom" not in source


def _compile_native_test(tmp_path: Path) -> tuple[Path, Path]:
    compiler = shutil.which("cc") or shutil.which("clang")
    readelf = shutil.which("readelf")
    if compiler is None or readelf is None:
        pytest.skip("native C compiler and readelf are required")

    shim = tmp_path / "liblcc_a1_focus_capture_shim.so"
    mock = tmp_path / "libmock_lcc_focus_hal.so"
    client = tmp_path / "mock_lcc_focus_client"
    common = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]

    subprocess.run(
        [
            compiler,
            *common,
            "-fPIC",
            "-shared",
            '-DL16_TARGET_LIBRARY="libmock_lcc_focus_hal.so"',
            '-DL16_METADATA_LIBRARY="libmock_lcc_focus_hal.so"',
            '-DL16_SHELL_PATH="/bin/sh"',
            "-DL16_AF_WAIT_TIMEOUT_MILLISECONDS=1000",
            "-DL16_AF_WAIT_POLL_MICROSECONDS=1000",
            "-DL16_EXPECTED_HELPER_COMMANDS=1",
            str(ROOT / "shim" / "lcc_a1_focus_capture_shim.c"),
            "-ldl",
            "-Wl,-z,now",
            "-Wl,-z,relro",
            "-o",
            str(shim),
        ],
        check=True,
    )
    subprocess.run(
        [
            compiler,
            *common,
            "-fPIC",
            "-fsemantic-interposition",
            "-fplt",
            "-shared",
            str(ROOT / "tests" / "native" / "mock_lcc_focus_hal.c"),
            "-ldl",
            "-pthread",
            "-Wl,-z,now",
            "-o",
            str(mock),
        ],
        check=True,
    )
    subprocess.run(
        [
            compiler,
            *common,
            str(ROOT / "tests" / "native" / "mock_lcc_focus_client.c"),
            f"-L{tmp_path}",
            "-lmock_lcc_focus_hal",
            "-Wl,-rpath,$ORIGIN",
            "-o",
            str(client),
        ],
        check=True,
    )

    relocations = subprocess.run(
        [readelf, "-rW", str(mock)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert START_SYMBOL in relocations
    assert CLOSE_CAMERA_SYMBOL in relocations
    assert PROCESS_REQUEST_SYMBOL in relocations
    assert PROCESS_RESULT_SYMBOL in relocations
    symbols = subprocess.run(
        [readelf, "--dyn-syms", "--wide", str(mock)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert CLOSE_SYMBOL in symbols
    return shim, client


def _run(
    shim: Path, client: Path, final_af_state: int
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = str(client.parent)
    environment["LD_BIND_NOW"] = "1"
    environment["LD_PRELOAD"] = str(shim)
    return subprocess.run(
        [str(client), str(final_af_state)],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_focused_locked_releases_capture_only_after_metadata_result(
    tmp_path: Path,
) -> None:
    shim, client = _compile_native_test(tmp_path)
    completed = _run(shim, client, 4)
    values = _values(completed.stdout)
    assert values["result"] == 11
    assert values["real_start_calls"] == 1
    assert values["real_close_camera_calls"] == 1
    assert values["direct_close_calls"] == 0
    assert values["real_process_request_calls"] >= 2
    assert values["real_process_result_calls"] == 2
    assert values["af_trigger_calls"] == 1
    assert values["af_hold_calls"] >= 1
    assert values["invalid_af_requests"] == 0
    assert values["ld_preload_present"] == 0

    log = completed.stderr
    constructor_order = [
        "loaded",
        "preload_cleared",
        "resolve_targets_ok",
        "metadata_resolve_ok",
        "preload_child_selftest_ok",
    ]
    focus_order = [
        "af_metadata_trigger_injected",
        "af_state_active_scan",
        "af_metadata_hold_injected",
        "af_state_focused_locked",
        "af_gate_pass",
        "capture_released",
        "helper_commands_ok",
        "close_reports_ok",
    ]
    for ordered in (constructor_order, focus_order):
        positions = [
            log.index(f"L16_A1_AF_SHIM {marker}") for marker in ordered
        ]
        assert positions == sorted(positions)
    # startCapture and the preview request run on different threads.  Once the
    # atomic gate is published, the request can be injected before the start
    # thread emits its informational "armed" marker; both must still precede
    # release of the real capture.
    assert log.index("L16_A1_AF_SHIM af_gate_enter") < log.index(
        "L16_A1_AF_SHIM af_trigger_request_armed"
    )
    assert log.index("L16_A1_AF_SHIM af_trigger_request_armed") < log.index(
        "L16_A1_AF_SHIM af_gate_pass"
    )
    assert "capture_suppressed" not in log
    assert "error" not in log


def test_not_focused_locked_suppresses_capture_and_closes_hal(
    tmp_path: Path,
) -> None:
    shim, client = _compile_native_test(tmp_path)
    completed = _run(shim, client, 5)
    values = _values(completed.stdout)
    assert values["result"] == 0
    assert values["real_start_calls"] == 0
    assert values["real_close_camera_calls"] == 0
    assert values["direct_close_calls"] == 1
    assert values["real_process_request_calls"] >= 2
    assert values["real_process_result_calls"] == 2
    assert values["af_trigger_calls"] == 1
    assert values["af_hold_calls"] >= 1
    assert values["invalid_af_requests"] == 0
    assert values["ld_preload_present"] == 0

    log = completed.stderr
    assert log.index("L16_A1_AF_SHIM af_metadata_trigger_injected") < log.index(
        "L16_A1_AF_SHIM af_state_not_focused_locked"
    )
    assert log.index("L16_A1_AF_SHIM af_state_not_focused_locked") < log.index(
        "L16_A1_AF_SHIM capture_suppressed"
    )
    assert log.index("L16_A1_AF_SHIM capture_suppressed") < log.index(
        "L16_A1_AF_SHIM close_without_capture"
    )
    assert "capture_released" not in log
    assert "close_reports_ok" not in log
