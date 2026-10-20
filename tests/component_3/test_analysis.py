"""Quick organization analysis (research.component_3.analysis) without network or database.

TEST DATA: none (configuration and validation only); the pipeline progress hook is exercised on a
snapshot id that does not exist, so the stage fails and is reported, never silently skipped.
"""

import pytest

from research.component_3 import analysis as an
from research.component_3 import pilot as pl

CH1, CH2 = "UC" + "a" * 22, "UC" + "b" * 22


def test_quick_config_is_fast_and_scoped():
    cfg = an.quick_config("Sirasa", ["Sirasa TV", "Shakthi TV"])
    assert cfg.max_videos_per_channel == 15 and cfg.max_threads_per_video == 50 and not cfg.fetch_all_replies
    assert cfg.snapshot_source == an.SNAPSHOT_SOURCE
    assert not {"hgt", "node2vec", "evaluation"} & set(cfg.stages)
    assert {"topics", "metapath2vec", "ppr_diffusion", "audience_bridge", "explainability"} <= set(cfg.stages)
    assert pl.estimate_quota(cfg, an.MAX_CHANNELS)["within_cap"]   # the largest allowed job fits the cap


@pytest.mark.parametrize("channels, message", [
    ({CH1: "A"}, "between 2 and"),
    ({f"UC{i:022d}": str(i) for i in range(an.MAX_CHANNELS + 1)}, "between 2 and"),
    ({CH1: "A", "bad id!": "B"}, "not valid"),
])
def test_validate_channels(channels, message):
    with pytest.raises(an.AnalysisError, match=message):
        an.validate_channels(channels)


def test_validate_channels_accepts_two():
    an.validate_channels({CH1: "A", CH2: "B"})


def test_every_step_has_a_label():
    assert set(an.STEPS) | set(an.COMPLETE_STEPS) == set(an.STEP_LABELS)
    assert not set(an.STEPS) & set(an.COMPLETE_STEPS)        # completion adds exactly what quick skips


def test_complete_refuses_research_snapshots(isolated_data_dir):
    with pytest.raises(Exception):
        an.complete_analysis("rs-20990101T000000Z")


def test_run_pipeline_reports_progress(isolated_data_dir):
    seen = []
    cfg = an.quick_config("Sirasa", ["A", "B"])
    results, _ = pl.run_pipeline("rs-20990101T000000Z", cfg, on_stage=lambda r: seen.append((r.stage, r.status)))
    assert seen[:2] == [("research_data", "running"), ("research_data", "failed")]
    assert results[0].status == "failed" and all(r.status == "not_executed" for r in results[1:]
                                                 if r.stage in cfg.stages)
