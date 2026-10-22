/** Small inline SVG icon set (no icon library); decorative, so hidden from screen readers. */
const PATHS: Record<string, string> = {
  dashboard: "M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  bridges: "M4 18c2-6 5-9 8-9s6 3 8 9M4 18h16M8 18v-4M16 18v-4M12 9V5",
  channels: "M4 6h16v12H4zM9 10l5 2.5L9 15z",
  explain: "M12 3a6 6 0 0 0-3 11.2V17h6v-2.8A6 6 0 0 0 12 3zM9.5 20h5",
  evaluation: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  overview: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  status: "M3 12h4l3-7 4 14 3-7h4",
  search: "M11 4a7 7 0 1 0 4.4 12.4L20 21M11 4a7 7 0 0 1 4.4 12.4",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.5-3.5 3.2-5.5 6.5-5.5s6 2 6.5 5.5M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.8c2 .7 3.2 2.5 3.5 5.2",
  play: "M4 5h16v14H4zM10 9l5 3-5 3z",
  eye: "M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  comment: "M4 5h16v11H9l-5 4z",
  thumb: "M7 10v10H4V10zM7 10l4-6a2 2 0 0 1 2 2v3h5a2 2 0 0 1 2 2.3l-1.2 6.5A2 2 0 0 1 16.8 20H7",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  topic: "M4 7h10M4 12h16M4 17h7",
  neural: "M5 6a1.5 1.5 0 1 0 0 .01M5 12a1.5 1.5 0 1 0 0 .01M5 18a1.5 1.5 0 1 0 0 .01M12 9a1.5 1.5 0 1 0 0 .01M12 15a1.5 1.5 0 1 0 0 .01M19 12a1.5 1.5 0 1 0 0 .01M6.5 6.5 10.5 9M6.5 11.5 10.5 9.5M6.5 12.5 10.5 14.5M6.5 17.5 10.5 15M13.5 9.5 17.5 11.5M13.5 14.5 17.5 12.5",
  flow: "M9 3h6v5H9zM3 16h6v5H3zM15 16h6v5h-6zM12 8v4M6 16v-4h12v4",
  broadcast: "M4 8h16v11H4zM8 3l4 5 4-5",
  tag: "M3 12V4h8l10 10-8 8zM7.5 7.5h.01",
  ripple: "M12 12h.01M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7M5.6 18.4a9 9 0 0 1 0-12.8M18.4 5.6a9 9 0 0 1 0 12.8",
  venn: "M4 12a5 5 0 1 0 10 0a5 5 0 1 0-10 0M10 12a5 5 0 1 0 10 0a5 5 0 1 0-10 0",
  route: "M6 19a2 2 0 1 0 0-.01M18 5a2 2 0 1 0 0-.01M6 17V9a3 3 0 0 1 3-3h7M18 7v8a3 3 0 0 1-3 3H8",
  graph: "M6 6a2 2 0 1 0 0 .01M18 6a2 2 0 1 0 0 .01M12 18a2 2 0 1 0 0 .01M7.5 7.5 11 16.5M16.5 7.5 13 16.5M8 6h8",
  file: "M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6",
  database: "M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zM5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3",
  calendar: "M4 6h16v15H4zM4 10h16M8 3v4M16 3v4",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1",
  layers: "M12 3 2 8l10 5 10-5zM2 13l10 5 10-5M2 17.5l10 5 10-5",
  shield: "M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  cube: "M12 3 4 7.5v9L12 21l8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9",
  target: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM12 11.5h.01",
};

export function Icon({ name, size = 18 }: { name: keyof typeof PATHS | string; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name] ?? PATHS.overview} />
    </svg>
  );
}
