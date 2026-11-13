"""Transaction categoriser: TF-IDF(char 2-5) over merchant text + amount/hour/
weekday -> LogisticRegression. Falls back to a plain keyword/fuzzy-match
baseline (via finsight_ml.normalise) when no trained artifact is present, and
flags low-confidence predictions for the (Phase 5) LLM few-shot hook.
"""

import math
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from finsight_ml.normalise import NormalisedMerchant, normalise_merchant

ARTIFACT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "artifacts" / "categoriser.joblib"
)
CONFIDENCE_THRESHOLD = 0.6

MAJORITY_FALLBACK_CATEGORY = "shopping"

_model_cache: Any = None


def _load_model() -> Any:
    global _model_cache
    if _model_cache is None and ARTIFACT_PATH.exists():
        _model_cache = joblib.load(ARTIFACT_PATH)
    return _model_cache


def _decode(surface_name: str, vpa: str) -> NormalisedMerchant:
    text = f"{surface_name} {vpa}".strip()
    return normalise_merchant(text)


def keyword_baseline(surface_name: str, vpa: str = "") -> str:
    """Simple rules baseline: fuzzy-match against the merchant seed dict (via
    finsight_ml.normalise), else guess the majority class. Used as the
    comparison point for the trained model's macro-F1, AND fed into the
    model itself as a feature — the model can't do worse than this rule
    since it's one of its own inputs."""
    r = _decode(surface_name, vpa)
    if r.matched and r.category:
        return r.category
    return MAJORITY_FALLBACK_CATEGORY


def _row_to_features(
    surface_name: str, vpa: str, amount_paise: int, hour: int, weekday: int
) -> dict[str, Any]:
    local = vpa.split("@", 1)[0] if vpa else ""
    decoded = _decode(surface_name, vpa)
    keyword_hit = (
        decoded.category
        if (decoded.matched and decoded.category)
        else MAJORITY_FALLBACK_CATEGORY
    )
    return {
        # Word-level TF-IDF on the DECODED (normalised/fuzzy-matched) name —
        # clean brand text, not raw narration noise.
        "decoded_text": decoded.name.lower(),
        # Char n-grams on the raw VPA local-part only, down-weighted in the
        # pipeline (transformer_weights) — still useful for messy/QR merchants
        # normalise couldn't resolve, but shouldn't dominate clean brand text.
        "vpa_text": local.lower(),
        # The baseline's own prediction, as a categorical input — this is
        # what guarantees the stacked model can't score worse than the rules.
        "keyword_hit": keyword_hit,
        "amount_log": math.log1p(amount_paise / 100),
        "hour": hour,
        "weekday": weekday,
    }


def build_feature_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row_to_features(
                r["surface_name"],
                r.get("vpa", ""),
                r["amount_paise"],
                r["hour"],
                r["weekday"],
            )
            for r in rows
        ]
    )


DICT_HIT_THRESHOLD = 90.0  # stricter than normalise's own 72 fallback cutoff


def _hour_weekday(transaction: dict[str, Any]) -> tuple[int, int]:
    ts = transaction.get("ts")
    if "hour" in transaction and "weekday" in transaction:
        return transaction["hour"], transaction["weekday"]
    if ts is not None:
        from datetime import datetime

        dt = ts if hasattr(ts, "hour") else datetime.fromisoformat(ts)
        return dt.hour, dt.weekday()
    return 12, 0


def cascade_predict(
    transaction: dict[str, Any], threshold: float = CONFIDENCE_THRESHOLD
) -> tuple[str, float, str]:
    """The real production path: (i) an exact/fuzzy merchant-dictionary hit
    short-circuits straight to that category, (ii) otherwise ask the model,
    (iii) if the model isn't confident, flag it for the (Phase 5) LLM step
    instead of guessing. Returns (category, confidence, stage) where stage
    is one of "dict_hit", "model", "needs_llm"."""
    surface_name = transaction.get("surface_name", "")
    vpa = transaction.get("vpa", "")
    decoded = _decode(surface_name, vpa)
    if (
        decoded.matched
        and decoded.category
        and decoded.match_score >= DICT_HIT_THRESHOLD
    ):
        return decoded.category, decoded.match_score / 100, "dict_hit"

    model = _load_model()
    if model is None:
        return keyword_baseline(surface_name, vpa), 0.5, "model"

    hour, weekday = _hour_weekday(transaction)
    frame = build_feature_frame(
        [
            {
                "surface_name": surface_name,
                "vpa": vpa,
                "amount_paise": transaction["amount_paise"],
                "hour": hour,
                "weekday": weekday,
            }
        ]
    )
    proba = model.predict_proba(frame)[0]
    classes = model.classes_
    best_idx = proba.argmax()
    category, confidence = str(classes[best_idx]), float(proba[best_idx])
    if confidence < threshold:
        return category, confidence, "needs_llm"
    return category, confidence, "model"


def categorise(transaction: dict[str, Any]) -> tuple[str, float]:
    """Thin wrapper over cascade_predict for callers that don't care about
    which cascade stage answered (e.g. the ingest endpoints)."""
    category, confidence, _stage = cascade_predict(transaction)
    return category, confidence


def needs_llm_assist(
    confidence: float, threshold: float = CONFIDENCE_THRESHOLD
) -> bool:
    """Phase 5 hook: low-confidence predictions should get an LLM few-shot
    pass using the user's own corrections. Not implemented yet — this just
    flags when that path should kick in."""
    return confidence < threshold
