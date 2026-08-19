#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Host-only reference model for an ownership-safe asynchronous LRI writer.

This module models the lifetime and completion rules needed by a future
source-level camera-HAL change.  It does not patch a vendor binary or connect
to a camera.
"""

from __future__ import annotations

import mmap
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


_UINT32_MAX = (1 << 32) - 1


class DescriptorError(ValueError):
    """The returned multi-buffer descriptor is internally inconsistent."""


class WriterBusyError(RuntimeError):
    """The bounded writer already owns its maximum number of buffer leases."""


@dataclass(frozen=True)
class Segment:
    """One descriptor entry copied while still inside the result callback."""

    fd: int
    length: int


@dataclass(frozen=True)
class DescriptorSnapshot:
    """Immutable copy of a multi-buffer descriptor."""

    segments: tuple[Segment, ...]
    declared_total: int

    def validate(self, *, maximum_segments: int) -> None:
        if not self.segments:
            raise DescriptorError("descriptor has no segments")
        if len(self.segments) > maximum_segments:
            raise DescriptorError(
                f"descriptor has {len(self.segments)} segments; "
                f"limit is {maximum_segments}"
            )
        if self.declared_total <= 0:
            raise DescriptorError("declared total must be positive")
        if self.declared_total > _UINT32_MAX:
            raise DescriptorError("declared total does not fit the 32-bit field")

        total = 0
        for index, segment in enumerate(self.segments):
            if segment.fd < 0:
                raise DescriptorError(f"segment {index} has a negative fd")
            if segment.length <= 0:
                raise DescriptorError(f"segment {index} has a non-positive length")
            if segment.length > _UINT32_MAX:
                raise DescriptorError(f"segment {index} length does not fit 32 bits")
            total += segment.length
        if total != self.declared_total:
            raise DescriptorError(
                f"segment lengths total {total}, descriptor declares "
                f"{self.declared_total}"
            )


@dataclass(frozen=True)
class WriteResult:
    destination: Path
    bytes_written: int
    committed: bool
    error: BaseException | None

    @property
    def success(self) -> bool:
        return self.committed and self.error is None


class JobHandle:
    """Completion object signalled only after commit, cleanup, and lease release."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: WriteResult | None = None

    @property
    def done(self) -> bool:
        return self._event.is_set()

    def result(self, timeout: float | None = None) -> WriteResult:
        if not self._event.wait(timeout):
            raise TimeoutError("LRI write did not finish before the timeout")
        if self._result is None:  # pragma: no cover - protects an invariant
            raise RuntimeError("writer signalled completion without a result")
        return self._result

    def _finish(self, result: WriteResult) -> None:
        self._result = result
        self._event.set()


@dataclass(frozen=True)
class _WriteJob:
    destination: Path
    temporary: Path
    snapshot: DescriptorSnapshot
    release_lease: Callable[[], None]
    handle: JobHandle


_STOP = object()


