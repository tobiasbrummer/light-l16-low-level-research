#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Conservatively classify a bundle from the fixed Light L16 A1 wrapper."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PASS_VERDICT = "CONTROL_PATH_PASS_LRI_FRAMING_ONLY"
FAILED_VERDICT = "CONTROL_PATH_FAILED"
WRAPPER_FAILED_VERDICT = "WRAPPER_FAILED"
INCOMPLETE_VERDICT = "INCOMPLETE_EVIDENCE"
PREFLIGHT_VERDICT = "PREFLIGHT_STOPPED"

_KEY_VALUE = re.compile(r"^([a-z][a-z0-9_]*)=(.*)$")
_MANUAL_ZERO = re.compile(r"(?:^|\s)(?:0|0x0)$", re.IGNORECASE)
_REMOTE_LRI = re.compile(r"^/sdcard/DCIM/camera/(RDI_[0-9]{8}_[0-9]{6}_[0-9]{3}\.lri)$")
_LRI_HEADER = struct.Struct("<4sQQIB7x")
_LRI_MAGIC = b"LELR"

_LCC_FAILURE_PATTERNS = (
    (
        "lcc_open_failed",
        re.compile(r"Unable to open camera pipeline", re.IGNORECASE),
    ),
    (
        "lcc_load_failed",
        re.compile(
            r"(?:Failed to load light-camera-interface\.so|Load function fail)",
            re.IGNORECASE,
        ),
    ),
    (
        "lcc_response_length_mismatch",
        re.compile(r"Received length .* does not match expected length", re.IGNORECASE),
    ),
    (
        "lcc_close_failed",
        re.compile(r"Closed camera pipeline, 0", re.IGNORECASE),
    ),
    (
        "lcc_capture_rejected",
        re.compile(
            r"(?:\*\*\*Error\*\*\*|Can't capture|Not enough data for capture|"
            r"Invalid (?:data|resolution)|Data need \d+ but Data input)",
            re.IGNORECASE,
        ),
    ),
    (
        "lcc_shell_failure",
        re.compile(
            r"(?:Permission denied|No such file or directory|not found)",
            re.IGNORECASE,
        ),
    ),
)

_DIAGNOSTIC_FAILURE_PATTERNS = (
    ("mipi_rx_error", re.compile(r"\bMIPI RX\[", re.IGNORECASE)),
    (
        "kernel_fault",
        re.compile(
            r"(?:\bBUG:|Kernel panic|\bOops:|Unable to handle kernel|"
            r"Internal error:|watchdog.*(?:bite|lockup))",
            re.IGNORECASE,
        ),
    ),
    (
        "process_fatal",
        re.compile(r"(?:FATAL EXCEPTION|Fatal signal \d+)", re.IGNORECASE),
    ),
    (
        "camera_stack_error",
        re.compile(
            r"(?:light_ccb|lightsvr|camera\.msm8996|QCamera|mm-camera|CCI|I2C|SPI)"
            r".{0,160}(?:NACK|timed\s+out|timeout(?!\s+thread\b)|fatal|failed|failure)",
            re.IGNORECASE,
        ),
    ),
    (
        "camera_stack_error",
        re.compile(
            r"(?:NACK|timed\s+out|timeout(?!\s+thread\b)|fatal|failed|failure)"
            r".{0,160}(?:light_ccb|lightsvr|camera\.msm8996|QCamera|mm-camera|CCI|I2C|SPI)",
            re.IGNORECASE,
        ),
    ),
)

_DIAGNOSTIC_REVIEW_PATTERNS = (
    (
        "camera_stack_error_review",
        re.compile(
            r"(?:light_ccb|lightsvr|camera\.msm8996|QCamera|mm-camera|CCI|I2C|SPI)"
            r".{0,160}\berror\b",
            re.IGNORECASE,
        ),
    ),
    (
        "camera_stack_error_review",
        re.compile(
            r"\berror\b.{0,160}"
            r"(?:light_ccb|lightsvr|camera\.msm8996|QCamera|mm-camera|CCI|I2C|SPI)",
            re.IGNORECASE,
        ),
    ),
)

