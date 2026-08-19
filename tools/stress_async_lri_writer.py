#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reassemble one real-size all-16 LRI through the host-only async model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from tools.async_lri_writer import AsyncLriWriter, DescriptorSnapshot, Segment


ALL16_SEGMENT_LENGTHS = (
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    4_096,
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    4_096,
    16_228_352,
    16_228_352,
    16_228_352,
    16_228_352,
    4_096,
    334_073,
)
ALL16_TOTAL = 259_999_993
_COPY_CHUNK = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_COPY_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_source(source: Path, directory: Path) -> tuple[DescriptorSnapshot, list[int]]:
    segments: list[Segment] = []
    fds: list[int] = []
    try:
        with source.open("rb") as input_stream:
            for index, length in enumerate(ALL16_SEGMENT_LENGTHS):
                path = directory / f"segment-{index:02d}.bin"
                remaining = length
                with path.open("xb") as output_stream:
                    while remaining:
                        chunk = input_stream.read(min(_COPY_CHUNK, remaining))
                        if not chunk:
                            raise OSError(
                                f"source ended inside segment {index}; "
                                f"{remaining} bytes missing"
                            )
                        output_stream.write(chunk)
                        remaining -= len(chunk)
                fd = os.open(path, os.O_RDONLY)
                fds.append(fd)
                segments.append(Segment(fd, length))
            if input_stream.read(1):
                raise OSError("source contains bytes beyond the all-16 descriptor")
        return DescriptorSnapshot(tuple(segments), ALL16_TOTAL), fds
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise


def run_stress(
    source: Path,
    *,
    work_directory: Path,
    expected_sha256: str | None,
    timeout: float,
) -> dict[str, object]:
    source = source.resolve()
    if source.stat().st_size != ALL16_TOTAL:
        raise ValueError(
            f"source size is {source.stat().st_size}, expected {ALL16_TOTAL}"
        )
    if len(ALL16_SEGMENT_LENGTHS) != 20 or sum(ALL16_SEGMENT_LENGTHS) != ALL16_TOTAL:
        raise RuntimeError("compiled-in all-16 descriptor shape is inconsistent")

    source_sha256 = _sha256(source)
    if expected_sha256 is not None and source_sha256 != expected_sha256.lower():
        raise ValueError(
            f"source SHA-256 is {source_sha256}, expected {expected_sha256.lower()}"
        )

    released = threading.Event()
    report: dict[str, object]
    with tempfile.TemporaryDirectory(
        prefix="light-l16-async-writer-", dir=work_directory
    ) as temporary_name:
        temporary = Path(temporary_name)
        snapshot, original_fds = _split_source(source, temporary)
        destination = temporary / "reassembled.lri"
        start = time.monotonic()
        try:
            with AsyncLriWriter(maximum_inflight=1) as writer:
                enqueue_start = time.monotonic()
                handle = writer.enqueue(destination, snapshot, released.set)
                enqueue_seconds = time.monotonic() - enqueue_start
                for fd in original_fds:
                    os.close(fd)
                original_fds.clear()
                result = handle.result(timeout)
        finally:
            for fd in original_fds:
                os.close(fd)
        elapsed = time.monotonic() - start

        if not result.success:
            raise RuntimeError(f"writer failed: {result.error!r}")
        if not released.is_set():
            raise RuntimeError("producer lease was not released")
        if result.bytes_written != ALL16_TOTAL:
            raise RuntimeError(
                f"writer reported {result.bytes_written} bytes, expected {ALL16_TOTAL}"
            )
        if destination.stat().st_size != ALL16_TOTAL:
            raise RuntimeError(
                f"output size is {destination.stat().st_size}, expected {ALL16_TOTAL}"
            )
        output_sha256 = _sha256(destination)
        if output_sha256 != source_sha256:
            raise RuntimeError(
                f"output SHA-256 is {output_sha256}, source is {source_sha256}"
            )
        partials = sorted(path.name for path in temporary.glob(".*.partial-*"))
        if partials:
            raise RuntimeError(f"partial files remain: {partials}")

        report = {
            "status": "PASS",
            "segments": len(snapshot.segments),
            "declared_total": snapshot.declared_total,
            "bytes_written": result.bytes_written,
            "source_sha256": source_sha256,
            "output_sha256": output_sha256,
            "enqueue_ms": round(enqueue_seconds * 1000, 3),
            "elapsed_seconds": round(elapsed, 3),
            "throughput_mib_s": round(
                ALL16_TOTAL / (1024 * 1024) / elapsed, 3
            ),
            "lease_released": released.is_set(),
            "remaining_partials": len(partials),
            "temporary_data_removed": True,
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Split an exact-size all-16 LRI into the 20 observed descriptor "
            "segments and reassemble it through the host-only async writer."
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--work-directory",
        type=Path,
        default=Path.cwd(),
        help="existing directory for temporary segment and output files",
    )
    parser.add_argument("--expected-sha256")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    work_directory = args.work_directory.resolve()
    if not work_directory.is_dir():
        parser.error(f"work directory is not a directory: {work_directory}")
    if args.timeout <= 0:
        parser.error("timeout must be positive")

    report = run_stress(
        args.source,
        work_directory=work_directory,
        expected_sha256=args.expected_sha256,
        timeout=args.timeout,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
