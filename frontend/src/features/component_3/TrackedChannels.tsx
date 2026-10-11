import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChannelAvatar } from "../../components/common/ChannelAvatar";
import { Icon } from "../../components/common/Icon";
import { useResearch } from "./ResearchContext";

/** Sidebar list of the research channels of the selected snapshot (real configuration, no extras). */
export function TrackedChannels({ limit = 8 }: { limit?: number }) {
  const { channels } = useResearch();
  const [all, setAll] = useState(false);
  if (channels.status !== "success" || channels.data.items.length === 0) return null;
  const items = [...channels.data.items].sort((a, b) => (b.observed_subscriber_count ?? -1) - (a.observed_subscriber_count ?? -1));
  const shown = all ? items : items.slice(0, limit);
  return (
    <div className="nav__group tracked">
      <p className="nav__heading">Tracked channels ({items.length})</p>
      <ul className="nav">
        {shown.map((c) => (
          <li key={c.channel_id}>
            <Link className="nav__link nav__link--channel" to={`/channels?channel=${encodeURIComponent(c.channel_id)}`}>
              <ChannelAvatar id={c.channel_id} name={c.channel_name} size={22} />
              <span>{c.channel_name ?? c.channel_id}</span>
            </Link>
          </li>
        ))}
      </ul>
      {items.length > limit && (
        <button type="button" className="link-button" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </div>
  );
}

/** Top-bar search: jump to a research channel by name (searches the snapshot's channel list only). */
export function ChannelSearch() {
  const { channels } = useResearch();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const list = channels.status === "success" ? channels.data.items : [];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const hit = list.find((c) => (c.channel_name ?? "").toLowerCase() === q.trim().toLowerCase())
      ?? list.find((c) => (c.channel_name ?? "").toLowerCase().includes(q.trim().toLowerCase()));
    if (hit && q.trim()) navigate(`/channels?channel=${encodeURIComponent(hit.channel_id)}`);
  };
  return (
    <form className="search" role="search" onSubmit={submit}>
      <Icon name="search" size={16} />
      <label htmlFor="channel-search" className="sr-only">Search channels</label>
      <input id="channel-search" list="channel-search-options" placeholder="Search research channels…" value={q}
        onChange={(e) => setQ(e.target.value)} />
      <datalist id="channel-search-options">
        {list.map((c) => <option key={c.channel_id} value={c.channel_name ?? c.channel_id} />)}
      </datalist>
    </form>
  );
}
