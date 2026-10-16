import { useEffect, useState } from "react";

/**
 * Animates a number from 0 to `value` once, then shows exactly `format(value)`. The final text is
 * always the real value; reduced-motion users and environments without animation frames see it at once.
 */
export function CountUp({ value, format, duration = 900 }: { value: number | null; format: (v: number | null) => string; duration?: number }) {
  const animate = value !== null && Number.isFinite(value) && typeof window !== "undefined"
    && typeof window.matchMedia === "function" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    && typeof requestAnimationFrame === "function" && !document.hidden;
  const [shown, setShown] = useState<number | null>(animate ? 0 : value);
  useEffect(() => {
    if (!animate || value === null) { setShown(value); return undefined; }
    let frame = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      setShown(p >= 1 ? value : value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // animation frames pause in hidden tabs; always land on the real value
    const done = window.setTimeout(() => setShown(value), duration + 150);
    return () => { cancelAnimationFrame(frame); window.clearTimeout(done); };
  }, [value, animate, duration]);
  return <span aria-label={format(value)}>{format(shown)}</span>;
}
