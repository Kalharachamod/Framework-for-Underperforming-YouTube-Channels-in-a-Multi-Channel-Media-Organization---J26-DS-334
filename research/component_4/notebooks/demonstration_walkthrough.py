# %% [markdown]
# # Component 4: Hierarchically Pooled Dynamic Topic Modelling with Bayesian Changepoint Flagging
# **Research Demonstration & Evaluation Walkthrough**
#
# **Student:** Sankalpa H D T P (IT23323452)
# **Project:** J26-DS-334 | CoEAI Data Science, SLIIT
#
# This interactive notebook demonstrates:
# 1. Dataset loading and language distribution profiling (Sinhala / English / Tanglish)
# 2. Semantic topic discovery across 1,682 videos from 52 channels
# 3. Dynamic weekly topic trajectories
# 4. Hierarchical Bayesian partial pooling (shrinkage effect on sparse channels)
# 5. Adams & MacKay (2007) Bayesian Online Changepoint Detection (BOCPD)
# 6. Experimental benchmarking vs. Baselines (MA, CUSUM, Non-hierarchical)

# %%
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from shared.utils.paths import component_dir

# %% [markdown]
# ### 1. Dataset Inspection & Language Profiling

# %%
target_dir = component_dir(4)
videos_df = pd.read_parquet(target_dir / "preprocessed_videos.parquet")

print(f"Total Videos Analyzed: {len(videos_df):,}")
print(f"Unique Channels in Portfolio: {videos_df['channel_id'].nunique()}")
print(f"Publication Date Range: {videos_df['published_at'].min()} to {videos_df['published_at'].max()}")

print("\n--- Language Profile Distribution ---")
print(videos_df["language_profile"].value_counts(normalize=True).round(3) * 100)

print("\n--- Content Format Distribution ---")
print(videos_df["duration_band"].value_counts())

# %% [markdown]
# ### 2. Discovered Semantic Portfolio Topics

# %%
trajectories_df = pd.read_parquet(target_dir / "channel_topic_weekly.parquet")

topics = (
    trajectories_df[["topic_id", "topic_label"]]
    .drop_duplicates()
    .sort_values("topic_id")
    .reset_index(drop=True)
)
print("Discovered Portfolio Topics:")
print(topics.to_string(index=False))

# %% [markdown]
# ### 3. Hierarchical Bayesian Partial Pooling Demonstration
# Shows how small/sparse channel weeks have their noisy estimates shrunk toward the niche prior mean.

# %%
pooled_df = pd.read_parquet(target_dir / "pooled_trajectories.parquet")

# Filter for a sample showing shrinkage effect
sample_shrinkage = pooled_df[[
    "channel_name", "channel_niche", "topic_label", "upload_week",
    "channel_weekly_total_uploads", "independent_prevalence",
    "shrinkage_factor", "hierarchical_prevalence", "ci_95_lower", "ci_95_upper"
]].head(10)

print("Sample Hierarchical Shrinkage on Sparse Channels:")
print(sample_shrinkage.to_string(index=False))

# %% [markdown]
# ### 4. Detected Emerging Topic Signals (BOCPD)

# %%
signals_df = pd.read_parquet(target_dir / "emerging_signals.parquet")

print(f"Total Emerging Topic Signals Detected: {len(signals_df)}")
if not signals_df.empty:
    display_cols = [
        "channel_name", "channel_niche", "topic_label", "changepoint_week",
        "changepoint_probability", "change_magnitude", "current_prevalence",
        "ci_lower", "ci_upper", "signal_score"
    ]
    print(signals_df[display_cols].to_string(index=False))

# %% [markdown]
# ### 5. Comparative Baseline Evaluation Results

# %%
benchmarks_df = pd.read_parquet(target_dir / "benchmark_evaluation.parquet")
print("=== EXPERIMENTAL EVALUATION TABLE ===")
print(benchmarks_df.to_string(index=False))
