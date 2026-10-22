/**
 * Live Results page. TEST DATA ONLY: synthetic nightly runs and scores; no request leaves the test.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../src/routes/AppRoutes";
import { defaultRoutes } from "./fixtures";

const L = "/api/v1/component-3/live";
const A = "UC" + "a".repeat(22), B = "UC" + "b".repeat(22), C = "UC" + "c".repeat(22);
const run = (over: Record<string, unknown> = {}) => ({
  run_id: "live-20261020T183000Z", started_at: "2026-10-20T18:30:00Z", finished_at: "2026-10-20T19:05:00Z", status: "completed",
  window_start: "2026-07-22T18:30:00Z", window_end: "2026-10-20T18:30:00Z", snapshot_id: "rs-20261020T184000Z",
  experiment_id: "abs-aaaaaaaaaaaa", channels: 3, videos: 120, comments: 900, unique_commenters: 700, quota_units: 850, error: null, ...over,
});
const bridge = (s: string, d: string, score: number, shared: number) => ({
  source_channel_id: s, destination_channel_id: d, source_channel_name: `Live ${s[2]}`, destination_channel_name: `Live ${d[2]}`,
  audience_bridge_score: score, base_score: 0.8, diffusion_component: 0.3, embedding_component: 0.3, topic_component: 0.2,
  confidence: 0.6, shared_commenters: shared, rank: 1, score_status: "ok",
});
const bridges = { run: run(), items: [bridge(A, B, 0.71, 9), bridge(B, C, 0.42, 4), bridge(C, A, 0, 0)],
  channels: [{ channel_id: A, channel_name: "Live a", videos: 50, comments: 400, unique_commenters: 300 }],
  pairs_with_evidence: 2, pairs: 6, note: "TEST" };

function mock(routes: (url: URL) => { status?: number; body: unknown } | undefined) {
  const base = defaultRoutes();
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    const res = routes(url) ?? base(url) ?? { status: 404, body: { error: { code: "not_found", message: "no mock" } } };
    return new Response(JSON.stringify(res.body), { status: res.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}

const renderLive = () => render(<MemoryRouter initialEntries={["/live"]}><AppRoutes /></MemoryRouter>);

describe("Live Results", () => {
  it("shows last night's bridges, channels, runs and a pair trend", async () => {
    mock((url) => {
      if (url.pathname === `${L}/bridges`) return { body: bridges };
      if (url.pathname === `${L}/runs`) return { body: { items: [run(), run({ run_id: "live-20261019T183000Z", started_at: "2026-10-19T18:30:00Z" })], latest_completed_run_id: "live-20261020T183000Z", note: "" } };
      if (url.pathname === `${L}/history`) return { body: { items: [
        { run_id: "live-20261019T183000Z", finished_at: "2026-10-19T19:00:00Z", audience_bridge_score: 0.6, confidence: 0.6, shared_commenters: 7, rank: 1 },
        { run_id: "live-20261020T183000Z", finished_at: "2026-10-20T19:00:00Z", audience_bridge_score: 0.71, confidence: 0.6, shared_commenters: 9, rank: 1 }] } };
      return undefined;
    });
    renderLive();
    expect(await screen.findByRole("button", { name: "Live a to Live b" }, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Live c to Live a" })).not.toBeInTheDocument();   // zero score: not a bridge
    expect(screen.getByText("live-20261020T183000Z")).toBeInTheDocument();
    expect(screen.getByText(/2 of 6 pairs share commenters/)).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Bridge score over 2 nightly runs" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Live b to Live c" }));
    expect(screen.getAllByText(/Live b → Live c/).length).toBeGreaterThan(0);
  });

  it("explains setup when no nightly results exist yet", async () => {
    mock((url) => {
      if (url.pathname === `${L}/bridges`) return { status: 404, body: { error: { code: "not_found", message: "no completed live run yet: the nightly job has not published results" } } };
      if (url.pathname === `${L}/runs`) return { body: { items: [], latest_completed_run_id: null, note: "" } };
      return undefined;
    });
    renderLive();
    expect(await screen.findByText("Live results are not available yet", undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/python -m shared.database.migrate/)).toBeInTheDocument();
  });

  it("warns when last night's run failed but keeps the last good results", async () => {
    mock((url) => {
      if (url.pathname === `${L}/bridges`) return { body: bridges };
      if (url.pathname === `${L}/runs`) return { body: { items: [run({ run_id: "live-20261021T183000Z", status: "failed", error: "network failure" }), run()], latest_completed_run_id: "live-20261020T183000Z", note: "" } };
      if (url.pathname === `${L}/history`) return { body: { items: [] } };
      return undefined;
    });
    renderLive();
    expect(await screen.findByRole("alert", undefined, { timeout: 4000 })).toHaveTextContent("network failure");
    expect(screen.getByRole("button", { name: "Live a to Live b" })).toBeInTheDocument();
  });
  it("explains a blocked network instead of the setup steps", async () => {
    mock((url) => {
      if (url.pathname === `${L}/bridges`) return { status: 503, body: { error: { code: "storage_unavailable", message: "live results are unavailable: the shared database is not reachable from this network" } } };
      if (url.pathname === `${L}/runs`) return { status: 503, body: { error: { code: "storage_unavailable", message: "not reachable" } } };
      return undefined;
    });
    renderLive();
    expect(await screen.findByText("Database not reachable from this network", undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText(/python -m shared.database.migrate/)).not.toBeInTheDocument();
  });

  it("marks an offline copy served when the database is unreachable", async () => {
    mock((url) => {
      if (url.pathname === `${L}/bridges`) return { body: { ...bridges, offline: { saved_at: "2026-10-20T19:10:00Z", reason: "saved copy" } } };
      if (url.pathname === `${L}/runs`) return { body: { items: [run()], latest_completed_run_id: "live-20261020T183000Z", note: "" } };
      if (url.pathname === `${L}/history`) return { body: { items: [] } };
      return undefined;
    });
    renderLive();
    expect(await screen.findByText(/Offline copy saved/, undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Live a to Live b" })).toBeInTheDocument();
  });
});
