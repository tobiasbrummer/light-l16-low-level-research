"""The mmap-failure probe compiled into the async writer preload.

The HAL prints `mmap failed on ion fd: %d` and nothing else, so a failed
capture says which descriptor failed but never why.  This probe adds the errno
and leaves everything else exactly as it was, which is the property most of
these tests check.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shim" / "lcc_async_writer_shim.c"
BUILDER = ROOT / "host" / "build_lcc_mmap_probe_shim.sh"
CLIENT_SOURCE = ROOT / "tests" / "native" / "mock_mmap_client.c"

# Enough for one capture's worth of buffers without letting a pathological
# process fill the log.
LOG_LIMIT = 64


def _build(tmp_path: Path) -> tuple[Path, Path]:
    compiler = shutil.which("cc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("a native C compiler is required")

    shim = tmp_path / "libshim.so"
    client = tmp_path / "client"
    subprocess.run(
        [
            compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-fPIC", "-shared",
            '-DL16_TARGET_LIBRARY="libmock_lcc_hal.so"',
            "-DL16_EXPECTED_HELPER_COMMANDS=0",
            '-DL16_SHELL_PATH="/bin/sh"',
            f"-DL16_LOG_MMAP_FAILURES={LOG_LIMIT}u",
            str(SOURCE), "-pthread", "-ldl",
            "-o", str(shim),
        ],
        check=True,
    )
    subprocess.run(
        [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         str(CLIENT_SOURCE), "-o", str(client)],
        check=True,
    )
    return shim, client


def _run(shim: Path, client: Path) -> tuple[dict[str, int], str]:
    result = subprocess.run(
        [str(client)],
        capture_output=True,
        text=True,
        env={"LD_PRELOAD": str(shim), "PATH": "/usr/bin:/bin"},
    )
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = int(value)
    return values, result.stderr


def test_a_successful_mapping_is_untouched_and_unlogged(tmp_path: Path) -> None:
    """The common case must not change, and must not produce noise.

    An anonymous mapping is the one call in the client that has to succeed;
    if the probe disturbed it, nothing else in this file would be meaningful.
    """
    shim, client = _build(tmp_path)
    values, stderr = _run(shim, client)
    assert values["ok_failed"] == 0
    # The client provokes exactly two failures; a third line would mean the
    # probe logged the successful mapping as well.
    assert stderr.count("mmap_failed") == 2


def test_errno_survives_the_probe(tmp_path: Path) -> None:
    """The caller must see the kernel's errno, not the logging's.

    Writing the log line is itself a syscall that sets errno, so the value has
    to be saved and restored around it.  This is the whole point of the probe:
    a wrong errno here would be worse than no errno at all.
    """
    shim, client = _build(tmp_path)
    values, _ = _run(shim, client)
    assert values["bad_fd_failed"] == 1
    assert values["bad_fd_errno"] == values["ebadf"]
    assert values["bad_len_failed"] == 1
    assert values["bad_len_errno"] == values["einval"]


def test_the_failure_line_carries_fd_length_and_errno(tmp_path: Path) -> None:
    """Without all three the line cannot be matched to a HAL buffer."""
    shim, client = _build(tmp_path)
    values, stderr = _run(shim, client)
    matches = re.findall(
        r"mmap_failed fd=(-?\d+) length=(\d+) errno=(\d+)", stderr
    )
    assert len(matches) == 2
    by_fd = {int(fd): (int(length), int(err)) for fd, length, err in matches}
    assert by_fd[999] == (4096, values["ebadf"])
    assert by_fd[0] == (0, values["einval"])


def test_the_probe_is_absent_unless_asked_for(tmp_path: Path) -> None:
    """The default build must not interpose mmap at all.

    Every existing profile pins the plain shim's hash, so the probe has to be
    invisible without its define.
    """
    compiler = shutil.which("cc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("a native C compiler is required")
    plain = tmp_path / "plain.so"
    subprocess.run(
        [
            compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-fPIC", "-shared",
            '-DL16_TARGET_LIBRARY="libmock_lcc_hal.so"',
            "-DL16_EXPECTED_HELPER_COMMANDS=0",
            '-DL16_SHELL_PATH="/bin/sh"',
            str(SOURCE), "-pthread", "-ldl", "-o", str(plain),
        ],
        check=True,
    )
    symbols = subprocess.run(
        ["nm", "-D", "--defined-only", str(plain)],
        capture_output=True, text=True,
    ).stdout
    assert " mmap" not in symbols


def test_source_saves_and_restores_errno_around_the_log() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    body = source[source.index("L16_LOG_MMAP_FAILURES"):]
    assert "saved_errno = l16_errno" in body
    assert "l16_errno = saved_errno" in body
    # The restore has to be the last thing before returning.
    assert body.index("saved_errno = l16_errno") < body.index(
        "l16_errno = saved_errno"
    )


def test_builder_enables_only_the_probe() -> None:
    build = BUILDER.read_text(encoding="utf-8")
    assert "L16_LOG_MMAP_FAILURES" in build
    assert "lcc_async_writer_shim.c" in build
    # The probe is a diagnostic; it must not also patch the timeout.
    assert "L16_TIMEOUT_PATCH_SECONDS" not in build


def test_the_reentrant_path_maps_and_reports_errors(tmp_path: Path) -> None:
    """The system-call fallback has to work on its own.

    Nothing in the tests above reaches it -- dlsym happens not to allocate
    here -- but on the device it recursed into a SIGSEGV, so the call number
    and the offset unit are checked directly rather than assumed.
    """
    compiler = shutil.which("cc") or shutil.which("clang")
    if compiler is None:
        pytest.skip("a native C compiler is required")

    client = tmp_path / "raw_client"
    subprocess.run(
        [
            compiler, "-std=gnu11", "-O2", "-Wall", "-Wextra",
            f"-I{ROOT / 'shim'}",
            str(ROOT / "tests" / "native" / "mock_raw_mmap_client.c"),
            "-pthread", "-ldl", "-o", str(client),
        ],
        check=True,
    )
    result = subprocess.run([str(client)], capture_output=True, text=True)
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = int(value)
    assert values["raw_mapped"] == 1
    assert values["raw_writable"] == 1
    assert values["raw_rejects_bad_fd"] == 1
