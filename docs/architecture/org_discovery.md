# Organization Channel Discovery

Code: [`shared/data_collection/org_discovery.py`](../../shared/data_collection/org_discovery.py), CLI [`discover.py`](../../shared/data_collection/discover.py), API client [`youtube_client.py`](../../shared/data_collection/youtube_client.py)
Tests: [`tests/shared/test_org_discovery.py`](../../tests/shared/test_org_discovery.py) (fake API, no real calls)

## Purpose

The research studies **large media organizations that run many YouTube channels**: a main channel plus sub-channels for news, education, music, programmes and so on. Instead of typing channel IDs by hand, you search for the organization by name, and the system proposes its channel family.

Example: searching **"Derana"** proposes TV Derana, Ada Derana, FM Derana, Ada Derana Education, Derana Shorts, and also channels without "Derana" in their name, such as **Pulse.lk**, **Dream Star** and **eTunes**, because the official Derana channels link to them.

## Ownership cannot be proven from YouTube

YouTube doesn't publish which company owns a channel. Discovery therefore produces **candidates with evidence and a confidence level**. A person reviews them and **confirms** which belong; only confirmed channels are used for data collection. In the methodology, this is *API-based candidate discovery with manual verification*.

## How it works

1. **Search:** YouTube channel search for the organization name (`search.list`, 100 quota units).
2. **Details:** title, handle, description, country and statistics for every result (`channels.list`, 1 unit per 50 channels).
3. **Seeds:** the channels whose name matches the organization best, up to 5.
4. **Linked channels:** the channels each seed lists in its featured or multi-channel sections (`channelSections.list`, 1 unit each). This finds sub-channels whose names don't contain the organization name.
5. **Link-back check:** whether each linked channel links back to a seed (up to 20 checks, 1 unit each).
6. **Score and rank** each candidate by its evidence:

| Evidence | Points |
|---|---|
| Organization name in the channel title | +3 |
| Name partly in the title or handle | +1.5 |
| Linked by a matching channel | +3 |
| Links back to a matching channel | +1 |
| Same website domain as *another* matching channel (generic sites such as Facebook, Instagram and bit.ly are ignored) | +2 |
| Organization named in the description | +1 |
| Same country as the matching channels (only when other evidence exists) | +0.5 |

**Confidence levels:** **high** is 5 points or more, **medium** is 3 or more, and **low** is everything else. The ranking is deterministic.

A typical run costs **about 100–150 units** (the Derana test used 127 of the 10,000 daily). It reads **public channel metadata only**: no videos, no comments and no commenter data.

## Usage

```powershell
# 1. Discover (uses quota). Candidates are saved for review in data/raw/discovery/ (git-ignored)
python -m shared.data_collection.discover search "Derana" --region LK

# 2. Review again at any time (no quota)
python -m shared.data_collection.discover review "Derana"

# 3. Confirm the channels that belong, by number, or "high" for all high-confidence ones
python -m shared.data_collection.discover confirm "Derana" 1 2 3 6 27

# 4. Show the confirmed list
python -m shared.data_collection.discover show "Derana"
```

From Python:

```python
from shared.data_collection.org_discovery import organization_channel_ids
channel_ids = organization_channel_ids("Derana")   # used by the collector (later step)
```

## Where results are stored

| File | Contents | In git? |
|---|---|---|
| `data/raw/discovery/<org>.json` | All candidates with evidence (review material) | No (`data/` is ignored) |
| `config/organizations/<org>.json` | **Confirmed** channels: ID, title, handle, confidence, evidence, dates, method | Yes; this is the shared, agreed channel list |

A confirmed list is not overwritten without `--overwrite`.

## Reviewing candidates: guidance

- **Confirm** official channels: these are high-confidence and linked by the main channels.
- **Check medium candidates** on YouTube. Programme and partner channels (e.g. "Travel With Chatura", "eTunes") can be linked by the organization without being owned by it. Decide according to your research definition of "organization channel" and record that decision.
- **Exclude** channels that match the name only and have very few subscribers and no links. These are usually unofficial copies or fan pages.

## Security

- Discovery uses the shared API client ([youtube_api.md](youtube_api.md)): the key comes from `.env`, is never shown, and is removed from every error message.
- Quota errors are reported clearly (`quotaExceeded`).
- Discovery files contain public channel information only.
