# Ownership-safe asynchronous LRI writing

## Status and verdict

The all-16 metadata-buffer failures are consistent with synchronous storage I/O
inside the camera result callback. The existing writer already processes the
returned FDs separately, but it performs every map and write before returning
from `LccInterface::processCaptureResult()`. Merely dividing the same callback
work into smaller writes would therefore not remove the stall. The useful
split is a bounded hand-off to one writer thread.

This document is a source-level patch specification. The accompanying Python
module is a host-only lifetime model, and the small clean-room preload library
is a deliberately narrower one-burst integration probe. That probe has now
completed one fixed A1 and one fixed all-16 device capture; the general
snapshot/lease implementation has not been installed or device-tested. None
of these is a patched LightOS HAL. No vendor binary has been modified or
installed.

The observations below apply to the exact `camera.msm8996.so` identity in
[`artifacts/known-builds.json`](../artifacts/known-builds.json).

## Measured reason for the change

The full-window A1 run wrote three returned FDs totalling 16,566,521 bytes. Its
last FD was logged 96 ms after `writeFile()` entered, and normal metadata
processing resumed two milliseconds later. The all-16 run wrote 20 FDs
totalling 259,999,993 bytes in about 1.144 seconds. Its first metadata-buffer
failure appeared 318 ms after `writeFile()` entered and repeated until the
write ended.

That size-dependent timing supports a callback-stall diagnosis. It does not
explain the separate RDI timeout or synthetic-buffer unmap diagnostics.

The current success convention is also too weak for asynchronous use. A zero
entry count or total produces the distinguished failure return, but an output
open failure ultimately follows the normal return path. Individual map
failures are logged and skipped, and a short stream write sets stream state
without being propagated to `processCaptureResult()`. Worker completion must
therefore carry a new explicit success/error result; it cannot reuse the old
return convention unchanged.

## Reconstructed ownership path

The special format-`0x30` result contains a 4 KiB descriptor rather than the
image bytes themselves. Its relevant fields are:

```text
+0x08  number of entries
+0x0c  declared total byte count
+0x10  first 12-byte entry
        +0x00  raw-buffer FD
        +0x08  raw-buffer length
```

The producer does not copy the raw payload into that descriptor. Instead:

1. `LightRawBufferManager::releaseBufferList()` moves the real
   `unique_ptr<LightRawBuffer>` objects out of the three transfer channels.
2. `TransferManager::checkStartTransfer()` fills the descriptor and invokes
   `QCamera3RawChannel::doStreamCbRoutine()` synchronously.
3. Only after that callback returns, it moves the same owning list into a
   `MultiBufferAllocation` retained by `TransferManager`.
4. `checkBuffersFreed()` later moves a released allocation into the size-keyed
   reuse cache.

`MultiBufferAllocation::isFree()` recognizes release by reading the first
eight bytes of its first raw allocation and comparing them with the two words
`0x89abcdef` and `0x01234567`.

The inspected LCC persistence path does not write that marker.
`LccInterface::writeFile()` maps every listed FD with read-only shared access,
writes it, and unmaps it. `processCaptureResult()` also contains no marker
store. Thus the current LCC flow leaves the producer allocation retained until
the HAL is closed; no early-reuse transition was found in this path.

This is enough to design a build-specific LCC change, but it is not permission
to treat a duplicated FD as ownership in a general camera client. `dup()` keeps
an FD number valid; it does not stop a producer, DMA engine, or allocator from
overwriting the same underlying ION allocation. A reusable implementation must
hold a producer-side lease and perform the marker/recycle transition only after
the writer has stopped reading.

For this exact LCC path, the implicit lease is the live HAL session plus the
absence of a marker store: `TransferManager` retains the allocation and
`closeCamera()` must not tear that owner down before worker completion. That
build-specific fact must not be generalized to another framework consumer.

## Required hand-off contract

The result callback should do only bounded memory and descriptor work:

1. Validate the entry count against the 4 KiB descriptor capacity (at most 340
   12-byte entries after the 16-byte header).
2. Copy every FD and length, using checked arithmetic to verify that their sum
   equals the declared total.
3. Duplicate the FDs, or transfer equivalent FD ownership, before returning.
4. Attach a producer lease which prevents reuse of the underlying allocations.
5. Reserve a unique final filename and enqueue one immutable job without
   waiting for storage.

The queue must fail closed when it already owns one large job. Blocking on a
full queue would recreate the callback stall; accepting an unbounded number of
all-16 jobs would retain hundreds of megabytes per job. A later burst request
should be delayed until the single permit is available.

