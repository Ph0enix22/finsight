from finsight_ml.normalise import normalise_merchant


def test_normalise_bare_vpa_matches_exactly() -> None:
    r = normalise_merchant("swiggy@ybl")
    assert r.matched
    assert r.name == "Swiggy"
    assert r.category == "food_delivery"


def test_normalise_csv_narration_matches() -> None:
    r = normalise_merchant("UPI/DR/1234567890/zomato@paytm/ZOMATO")
    assert r.matched
    assert r.name == "Zomato"
    assert r.category == "food_delivery"


def test_normalise_truncated_name_still_matches() -> None:
    r = normalise_merchant("UPI/DR/1234567890/starbuc@apl/STARBUC")
    assert r.matched
    assert r.name == "Starbucks"


def test_normalise_falls_back_on_kirana_qr_vpa() -> None:
    r = normalise_merchant(
        "UPI/DR/1234567890/paytmqr2810051501rla@paytm/LOCAL KIRANA STORE"
    )
    assert not r.matched
    assert r.category is None
    assert "@" not in r.name


def test_normalise_falls_back_on_p2p_person() -> None:
    r = normalise_merchant("UPI/DR/1234567890/6396278972@upi/SIDDHARTH VERMA")
    assert not r.matched
    assert r.category is None


def test_normalise_empty_string_does_not_crash() -> None:
    r = normalise_merchant("")
    assert not r.matched
