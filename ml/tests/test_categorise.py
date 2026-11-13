import finsight_ml.categorise as categorise_mod
from finsight_ml.categorise import (
    build_feature_frame,
    keyword_baseline,
    needs_llm_assist,
)


def test_keyword_baseline_matches_known_merchant() -> None:
    assert keyword_baseline("Swiggy", "swiggy@ybl") == "food_delivery"


def test_keyword_baseline_falls_back_for_unknown_text() -> None:
    assert (
        keyword_baseline("zzz_totally_unknown_merchant_zzz", "q83jd72@ybl")
        == categorise_mod.MAJORITY_FALLBACK_CATEGORY
    )


def test_build_feature_frame_has_expected_columns() -> None:
    rows = [
        {
            "surface_name": "Swiggy",
            "vpa": "swiggy@ybl",
            "amount_paise": 24900,
            "hour": 13,
            "weekday": 2,
        }
    ]
    frame = build_feature_frame(rows)
    assert list(frame.columns) == ["text", "amount_log", "hour", "weekday"]
    assert frame.loc[0, "hour"] == 13


def test_needs_llm_assist_threshold() -> None:
    assert needs_llm_assist(0.4)
    assert not needs_llm_assist(0.9)


def test_categorise_falls_back_to_keyword_baseline_without_artifact(
    monkeypatch,
) -> None:
    monkeypatch.setattr(categorise_mod, "_model_cache", None)
    monkeypatch.setattr(
        categorise_mod,
        "ARTIFACT_PATH",
        categorise_mod.ARTIFACT_PATH.parent / "does-not-exist.joblib",
    )
    category, confidence = categorise_mod.categorise(
        {
            "surface_name": "Swiggy",
            "vpa": "swiggy@ybl",
            "amount_paise": 24900,
            "ts": "2026-11-07T13:00:00",
        }
    )
    assert category == "food_delivery"
    assert confidence == 0.5