The writer thread should then:

1. create a same-directory hidden `.partial-*` file with exclusive creation;
2. map each duplicated FD read-only and copy it in bounded chunks, preserving
   descriptor order;
3. require exact byte counts and treat map, write, flush, or close failures as
   capture failures;
4. `fsync()` and close the completed file;
5. rename it to the reserved `.lri` name so incomplete output never appears as
   a final artifact;
6. unmap and close all worker-side resources;
7. release the producer lease; and
8. publish completion to `closeCamera()`.

The completion signal must mean “committed or definitively failed,” not merely
“queued.” Otherwise `closeCamera()` can destroy the HAL and its retained raw
allocations while the worker still maps them. The request thread, result
condition, and writer error state must also share one synchronized shutdown
rule. Its condition wait should use a predicate loop. If the outer timeout
expires, shutdown must still join or safely cancel the worker before destroying
the producer; timing out is not permission to close live ION ownership.

```text
callback:  descriptor -> validate/snapshot -> acquire lease -> enqueue -> return
                                                       |
worker:                                                v
          partial -> ordered chunks -> fsync -> rename -> release -> complete
                                                       |
closeCamera:                          wait for this ----+
```

## Source-level patch points

For a source rebuild of this identified HAL, the smallest LCC-only change is:

- give `LccInterface` a writer state whose lifetime begins after camera setup
  and ends before the `QCamera3HardwareInterface` object is destroyed;
- change `processCaptureResult()` from a direct `writeFile()` call to the
  validated snapshot/enqueue operation;
- change `writeFile()` to consume an immutable job instead of rereading the
  mutable `LccBuffer` descriptor at `this + 0xf4`;
- move burst success/failure accounting and the result-condition signal to
  worker completion; and
- gate another burst result while the one-job lease is occupied.

For a general camera-consumer change, the stronger patch belongs on the
producer side: transfer or reference-count the `MultiBufferAllocation` itself
into the job and return it to the reuse cache only on worker completion. Since
the current producer constructs that object only after the synchronous callback
returns, this variant must also move construction before hand-off or introduce
an equivalent reference-counted token. It remains safe even if a future
consumer starts writing the release marker.

Adding fields directly to the stripped 32-bit object or redirecting calls in
place would be a fragile binary patch: it changes object layout, constructor,
destructor, callback, and shutdown behavior together. The current evidence is
therefore a design for a source rebuild or controlled shim, not justification
for installing a hand-edited HAL.

## Executable host model

[`tools/async_lri_writer.py`](../tools/async_lri_writer.py) implements the
contract with synthetic regular-file FDs. It deliberately models FD duplication
and the separate producer lease. Its tests cover:

- callback hand-off completing while I/O remains blocked;
- exact concatenation and descriptor order across short chunks;
- the observed 20-entry all-16 descriptor shape and exact total;
- refusal of a second in-flight lease;
- prevention of producer recycling until completion;
- descriptor-total validation; and
- removal of partial output plus lease release after a short source/map error.

Run only these host tests with:

```bash
.venv/bin/python -m pytest -q tests/test_async_lri_writer.py
```

Passing them validates the state machine, not Android/ION behavior or a camera
HAL patch.

An optional full-size test takes a locally retained 259,999,993-byte all-16
LRI, splits it at the exact 20 boundaries recorded by `writeFile()`, closes the
original FDs immediately after enqueue, and reassembles it through the worker.
It requires a bit over 500 MB of temporary space and removes that data after
the source/output SHA-256 comparison:

```bash
.venv/bin/python -m tools.stress_async_lri_writer \
  output/all16-capture-20260809T192149Z/pixels/RDI_20260809_212153_985.lri \
  --work-directory /home/t0bybr \
  --expected-sha256 2fef156da924746ce3e7cf6f71f558c74b3f47f632a4f9d404c75f19cfa85ceb
```

## Confirmed full-size host reassembly

The command above passed on 2026-08-09 using the retained all-16 LRI. The 20
observed segments consist of 16 raw allocations of 16,228,352 bytes, three
4,096-byte allocations, and one 334,073-byte final allocation. The source and
reassembled output were both exactly 259,999,993 bytes and had SHA-256
`2fef156da924746ce3e7cf6f71f558c74b3f47f632a4f9d404c75f19cfa85ceb`.

The enqueue hand-off took 0.143 ms while completion including file `fsync()`
took 1.105 seconds on the host filesystem, or 224.346 MiB/s. The test closed
all 20 original FDs immediately after enqueue, observed the lease release only
at completion, found no partial file, and removed its temporary split/output
data.

