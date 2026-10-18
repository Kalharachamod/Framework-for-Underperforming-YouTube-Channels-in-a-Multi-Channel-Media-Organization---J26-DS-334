"""Bayesian Online Changepoint Detection (BOCPD) for Component 4.

Implements the Adams & MacKay (2007) algorithm for probabilistic changepoint detection
on topic prevalence trajectories. Detects run-length resets and flags emerging-topic momentum
with calibrated posterior uncertainty.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from dataclasses import dataclass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from scipy import stats
from shared.utils.paths import component_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class EmergingSignal:
    channel_id: str
    channel_name: str
    channel_niche: str
    topic_id: int
    topic_label: str
    changepoint_week: str
    changepoint_probability: float
    trend_direction: str  # 'emerging_upward' or 'stable' or 'declining'
    change_magnitude: float
    current_prevalence: float
    prior_prevalence: float
    ci_lower: float
    ci_upper: float
    signal_score: float
    is_sparse_channel: bool


class BayesianOnlineChangepointDetector:
    """Adams & MacKay (2007) BOCPD with normal-inverse-gamma conjugate prior."""

    def __init__(
        self,
        hazard_rate: float = 1.0 / 12.0,  # Expected regime duration: 12 weeks
        mu_0: float = 0.15,              # Prior mean prevalence
        kappa_0: float = 1.0,            # Prior precision
        alpha_0: float = 2.0,            # Prior shape
        beta_0: float = 0.02,            # Prior scale
    ) -> None:
        self.hazard = hazard_rate
        self.mu_0 = mu_0
        self.kappa_0 = kappa_0
        self.alpha_0 = alpha_0
        self.beta_0 = beta_0

    def detect(self, trajectory: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Run online detection on a 1D sequence of prevalence observations.

        Returns:
            (run_length_matrix, changepoint_probs, posterior_means)
        """
        T = len(trajectory)
        if T == 0:
            return np.empty((0, 0)), np.empty(0), np.empty(0)

        # Run length distribution matrix: R[r, t]
        R = np.zeros((T + 1, T + 1))
        R[0, 0] = 1.0

        # Sufficient statistics vectors
        mu_t = np.array([self.mu_0])
        kappa_t = np.array([self.kappa_0])
        alpha_t = np.array([self.alpha_0])
        beta_t = np.array([self.beta_0])

        cp_probs = np.zeros(T)
        post_means = np.zeros(T)

        for t in range(T):
            x = trajectory[t]

            # 1. Evaluate predictive probability: Student-t distribution
            df = 2.0 * alpha_t
            loc = mu_t
            scale = np.sqrt(beta_t * (kappa_t + 1.0) / (alpha_t * kappa_t))
            pred_probs = stats.t.pdf(x, df=df, loc=loc, scale=scale)
            pred_probs = np.nan_to_num(pred_probs, nan=1e-8, posinf=1e-8, neginf=1e-8)
            pred_probs = np.clip(pred_probs, a_min=1e-12, a_max=None)

            # 2. Growth probabilities: r_t = r_{t-1} + 1
            growth_probs = R[: t + 1, t] * pred_probs * (1.0 - self.hazard)

            # 3. Changepoint probability: r_t = 0
            cp_prob = np.sum(R[: t + 1, t] * pred_probs * self.hazard)

            # 4. Normalize evidence
            evidence = np.sum(growth_probs) + cp_prob
            if evidence > 0:
                R[1 : t + 2, t + 1] = growth_probs / evidence
                R[0, t + 1] = cp_prob / evidence
            else:
                R[1 : t + 2, t + 1] = 0.0
                R[0, t + 1] = 1.0

            # In Adams & MacKay, the probability of a recent changepoint having occurred
            # is the posterior mass at low run-lengths (r_t <= 1)
            cp_probs[t] = float(np.sum(R[:2, t + 1]))

            # Posterior mean prevalence estimate
            post_means[t] = float(np.sum(R[: t + 2, t + 1] * np.append(self.mu_0, mu_t)))

            # 5. Update posterior parameters for next step
            mu_next = np.append(self.mu_0, (kappa_t * mu_t + x) / (kappa_t + 1.0))
            kappa_next = np.append(self.kappa_0, kappa_t + 1.0)
            alpha_next = np.append(self.alpha_0, alpha_t + 0.5)
            beta_next = np.append(
                self.beta_0,
                beta_t + (kappa_t * (x - mu_t) ** 2) / (2.0 * (kappa_t + 1.0)),
            )

            mu_t, kappa_t, alpha_t, beta_t = mu_next, kappa_next, alpha_next, beta_next

        return R, cp_probs, post_means