_POSITIVE_LCC_MARKERS = (
    "Open camera pipeline",
    "Start Capture",
    "Closed camera pipeline, 1",
)


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str


@dataclass(frozen=True)
class Analysis:
    verdict: str
    exit_code: int
    capture_attempted: str
    wrapper_status: str
    pixel_validation: str
    post_reboot_validation: str
    evidence_directory: str | None
    findings: tuple[Finding, ...]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_key_values(text: str) -> dict[str, str]:
    """Return the last value for each simple wrapper result/state key."""

    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _KEY_VALUE.fullmatch(line.rstrip("\r"))
        if match:
            values[match.group(1)] = match.group(2)
    return values


def new_lines(before: str, after: str) -> list[str]:
    """Subtract an overlapping bounded snapshot without assuming a prefix."""

    remaining = Counter(before.splitlines())
    delta: list[str] = []
    for line in after.splitlines():
        if remaining[line]:
            remaining[line] -= 1
        else:
            delta.append(line)
    return delta


def _manual_is_zero(value: str) -> bool:
    return bool(_MANUAL_ZERO.search(value.strip()))


def _camera_clients_none(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines()]
    try:
        start = lines.index("Active Camera Clients:")
    except ValueError:
        return False
    for line in lines[start + 1 :]:
        if not line:
            continue
        return line == "[]"
    return False


def _evidence_directory(root: Path) -> Path:
    direct = root / "device"
    if (direct / "lcc.txt").is_file():
        return direct
    candidates = sorted({path.parent for path in direct.rglob("lcc.txt")})
    if len(candidates) == 1:
        return candidates[0]
    return direct


def _short_log_line(line: str, maximum: int = 240) -> str:
    compact = " ".join(line.split())
    if len(compact) <= maximum:
        return compact
    return compact[: maximum - 3] + "..."


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_lri_container(path: Path) -> tuple[int, str | None]:
    """Validate only the public 32-byte LELR block framing.

    This intentionally does not decode proprietary protobuf messages or judge
    whether the raw samples are plausible.
    """

    size = path.stat().st_size
    offset = 0
    blocks = 0
    with path.open("rb") as stream:
        while offset < size:
            remaining = size - offset
            if remaining < _LRI_HEADER.size:
                return blocks, f"trailing {remaining} bytes at offset {offset}"
            stream.seek(offset)
            raw_header = stream.read(_LRI_HEADER.size)
            if len(raw_header) != _LRI_HEADER.size:
                return blocks, f"short header read at offset {offset}"
            magic, block_length, message_offset, message_length, _ = _LRI_HEADER.unpack(
                raw_header
            )
            if magic != _LRI_MAGIC:
                return blocks, f"bad magic at block {blocks} offset {offset}"
            if block_length < _LRI_HEADER.size:
                return blocks, f"invalid block length {block_length} at block {blocks}"
            if block_length > remaining:
                return blocks, f"block {blocks} extends beyond end of file"
            if not (_LRI_HEADER.size <= message_offset <= block_length):
                return blocks, f"invalid message offset at block {blocks}"
            if message_length > block_length - message_offset:
                return blocks, f"message extends beyond block {blocks}"
            offset += block_length
            blocks += 1
    if blocks == 0:
        return 0, "container has no blocks"
    return blocks, None


def _scan_lines(
    lines: Iterable[str],
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
    *,
    level: str = "FAIL",
) -> list[Finding]:
    findings: list[Finding] = []
    for line in lines:
        for code, pattern in patterns:
            if pattern.search(line):
                findings.append(Finding(level, code, _short_log_line(line)))
                break
    return findings


