from finsight_ml.categorise import categorise


def test_categorise_returns_category_and_confidence() -> None:
    category, confidence = categorise({"merchant": "swiggy"})
    assert isinstance(category, str)
    assert isinstance(confidence, float)
