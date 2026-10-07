"""Tests for organization channel discovery, using a fake YouTube API.

All channels here are TEST DATA: invented names, ids and websites. No real API
calls are made.
"""

import json

import pytest

from shared.data_collection import discover as cli
from shared.data_collection import org_discovery as od
from shared.data_collection.youtube_client import (
    HttpResult,
    MissingAPIKeyError,
    QuotaExceededError,
    YouTubeClient,
)


def channel(cid, title, *, handle=None, description="", subs=1000, country="LK", hidden=False):
    return {
        "id": cid,
        "snippet": {"title": title, "customUrl": handle, "description": description, "country": country},
        "statistics": {"subscriberCount": str(subs), "videoCount": "10", "hiddenSubscriberCount": hidden},
    }


# TEST DATA: a fictional media organization "Testorg" with sub-channels.
CHANNELS = {
    "UC_main": channel("UC_main", "Testorg TV", handle="@testorgtv",
                       description="Official channel. www.testorg.lk", subs=900_000),
    "UC_news": channel("UC_news", "Ada Testorg", handle="@adatestorg",
                       description="News from Testorg. https://news.testorg.lk/live", subs=500_000),
    "UC_edu": channel("UC_edu", "Testorg Education", description="Lessons. contact@testorg.lk", subs=20_000),
    "UC_pulse": channel("UC_pulse", "Pulse Test", handle="@pulsetest",
                        description="Entertainment. Visit testorg.lk", subs=150_000),
    "UC_fan": channel("UC_fan", "Testorg Fan Clips", description="Unofficial clips! facebook.com/x", subs=300,
                      country=None),
    "UC_other": channel("UC_other", "Other Media", description="www.othermedia.com", subs=50_000),
}
SEARCH = ["UC_main", "UC_news", "UC_edu", "UC_fan", "UC_other"]  # Pulse is NOT in search results
LINKS = {"UC_main": ["UC_news", "UC_pulse", "UC_edu"], "UC_news": ["UC_main"], "UC_pulse": ["UC_main"]}


class FakeYouTube:
    """Mocked HTTP transport answering like the YouTube API (no network)."""

    def __init__(self, error_status=None, error_body=None):
        self.error_status = error_status
        self.error_body = error_body
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params)))
        if self.error_status:
            return HttpResult(self.error_status, {}, json.dumps(self.error_body).encode())
        resource = url.rsplit("/", 1)[-1]
        if resource == "search":
            body = {"items": [{"id": {"channelId": c}} for c in SEARCH]}
        elif resource == "channelSections":
            ids = LINKS.get(params["channelId"], [])
            body = {"items": [{"contentDetails": {"channels": ids}}] if ids else []}
        else:
            body = {"items": [CHANNELS[i] for i in params["id"].split(",") if i in CHANNELS]}
        return HttpResult(200, {}, json.dumps(body).encode())


def make_client(transport=None):
    return YouTubeClient(api_key="TEST_KEY_NOT_REAL", transport=transport or FakeYouTube(), sleep=lambda s: None)


@pytest.fixture
def client():
    return make_client()


