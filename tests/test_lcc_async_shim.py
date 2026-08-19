from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRITE_SYMBOL = "_ZN7qcamera12LccInterface9writeFileEv"
CLOSE_SYMBOL = "_ZN7qcamera12LccInterface11closeCameraEv"


def _values(stdout: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            result[key] = int(value)
    return result


def _compile_native_test(tmp_path: Path) -> tuple[Path, Path, Path]:
    compiler = shutil.which("cc") or shutil.which("clang")
    readelf = shutil.which("readelf")
    if compiler is None or readelf is None:
        pytest.skip("native C compiler and readelf are required")

    shim = tmp_path / "liblcc_async_writer_shim.so"
    mock = tmp_path / "libmock_lcc_hal.so"
    client = tmp_path / "mock_lcc_client"
    common = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]

    subprocess.run(
        [
            compiler,
            *common,
            "-fPIC",
            "-shared",
            '-DL16_TARGET_LIBRARY="libmock_lcc_hal.so"',
            "-DL16_EXPECTED_HELPER_COMMANDS=0",
            '-DL16_SHELL_PATH="/bin/sh"',
            str(ROOT / "shim" / "lcc_async_writer_shim.c"),
            "-pthread",
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
            str(ROOT / "tests" / "native" / "mock_lcc_hal.c"),
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
            str(ROOT / "tests" / "native" / "mock_lcc_client.c"),
            f"-L{tmp_path}",
            "-lmock_lcc_hal",
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
    assert WRITE_SYMBOL in relocations
    assert CLOSE_SYMBOL in relocations
    return shim, mock, client


def test_preload_moves_write_off_callback_and_joins_before_close(
    tmp_path: Path,
) -> None:
    shim, _mock, client = _compile_native_test(tmp_path)
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = str(tmp_path)
    environment["LD_BIND_NOW"] = "1"

    baseline = subprocess.run(
        [str(client)],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    baseline_values = _values(baseline.stdout)
    assert baseline_values["callback_us"] >= 200_000
    assert baseline_values["writer_other_thread"] == 0
    assert baseline_values["close_observed_finished"] == 1

    environment["LD_PRELOAD"] = str(shim)
    asynchronous = subprocess.run(
        [str(client)],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    async_values = _values(asynchronous.stdout)
    assert async_values["result"] == 1
    assert async_values["callback_us"] < 50_000
    assert async_values["total_us"] >= 200_000
    assert async_values["writer_other_thread"] == 1
    assert async_values["close_observed_finished"] == 1
    assert async_values["write_return"] == 0
    assert async_values["close_return"] == 1
    assert async_values["ld_preload_present"] == 0

    log = asynchronous.stderr
    assert log.index("L16_ASYNC_SHIM loaded") < log.index(
        "L16_ASYNC_SHIM preload_cleared"
    )
    assert log.index("L16_ASYNC_SHIM preload_cleared") < log.index(
        "L16_ASYNC_SHIM resolve_targets_ok"
    )
    assert log.index("L16_ASYNC_SHIM resolve_targets_ok") < log.index(
        "L16_ASYNC_SHIM preload_child_selftest_ok"
    )
    assert log.index("L16_ASYNC_SHIM preload_child_selftest_ok") < log.index(
        "L16_ASYNC_SHIM enqueue_ok"
    )
    assert "unexpected_second_write" not in log
    assert log.index("L16_ASYNC_SHIM close_wait") < log.index(
        "L16_ASYNC_SHIM worker_done_ok"
    )
    assert log.index("L16_ASYNC_SHIM worker_done_ok") < log.index(
        "L16_ASYNC_SHIM close_continue"
    )
    assert log.index("L16_ASYNC_SHIM close_continue") < log.index(
        "L16_ASYNC_SHIM helper_commands_ok"
    )
    assert log.index("L16_ASYNC_SHIM helper_commands_ok") < log.index(
        "L16_ASYNC_SHIM close_reports_ok"
    )
