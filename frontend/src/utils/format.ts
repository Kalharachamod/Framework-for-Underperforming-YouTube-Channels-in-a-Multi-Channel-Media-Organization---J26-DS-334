/** Display helpers. NULL is shown as an em dash ("not available"), never as 0. */

export const DASH = "—";

export function num(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return value.toFixed(digits);
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return Math.round(value).toLocaleString("en-US");
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

export function date(value: string | null | undefined): string {
  if (!value) return DASH;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? DASH : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

/** Research terms keep their conventional spelling in generated labels. */
const TERMS: Record<string, string> = {
  ppr: "PPR", hgt: "HGT", abs: "ABS", topk: "Top-k", jaccard: "Jaccard", kendall: "Kendall", spearman: "Spearman",
  louvain: "Louvain", ndcg: "NDCG", mrr: "MRR", roc: "ROC", auc: "AUC",
};
const LOWERCASE_NAMES = new Set(["metapath2vec", "node2vec"]);

export function label(code: string): string {
  const words = code.split("_").map((w) => TERMS[w.toLowerCase()] ?? w);
  const text = words.join(" ");
  return LOWERCASE_NAMES.has(words[0]) ? text : text.replace(/^./, (c) => c.toUpperCase());
}

export function scalar(value: unknown): string {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

/** 1234 -> "1.2K", 2_400_000 -> "2.4M"; NULL -> "—" (never 0). */
export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${Math.round(value / 1e3)}K`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(Math.round(value));
}

/** A score of exactly 0 means the pair shares no public commenters (confidence 0). Its rank is only a
 * deterministic tie-break, so it is shown as "no bridge evidence" instead of a position. A missing score
 * (null: incomplete components) is a different state and keeps its own "—". */
export function isNoBridgeEvidence(score: number | null | undefined): boolean {
  return score === 0;
}
export const NO_EVIDENCE_TITLE = "Score 0: no shared public commenters, so this pair has no bridge evidence and its rank is only a tie-break.";
