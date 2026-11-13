"""The honest number: accuracy on 20 hand-written SMS in a different voice
from the 5 generator templates (generic Indian-bank phrasing, fictional
banks the parser has never seen). Unlike test_parse.py's templated samples,
this is NOT expected to score anywhere near 95% — it's here to show the
real gap between "parses its own generator's output" and "parses an SMS
nobody wrote the regex against"."""

import json
from pathlib import Path

import pytest

from finsight_ml.parse import parse_sms

SAMPLES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "sample"
    / "sms_handwritten.txt"
)


def _load_samples() -> list[dict]:
    if not SAMPLES_PATH.exists():
        return []
    with SAMPLES_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


_SAMPLES = _load_samples()


def test_handwritten_accuracy_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    if not _SAMPLES:
        pytest.skip("data/sample/sms_handwritten.txt missing")

    parseable = [s for s in _SAMPLES if s["expected"] is not None]
    correct = 0
    for s in parseable:
        r = parse_sms(s["sms"])
        if (
            r is not None
            and r.amount_paise == s["expected"]["amount_paise"]
            and r.direction == s["expected"]["direction"]
            and r.vpa == s["expected"]["vpa"]
        ):
            correct += 1
    accuracy = correct / len(parseable) if parseable else 0.0

    with capsys.disabled():
        print(
            f"\n[honest number] hand-written SMS parse accuracy: {correct}/{len(parseable)} = {accuracy:.1%} "
            f"(5 generator templates vs 20 differently-phrased, fictional-bank messages)"
        )

    # Not a pass/fail gate — this file exists to report the real number, not
    # to enforce one. Just a sanity check that nothing crashed.
    assert 0.0 <= accuracy <= 1.0
