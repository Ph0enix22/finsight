from finsight_ml.recurring import detect_recurring


def test_detect_recurring_returns_list() -> None:
    assert detect_recurring([]) == []
