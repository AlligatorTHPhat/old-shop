"""Transaction risk scoring.

An IsolationForest model (trained offline on PaySim-style data, 12 features) is
loaded once from FRAUD_MODEL_DIR. The artifacts are not committed; when they are
missing the service falls back to the hard business rules only, so the shop
still works in dev/CI.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import joblib
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

HARD_LIMIT_VND = Decimal("100000000")  # anything above is rejected outright
FRAUD_THRESHOLD = 0.9
SUSPICIOUS_THRESHOLD = 0.7
N_FEATURES = 12
FALLBACK_SCORE = 0.1


@dataclass(frozen=True)
class RiskResult:
    score: float
    is_suspicious: bool
    is_fraud: bool

    def __getitem__(self, key: str):  # dict-style access kept for older call sites
        return getattr(self, key)


@lru_cache(maxsize=1)
def _load_model():
    model_path = settings.FRAUD_MODEL_DIR / "fraud_model.joblib"
    scaler_path = settings.FRAUD_MODEL_DIR / "scaler.joblib"
    try:
        return joblib.load(model_path), joblib.load(scaler_path)
    except (OSError, ValueError) as exc:
        logger.warning("Fraud model unavailable, using rule-based scoring only: %s", exc)
        return None


def _model_score(amount: float, balance: float) -> float:
    loaded = _load_model()
    if loaded is None:
        return FALLBACK_SCORE
    model, scaler = loaded

    # The model was trained on 12 features; only these three are known at checkout time.
    features = np.array([[amount, balance, balance - amount] + [0.0] * (N_FEATURES - 3)])
    try:
        raw = model.decision_function(scaler.transform(features))[0]
    except ValueError:
        logger.exception("Fraud model rejected the feature vector")
        return FALLBACK_SCORE

    # decision_function is positive for inliers and negative for anomalies.
    return round(float(min(FRAUD_THRESHOLD, max(0.0, -raw * 5))), 4)


def score_transaction(amount: Decimal | float, balance: Decimal | float | None) -> RiskResult:
    amount_d = Decimal(str(amount))
    if amount_d > HARD_LIMIT_VND:
        return RiskResult(score=1.0, is_suspicious=True, is_fraud=True)

    score = _model_score(float(amount_d), float(balance or 0))
    return RiskResult(score=score, is_suspicious=score > SUSPICIOUS_THRESHOLD, is_fraud=score > FRAUD_THRESHOLD)
