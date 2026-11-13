"""Train the transaction categoriser on data/generated/*.json and report an
HONEST evaluation: a merchant-level split (not a user-level one — a user-level
split leaks every merchant into both train and test and makes macro-F1 look
artificially close to 1.0). For each category, ~25% of its merchants are held
out entirely (their transactions never appear in training) so "unseen
merchant" macro-F1 measures real generalisation, not memorisation.

Run: cd ml && uv run python scripts/train_categoriser.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from finsight_ml.categorise import ARTIFACT_PATH, build_feature_frame, keyword_baseline

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATED_DIR = REPO_ROOT / "data" / "generated"
SEED = 42
UNSEEN_MERCHANT_FRACTION = 0.25


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(GENERATED_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for t in payload["txns"]:
            from datetime import datetime

            ts = datetime.fromisoformat(t["ts"])
            rows.append(
                {
                    "category": t[
                        "category"
                    ],  # noisy target, as a real system would see it
                    "true_category": t["true_category"],
                    "merchant_key": t["merchant_key"],
                    "surface_name": t["surface_name"],
                    "vpa": t["vpa"],
                    "amount_paise": t["amount_paise"],
                    "hour": ts.hour,
                    "weekday": ts.weekday(),
                }
            )
    return rows


def merchant_level_split(
    rows: list[dict], rng: random.Random
) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (train, seen_test, unseen_test)."""
    by_true_cat: dict[str, set[str]] = {}
    for r in rows:
        by_true_cat.setdefault(r["true_category"], set()).add(r["merchant_key"])

    unseen_merchants: set[str] = set()
    for merchant_set in by_true_cat.values():
        merchants = sorted(merchant_set)
        rng.shuffle(merchants)
        n_unseen = (
            max(1, round(len(merchants) * UNSEEN_MERCHANT_FRACTION))
            if len(merchants) > 1
            else 0
        )
        unseen_merchants.update(merchants[:n_unseen])

    seen_pool = [r for r in rows if r["merchant_key"] not in unseen_merchants]
    unseen_test = [r for r in rows if r["merchant_key"] in unseen_merchants]

    train, seen_test = train_test_split(seen_pool, test_size=0.2, random_state=SEED)
    return train, seen_test, unseen_test


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            (
                "text",
                TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=2),
                "text",
            ),
            ("num", StandardScaler(), ["amount_log", "hour"]),
            ("weekday", OneHotEncoder(handle_unknown="ignore"), ["weekday"]),
        ]
    )
    return Pipeline(
        [
            ("features", preprocessor),
            ("clf", LogisticRegression(max_iter=2000)),
        ]
    )


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    return f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)


def main() -> None:
    rng = random.Random(SEED)
    rows = load_rows()
    print(
        f"Loaded {len(rows)} transactions from {len(list(GENERATED_DIR.glob('*.json')))} users"
    )

    train, seen_test, unseen_test = merchant_level_split(rows, rng)
    print(
        f"train={len(train)}  seen_test={len(seen_test)}  unseen_test={len(unseen_test)}"
    )

    pipeline = build_pipeline()
    X_train = build_feature_frame(train)
    y_train = [r["category"] for r in train]
    pipeline.fit(X_train, y_train)

    results = {}
    for name, split in (
        ("seen", seen_test),
        ("unseen", unseen_test),
        ("overall", seen_test + unseen_test),
    ):
        if not split:
            results[name] = (float("nan"), float("nan"))
            continue
        X = build_feature_frame(split)
        y_true = [r["category"] for r in split]
        y_pred_model = list(pipeline.predict(X))
        y_pred_baseline = [keyword_baseline(r["surface_name"], r["vpa"]) for r in split]
        results[name] = (
            macro_f1(y_true, y_pred_model),
            macro_f1(y_true, y_pred_baseline),
        )

    print("\nMacro-F1 (model vs keyword baseline):")
    print(f"{'split':<10} {'model':>8} {'baseline':>10}")
    for name in ("seen", "unseen", "overall"):
        m, b = results[name]
        print(f"{name:<10} {m:>8.4f} {b:>10.4f}")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ARTIFACT_PATH)
    print(f"\nSaved model to {ARTIFACT_PATH}")

    unseen_f1 = results["unseen"][0]
    if unseen_f1 < 0.75:
        print(f"\nWARNING: unseen-merchant macro-F1 ({unseen_f1:.4f}) is below 0.75.")


if __name__ == "__main__":
    main()
