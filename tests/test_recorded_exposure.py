"""The exposure a capture used, versus the one it was asked for.

A 29 s request comes back as 19,450,064,896 ns with no error anywhere: lcc
exits 0, the LRI is complete, the logs read like success.  This project
published "29 s captures work" because the recorded value was checked at 6 s
and assumed at 29 s.  These tests encode the difference so the documentation
cannot drift back.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Measured on the covered 15-capture series, three repeats per step.
RECORDED = {
    100_000_000: 99_999_776,
    1_000_000_000: 999_927_744,
    6_000_000_000: 6_000_159_744,
    29_000_000_000: 19_450_064_896,
}
CLAMP_NS = 19_450_064_896


def test_short_requests_are_honoured_to_within_row_quantisation() -> None:
    """Everything below the clamp lands within 0.01% of the request."""
    for requested, recorded in RECORDED.items():
        if recorded == CLAMP_NS:
            continue
        error = abs(recorded - requested) / requested
        assert error < 1e-4, f"{requested} ns recorded as {recorded} ns"


def test_the_longest_request_is_clamped_not_honoured() -> None:
    assert RECORDED[29_000_000_000] == CLAMP_NS
    assert CLAMP_NS < 29_000_000_000


def test_no_document_claims_captures_run_at_29_s() -> None:
    """The claim that was published and had to be corrected.

    History files are exempt: they record what was believed at the time, and
    the correction is part of the record.
    """
    for name in ("README.md", "SECURITY.md", "docs/lcc-control.md",
                 "docs/dark-frame-series.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for match in re.finditer(r"[^.]*\b29 s\b[^.]*\.", text):
            sentence = match.group(0)
            # Mentioning 29 s is fine; claiming it as the exposure used is
            # not.  A sentence that retracts the claim necessarily quotes it,
            # so retractions are allowed to say the words.
            claims_it_ran = re.search(
                r"29 s (capture|exposure)s? (work|complete|succeed)", sentence
            )
            retracts = re.search(
                r"previously|no longer|does not|did not|wrong|correction",
                sentence, re.I,
            )
            assert not (claims_it_ran and not retracts), (
                f"{name}: {sentence.strip()}"
            )


def test_the_readme_tells_readers_to_read_the_exposure_back() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "19.45 s" in readme
    assert "clamped" in readme.lower()
    assert "recorded" in readme.lower()
