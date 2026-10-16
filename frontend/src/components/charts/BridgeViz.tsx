/** Sequential colour scale for score intensity, shared by charts (light = weak, dark = strong). */

export function scoreColor(score: number | null): string {
  // light blue sequential scale (near white -> light blue -> blue): stronger score, darker
  const stops = [[248, 250, 252], [191, 219, 254], [37, 99, 235]];
  const t = Math.max(0, Math.min(1, score ?? 0)) * 2;
  const k = Math.min(1, Math.floor(t)), f = t - k;
  const c = stops[k].map((v, i) => Math.round(v + (stops[k + 1][i] - v) * f));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}