class AsyncLriWriter:
    """Single-worker, bounded reference implementation.

    ``enqueue`` copies FD ownership with ``dup`` before returning.  The caller's
    ``release_lease`` callback represents the separate producer-side promise
    that the underlying allocation will not be recycled or overwritten.  A
    duplicated FD alone cannot provide that promise for ION/DMA memory.
    """

    def __init__(
        self,
        *,
        maximum_inflight: int = 1,
        maximum_segments: int = 340,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        if maximum_inflight <= 0:
            raise ValueError("maximum_inflight must be positive")
        if maximum_segments <= 0:
            raise ValueError("maximum_segments must be positive")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        self._maximum_segments = maximum_segments
        self._chunk_size = chunk_size
        self._permits = threading.BoundedSemaphore(maximum_inflight)
        self._jobs: queue.Queue[_WriteJob | object] = queue.Queue()
        self._state_lock = threading.Lock()
        self._closed = False
        self._sequence = 0
        self._thread = threading.Thread(
            target=self._run,
            name="lri-writer",
            daemon=False,
        )
        self._thread.start()

    def enqueue(
        self,
        destination: Path,
        snapshot: DescriptorSnapshot,
        release_lease: Callable[[], None],
    ) -> JobHandle:
        """Validate, duplicate descriptors, and queue without waiting for I/O.

        A busy writer fails closed instead of blocking the camera callback.  If
        this method raises, ownership was not accepted and ``release_lease`` is
        not called.
        """

        snapshot.validate(maximum_segments=self._maximum_segments)
        destination = Path(destination)
        if not self._permits.acquire(blocking=False):
            raise WriterBusyError("the asynchronous writer already has an active job")

        duplicated: list[Segment] = []
        try:
            with self._state_lock:
                if self._closed:
                    raise RuntimeError("the asynchronous writer is closed")
                for segment in snapshot.segments:
                    duplicated.append(Segment(os.dup(segment.fd), segment.length))
                self._sequence += 1
                temporary = destination.with_name(
                    f".{destination.name}.partial-{os.getpid()}-{self._sequence}"
                )
                accepted = DescriptorSnapshot(
                    tuple(duplicated), snapshot.declared_total
                )
                handle = JobHandle()
                self._jobs.put_nowait(
                    _WriteJob(
                        destination,
                        temporary,
                        accepted,
                        release_lease,
                        handle,
                    )
                )
            return handle
        except BaseException:
            for segment in duplicated:
                os.close(segment.fd)
            self._permits.release()
            raise

    def close(self, timeout: float | None = None) -> None:
        """Drain accepted work and stop the worker."""

        with self._state_lock:
            if not self._closed:
                self._closed = True
                self._jobs.put_nowait(_STOP)
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise TimeoutError("asynchronous writer did not stop before the timeout")

    def __enter__(self) -> AsyncLriWriter:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _run(self) -> None:
        while True:
            item = self._jobs.get()
            if item is _STOP:
                return
            if not isinstance(item, _WriteJob):  # pragma: no cover - invariant
                raise RuntimeError("unexpected writer queue item")
            self._execute(item)

    def _execute(self, job: _WriteJob) -> None:
        bytes_written = 0
        committed = False
        temporary_created = False
        error: BaseException | None = None
        output_fd: int | None = None

        try:
            if job.destination.exists():
                raise FileExistsError(job.destination)
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            output_fd = os.open(job.temporary, flags, 0o600)
            temporary_created = True
            for segment in job.snapshot.segments:
                bytes_written += self._copy_segment(output_fd, segment)
            if bytes_written != job.snapshot.declared_total:
                raise OSError(
                    f"wrote {bytes_written} bytes, expected "
                    f"{job.snapshot.declared_total}"
                )
            os.fsync(output_fd)
            os.close(output_fd)
            output_fd = None
            if job.destination.exists():
                raise FileExistsError(job.destination)
            os.rename(job.temporary, job.destination)
            committed = True
        except BaseException as exc:
            error = exc
        finally:
            if output_fd is not None:
                try:
                    os.close(output_fd)
                except BaseException as exc:
                    if error is None:
                        error = exc
            if temporary_created and not committed:
                try:
                    job.temporary.unlink()
                except FileNotFoundError:
                    pass
                except BaseException as exc:
                    if error is None:
                        error = exc
            for segment in job.snapshot.segments:
                try:
                    os.close(segment.fd)
                except BaseException as exc:
                    if error is None:
                        error = exc
            try:
                job.release_lease()
            except BaseException as exc:
                if error is None:
                    error = exc
            self._permits.release()
            job.handle._finish(
                WriteResult(job.destination, bytes_written, committed, error)
            )

    def _copy_segment(self, output_fd: int, segment: Segment) -> int:
        copied = 0
        with mmap.mmap(segment.fd, segment.length, access=mmap.ACCESS_READ) as source:
            while copied < segment.length:
                end = min(copied + self._chunk_size, segment.length)
                chunk = source[copied:end]
                offset = 0
                while offset < len(chunk):
                    try:
                        written = os.write(output_fd, chunk[offset:])
                    except InterruptedError:
                        continue
                    if written <= 0:
                        raise OSError("output write made no forward progress")
                    offset += written
                copied = end
        return copied
