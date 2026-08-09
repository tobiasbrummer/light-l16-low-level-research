from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_known_build_hashes_have_expected_shape() -> None:
    manifest = json.loads(
        (ROOT / "artifacts" / "known-builds.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    artifacts = manifest["targets"][0]["artifacts"]
    assert artifacts
    for identity in artifacts.values():
        assert re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
        if "gnu_build_id" in identity:
            build_id = identity["gnu_build_id"]
            assert re.fullmatch(r"[0-9a-f]+", build_id)
            assert 16 <= len(build_id) <= 64
            assert len(build_id) % 2 == 0


def test_root_probe_is_syntax_valid_and_bounded() -> None:
    payload = ROOT / "device" / "root_probe_payload.sh"
    text = payload.read_text(encoding="utf-8")
    shell = shutil.which("sh")
    if shell is not None:
        subprocess.run([shell, "-n", str(payload)], check=True)

    assert text.index("setprop persist.sys.fihop 0") < text.index("id\n")
    for argument in range(1, 6):
        assert f'setprop persist.sys.fihop{argument} ""' in text
    for forbidden in ("/dev/block", "reboot", "mount ", "camera_enable", "eeprom"):
        assert forbidden not in text


def test_repository_contains_no_proprietary_binary_extensions() -> None:
    forbidden_suffixes = {".apk", ".bin", ".elf", ".img", ".so", ".zip"}
    offenders = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(ROOT).parts)
        and path.suffix.lower() in forbidden_suffixes
    ]
    assert offenders == []


def test_relative_markdown_links_resolve() -> None:
    pattern = re.compile(r"]\((?!https?://|mailto:|#)([^)#]+)(?:#[^)]+)?\)")
    missing: list[str] = []
    for document in ROOT.rglob("*.md"):
        text = document.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            target = document.parent / match.group(1)
            if not target.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {match.group(1)}")
    assert missing == []
