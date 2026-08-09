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
