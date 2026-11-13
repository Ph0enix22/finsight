import finsight_ml.categorise as categorise_mod
from finsight_ml.categorise import (
    build_feature_frame,
    cascade_predict,
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
    assert list(frame.columns) == [
        "decoded_text",
        "vpa_text",
        "keyword_hit",
        "amount_log",
        "hour",
        "weekday",
    ]
    assert frame.loc[0, "hour"] == 13
    assert frame.loc[0, "decoded_text"] == "swiggy"
    assert frame.loc[0, "keyword_hit"] == "food_delivery"


def test_needs_llm_assist_threshold() -> None:
    assert needs_llm_assist(0.4)
    assert not needs_llm_assist(0.9)


def test_cascade_exact_match_short_circuits_to_dict_hit() -> None:
    category, confidence, stage = cascade_predict(
        {
            "surface_name": "Swiggy",
            "vpa": "swiggy@ybl",
            "amount_paise": 24900,
            "hour": 13,
            "weekday": 2,
        }
    )
    assert stage == "dict_hit"
    assert category == "food_delivery"
    assert confidence >= 0.9


def test_cascade_falls_back_to_keyword_baseline_without_artifact(monkeypatch) -> None:
    monkeypatch.setattr(categorise_mod, "_model_cache", None)
    monkeypatch.setattr(
        categorise_mod,
        "ARTIFACT_PATH",
        categorise_mod.ARTIFACT_PATH.parent / "does-not-exist.joblib",
    )
    category, confidence, _stage = cascade_predict(
        {
            "surface_name": "zzz_totally_unknown_merchant_zzz",
            "vpa": "q83jd72@ybl",
            "amount_paise": 24900,
            "ts": "2026-11-07T13:00:00",
        }
    )
    assert category == categorise_mod.MAJORITY_FALLBACK_CATEGORY
    assert confidence == 0.5


def test_categorise_wraps_cascade() -> None:
    category, confidence = categorise_mod.categorise(
        {
            "surface_name": "Swiggy",
            "vpa": "swiggy@ybl",
            "amount_paise": 24900,
            "hour": 13,
            "weekday": 2,
        }
    )
    assert category == "food_delivery"
    assert confidence >= 0.9
