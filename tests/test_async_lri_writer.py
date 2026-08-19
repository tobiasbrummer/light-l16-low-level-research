from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from tools.async_lri_writer import (
    AsyncLriWriter,
    DescriptorError,
    DescriptorSnapshot,
    Segment,
    WriterBusyError,
)
from tools.stress_async_lri_writer import ALL16_SEGMENT_LENGTHS, ALL16_TOTAL


def _open_snapshot(
    root: Path, payloads: tuple[bytes, ...]
) -> tuple[DescriptorSnapshot, list[int]]:
    root.mkdir(parents=True, exist_ok=True)
    descriptors: list[Segment] = []
    original_fds: list[int] = []
    for index, payload in enumerate(payloads):
        source = root / f"segment-{index}.bin"
        source.write_bytes(payload)
        fd = os.open(source, os.O_RDONLY)
        original_fds.append(fd)
        descriptors.append(Segment(fd, len(payload)))
    return DescriptorSnapshot(tuple(descriptors), sum(map(len, payloads))), original_fds


def _close_all(fds: list[int]) -> None:
    for fd in fds:
        os.close(fd)


def test_observed_all16_descriptor_shape_is_exact() -> None:
    assert len(ALL16_SEGMENT_LENGTHS) == 20
    assert ALL16_SEGMENT_LENGTHS.count(16_228_352) == 16
    assert ALL16_SEGMENT_LENGTHS.count(4_096) == 3
    assert ALL16_SEGMENT_LENGTHS[-1] == 334_073
    assert sum(ALL16_SEGMENT_LENGTHS) == ALL16_TOTAL == 259_999_993


def test_writer_commits_segments_in_descriptor_order_and_releases_lease(
    tmp_path: Path,
) -> None:
    payloads = (b"first", b"-second-", b"third")
    snapshot, original_fds = _open_snapshot(tmp_path, payloads)
    releases: list[str] = []
    destination = tmp_path / "capture.lri"

    try:
        with AsyncLriWriter(chunk_size=3) as writer:
            handle = writer.enqueue(
                destination, snapshot, lambda: releases.append("done")
            )
            _close_all(original_fds)
            original_fds.clear()
            result = handle.result(2)
    finally:
        _close_all(original_fds)

    assert result.success
    assert result.committed
    assert result.error is None
    assert result.bytes_written == sum(map(len, payloads))
    assert destination.read_bytes() == b"".join(payloads)
    assert releases == ["done"]
    assert not list(tmp_path.glob(".*.partial-*"))


class _BlockingWriter(AsyncLriWriter):
    def __init__(self) -> None:
        self.copy_started = threading.Event()
        self.allow_copy = threading.Event()
        super().__init__(maximum_inflight=1, chunk_size=2)

    def _copy_segment(self, output_fd: int, segment: Segment) -> int:
        self.copy_started.set()
        if not self.allow_copy.wait(2):
            raise TimeoutError("test did not release the blocked writer")
        return super()._copy_segment(output_fd, segment)


def test_enqueue_returns_before_io_and_lease_blocks_recycling(tmp_path: Path) -> None:
    snapshot, original_fds = _open_snapshot(tmp_path, (b"abcdef",))
    destination = tmp_path / "async.lri"

    class FakeProducerLease:
        active = True

        def release(self) -> None:
            self.active = False

        def recycle(self) -> None:
            if self.active:
                raise RuntimeError("producer attempted to recycle a leased buffer")

    lease = FakeProducerLease()
    writer = _BlockingWriter()
    try:
        handle = writer.enqueue(destination, snapshot, lease.release)
        assert writer.copy_started.wait(1)
        assert not handle.done
        _close_all(original_fds)
        original_fds.clear()
        with pytest.raises(RuntimeError, match="leased buffer"):
            lease.recycle()

        writer.allow_copy.set()
        result = handle.result(2)
        lease.recycle()
    finally:
        writer.allow_copy.set()
        writer.close(2)
        _close_all(original_fds)

    assert result.success
    assert destination.read_bytes() == b"abcdef"
    assert not lease.active


def test_writer_rejects_a_second_large_lease_instead_of_blocking_callback(
    tmp_path: Path,
) -> None:
    first, first_fds = _open_snapshot(tmp_path / "first", (b"one",))
    second, second_fds = _open_snapshot(tmp_path / "second", (b"two",))
    first_release = threading.Event()
    second_release = threading.Event()
    writer = _BlockingWriter()

    try:
        handle = writer.enqueue(
            tmp_path / "first.lri", first, first_release.set
        )
        assert writer.copy_started.wait(1)
        with pytest.raises(WriterBusyError):
            writer.enqueue(tmp_path / "second.lri", second, second_release.set)
        assert not second_release.is_set()

        writer.allow_copy.set()
        assert handle.result(2).success
    finally:
        writer.allow_copy.set()
        writer.close(2)
        _close_all(first_fds)
        _close_all(second_fds)

    assert first_release.is_set()
    assert not (tmp_path / "second.lri").exists()


def test_short_source_removes_partial_and_releases_lease(tmp_path: Path) -> None:
    source = tmp_path / "short.bin"
    source.write_bytes(b"abc")
    fd = os.open(source, os.O_RDONLY)
    snapshot = DescriptorSnapshot((Segment(fd, 4),), 4)
    released = threading.Event()
    destination = tmp_path / "failed.lri"

    try:
        with AsyncLriWriter() as writer:
            result = writer.enqueue(destination, snapshot, released.set).result(2)
    finally:
        os.close(fd)

    assert not result.success
    assert not result.committed
    assert result.error is not None
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.partial-*"))
    assert released.is_set()


def test_20_segment_shape_preserves_all16_descriptor_order(tmp_path: Path) -> None:
    payloads = tuple(bytes((index,)) * (index + 1) for index in range(20))
    snapshot, original_fds = _open_snapshot(tmp_path / "segments", payloads)
    destination = tmp_path / "all16-shape.lri"

    try:
        with AsyncLriWriter(chunk_size=7) as writer:
            result = writer.enqueue(destination, snapshot, lambda: None).result(2)
    finally:
        _close_all(original_fds)

    assert result.success
    assert destination.read_bytes() == b"".join(payloads)


def test_preexisting_partial_is_not_deleted_on_exclusive_create_failure(
    tmp_path: Path,
) -> None:
    snapshot, original_fds = _open_snapshot(tmp_path / "source", (b"payload",))
    destination = tmp_path / "capture.lri"
    stale = tmp_path / f".capture.lri.partial-{os.getpid()}-1"
    stale.write_bytes(b"older evidence")

    try:
        with AsyncLriWriter() as writer:
            result = writer.enqueue(destination, snapshot, lambda: None).result(2)
    finally:
        _close_all(original_fds)

    assert not result.success
    assert not destination.exists()
    assert stale.read_bytes() == b"older evidence"


def test_descriptor_mismatch_is_rejected_before_ownership_transfer(
    tmp_path: Path,
) -> None:
    snapshot, original_fds = _open_snapshot(tmp_path, (b"abc",))
    invalid = DescriptorSnapshot(snapshot.segments, snapshot.declared_total + 1)
    released = threading.Event()

    try:
        with AsyncLriWriter() as writer:
            with pytest.raises(DescriptorError, match="descriptor declares"):
                writer.enqueue(tmp_path / "invalid.lri", invalid, released.set)
    finally:
        _close_all(original_fds)

    assert not released.is_set()
    assert not (tmp_path / "invalid.lri").exists()