Those timings are not a prediction for the camera: the host used different
storage and the freshly split inputs were cache-hot. The useful result is the
separation of a sub-millisecond descriptor/FD hand-off from roughly one second
of ordered I/O, with a bit-identical final artifact. The later bounded A1 and
all-16 device probes verify the build-specific live-object lifetime path used
by the shim; they do not validate the general producer-lease implementation.

## Reversible preload integration probe

[`shim/lcc_async_writer_shim.c`](../shim/lcc_async_writer_shim.c) is a
clean-room, build-specific probe for the fixed one-frame profiles. The exact
examined HAL has dynamic jump-slot relocations for both
`LccInterface::writeFile()` and `LccInterface::closeCamera()` and does not use
`DT_SYMBOLIC`, so a library loaded before the HAL can interpose those two calls
without changing the file under `/system`.

At load time the probe opens the exact 32-bit HAL path, resolves both original
methods from that handle, and rejects either address if it points back to the
shim. It then removes `LD_PRELOAD` from the process environment so 64-bit helper
programs cannot inherit a 32-bit library. Because this Android 6 build's
`system()` still propagated the preload string after `unsetenv()`, the probe
also supplies a bounded shell wrapper with an explicitly filtered environment.
The fixed profile requires exactly seven successful factory helper commands.
The interposed writer starts exactly
one worker and returns immediately. The worker calls the resolved original
`writeFile()`. The interposed close path
joins that worker before it calls the original `closeCamera()`, keeping the
LCC object and HAL session alive until the original writer has stopped reading.
It fails closed through fixed lifecycle markers if symbol resolution, thread
creation, the writer, joining, or the one-job protocol fails.

This prototype is intentionally not the general implementation specified
above. It does not snapshot and duplicate every descriptor entry; the original
writer still rereads the LCC-owned descriptor through the live object. That is
acceptable only as a bounded compatibility probe for the fixed `n_burst=1`
workflow, where no second request can overwrite the descriptor and teardown is
held at `closeCamera()`. It must not be reused for bursts, another HAL build, or
another consumer without implementing the full snapshot and producer-lease
contract.

The native mock in [`tests/test_lcc_async_shim.py`](../tests/test_lcc_async_shim.py)
proves that the unmodified callback blocks for at least 200 ms, while the
preloaded callback returns in under 50 ms on another thread and the close path
still observes completed writing. The mock also checks the join ordering and
the exact interposed symbol relocations.

The reviewed Android build is reproducible with:

```bash
L16_LLD=/path/to/ld.lld \
  host/build_lcc_async_shim.sh \
  /absolute/output/liblcc_async_writer_shim.so
```

Using Ubuntu Clang and LLD 20.1.8 produced an 9,080-byte ARMv7/Thumb-2,
soft-float EABI shared object with SHA-1
`0b93dc17a2c4219943293d96b7edda39be61613d`, SHA-256
`f2da28cefc60027a884680ee9f4d0bf1966555982c7cacc9dda17ea65fa2be2b`,
and GNU build ID `0151acd49bc0ace82b96b6be770fdc1352768021`. It has no
`DT_NEEDED` entry. Its imports are the documented Bionic loader, environment,
process, thread, and write primitives; its only exports are the two target
methods and the bounded `system` wrapper. It uses supported ARM relative,
global-data, and jump-slot relocations and has a non-executable stack.

An Android 6.0.1 loader-only smoke test copied the identified 32-bit `lcc` and
this library to `/data/local/tmp`, ran only `lcc -h` with `LD_PRELOAD`, and
observed successful target resolution plus the filtered-child self-test with
exit status zero. The temporary files were removed and CameraService remained
empty. This proves that the production linker accepts the DSO and that its
early fail-closed checks run before camera open.

## Device integration history

The first bounded A1 integration attempt is retained under
`output/a1-async-capture-20260809T214454Z/`. It failed closed: `lcc` exited 138,
no new LRI was accepted, and the then-current `RTLD_NEXT` lookup resolved the
interposed methods back into the shim. The resulting `unexpected_second_write`
and repeated `close_continue` markers exposed the recursion. Seven 64-bit shell
helpers also inherited the 32-bit preload and failed to link. The wrapper still
restored `manual_control=0`, found no surviving `lcc` or CameraService client,
cleaned its staging files, and requested the mandatory reboot. The post-boot
state was healthy. Resolution was changed to an exact handle for the identified
HAL, with an explicit rejection of self-resolution.

