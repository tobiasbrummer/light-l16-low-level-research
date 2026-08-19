# Contributors and AI-assistance disclosure

## Tobias Brummer

Tobias Brummer is the research lead, device owner, repository maintainer, and
publisher. He supplied the lawfully controlled device and local artifacts,
directed the investigation, authorized device operations, evaluated the
practical risk, and made the publication and licensing decisions.

## OpenAI Codex

OpenAI Codex was used as an AI research and implementation assistant. Its
substantial contributions included:

- inspecting and correlating the firmware, kernel, userspace libraries, and
  existing project evidence;
- orchestrating targeted symbol recovery, disassembly, and decompilation;
- comparing the Light-specific driver behavior with the public Qualcomm MSM
  baseline;
- reconstructing and cross-checking the private compat ABI and driver data
  flow;
- identifying safety boundaries and statically reachable robustness defects;
- drafting and refining the documentation, clean-room header, host tools, and
  tests; and
- preparing and validating the publication repository.

The generated work was checked through exact artifact hashes, ARM64 instruction
inspection, independent userspace-consumer evidence, compilation, automated
tests, repository scans, and human direction. Codex is an assistance tool, not
the repository maintainer or copyright holder, and this disclosure does not
claim endorsement by OpenAI.

## Anthropic Claude

Anthropic Claude was used as an AI research and implementation assistant from
2026-08-18 onward. Its contributions included:

- designing and implementing the all-16 dark frame series: the capture plan,
  the device payloads, the Android application, and the Camera2 darkness check;
- extending the bounded capture architecture from a single exposure to a
  series inside one root session, replacing the reboot-after-every-attempt
  policy with a settle gate between captures while keeping the fail-closed
  behaviour;
- writing the pixel-level analysis tool, which is the first in this repository
  to decode RAW10 samples rather than stopping at the metadata;
- correcting two of its own errors that the first physical measurements
  exposed: the RAW10 packing had been assumed to follow the byte-aligned MIPI
  layout when it is a continuous little-endian bitstream, and a dark current
  slope had been computed from one frame per cell, letting drift enter as
  signal;
- finding a 32-bit overflow in the exposure bounds that made second-scale
  requests unrepresentable on this 32-bit device, and adding a static check
  that catches the class of defect without a device present;
- reducing the first physical series to per-module black level, fixed pattern
  noise, read noise, and the gain mapping, including the identification of
  stable uncorrected hot pixels; and
- consolidating the working tree into thematic commits and reviewing the
  publication boundary before each push.

Its work was checked through host tests, native mocks, device execution,
artifact hashes verified against the camera's own manifest, and human
direction. Several of its assumptions were disproved by measurement and are
documented as such rather than quietly corrected. Claude is an assistance
tool, not the repository maintainer or copyright holder, and this disclosure
does not claim endorsement by Anthropic.
