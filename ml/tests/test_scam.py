from finsight_ml.scam import check_scam


def test_check_scam_returns_flag_and_reasons() -> None:
    result = check_scam("You won a prize, click here")
    assert result == {"is_scam": False, "reasons": []}