def flag_emerging_topics(
    pooled_df: pd.DataFrame,
    cp_threshold: float = 0.12,
    min_trajectory_length: int = 2,
    save_parquet: bool = True,
) -> pd.DataFrame:
    """Apply BOCPD across all channel-topic trajectories to flag emerging signals.

    Args:
        pooled_df: DataFrame output from hierarchical_pooling.py.
        cp_threshold: Minimum posterior changepoint probability (P(r <= 1)).
        min_trajectory_length: Minimum observations required in trajectory.
        save_parquet: If True, saves to data/processed/component_4/emerging_signals.parquet.

    Returns:
        DataFrame of detected emerging topic signals ranked by signal score.
    """
    detector = BayesianOnlineChangepointDetector()
    signals: list[EmergingSignal] = []

    # Group by channel and topic
    grouped = pooled_df.groupby(["channel_id", "topic_id"])

    for (ch_id, topic_id), group in grouped:
        if len(group) < min_trajectory_length:
            continue

        group = group.sort_values("upload_week").reset_index(drop=True)
        # Use hierarchically-pooled prevalence (which borrows strength across niche)
        obs_seq = group["hierarchical_prevalence"].to_numpy()

        _, cp_probs, _ = detector.detect(obs_seq)

        for t in range(1, len(group)):
            prob = float(cp_probs[t])
            curr_prev = float(obs_seq[t])
            prior_prev = float(obs_seq[t - 1])
            magnitude = curr_prev - prior_prev

            # Emerging criteria: high changepoint probability AND positive shift magnitude
            if prob >= cp_threshold and magnitude >= 0.05:
                direction = "emerging_upward"

                row = group.iloc[t]
                ci_low = float(row.get("ci_95_lower", max(0.0, curr_prev - 0.1)))
                ci_high = float(row.get("ci_95_upper", min(1.0, curr_prev + 0.1)))
                is_sparse = bool(row.get("is_sparse_channel_week", False))

                # Calibrated Signal Score: prob * magnitude * confidence (1 - CI_width)
                ci_width = max(0.01, ci_high - ci_low)
                confidence_factor = 1.0 - np.clip(ci_width, 0.0, 0.8)
                score = round(float(prob * np.clip(magnitude, 0.1, 1.0) * confidence_factor), 4)

                signals.append(EmergingSignal(
                    channel_id=ch_id,
                    channel_name=str(row["channel_name"]),
                    channel_niche=str(row["channel_niche"]),
                    topic_id=int(topic_id),
                    topic_label=str(row["topic_label"]),
                    changepoint_week=str(row["upload_week"]),
                    changepoint_probability=round(prob, 4),
                    trend_direction=direction,
                    change_magnitude=round(magnitude, 4),
                    current_prevalence=round(curr_prev, 4),
                    prior_prevalence=round(prior_prev, 4),
                    ci_lower=round(ci_low, 4),
                    ci_upper=round(ci_high, 4),
                    signal_score=score,
                    is_sparse_channel=is_sparse,
                ))

    # Convert to DataFrame
    signals_df = pd.DataFrame([s.__dict__ for s in signals])

    if not signals_df.empty:
        # Rank by signal score descending
        signals_df = signals_df.sort_values(by="signal_score", ascending=False).reset_index(drop=True)

    if save_parquet:
        out_path = component_dir(4) / "emerging_signals.parquet"
        signals_df.to_parquet(out_path, index=False)
        logger.info("Saved %d emerging topic signals to %s", len(signals_df), out_path)

    return signals_df


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    target_dir = component_dir(4)
    pooled_path = target_dir / "pooled_trajectories.parquet"

    if not pooled_path.exists():
        logger.error("pooled_trajectories.parquet not found. Run hierarchical_pooling.py first.")
        sys.exit(1)

    p_df = pd.read_parquet(pooled_path)
    signals_df = flag_emerging_topics(p_df, cp_threshold=0.12, min_trajectory_length=2)

    print(f"\nTop Detected Emerging Topic Signals ({len(signals_df)} total detected):")
    if not signals_df.empty:
        display_cols = [
            "channel_name", "channel_niche", "topic_label", "changepoint_week",
            "changepoint_probability", "change_magnitude", "current_prevalence",
            "ci_lower", "ci_upper", "signal_score"
        ]
        print(signals_df[display_cols].head(20).to_string(index=False))
