from finsight_ml.anomaly import detect_anomalies


def test_detect_anomalies_returns_list() -> None:
    assert detect_anomalies([]) == []
