"""Tests for organization channel discovery, using a fake YouTube API.

All channels here are TEST DATA: invented names, ids and websites. No real API
calls are made.
"""

import json

import pytest

from shared.data_collection import discover as cli
from shared.data_collection import org_discovery as od
from shared.data_collection.youtube_client import YouTubeAPIError, YouTubeClient, _sanitized_error


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


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self, num_retries=0):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeYouTube:
    """Mimics the googleapiclient resource methods the client uses."""

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def search(self):
        return self

    def channels(self):
        return self

    def channelSections(self):
        return self

    def list(self, **params):
        self.calls.append(params)
        if self.error:
            return FakeRequest(self.error)
        if params.get("type") == "channel":
            return FakeRequest({"items": [{"id": {"channelId": c}} for c in SEARCH]})
        if "channelId" in params:
            ids = LINKS.get(params["channelId"], [])
            return FakeRequest({"items": [{"contentDetails": {"channels": ids}}] if ids else []})
        ids = params["id"].split(",")
        return FakeRequest({"items": [CHANNELS[i] for i in ids if i in CHANNELS]})


@pytest.fixture
def client():
    return YouTubeClient(service=FakeYouTube())


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
    b = od.discover_organization("Testorg", YouTubeClient(service=FakeYouTube()))
    assert [c.channel_id for c in a.candidates] == [c.channel_id for c in b.candidates]
    assert a.candidates[-1].channel_id == "UC_other"


def test_quota_accounting(result):
    # 1 search (100) + channels.list x2 (2)
    # + sections for 4 name-matching seeds (main, news, edu, fan) + 1 link-back check (pulse)
    assert result.quota_used == 107


def test_no_self_website_evidence():
    only = {"UC_solo": channel("UC_solo", "Solo Org", description="www.soloorg.lk")}
    fake = FakeYouTube()
    fake.list = lambda **p: FakeRequest(
        {"items": [{"id": {"channelId": "UC_solo"}}]} if p.get("type") == "channel"
        else {"items": []} if "channelId" in p else {"items": [only[i] for i in p["id"].split(",") if i in only]}
    )
    r = od.discover_organization("Solo Org", YouTubeClient(service=fake))
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
    monkeypatch.setattr(cli, "YouTubeClient", lambda: YouTubeClient(service=FakeYouTube()))
    assert cli.main(["search", "Testorg"]) == 0
    out = capsys.readouterr().out
    assert "Pulse Test" in out and "confirm only channels you know" in out

    assert cli.main(["confirm", "Testorg", "high"]) == 0
    assert cli.main(["show", "Testorg"]) == 0
    assert "Pulse Test" in capsys.readouterr().out
    assert cli.main(["confirm", "Testorg", "1"]) == 1  # exists, no --overwrite
    assert "already exists" in capsys.readouterr().err


# --- client safety ------------------------------------------------------------------

def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(YouTubeAPIError, match="YOUTUBE_API_KEY is not set"):
        YouTubeClient()


def test_api_key_never_in_error_message():
    class FakeHttpError(Exception):
        resp = type("R", (), {"status": 403})()
        error_details = [{"reason": "quotaExceeded"}]

        def __str__(self):
            return "<HttpError 403 when requesting https://youtube.googleapis.com/youtube/v3/search?q=x&key=TESTKEY123&alt=json>"

    client = YouTubeClient(service=FakeYouTube(error=FakeHttpError()))
    with pytest.raises(YouTubeAPIError) as err:
        client.search_channels("Testorg")
    assert "TESTKEY123" not in str(err.value)
    assert err.value.reason == "quotaExceeded" and err.value.status == 403
    assert "quota used up" in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__


def test_sanitizer_handles_plain_errors():
    e = _sanitized_error("channels.list", OSError("connect failed key=SECRETX"))
    assert "SECRETX" not in str(e)


def test_empty_query_rejected(client):
    with pytest.raises(ValueError):
        client.search_channels("  ")
