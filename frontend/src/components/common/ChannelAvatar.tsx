/** Channel badge: initials on a colour derived from the channel id (no external logos are loaded). */
/** Six muted channel tones, assigned in the snapshot's channel order (names always accompany them). */
export const PALETTE = ["#1d4ed8", "#0f766e", "#b45309", "#be123c", "#6d28d9", "#475569"];

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

export function ChannelAvatar({ id, name, size = 28, order }: { id: string; name: string | null; size?: number; order?: string[] }) {
  return (
    <span className="avatar" style={{ width: size, height: size, background: colorFor(id, order), fontSize: size * 0.38 }} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
