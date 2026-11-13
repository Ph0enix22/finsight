from finsight_ml.normalise import normalise_merchant


def test_normalise_merchant_strips_whitespace() -> None:
    assert normalise_merchant("  swiggy@upi  ") == "swiggy@upi"
