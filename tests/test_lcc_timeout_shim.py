from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shim" / "lcc_open_camera_timeout_shim.c"
BUILDER = ROOT / "host" / "build_lcc_timeout_shim.sh"
MOCK_HAL = ROOT / "tests" / "native" / "mock_lcc_timeout_hal.c"
MOCK_CLIENT = ROOT / "tests" / "native" / "mock_lcc_timeout_client.c"

# Written by openCamera at 0x97f54 as str r3, [r4, #0x24].
TIMEOUT_OFFSET = 0x24
# The shim's replacement value.
PATCHED_SECONDS = 120


def stock_timeout(exposure_seconds: int) -> int:
    """The value openCamera derives, from the disassembly at 0x97f40."""
    return exposure_seconds + 5 if exposure_seconds > 9 else 15


def test_the_shim_patches_only_the_timeout_field() -> None:
    """One computed address into the instance, one store, nothing else.

    The point is not that certain words are absent -- the comments describe
    the capture parameters at length -- but that the code derives exactly one
    address inside the instance and writes exactly one field there.
    """
    source = SOURCE.read_text(encoding="utf-8")
    assert "L16_TIMEOUT_OFFSET 0x24" in source
    assert "_ZN7qcamera12LccInterface10openCameraEjhj" in source

    # "* " continues a block comment; "*field" dereferences a pointer.
    code = [
        line.split("/*")[0]
        for line in source.splitlines()
        if not line.lstrip().startswith(("* ", "*/", "//", "/*"))
    ]
    body = "\n".join(code)
    assert body.count("(char *)self +") == 1
    assert body.count("*field =") == 1
    # The forwarded arguments must reach the real call unchanged.
    assert "l16_real_open_camera(self, first, second, third)" in body


def test_the_shim_refuses_rather_than_writing_blind() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "l16_expected_timeout" in source
    assert "timeout_field_unexpected_not_patched" in source
    assert "timeout_write_did_not_stick" in source
    # The verification must happen before the write.
    assert source.index("found != expected") < source.index(
        "*field = (unsigned int)L16_TIMEOUT_SECONDS"
    )


def test_the_shim_clears_the_preload_for_child_processes() -> None:
    """lcc forks shell helpers; they must not inherit a 32-bit preload."""
    source = SOURCE.read_text(encoding="utf-8")
    assert 'unsetenv("LD_PRELOAD")' in source
    assert "preload_still_present_error" in source
    assert "l16_prepare_clean_environment" in source


def test_builder_pins_nothing_it_does_not_build() -> None:
    build = BUILDER.read_text(encoding="utf-8")
    assert "lcc_open_camera_timeout_shim.c" in build
    assert "liblcc_open_camera_timeout_shim" in build


def _build_native(tmp_path: Path) -> tuple[Path, Path]:
    compiler = shutil.which("cc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("a native C compiler is required")

    mock = tmp_path / "libmock_lcc_timeout_hal.so"
    shim = tmp_path / "libshim.so"
    client = tmp_path / "client"

    subprocess.run(
        [compiler, "-shared", "-fPIC", "-O1", "-o", str(mock), str(MOCK_HAL)],
        check=True,
    )
    subprocess.run(
        [
            compiler, "-shared", "-fPIC", "-O1",
            f'-DL16_TARGET_LIBRARY="{mock}"',
            f"-DL16_TIMEOUT_SECONDS={PATCHED_SECONDS}u",
            '-DL16_SHELL_PATH="/bin/sh"',
            "-o", str(shim), str(SOURCE), "-ldl",
        ],
        check=True,
    )
    subprocess.run(
        [
            compiler, "-O1", "-o", str(client), str(MOCK_CLIENT),
            str(mock), "-Wl,-rpath," + str(tmp_path),
        ],
        check=True,
    )
    return shim, client


def _run(shim: Path, client: Path, *arguments: str) -> dict[str, str]:
    result = subprocess.run(
        [str(client), *arguments],
        capture_output=True,
        text=True,
        env={"LD_PRELOAD": str(shim), "PATH": "/usr/bin:/bin"},
    )
    values = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    values["_stderr"] = result.stderr
    return values


@pytest.mark.parametrize("exposure", [1, 6, 15, 29])
def test_timeout_is_raised_for_every_exposure(tmp_path: Path, exposure: int) -> None:
    """The stock budget is flat at 15 s below 9 s and never keeps up above it."""
    shim, client = _build_native(tmp_path)
    values = _run(shim, client, str(exposure))
    assert values["open_result"] == "0"
    assert values["mock_open_calls"] == "1"
    assert values["mock_stored_timeout"] == str(stock_timeout(exposure))
    assert values["observed_timeout"] == str(PATCHED_SECONDS)
    assert "timeout_patched" in values["_stderr"]


def test_an_unexpected_field_value_is_left_alone(tmp_path: Path) -> None:
    """If the offset assumption no longer holds, refuse instead of clobbering.

    The mock stores 4242 where the formula predicts 15; the shim must notice
    and leave the field untouched rather than write into an unknown member.
    """
    shim, client = _build_native(tmp_path)
    values = _run(shim, client, "1", "4242")
    assert values["mock_stored_timeout"] == "4242"
    assert values["observed_timeout"] == "4242"
    assert "timeout_field_unexpected_not_patched" in values["_stderr"]
    assert "timeout_patched" not in values["_stderr"]


def test_the_real_open_camera_is_actually_called(tmp_path: Path) -> None:
    shim, client = _build_native(tmp_path)
    values = _run(shim, client, "15")
    assert values["mock_open_calls"] == "1"
    assert "real_open_camera_ok" in values["_stderr"]
    assert "resolve_targets_ok" in values["_stderr"]
