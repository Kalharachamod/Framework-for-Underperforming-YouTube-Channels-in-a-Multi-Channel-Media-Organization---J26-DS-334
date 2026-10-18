"""Content-Format and Temporal Feature Extraction for Component 4.

Extracts format attributes (Shorts vs Long-form duration bands), temporal weekly bins,
engagement ratios, and channel niche grouping for hierarchical topic modeling.
"""

from __future__ import annotations

import re
import pandas as pd

# Channel Niche Hierarchy Mapping for Derana / Sirasa Portfolios
NICHE_MAP = {
    # News & Current Affairs
    "UCCK3OZi788Ok44K97WAhLKQ": "News",         # Ada Derana
    "UC11bd3xGXwzf_naIePO1n4g": "News",         # Ada Derana Tamil
    "UCuOtdpOPjHeoEAT4i44mVOg": "News",         # Ada Derana News English
    "UCW_rA_jb-_vbZtU4cTpnT5Q": "News",         # Ada Derana News Channel
    "UCSTl549eJYdeUAY0NmZLU6A": "News",         # Ada Derana Biz
    "UCHKtXGbqRIM0hA4Manb9DNg": "News",         # Ada Derana Sports
    "UCir6eRv6gShvpiWR2TehHzg": "News",         # Ada Derana World News
    "UCgnFSj7jQffD5V5m05j4dPw": "News",         # Newsfirst Sri Lanka
    "UCZivioxyP41QI_BfFT6BsyA": "News",         # Aruna lk
    "UC_pXLr9PembJqvg24Ij28Dg": "News",         # The Morning

    # Music & Reality Competitions
    "UCu_V8lfzyGspxP-LNFowW9w": "Music",        # eTunes
    "UCs8gVM6lPhRZk3L_zZmedpw": "Music",        # Dream Star
    "UCJr5vlnK6HEBVISUtxnq_sg": "Music",        # Derana Little Star
    "UCZ418aLcVbJDo0fc01aQDQQ": "Music",        # Derana 60 Plus
    "UCrZs77rjxjbn_BMaSccMXnQ": "Music",        # Derana City Of Music
    "UCmqflTSJ6911aCrnaWIXxsA": "Music",        # The Voice Sri Lanka
    "UCtBhlCYSLlz2TO9hK93micg": "Music",        # The Voice Kids
    "UC7mhtAaF1ESJgCozpoS2lcQ": "Music",        # Derana Teen Star
    "UCBNxaWOXx6B1B4CEtxoNS3Q": "Music",        # Sirasa Dancing Star
    "UCfnZtEDnl84njUQgtF186cA": "Music",        # Sirasa Lakshapathi
    "UCrWPzTW4EjXNQGcCkCfOvog": "Music",        # Sri Lanka's Got Talent
    "UCe13xXtdfx_n0_z1qeXV6_g": "Music",        # M Entertainments

    # General Entertainment & Drama
    "UCRDDfbYPHX_GUJ4lcQYTc8A": "Entertainment",  # TV Derana
    "UCbkMFGQ_RWIf0OiYeOpf6Ng": "Entertainment",  # TV Derana LIVE
    "UCn0XmAUFv6d2tofMFEesSNw": "Entertainment",  # Sirasa TV
    "UC1YAG2ZbQUjBx3b60c0Qmyg": "Entertainment",  # Sirasa Live
    "UCLNz9bgiJfM3ImTtYDOt8Ew": "Entertainment",  # Sirasa TV Digital
    "UCXJQwWh7dEdEfmIaIJpZ4SQ": "Entertainment",  # Sirasa Lunch Time TV
    "UCEbTQZF9_vDOducFY8gOfag": "Entertainment",  # Sirasa Catchpoint
    "UCVxIst9V-MFBFlpdg3ZNItw": "Entertainment",  # IdeaHell
    "UCjoHgKC53A6DontGbjp0Fbw": "Entertainment",  # Ma Nowana Mama
    "UCYPchfdlyZHi2gt2_FrLL3Q": "Entertainment",  # Lokaya Saha Lokayo
    "UClSmnnGOPwfN-cnhQpdR2Cg": "Entertainment",  # Kisa - Sirasa TV
    "UCqrJfySpfHED-jYFNjWNIqw": "Entertainment",  # 5 Million Money Drop
    "UC_m6TcsKwid_mmOScbuYltg": "Entertainment",  # Derana Shorts

    # Youth, Lifestyle & Radio
    "UCVsi4vIpAcKl825aPQV4IjA": "Lifestyle",    # Pulse.lk
    "UCOPPH1_whpThgY6e7r3qg-w": "Lifestyle",    # FM Derana
    "UCsExZudI-3Bfi2ubAdwcgHw": "Lifestyle",    # Y FM
    "UCXFcukf9VvSWp731oQDJ7Bg": "Lifestyle",    # Yes FM
    "UCKkzOyGRuPyea04qr7aC1NQ": "Lifestyle",    # Shakthi FM
    "UCpp3TTx7OU3SmCECA1-6r3w": "Lifestyle",    # Sirasa FM

    # Education, Tech & Special Interest
    "UCV1NPkc2O0YZBtx_rhDkicw": "Education",    # Ada Derana Education
    "UC0SezLxzrRdTHKiL-lsysHg": "Education",    # Ada Derana Education Kids
    "UCK38_tUB5izyVAWBoLXTkXA": "Special_Interest", # Tech Life
    "UCGnnbsbqbCc7KxSIAbC_d2A": "Special_Interest", # Auto Vision
    "UCwXfRdTtVeVnXXF4poaYw0Q": "Special_Interest", # Travel With Chatura
    "UCkFov8ZOO7NuQcaxZYBJK6w": "Special_Interest", # Talk with Chatura

    # Religion & Culture
    "UCUDuHXAgS9jJgaIUi5Mkvhg": "Culture",      # DAM DERANA
    "UC8fCPqq-Q3Ki3RrMyTsmckg": "Culture",      # Sirasa Dhamma
    "UCXhjcvbJcbtKLxjTZpO1Xvw": "Culture",      # Sirasa Subasiri
    "UCBXlitp9n7KIVFvC_CnTiFQ": "Culture",      # Neth Derana
    "UCSRvGJzj1GHC1fo-Uruot8w": "Culture",      # Tharu Derana
    "UC0T3PeD9A27-vQg-dSvr1MQ": "Culture",      # Sparsha
    "UCLJoVPzEi5ucWU9qJU11j5Q": "Culture",      # Yugathra
}

