import { createContext, useContext, useState } from "react";
/** Channel badge: initials on a colour derived from the channel id (no external logos are loaded). */
/** Six muted channel tones, assigned in the snapshot's channel order (names always accompany them). */
export const PALETTE = ["#4f46e5", "#0d9488", "#d97706", "#e11d48", "#7c3aed", "#475569"];

export function colorFor(id: string, order?: string[]): string {
  const i = order ? order.indexOf(id) : -1;
  if (i >= 0) return PALETTE[i % PALETTE.length];
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export function initials(name: string | null | undefined): string {
  const words = (name ?? "?").replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  return (words.length >= 2 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2)).toUpperCase();
}

/** Public channel profile-image URLs by channel id (from the API; empty until icons were fetched). */
export const ChannelIconContext = createContext<ReadonlyMap<string, string>>(new Map());

export function ChannelAvatar({ id, name, size = 28, order }: { id: string; name: string | null; size?: number; order?: string[] }) {
  const src = useContext(ChannelIconContext).get(id);
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return (
      <img className="avatar avatar--img" src={src} alt="" aria-hidden="true" width={size} height={size} loading="lazy"
        referrerPolicy="no-referrer" onError={() => setFailed(true)} style={{ width: size, height: size }} />
    );
  }
  return (
    <span className="avatar" style={{ width: size, height: size, background: colorFor(id, order), fontSize: size * 0.38 }} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