The second attempt, `output/a1-async-capture-20260809T215248Z/`, proved that
the recursion was gone: `lcc` returned zero, the worker/close join completed,
and one 16,566,521-byte LRI was transferred. It was not a valid fixed-profile
control result. All seven factory shell helpers still inherited the 32-bit
preload, so the manual CCB commands did not run. Decoding caught the semantic
failure: A1 recorded 36,490,776 ns, analog gain 3.75, and digital gain 1.03125
instead of the requested 20 ms and gain 1.0. The old wrapper's `PASS` meant only
that its then-required lifecycle and artifact checks succeeded; it did not
validate LRI capture metadata.

The final shim supplies a bounded `system` wrapper which forks the fixed system
shell with an explicitly filtered environment. Its constructor runs a harmless
child self-test before camera open, and production close now requires exactly
seven successful helper commands. The final attempt is retained under
`output/a1-async-capture-20260809T220728Z/`. It returned `lcc` status zero,
produced exactly one 16,566,521-byte LRI with matching device/host SHA-1
`008dc190d2a9a1e38615bcb5a73d4e342a1de3f8`, and emitted all eleven expected
lifecycle markers exactly once. The marker order proves one enqueue and worker,
writer completion before original close continuation, and successful helper
and close reporting.

All eight LRI blocks decode completely, with no unknown protobuf field or
unused message bytes. The only fired module is A1, packed RAW10 at 4160 x 3120,
with 19,999,956 ns exposure and analog/digital gain 1.0. Normalization completed
without warning or saturated pixels. The conservative log analyzer still
reports `CONTROL_PATH_FAILED` for two RDI SOF timeouts and the independent
buffer-unmap chain; it found no metadata-pool exhaustion or paired failure to
issue SOF to all modules. The current `lcc` stream and 00:07 capture interval
contain no helper/linker failure. The retained logcat crash ring does contain
one `page record` line from 23:58:50, more than eight minutes before the final
LRI, so it is historical evidence rather than a failure of this attempt. The
mandatory reboot returned to the expected clean service, process,
runner-property, manual-control, and CameraService state.

This first established the exact fixed one-frame A1 probe. The wrapper's `PASS`
remains a lifecycle, cleanup, and byte-transfer verdict; decoded exposure and
gain were checked separately.

## All-16 device confirmation

The same reviewed DSO was then exercised with the fixed explicit all-module
mask `FE FF 01`. The retained bundle is
`output/all16-async-capture-20260810T145618Z/`. `lcc` returned zero, all eleven
lifecycle markers occurred exactly once, and the wrapper copied one
259,999,993-byte LRI with matching device/host SHA-1
`9fb56c01ad11cb3507bb091c89866f51e3fa0295`. All ten blocks decode completely;
all 16 expected RAW10 surfaces record 19,999,956 ns and analog/digital gain 1.0.
Full normalization completed without a saturated pixel.

Against the synchronous all-16 baseline, both 49-message failure series fell
to zero: no `mct_stream_get_metadata_buffer` failure and no paired `Failed to
issue SOF cmd to all modules` remained. The count of `RDI SOF` timeouts stayed
at 19 and the two-message unmap chain stayed at two. Moving only the original
writer call off the callback therefore removed the size-dependent metadata
exhaustion while leaving the independent diagnostics unchanged. This confirms
the callback-stall hypothesis for the exact build and fixed one-frame workflow;
it does not turn the remaining camera control path into a clean pass.

The host removed every staged executable/library and requested the mandatory
normal reboot. Boot, services, manual control, runner properties, and process
state returned cleanly. The stock camera application was the only CameraService
client observed immediately after boot; a later check found no active client.
No installed HAL or partition changed.

## Safe device-test ladder

1. Run the host tests and a synthetic 20-segment, approximately 260 MB job.
   Passed with a bit-identical full-size reassembly using the exact 20 observed
   segment sizes from the retained synchronous all-16 artifact.
2. Load the implementation only from a reversible test location; retain the
   original HAL hash and a recovery path. Passed; the system copy was not
   replaced.
3. Run the bounded A1 profile first. Require a fully framed and decoded LRI,
   exact requested capture metadata, clean teardown, and a mandatory reboot.
   Passed after the two fail-closed iterations documented above.
4. Only then run the bounded all-16 async profile. Passed with the mandatory
   reboot policy and the fully decoded 260 MB artifact documented above.
5. Compare the full diagnostic window with the synchronous baseline. Passed:
   the 49 metadata-pool/SOF pairs disappeared, confirming the stall hypothesis.
   The unchanged 19 RDI timeouts and two-message unmap chain remain separate,
   unresolved control-path defects.
