/**
 * Analyze Organization page. TEST DATA ONLY: invented channels and a synthetic job; no request
 * leaves the test (fetch is mocked) and no number shown here is a research result.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../src/routes/AppRoutes";
import { defaultRoutes, status } from "./fixtures";

const ORG = "Testvision";
const H1 = "UC" + "a".repeat(22);
const H2 = "UC" + "b".repeat(22);
const L1 = "UC" + "c".repeat(22);
const NEW_SID = "rs-20260202T000000Z";

const config = (over: Record<string, unknown> = {}) => ({
  enabled: true, min_channels: 2, max_channels: 25,
  limits: { max_videos_per_channel: 15, max_threads_per_video: 50, fetch_all_replies: false },
  stages: [{ step: "preflight", label: "Checking configuration" }], active_job_id: null, note: "TEST", ...over,
});
const candidate = (channel_id: string, title: string, confidence: string) => ({
  channel_id, title, handle: null, country: "LK", subscriber_count: 1200, video_count: 30, score: 5,
  confidence, evidence: ["organization name in channel title"], previously_confirmed: false,
});
const discovery = { organization: ORG, discovered_at: "2026-02-02T00:00:00Z", quota_used: 120, source: "youtube",
  candidates: [candidate(H1, "Testvision TV", "high"), candidate(H2, "Testvision News", "high"), candidate(L1, "Fan page", "low")] };
const job = (status: string, over: Record<string, unknown> = {}) => ({
  job_id: "job-0123456789ab", organization: ORG, channels: [{ channel_id: H1, title: "Testvision TV" }, { channel_id: H2, title: "Testvision News" }],
  status, created_at: "2026-02-02T00:00:00Z", started_at: "2026-02-02T00:00:00Z", finished_at: status === "completed" ? "2026-02-02T00:04:00Z" : null,
  steps: [
    { step: "comments", label: "Collecting public comments", status: "completed", details: { videos_total: 30, collected: 210 } },
    { step: "audience_bridge", label: "Audience Bridge Score", status: status === "completed" ? "completed" : "running", details: {} },
  ],
  result: status === "completed" ? { snapshot_id: NEW_SID, experiment_id: "abs-aaaaaaaaaaaa", rows: { channels: 2, videos: 30, comments: 210 }, quota_units: 47 } : null,
  error: null, ...over,
});

type Answer = { status?: number; body: unknown };

/** Fetch mock that also sees the method and body (POST endpoints). */
function mock(routes: (url: URL, method: string, body: unknown) => Answer | undefined, base = defaultRoutes()) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const res = routes(url, method, init?.body ? JSON.parse(String(init.body)) : null) ?? base(url)
      ?? { status: 404, body: { error: { code: "not_found", message: "no mock" } } };
    return new Response(JSON.stringify(res.body), { status: res.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const A = "/api/v1/component-3/analysis";

/** The search box is enabled once the analysis settings have loaded. */
async function searchBox() {
  const input = await screen.findByLabelText("Organization or main channel");
  await waitFor(() => expect(input).toBeEnabled());
  return input;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/analyze"]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("Analyze Organization", () => {
  it("searches, pre-selects high-confidence channels and runs a quick analysis", async () => {
    const posts: unknown[] = [];
    mock((url, method, body) => {
      if (url.pathname === `${A}/config`) return { body: config() };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [] } };
      if (url.pathname === `${A}/discover` && method === "POST") { posts.push(body); return { body: discovery }; }
      if (url.pathname === `${A}/jobs` && method === "POST") { posts.push(body); return { status: 202, body: job("running") }; }
      if (url.pathname === `${A}/jobs/job-0123456789ab`) return { body: job("completed") };
      return undefined;
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await searchBox(), ORG);
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Testvision TV", undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(posts[0]).toEqual({ organization: ORG, region_code: "LK" });
    expect(screen.getByRole("checkbox", { name: "Include Testvision TV" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Include Fan page" })).not.toBeChecked();   // low confidence

    await user.click(screen.getByRole("button", { name: "Analyze 2 channels" }));
    expect(posts[1]).toEqual({ organization: ORG, channels: [{ channel_id: H1, title: "Testvision TV" }, { channel_id: H2, title: "Testvision News" }] });
    expect(await screen.findByRole("button", { name: "Open results" }, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("210 comments", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(NEW_SID)).toBeInTheDocument();
  });

  it("needs at least two channels before analysing", async () => {
    mock((url, method) => {
      if (url.pathname === `${A}/config`) return { body: config() };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [] } };
      if (url.pathname === `${A}/discover`) return { body: discovery };
      return undefined;
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await searchBox(), ORG);
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("checkbox", { name: "Include Testvision News" }));
    expect(screen.getByRole("button", { name: "Analyze 1 channels" })).toBeDisabled();
    expect(screen.getByText(/select at least 2 channels/)).toBeInTheDocument();
  });

  it("explains a conflict when another analysis is running", async () => {
    mock((url, method) => {
      if (url.pathname === `${A}/config`) return { body: config() };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [] } };
      if (url.pathname === `${A}/discover`) return { body: discovery };
      if (url.pathname === `${A}/jobs` && method === "POST")
        return { status: 409, body: { error: { code: "conflict", message: "an analysis is already running" } } };
      return undefined;
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await searchBox(), ORG);
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("button", { name: "Analyze 2 channels" }));
    expect(await screen.findByText(/Another analysis is already running/)).toBeInTheDocument();
  });

  it("shows a search failure without inventing candidates", async () => {
    mock((url, method) => {
      if (url.pathname === `${A}/config`) return { body: config() };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [] } };
      if (url.pathname === `${A}/discover`)
        return { status: 502, body: { error: { code: "upstream_error", message: "YouTube Data API request failed: quotaExceeded" } } };
      return undefined;
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await searchBox(), ORG);
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quotaExceeded");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("disables searching when the server has analysis switched off", async () => {
    mock((url, method) => {
      if (url.pathname === `${A}/config`) return { body: config({ enabled: false }) };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [] } };
      return undefined;
    });
    renderPage();
    expect(await screen.findByText(/switched off on this server/)).toBeInTheDocument();
    expect(screen.getByLabelText("Organization or main channel")).toBeDisabled();
  });

  it("labels snapshots with their organization in the snapshot selector", async () => {
    const snaps = [{ snapshot_id: NEW_SID, created_at: "2026-02-02T00:00:00Z", extracted_at: "2026-02-02T00:00:00Z",
      channels: 2, videos: 30, comments: 210, organization: ORG, quick_analysis: true }];
    mock((url, method) => {
      if (url.pathname === `${A}/config`) return { body: config() };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [job("completed")] } };
      return undefined;
    }, defaultRoutes({ status: status({ snapshots: snaps, latest_snapshot_id: NEW_SID, snapshot_id: NEW_SID }) }));
    renderPage();
    const select = await screen.findByLabelText("Snapshot");
    await waitFor(() => expect(within(select).getByRole("option", { name: new RegExp(`${ORG} \\(quick\\) · ${NEW_SID}`) })).toBeInTheDocument());
    expect(await screen.findByText("Recent analyses")).toBeInTheDocument();
  });
});

