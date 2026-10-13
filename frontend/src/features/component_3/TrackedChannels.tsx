import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../../components/common/Icon";
import { useResearch } from "./ResearchContext";

/** Top-bar search: jump to a research channel by name (searches the snapshot's channel list only). */
export function ChannelSearch() {
  const { channels } = useResearch();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    // Ctrl+K / Cmd+K focuses the search box
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
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
      <input ref={input} id="channel-search" aria-keyshortcuts="Control+K" list="channel-search-options" placeholder="Search research channels…" value={q}
        onChange={(e) => setQ(e.target.value)} />
      <kbd aria-hidden="true">Ctrl K</kbd>
      <datalist id="channel-search-options">
        {list.map((c) => <option key={c.channel_id} value={c.channel_name ?? c.channel_id} />)}
      </datalist>
    </form>
  );
}