@pytest.fixture
def result(client):
    return od.discover_organization("Testorg", client)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(od.paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def by_id(result):
    return {c.channel_id: c for c in result.candidates}


# --- discovery -----------------------------------------------------------------

def test_finds_sub_channel_without_name_match(result):
    pulse = by_id(result)["UC_pulse"]  # not in search results, no "Testorg" in its name
    assert any("linked by Testorg TV" in e for e in pulse.evidence)
    assert any("links back" in e for e in pulse.evidence)
    assert any("testorg.lk" in e for e in pulse.evidence)
    assert pulse.confidence == "high"


def test_official_channels_rank_high(result):
    c = by_id(result)
    for cid in ("UC_main", "UC_news", "UC_edu"):
        assert c[cid].confidence == "high", (cid, c[cid].evidence)


def test_fan_channel_is_not_high(result):
    fan = by_id(result)["UC_fan"]
    assert fan.confidence != "high"
    assert not any("linked by" in e or "website" in e for e in fan.evidence)  # generic facebook.com ignored


def test_unrelated_channel_low(result):
    other = by_id(result)["UC_other"]
    assert other.confidence == "low"
    assert other.evidence == ["returned by search only"]


def test_ranking_is_deterministic(client):
    a = od.discover_organization("Testorg", client)
    b = od.discover_organization("Testorg", make_client())
    assert [c.channel_id for c in a.candidates] == [c.channel_id for c in b.candidates]
    assert a.candidates[-1].channel_id == "UC_other"


def test_quota_accounting(result):
    # 1 search (100) + channels.list x2 (2)
    # + sections for 4 name-matching seeds (main, news, edu, fan) + 1 link-back check (pulse)
    assert result.quota_used == 107


def test_no_self_website_evidence():
    only = {"UC_solo": channel("UC_solo", "Solo Org", description="www.soloorg.lk")}

    def transport(url, params, timeout):
        resource = url.rsplit("/", 1)[-1]
        body = ({"items": [{"id": {"channelId": "UC_solo"}}]} if resource == "search"
                else {"items": []} if resource == "channelSections"
                else {"items": [only[i] for i in params["id"].split(",") if i in only]})
        return HttpResult(200, {}, json.dumps(body).encode())

    r = od.discover_organization("Solo Org", make_client(transport))
    assert not any("website" in e for e in r.candidates[0].evidence)


@pytest.mark.parametrize("bad", ["", " ", "x"])
def test_invalid_organization_name(client, bad):
    with pytest.raises(ValueError):
        od.discover_organization(bad, client)


def test_domains_ignore_generic_and_keep_country_tlds():
    ch = channel("x", "x", description="a.testorg.lk b@testorg.lk youtube.com/@x fb.me/x bit.ly/y")
    assert od._domains(ch) == {"testorg.lk"}


# --- review / confirm / storage --------------------------------------------------------

def test_review_round_trip_and_confirm(project, result):
    od.save_review(result)
    loaded = od.load_review("Testorg")
    assert [c.channel_id for c in loaded.candidates] == [c.channel_id for c in result.candidates]

    path = od.confirm_organization(loaded, ["UC_main", "UC_pulse"])
    assert path == project / "config" / "organizations" / "testorg.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert [c["channel_id"] for c in saved["channels"]] == ["UC_main", "UC_pulse"]
    assert "reviewer-confirmed" in saved["method"]
    assert od.organization_channel_ids("Testorg") == ["UC_main", "UC_pulse"]


def test_confirm_protects_existing_list(project, result):
    od.confirm_organization(result, ["UC_main"])
    with pytest.raises(FileExistsError):
        od.confirm_organization(result, ["UC_news"])
    od.confirm_organization(result, ["UC_news"], overwrite=True)
    assert od.organization_channel_ids("Testorg") == ["UC_news"]


def test_confirm_rejects_unknown_or_empty(project, result):
    with pytest.raises(ValueError, match="not among"):
        od.confirm_organization(result, ["UC_made_up"])
    with pytest.raises(ValueError):
        od.confirm_organization(result, [])


def test_review_files_are_git_ignored_location(project, result):
    path = od.save_review(result)
    assert path == project / "data" / "raw" / "discovery" / "testorg.json"


def test_missing_review_or_org(project):
    with pytest.raises(FileNotFoundError):
        od.load_review("Nothing")
    with pytest.raises(FileNotFoundError):
        od.load_organization("Nothing")


def test_slugify():
    assert od.slugify("Derana TV (Sri Lanka)") == "derana-tv-sri-lanka"
    with pytest.raises(ValueError):
        od.slugify("!!!")


# --- CLI ---------------------------------------------------------------------

def test_cli_select(result):
    n = {c.channel_id: i for i, c in enumerate(result.candidates, 1)}
    assert cli.select(result, [str(n["UC_main"]), str(n["UC_edu"])]) == ["UC_main", "UC_edu"]
    assert cli.select(result, [f"{n['UC_main']},{n['UC_edu']}"]) == ["UC_main", "UC_edu"]
    assert set(cli.select(result, ["high"])) == {"UC_main", "UC_news", "UC_edu", "UC_pulse"}
    with pytest.raises(ValueError):
        cli.select(result, ["99"])
    with pytest.raises(ValueError):
        cli.select(result, ["abc"])


def test_cli_flow(project, monkeypatch, capsys):
    monkeypatch.setattr(cli, "YouTubeClient", lambda: make_client())
    assert cli.main(["search", "Testorg"]) == 0
    out = capsys.readouterr().out
    assert "Pulse Test" in out and "confirm only channels you know" in out

    assert cli.main(["confirm", "Testorg", "high"]) == 0
    assert cli.main(["show", "Testorg"]) == 0
    assert "Pulse Test" in capsys.readouterr().out
    assert cli.main(["confirm", "Testorg", "1"]) == 1  # exists, no --overwrite
    assert "already exists" in capsys.readouterr().err


# --- client use by discovery ---------------------------------------------------------

def test_discovery_requires_api_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError):
        YouTubeClient()


def test_discovery_reports_quota_errors(project, monkeypatch, capsys):
    body = {"error": {"code": 403, "message": "quota", "errors": [{"reason": "quotaExceeded"}]}}
    monkeypatch.setattr(cli, "YouTubeClient", lambda: make_client(FakeYouTube(403, body)))
    assert cli.main(["search", "Testorg"]) == 1
    err = capsys.readouterr().err
    assert "quotaExceeded" in err and "TEST_KEY_NOT_REAL" not in err
    with pytest.raises(QuotaExceededError):
        od.discover_organization("Testorg", make_client(FakeYouTube(403, body)))


def test_empty_query_rejected(client):
    with pytest.raises(ValueError):
        client.search_channels("  ")
