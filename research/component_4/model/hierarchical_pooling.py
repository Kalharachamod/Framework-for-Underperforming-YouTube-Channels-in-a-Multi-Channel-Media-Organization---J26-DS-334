"""Hierarchical Bayesian Partial Pooling for Component 4.

Stabilizes topic prevalence trajectories for small/underperforming channels with sparse histories
by sharing statistical strength across niche-similar channels using Empirical Bayes shrinkage:
\theta_c \sim \mathcal{N}(\mu_{g(c)}, \sigma_{g(c)}^2)
Outputs stabilized prevalence estimates alongside posterior credible uncertainty intervals.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from shared.utils.paths import component_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def apply_hierarchical_pooling(
    trajectories_df: pd.DataFrame,
    save_parquet: bool = True,
) -> pd.DataFrame:
    """Apply hierarchical Bayesian partial pooling across niche-similar channels.

    Args:
        trajectories_df: DataFrame containing channel_id, channel_niche, topic_id, upload_week,
                         topic_prevalence, and channel_weekly_total_uploads.
        save_parquet: If True, saves to data/processed/component_4/pooled_trajectories.parquet.

    Returns:
        DataFrame with raw, complete pooled, and hierarchical partial pooled prevalence + uncertainty.
    """
    df = trajectories_df.copy()

    # 1. Compute niche-group level prior statistics for each topic k:
    #    Group mean \mu_{g, k} and between-channel variance \tau_{g, k}^2
    niche_stats = (
        df.groupby(["channel_niche", "topic_id"])["topic_prevalence"]
        .agg(["mean", "var", "count"])
        .reset_index()
        .rename(columns={
            "mean": "niche_prior_mean",
            "var": "niche_prior_var",
            "count": "niche_observation_count",
        })
    )
    # Impute small default variance if variance is 0 or NaN (e.g. single observation)
    niche_stats["niche_prior_var"] = niche_stats["niche_prior_var"].fillna(0.05).clip(lower=0.005)

    # 2. Compute channel-specific observation variance
    #    Channels with small historical uploads have higher estimation variance \sigma_c^2
    channel_volume = (
        df.groupby(["channel_id", "topic_id"])["video_count"]
        .agg(["sum", "var"])
        .reset_index()
        .rename(columns={"sum": "channel_total_topic_videos", "var": "channel_prevalence_var"})
    )
    channel_volume["channel_prevalence_var"] = channel_volume["channel_prevalence_var"].fillna(0.1).clip(lower=0.01)

    # Merge priors and channel variance
    df = df.merge(niche_stats, on=["channel_niche", "topic_id"], how="left")
    df = df.merge(channel_volume, on=["channel_id", "topic_id"], how="left")

    # 3. Calculate sampling variance: \sigma_{c, k}^2 = s^2 / max(1, N_{uploads})
    uploads = df["channel_weekly_total_uploads"].clip(lower=1)
    df["sampling_variance"] = (df["channel_prevalence_var"] / uploads).clip(lower=0.005, upper=0.5)

    # 4. Compute Shrinkage Factor B_{c, k} = \sigma^2 / (\sigma^2 + \tau^2)
    tau_sq = df["niche_prior_var"]
    sigma_sq = df["sampling_variance"]
    df["shrinkage_factor"] = (sigma_sq / (sigma_sq + tau_sq)).clip(lower=0.0, upper=1.0)

    # 5. Three Estimation Conditions (Proposal Section 5.8):
    #    Condition 1: Independent Estimation (Raw prevalence)
    df["independent_prevalence"] = df["topic_prevalence"].round(4)

    #    Condition 2: Complete Pooling (Niche prior mean)
    df["complete_pooled_prevalence"] = df["niche_prior_mean"].round(4)

    #    Condition 3: Hierarchical Partial Pooling
    #    \hat{\theta} = (1 - B) * y + B * \mu_g
    raw_y = df["topic_prevalence"]
    prior_mu = df["niche_prior_mean"]
    B = df["shrinkage_factor"]

    pooled_theta = (1.0 - B) * raw_y + B * prior_mu
    df["hierarchical_prevalence"] = pooled_theta.clip(lower=0.0, upper=1.0).round(4)

    # 6. Posterior Standard Error and 95% Credible Interval
    #    1 / Var_{post} = 1/\sigma^2 + 1/\tau^2
    post_precision = (1.0 / sigma_sq) + (1.0 / tau_sq)
    post_se = np.sqrt(1.0 / post_precision)
    df["posterior_se"] = post_se.round(4)
    df["ci_95_lower"] = (df["hierarchical_prevalence"] - 1.96 * post_se).clip(lower=0.0).round(4)
    df["ci_95_upper"] = (df["hierarchical_prevalence"] + 1.96 * post_se).clip(upper=1.0).round(4)
    df["credible_interval_width"] = (df["ci_95_upper"] - df["ci_95_lower"]).round(4)

    # Sort results
    df = df.sort_values(by=["channel_id", "topic_id", "upload_week"]).reset_index(drop=True)

    if save_parquet:
        out_path = component_dir(4) / "pooled_trajectories.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("Saved %d hierarchically pooled observations to %s", len(df), out_path)

    return df


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    target_dir = component_dir(4)
    traj_path = target_dir / "channel_topic_weekly.parquet"

    if not traj_path.exists():
        logger.error("channel_topic_weekly.parquet not found. Run dynamic_prevalence.py first.")
        sys.exit(1)

    t_df = pd.read_parquet(traj_path)
    pooled_df = apply_hierarchical_pooling(t_df)

    print("\nHierarchical Shrinkage Demonstration (Sparse vs Active Channel Weeks):")
    sample_cols = [
        "channel_name", "channel_niche", "topic_label", "upload_week",
        "channel_weekly_total_uploads", "independent_prevalence",
        "shrinkage_factor", "hierarchical_prevalence", "ci_95_lower", "ci_95_upper"
    ]
    print(pooled_df[sample_cols].head(15).to_string(index=False))
