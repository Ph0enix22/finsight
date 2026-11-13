"""Train the transaction categoriser on data/generated/*.json and report an
HONEST evaluation: a merchant-level split (not a user-level one — a user-level
split leaks every merchant into both train and test and makes macro-F1 look
artificially close to 1.0). For each category, ~25% of its merchants are held
out entirely (their transactions never appear in training) so "unseen
merchant" macro-F1 measures real generalisation, not memorisation.

A validation split (carved out of the "seen" pool, never touched by the
final report) is where cascade thresholds get sanity-checked — the seen/
unseen TEST splits are reported once, at the end, and never used to pick
anything.

Reports three things on each of seen/unseen/overall:
  - the keyword baseline alone
  - the trained model alone
  - the production cascade (dict-hit -> model -> needs-LLM), excluding
    needs-LLM rows from the F1 (they're not predictions), with the %
    routed to LLM shown separately.

Run: cd ml && uv run python scripts/train_categoriser.py
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Self

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import finsight_ml.normalise as normalise_mod
from finsight_ml.categorise import (
    ARTIFACT_PATH,
    CONFIDENCE_THRESHOLD,
    DICT_HIT_THRESHOLD,
    build_feature_frame,
    keyword_baseline,
)
from finsight_ml.normalise import normalise_merchant

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATED_DIR = REPO_ROOT / "data" / "generated"
SEED = 42
UNSEEN_MERCHANT_FRACTION = 0.25


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(GENERATED_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for t in payload["txns"]:
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
) -> tuple[list[dict], list[dict], list[dict], list[dict], set[str]]:
    """Returns (train, validation, seen_test, unseen_test, unseen_merchants).
    Validation and seen_test are both drawn from merchants the model trains
    on; validation is for sanity-checking cascade thresholds, seen_test/
    unseen_test are reported once at the end and never used to pick
    anything."""
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

    train, rest = train_test_split(seen_pool, test_size=0.3, random_state=SEED)
    validation, seen_test = train_test_split(rest, test_size=0.5, random_state=SEED)
    return train, validation, seen_test, unseen_test, unseen_merchants


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            (
                "decoded_word",
                TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2),
                "decoded_text",
            ),
            (
                "vpa_char",
                TfidfVectorizer(
                    analyzer="char", ngram_range=(2, 4), min_df=2, max_features=200
                ),
                "vpa_text",
            ),
            ("keyword", OneHotEncoder(handle_unknown="ignore"), ["keyword_hit"]),
            ("num", StandardScaler(), ["amount_log", "hour"]),
            ("weekday", OneHotEncoder(handle_unknown="ignore"), ["weekday"]),
        ],
        # char n-grams on the raw VPA are a weaker, noisier signal than the
        # decoded brand name — down-weight so they can't drown it out.
        transformer_weights={
            "decoded_word": 1.0,
            "vpa_char": 0.3,
            "keyword": 1.0,
            "num": 1.0,
            "weekday": 1.0,
        },
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


def cascade_on_split(
    pipeline: Pipeline, split: list[dict]
) -> tuple[list[str], list[str], int]:
    """Replicates finsight_ml.categorise.cascade_predict using the
    in-memory pipeline (the trained artifact isn't saved yet at eval time).
    Returns (y_true_excl_llm, y_pred_excl_llm, n_routed_to_llm)."""
    X = build_feature_frame(split)
    proba = pipeline.predict_proba(X)
    classes = pipeline.classes_

    y_true, y_pred = [], []
    n_llm = 0
    for row, p in zip(split, proba, strict=True):
        decoded = normalise_merchant(f"{row['surface_name']} {row['vpa']}".strip())
        if (
            decoded.matched
            and decoded.category
            and decoded.match_score >= DICT_HIT_THRESHOLD
        ):
            y_true.append(row["category"])
            y_pred.append(decoded.category)
            continue
        best_idx = p.argmax()
        confidence = p[best_idx]
        if confidence < CONFIDENCE_THRESHOLD:
            n_llm += 1
            continue
        y_true.append(row["category"])
        y_pred.append(str(classes[best_idx]))
    return y_true, y_pred, n_llm


class _DictionaryExclusion:
    """Temporarily removes a set of merchant names from the fuzzy-match
    dictionary — used to measure a TRUE out-of-dictionary number, where the
    held-out merchants aren't just absent from training, they're absent
    from the rules too. keyword_baseline, cascade's dict-hit stage, AND the
    model's own keyword_hit/decoded_text features all go through
    normalise_merchant(), so this one patch degrades all three correctly."""

    def __init__(self, excluded_names: set[str]) -> None:
        self.excluded_names = excluded_names
        self._orig_candidates: list[str] | None = None
        self._orig_mapping: dict | None = None

    def __enter__(self) -> Self:
        self._orig_candidates = normalise_mod._CANDIDATES
        self._orig_mapping = normalise_mod._CANDIDATE_TO_MERCHANT
        filtered_candidates = [
            c
            for c in self._orig_candidates
            if self._orig_mapping[c].canonical_name not in self.excluded_names
        ]
        filtered_mapping = {c: self._orig_mapping[c] for c in filtered_candidates}
        normalise_mod._CANDIDATES = filtered_candidates
        normalise_mod._CANDIDATE_TO_MERCHANT = filtered_mapping
        return self

    def __exit__(self, *exc: object) -> None:
        normalise_mod._CANDIDATES = self._orig_candidates
        normalise_mod._CANDIDATE_TO_MERCHANT = self._orig_mapping


def evaluate_out_of_dictionary(
    pipeline: Pipeline, unseen_test: list[dict], unseen_merchants: set[str]
) -> tuple[dict[str, float], int, int]:
    """The honest generalisation number: the held-out merchants are gone
    from training AND from the dictionary, so keyword_hit/decoded_text/
    dict-hit can't quietly bail the model out with rule knowledge it
    shouldn't have about a merchant it's never seen. Not tuned against —
    reported once, as-is."""
    with _DictionaryExclusion(unseen_merchants):
        X = build_feature_frame(unseen_test)
        y_actual = [r["category"] for r in unseen_test]
        y_pred_baseline = [
            keyword_baseline(r["surface_name"], r["vpa"]) for r in unseen_test
        ]
        y_pred_model = list(pipeline.predict(X))
        cascade_true, cascade_pred, n_llm = cascade_on_split(pipeline, unseen_test)

        metrics = {
            "baseline": macro_f1(y_actual, y_pred_baseline),
            "model": macro_f1(y_actual, y_pred_model),
            "cascade": (
                macro_f1(cascade_true, cascade_pred) if cascade_true else float("nan")
            ),
        }
    return metrics, n_llm, len(unseen_test)


def top_confusions(
    y_true: list[str], y_pred: list[str], n: int = 3
) -> list[tuple[str, str, int]]:
    labels = sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    pairs = []
    for i, true_label in enumerate(labels):
        for j, pred_label in enumerate(labels):
            if i != j and cm[i, j] > 0:
                pairs.append((true_label, pred_label, int(cm[i, j])))
    pairs.sort(key=lambda p: -p[2])
    return pairs[:n]


def main() -> None:
    rng = random.Random(SEED)
    rows = load_rows()
    print(
        f"Loaded {len(rows)} transactions from {len(list(GENERATED_DIR.glob('*.json')))} users"
    )

    train, validation, seen_test, unseen_test, unseen_merchants = merchant_level_split(
        rows, rng
    )
    print(
        f"train={len(train)}  validation={len(validation)}  seen_test={len(seen_test)}  unseen_test={len(unseen_test)}"
    )

    pipeline = build_pipeline()
    X_train = build_feature_frame(train)
    y_train = [r["category"] for r in train]
    pipeline.fit(X_train, y_train)

    # Validation: sanity-check the cascade thresholds BEFORE touching test.
    val_true, val_pred, val_llm = cascade_on_split(pipeline, validation)
    val_f1 = macro_f1(val_true, val_pred) if val_true else float("nan")
    print(
        f"\n[validation, not reported below] cascade macro-F1={val_f1:.4f}, routed-to-LLM={val_llm}/{len(validation)} "
        f"({val_llm / len(validation):.1%}) — thresholds: dict_hit>={DICT_HIT_THRESHOLD}, confidence>={CONFIDENCE_THRESHOLD}"
    )

    results: dict[str, dict[str, tuple[float, float]]] = {}
    llm_routed: dict[str, tuple[int, int]] = {}
    for name, split in (
        ("seen", seen_test),
        ("unseen", unseen_test),
        ("overall", seen_test + unseen_test),
    ):
        if not split:
            results[name] = {
                "baseline": (float("nan"), 0),
                "model": (float("nan"), 0),
                "cascade": (float("nan"), 0),
            }
            continue
        X = build_feature_frame(split)
        y_actual = [r["category"] for r in split]

        y_pred_baseline = [keyword_baseline(r["surface_name"], r["vpa"]) for r in split]
        y_pred_model = list(pipeline.predict(X))
        cascade_true, cascade_pred, n_llm = cascade_on_split(pipeline, split)

        results[name] = {
            "baseline": macro_f1(y_actual, y_pred_baseline),
            "model": macro_f1(y_actual, y_pred_model),
            "cascade": (
                macro_f1(cascade_true, cascade_pred) if cascade_true else float("nan")
            ),
        }
        llm_routed[name] = (n_llm, len(split))

    # The honest generalisation number: same unseen_test transactions, but
    # with those merchants ALSO stripped from the fuzzy-match dictionary —
    # not just absent from training. Not tuned against, reported as-is.
    ood_metrics, ood_llm, ood_total = evaluate_out_of_dictionary(
        pipeline, unseen_test, set(unseen_merchants)
    )
    results["out_of_dict"] = ood_metrics
    llm_routed["out_of_dict"] = (ood_llm, ood_total)

    print(
        "\nMacro-F1 — keyword baseline / model alone / cascade (cascade excludes needs-LLM rows):"
    )
    print(
        f"{'split':<14} {'baseline':>10} {'model':>8} {'cascade':>9} {'% to LLM':>10}"
    )
    for name in ("seen", "unseen", "overall", "out_of_dict"):
        r = results[name]
        n_llm, n_total = llm_routed.get(name, (0, 1))
        pct = n_llm / n_total if n_total else 0.0
        print(
            f"{name:<14} {r['baseline']:>10.4f} {r['model']:>8.4f} {r['cascade']:>9.4f} {pct:>9.1%}"
        )

    unseen_model_f1 = results["unseen"]["model"]
    print(
        f"\nTarget check: cascade beats baseline on all rows = "
        f"{all(results[n]['cascade'] >= results[n]['baseline'] for n in ('seen', 'unseen', 'overall'))}"
    )
    print(
        f"Target check: model-alone unseen macro-F1 >= 0.75 = {unseen_model_f1 >= 0.75} (actual {unseen_model_f1:.4f})"
    )

    if unseen_model_f1 < 0.75:
        X_unseen = build_feature_frame(unseen_test)
        y_true_unseen = [r["category"] for r in unseen_test]
        y_pred_unseen = list(pipeline.predict(X_unseen))
        print(
            "\nTop 3 confusion pairs on unseen-merchant test (model alone), true -> predicted:"
        )
        for true_label, pred_label, count in top_confusions(
            y_true_unseen, y_pred_unseen
        ):
            print(f"  {true_label} -> {pred_label}: {count}")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, ARTIFACT_PATH)
    print(f"\nSaved model to {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
