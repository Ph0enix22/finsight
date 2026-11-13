from finsight_ml.twin import simulate


def test_simulate_returns_percentile_bands() -> None:
    result = simulate([], [])
    assert {"p10", "p50", "p90", "p_run_out"} <= result.keys()
