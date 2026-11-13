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

from finsight_ml.normalise import normalise_merchant

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


def keyword_baseline(surface_name: str, vpa: str = "") -> str:
    """Simple rules baseline: fuzzy-match against the merchant seed dict (via
    finsight_ml.normalise), else guess the majority class. Used as the
    comparison point for the trained model's macro-F1."""
    text = f"{surface_name} {vpa}".strip()
    r = normalise_merchant(text)
    if r.matched and r.category:
        return r.category
    return MAJORITY_FALLBACK_CATEGORY


def _row_to_features(
    surface_name: str, vpa: str, amount_paise: int, hour: int, weekday: int
) -> dict[str, Any]:
    local = vpa.split("@", 1)[0] if vpa else ""
    return {
        "text": f"{surface_name} {local}".strip().lower(),
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


def categorise(transaction: dict[str, Any]) -> tuple[str, float]:
    """`transaction` needs surface_name, amount_paise, and a timestamp
    (ts: datetime or isoformat str) or explicit hour/weekday. Returns
    (category, confidence)."""
    model = _load_model()
    ts = transaction.get("ts")
    if "hour" in transaction and "weekday" in transaction:
        hour, weekday = transaction["hour"], transaction["weekday"]
    elif ts is not None:
        from datetime import datetime

        dt = ts if hasattr(ts, "hour") else datetime.fromisoformat(ts)
        hour, weekday = dt.hour, dt.weekday()
    else:
        hour, weekday = 12, 0

    if model is None:
        category = keyword_baseline(
            transaction.get("surface_name", ""), transaction.get("vpa", "")
        )
        return category, 0.5

    frame = build_feature_frame(
        [
            {
                "surface_name": transaction.get("surface_name", ""),
                "vpa": transaction.get("vpa", ""),
                "amount_paise": transaction["amount_paise"],
                "hour": hour,
                "weekday": weekday,
            }
        ]
    )
    proba = model.predict_proba(frame)[0]
    classes = model.classes_
    best_idx = proba.argmax()
    return str(classes[best_idx]), float(proba[best_idx])


def needs_llm_assist(
    confidence: float, threshold: float = CONFIDENCE_THRESHOLD
) -> bool:
    """Phase 5 hook: low-confidence predictions should get an LLM few-shot
    pass using the user's own corrections. Not implemented yet — this just
    flags when that path should kick in."""
    return confidence < threshold
