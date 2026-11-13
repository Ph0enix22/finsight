import json
from pathlib import Path

import pytest

from finsight_ml.parse import parse_sms

SAMPLES_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "sample"
    / "sms_samples.txt"
)


def _load_samples() -> list[dict]:
    if not SAMPLES_PATH.exists():
        return []
    with SAMPLES_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


_SAMPLES = _load_samples()


@pytest.mark.skipif(
    not _SAMPLES,
    reason="data/sample/sms_samples.txt not generated — run scripts/generate.py",
)
@pytest.mark.parametrize("sample", _SAMPLES, ids=lambda s: s["sms"][:40])
def test_sms_sample(sample: dict) -> None:
    result = parse_sms(sample["sms"])
    expected = sample["expected"]
    if expected is None:
        assert result is None, f"expected unparseable but got {result}"
        return
    assert result is not None, "expected a parse but got None"
    assert result.amount_paise == expected["amount_paise"]
    assert result.direction == expected["direction"]
    assert result.vpa == expected["vpa"]
    assert result.bank_label == expected["bank"]


def test_sms_sample_accuracy_meets_spec_target() -> None:
    """SPEC target: >=95% parse accuracy. Measured on the full varied set
    (format-noise + ~5% deliberately unparseable)."""
    if not _SAMPLES:
        pytest.skip("data/sample/sms_samples.txt not generated")
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
    accuracy = correct / len(parseable)
    assert accuracy >= 0.95, f"parse accuracy {accuracy:.2%} below the 95% SPEC target"


def test_unparseable_messages_do_not_false_positive() -> None:
    if not _SAMPLES:
        pytest.skip("data/sample/sms_samples.txt not generated")
    unparseable = [s for s in _SAMPLES if s["expected"] is None]
    false_positives = sum(1 for s in unparseable if parse_sms(s["sms"]) is not None)
    assert false_positives == 0


def test_llm_fallback_flag_is_stubbed() -> None:
    from finsight_ml.parse import LLMFallbackNotImplemented

    with pytest.raises(LLMFallbackNotImplemented):
        parse_sms("not a real bank message at all", use_llm_fallback=True)
