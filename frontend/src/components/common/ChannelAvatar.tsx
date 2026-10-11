/** Channel badge: initials on a colour derived from the channel id (no external logos are loaded). */
export const PALETTE = ["#e5484d", "#f2a33a", "#2f6fd0", "#8e4ec6", "#1f9d74", "#d6409f", "#0b8ea0", "#7c6f2a",
  "#c2410c", "#4f46e5", "#15803d", "#be123c", "#0369a1", "#a16207", "#6d28d9", "#0f766e", "#b45309", "#1d4ed8"];

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
