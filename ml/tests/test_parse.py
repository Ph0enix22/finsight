from finsight_ml.parse import parse_sms


def test_parse_sms_returns_dict() -> None:
    assert parse_sms("Rs.100 debited") == {}