_SHORTS_REGEX = re.compile(r"#shorts?\b", re.IGNORECASE)


def assign_niche(channel_id: str, default: str = "General") -> str:
    """Return the content niche family for a channel."""
    return NICHE_MAP.get(channel_id, default)


def classify_duration_band(duration_seconds: float | None) -> str:
    """Classify video duration into standard research bands."""
    if duration_seconds is None or duration_seconds < 0:
        return "Unknown"
    if duration_seconds <= 60:
        return "Shorts (<=1m)"
    if duration_seconds <= 300:
        return "Short (1-5m)"
    if duration_seconds <= 1200:
        return "Mid (5-20m)"
    if duration_seconds <= 3600:
        return "Long (20-60m)"
    return "Extended (>60m)"


def extract_format_features(videos_df: pd.DataFrame) -> pd.DataFrame:
    """Enrich the video dataset with format, temporal, and engagement metrics."""
    df = videos_df.copy()

    # 1. Parse timestamps into UTC datetimes
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)

    # 2. Extract temporal aggregation features (Weekly bins for DTM)
    df["upload_year"] = df["published_at"].dt.year
    df["upload_month"] = df["published_at"].dt.month
    df["upload_date"] = df["published_at"].dt.date
    # Format weekly period: e.g. '2026-W42'
    df["upload_week"] = df["published_at"].dt.strftime("%G-W%V")
    df["upload_day_of_week"] = df["published_at"].dt.dayofweek
    df["upload_hour"] = df["published_at"].dt.hour

    # 3. Detect Shorts vs. Long-form
    title_has_short = df["title"].fillna("").str.contains(_SHORTS_REGEX)
    is_short_duration = df["duration_seconds"].fillna(9999) <= 60
    df["is_short"] = title_has_short | is_short_duration

    # 4. Duration Band
    df["duration_band"] = df["duration_seconds"].apply(classify_duration_band)

    # 5. Assign Channel Content Niche
    df["channel_niche"] = df["channel_id"].apply(assign_niche)

    # 6. Public Engagement Indicators
    views = df["view_count"].fillna(0).clip(lower=0)
    likes = df["like_count"].fillna(0).clip(lower=0)
    comments = df["comment_count"].fillna(0).clip(lower=0)

    # Safe rates (per 1,000 views)
    safe_views = views.replace(0, pd.NA)
    df["likes_per_1k_views"] = ((likes / safe_views) * 1000).fillna(0.0).round(2)
    df["comments_per_1k_views"] = ((comments / safe_views) * 1000).fillna(0.0).round(2)
    df["engagement_rate"] = (((likes + comments) / safe_views) * 100).fillna(0.0).round(3)

    return df