def analyze_capture(root: Path) -> Analysis:
    """Analyze one ``output/a1-capture-<UTC>`` directory."""

    root = root.resolve()
    result_path = root / "result.txt"
    if not result_path.is_file():
        partial = root / "result.partial.txt"
        note = "completed result.txt is missing"
        if partial.is_file():
            note += "; result.partial.txt exists"
        return Analysis(
            INCOMPLETE_VERDICT,
            2,
            "unknown",
            "unknown",
            "not_available_capture_bundle_incomplete",
            "not_in_capture_bundle",
            None,
            (Finding("INCOMPLETE", "result_missing", note),),
        )

    result = parse_key_values(_read_text(result_path))
    attempted = result.get("capture_attempted", "unknown")
    wrapper_status = result.get("final_status", "unknown")

    if attempted == "no" and wrapper_status == "FAIL":
        reason = result.get("final_reason", result.get("failure", "unknown"))
        return Analysis(
            PREFLIGHT_VERDICT,
            2,
            attempted,
            wrapper_status,
            "not_attempted",
            "not_required_by_capture",
            None,
            (
                Finding(
                    "NOTE",
                    "preflight_stopped",
                    f"lcc was not reached; reason={reason}",
                ),
            ),
        )

    findings: list[Finding] = []
    pixel_validation = "not_available_capture_artifact_missing"
    normal_reboot = result.get("normal_reboot_required")
    required_result_keys = [
        "capture_attempted",
        "final_status",
        "lcc_exit_status",
        "cleanup_ok",
        "manual_control_after",
        "lcc_process_after",
        "normal_reboot_required",
        "lri_output_count",
        "lri_output_path",
        "lri_output_size",
        "lri_output_sha1",
    ]
    if normal_reboot == "no":
        required_result_keys.extend(
            ("settled_camera_clients", "media_after", "lightsvr_after")
        )
    missing_result_keys = [
        key for key in required_result_keys if key not in result
    ]
    if missing_result_keys:
        findings.append(
            Finding(
                "INCOMPLETE",
                "result_fields_missing",
                ",".join(missing_result_keys),
            )
        )

    explicit_wrapper_failures: list[str] = []
    expected_values = {
        "capture_attempted": "yes",
        "final_status": "PASS",
        "lcc_exit_status": "0",
        "cleanup_ok": "yes",
        "lcc_process_after": "no",
        "lri_output_count": "1",
    }
    for key, expected in expected_values.items():
        actual = result.get(key)
        if actual is not None and actual != expected:
            explicit_wrapper_failures.append(f"{key}={actual} (expected {expected})")
    manual_after = result.get("manual_control_after")
    if manual_after is not None and not _manual_is_zero(manual_after):
        explicit_wrapper_failures.append(
            f"manual_control_after={manual_after} (expected zero)"
        )
    if normal_reboot is not None and normal_reboot not in {"yes", "no"}:
        explicit_wrapper_failures.append(
            f"normal_reboot_required={normal_reboot} (expected yes or no)"
        )
    if normal_reboot == "no":
        no_reboot_values = {
            "settled_camera_clients": "none",
            "media_after": "running",
            "lightsvr_after": "running",
        }
        for key, expected in no_reboot_values.items():
            actual = result.get(key)
            if actual is not None and actual != expected:
                explicit_wrapper_failures.append(
                    f"{key}={actual} (expected {expected} for no reboot)"
                )
    if "failure" in result and wrapper_status == "PASS":
        explicit_wrapper_failures.append(
            f"failure={result['failure']} is inconsistent with final_status=PASS"
        )
    if explicit_wrapper_failures:
        findings.append(
            Finding(
                "FAIL",
                "wrapper_postcondition_failed",
                "; ".join(explicit_wrapper_failures),
            )
        )

    evidence = _evidence_directory(root)
    required_files = [
        "lcc.txt",
        "dmesg.before.txt",
        "dmesg.after.txt",
        "logcat.before.txt",
        "logcat.after.txt",
        "state.after.txt",
        "camera.after_immediate.txt",
    ]
    if normal_reboot == "no":
        required_files.append("camera.after.txt")
    missing_files = [name for name in required_files if not (evidence / name).is_file()]
    if missing_files:
        findings.append(
            Finding("INCOMPLETE", "evidence_files_missing", ",".join(missing_files))
        )

    lcc_path = evidence / "lcc.txt"
    if lcc_path.is_file():
        lcc_text = _read_text(lcc_path)
        findings.extend(_scan_lines(lcc_text.splitlines(), _LCC_FAILURE_PATTERNS))
        missing_markers = [
            marker for marker in _POSITIVE_LCC_MARKERS if marker not in lcc_text
        ]
        if missing_markers:
            findings.append(
                Finding(
                    "INCOMPLETE",
                    "lcc_success_markers_missing",
                    ",".join(missing_markers),
                )
            )

    for source in ("dmesg", "logcat"):
        before_path = evidence / f"{source}.before.txt"
        after_path = evidence / f"{source}.after.txt"
        if before_path.is_file() and after_path.is_file():
            delta = new_lines(_read_text(before_path), _read_text(after_path))
            findings.extend(_scan_lines(delta, _DIAGNOSTIC_FAILURE_PATTERNS))
            review_lines = [
                line
                for line in delta
                if not re.search(r"\berrors?\s*(?:count\s*)?[:=]?\s*0\b", line, re.I)
                and not any(
                    pattern.search(line)
                    for _code, pattern in _DIAGNOSTIC_FAILURE_PATTERNS
                )
            ]
            findings.extend(
                _scan_lines(review_lines, _DIAGNOSTIC_REVIEW_PATTERNS, level="REVIEW")
            )

    state_path = evidence / "state.after.txt"
    if state_path.is_file():
        state = parse_key_values(_read_text(state_path))
        manual = state.get("manual_control")
        if manual is None:
            findings.append(
                Finding("INCOMPLETE", "state_manual_missing", "manual_control")
            )
        elif not _manual_is_zero(manual):
            findings.append(
                Finding("FAIL", "state_manual_nonzero", f"manual_control={manual}")
            )
        for service in ("media", "lightsvr"):
            status = state.get(service)
            if status is None:
                findings.append(Finding("INCOMPLETE", "state_service_missing", service))
            elif status != "running":
                findings.append(
                    Finding("FAIL", "state_service_not_running", f"{service}={status}")
                )

    camera_path = evidence / "camera.after_immediate.txt"
    if camera_path.is_file() and not _camera_clients_none(_read_text(camera_path)):
        findings.append(
            Finding(
                "FAIL",
                "camera_clients_not_empty_or_unknown",
                "the immediate post-capture CameraService snapshot is not empty",
            )
        )

    if normal_reboot == "no":
        settled_camera_path = evidence / "camera.after.txt"
        if settled_camera_path.is_file() and not _camera_clients_none(
            _read_text(settled_camera_path)
        ):
            findings.append(
                Finding(
                    "FAIL",
                    "settled_camera_clients_not_empty_or_unknown",
                    "the settled no-reboot CameraService snapshot is not empty",
                )
            )

    if result.get("lri_output_count") == "1":
        remote_path = result.get("lri_output_path", "")
        remote_match = _REMOTE_LRI.fullmatch(remote_path)
        expected_size_text = result.get("lri_output_size", "")
        expected_sha1 = result.get("lri_output_sha1", "")
        if remote_match is None:
            findings.append(
                Finding("FAIL", "lri_remote_path_invalid", remote_path or "missing")
            )
        elif not expected_size_text.isdecimal():
            findings.append(
                Finding(
                    "FAIL", "lri_reported_size_invalid", expected_size_text or "missing"
                )
            )
        elif re.fullmatch(r"[0-9a-f]{40}", expected_sha1) is None:
            findings.append(
                Finding("FAIL", "lri_reported_sha1_invalid", expected_sha1 or "missing")
            )
        else:
            local_lri = root / "pixels" / remote_match.group(1)
            if not local_lri.is_file():
                pixel_validation = "lri_reported_but_not_in_capture_bundle"
                findings.append(
                    Finding(
                        "INCOMPLETE",
                        "lri_artifact_not_pulled",
                        str(local_lri),
                    )
                )
            else:
                actual_size = local_lri.stat().st_size
                actual_sha1 = _sha1(local_lri)
                expected_size = int(expected_size_text)
                if actual_size != expected_size:
                    pixel_validation = "lri_transfer_integrity_failed"
                    findings.append(
                        Finding(
                            "INCOMPLETE",
                            "lri_size_mismatch",
                            f"device={expected_size} host={actual_size}",
                        )
                    )
                elif actual_sha1 != expected_sha1:
                    pixel_validation = "lri_transfer_integrity_failed"
                    findings.append(
                        Finding(
                            "INCOMPLETE",
                            "lri_sha1_mismatch",
                            f"device={expected_sha1} host={actual_sha1}",
                        )
                    )
                else:
                    blocks, framing_error = validate_lri_container(local_lri)
                    if framing_error is not None:
                        pixel_validation = "lri_container_framing_invalid"
                        findings.append(
                            Finding("FAIL", "lri_container_invalid", framing_error)
                        )
                    else:
                        pixel_validation = (
                            "lri_transfer_and_container_framing_valid_"
                            "protobuf_and_pixels_unverified"
                        )
                        findings.append(
                            Finding(
                                "NOTE",
                                "lri_container_framing_valid",
                                f"blocks={blocks} size={actual_size} sha1={actual_sha1}",
                            )
                        )

    if explicit_wrapper_failures:
        verdict, exit_code = WRAPPER_FAILED_VERDICT, 1
    elif any(finding.level == "FAIL" for finding in findings):
        verdict, exit_code = FAILED_VERDICT, 1
    elif any(finding.level in {"INCOMPLETE", "REVIEW"} for finding in findings):
        verdict, exit_code = INCOMPLETE_VERDICT, 2
    else:
        verdict, exit_code = PASS_VERDICT, 0
        findings.append(
            Finding(
                "NOTE",
                "scope_boundary",
                "LRI transfer and block framing only; module identity, protobuf content, and raw samples remain unverified",
            )
        )
        if normal_reboot == "yes":
            findings.append(
                Finding(
                    "NOTE",
                    "reboot_check_required",
                    "confirm normal boot, services, manual_control, and fihop properties live",
                )
            )
        elif normal_reboot == "no":
            findings.append(
                Finding(
                    "NOTE",
                    "continued_uptime_check_required",
                    "confirm continued uptime, services, manual_control, CameraService, and fihop properties live",
                )
            )

    return Analysis(
        verdict,
        exit_code,
        attempted,
        wrapper_status,
        pixel_validation,
        "not_in_capture_bundle",
        str(evidence),
        tuple(findings),
    )


def format_analysis(analysis: Analysis) -> str:
    lines = [
        f"verdict={analysis.verdict}",
        f"capture_attempted={analysis.capture_attempted}",
        f"wrapper_status={analysis.wrapper_status}",
        f"pixel_validation={analysis.pixel_validation}",
        f"post_reboot_validation={analysis.post_reboot_validation}",
    ]
    if analysis.evidence_directory is not None:
        lines.append(f"evidence_directory={analysis.evidence_directory}")
    lines.extend(
        f"finding={finding.level}:{finding.code}:{finding.message}"
        for finding in analysis.findings
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_directory", type=Path)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args(argv)

    if not args.capture_directory.is_dir():
        parser.error(f"not a directory: {args.capture_directory}")
    analysis = analyze_capture(args.capture_directory)
    if args.json:
        print(json.dumps(asdict(analysis), indent=2, sort_keys=True))
    else:
        print(format_analysis(analysis))
    return analysis.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