describe("Quick-analysis snapshots", () => {
  const quickStatus = status({
    snapshots: [{ snapshot_id: NEW_SID, created_at: "2026-02-02T00:00:00Z", extracted_at: "2026-02-02T00:00:00Z",
      channels: 2, videos: 30, comments: 210, organization: ORG, quick_analysis: true }],
    latest_snapshot_id: NEW_SID, snapshot_id: NEW_SID,
  });

  it("explains a skipped evaluation and completes the analysis on request", async () => {
    const posts: unknown[] = [];
    mock((url, method, body) => {
      if (url.pathname === `${A}/complete` && method === "POST") {
        posts.push(body);
        return { status: 202, body: job("running", { kind: "complete", snapshot_id: NEW_SID, channels: [] }) };
      }
      if (url.pathname === `${A}/jobs/job-0123456789ab`) return { body: job("running", { kind: "complete", snapshot_id: NEW_SID, channels: [] }) };
      if (url.pathname === `${A}/config`) return { body: config() };
      if (url.pathname === `${A}/jobs` && method === "GET") return { body: { items: [] } };
      return undefined;
    }, defaultRoutes({ status: quickStatus, evaluationRuns: { snapshot_id: NEW_SID, items: [] } }));
    render(<MemoryRouter initialEntries={["/evaluation"]}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByText("The evaluation was skipped in the quick analysis", undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText("No evaluation has been run for this snapshot")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Complete analysis" }));
    expect(posts).toEqual([{ snapshot_id: NEW_SID }]);
    expect(await screen.findByText(`Completing analysis: ${ORG}`, undefined, { timeout: 4000 })).toBeInTheDocument();
  });

  it("keeps the normal empty state for research snapshots", async () => {
    mock(() => undefined, defaultRoutes({ evaluationRuns: { snapshot_id: "rs-20260101T000000Z", items: [] } }));
    render(<MemoryRouter initialEntries={["/evaluation"]}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByText("No evaluation has been run for this snapshot", undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete analysis" })).not.toBeInTheDocument();
  });
});
