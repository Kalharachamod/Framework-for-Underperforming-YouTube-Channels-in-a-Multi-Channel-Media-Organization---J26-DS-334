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
  flow: "M9 3h6v5H9zM3 16h6v5H3zM15 16h6v5h-6zM12 8v4M6 16v-4h12v4",
  graph: "M6 6a2 2 0 1 0 0 .01M18 6a2 2 0 1 0 0 .01M12 18a2 2 0 1 0 0 .01M7.5 7.5 11 16.5M16.5 7.5 13 16.5M8 6h8",
};

export function Icon({ name, size = 18 }: { name: keyof typeof PATHS | string; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name] ?? PATHS.overview} />
    </svg>
  );
}
