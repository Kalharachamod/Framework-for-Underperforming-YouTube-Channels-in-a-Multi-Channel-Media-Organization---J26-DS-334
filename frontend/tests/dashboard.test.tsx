import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes, NAV } from "../src/routes/AppRoutes";
import { A, B, C, EID, SID, XID, defaultRoutes, mockFetch, pair, ranking, status } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("navigation and layout", () => {
  it("offers every section as an accessible link", async () => {
    mockFetch(defaultRoutes());
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const item of NAV) expect(within(nav).getByRole("link", { name: item.label })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByLabelText("Snapshot")).toBeInTheDocument();
    expect(screen.getByLabelText("Scoring experiment")).toBeInTheDocument();
  });
});

describe("Overview", () => {
  it("shows loading and then only values returned by the API", async () => {
    mockFetch(defaultRoutes());
    renderAt("/");
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/);
    expect((await screen.findAllByText(EID)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(SID).length).toBeGreaterThan(0);
    expect(screen.getByText("Provisional")).toBeInTheDocument();
    expect(screen.getByText("3 research channels in this snapshot.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Louvain baseline").parentElement).toHaveTextContent("Missing");
  });

  it("shows an empty state when no research data exists", async () => {
    mockFetch(defaultRoutes({ status: status({ research_data: "missing", snapshots: [], latest_snapshot_id: null, snapshot_id: null, artifacts: [] }) }));
    renderAt("/");
    expect(await screen.findByText("No research data yet")).toBeInTheDocument();
  });

  it("shows an error with no fabricated numbers when the API fails", async () => {
    mockFetch(() => ({ status: 503, body: { error: { code: "storage_unavailable", message: "research artifacts could not be read" } } }));
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("research artifacts could not be read");
    expect(screen.queryByText(/\d+\.\d{3}/)).not.toBeInTheDocument();
  });
});

describe("Audience Bridges", () => {
  it("loads rankings for the selected source and shows the stored components", async () => {
    const fetchMock = mockFetch(defaultRoutes());
    renderAt("/bridges");
    const select = await screen.findByLabelText("Source channel");
    await waitFor(() => expect(select).toBeEnabled());
    await userEvent.selectOptions(select, A);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("1Test Channel C0.43210.5000.3000.540");
    expect(rows[2]).toHaveTextContent("Test Channel B");
    expect(screen.getByText(EID)).toBeInTheDocument();
    const called = fetchMock.mock.calls.map((c) => String(c[0])).find((u) => u.includes("/destinations"));
    expect(called).toContain(`/bridge/${A}/destinations`);
  });

  it("never lists the source channel as its own destination", async () => {
    const bad = ranking(A);
    bad.items.push({ ...bad.items[0], rank: 3, destination_channel_id: A, destination_channel_name: "Test Channel A" });
    mockFetch(defaultRoutes({ ranking: bad }));
    renderAt(`/bridges?source=${A}`);
    const table = await screen.findByRole("table");
    expect(within(table).queryByText("Test Channel A")).not.toBeInTheDocument();
  });

  it("shows an empty state when the source has no ranked destinations", async () => {
    mockFetch(defaultRoutes({ ranking: { ...ranking(A), items: [], total: 0 } }));
    renderAt(`/bridges?source=${A}`);
    expect(await screen.findByText("No ranked destinations")).toBeInTheDocument();
  });

  it("passes the selected experiment to the API", async () => {
    const fetchMock = mockFetch(defaultRoutes());
    renderAt(`/bridges?source=${A}`);
    const exp = await screen.findByLabelText("Scoring experiment");
    await waitFor(() => expect(exp).toBeEnabled());
    await userEvent.selectOptions(exp, EID);
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(`experiment_id=${EID}`))).toBe(true));
  });
});

describe("Explainability", () => {
  it("shows decomposition, evidence states, reasons and uncertainty", async () => {
    mockFetch(defaultRoutes());
    renderAt(`/explainability?source=${A}&destination=${C}`);
    expect(await screen.findByText("0.4321")).toBeInTheDocument();
    expect(screen.getByText("0.500 = 0.5 × 1.000")).toBeInTheDocument();
    expect(screen.getByText(/× 0.540/)).toBeInTheDocument();
    expect(screen.getAllByText("Observed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Zero").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Missing").length).toBeGreaterThan(0);
    expect(screen.getByText(/Strong structural connectivity \(test\)/)).toBeInTheDocument();
    expect(screen.getByText(/not empirically validated/)).toBeInTheDocument();
    expect(screen.getByText(XID, { exact: false })).toBeInTheDocument();
  });

  it("states clearly when no explanation artifact exists", async () => {
    mockFetch(defaultRoutes({ pair: pair({ explanation_status: "unavailable", explanation_detail: "no explanation artifact (STEP 22) exists", explanation_id: null, evidence_summary: null, explanation_reasons: [], uncertainty_notes: [], ranking_context: null, explanation_outcome: null, explanation_text: null }) }));
    renderAt(`/explainability?source=${A}&destination=${C}`);
    expect(await screen.findByText("Explanation not available")).toBeInTheDocument();
    expect(screen.getByText(/no explanation artifact \(STEP 22\) exists/)).toBeInTheDocument();
    expect(screen.queryByText("Explanation reasons")).not.toBeInTheDocument();
  });

  it("excludes the source from the destination choices", async () => {
    mockFetch(defaultRoutes());
    renderAt(`/explainability?source=${A}`);
    const dest = await screen.findByLabelText("Destination channel");
    await waitFor(() => expect(within(dest).queryAllByRole("option").length).toBe(3));
    expect(within(dest).queryByRole("option", { name: "Test Channel A" })).not.toBeInTheDocument();
    expect(within(dest).getByRole("option", { name: "Test Channel B" })).toBeInTheDocument();
  });
});

describe("Evaluation", () => {
  it("shows backend metrics and labels unavailable ones", async () => {
    mockFetch(defaultRoutes());
    renderAt("/evaluation");
    expect(await screen.findByText(/no explicit relevance labels were supplied/i)).toBeInTheDocument();
    expect((await screen.findAllByText("0.314")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("-0.272").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Insufficient temporal data").length).toBeGreaterThan(0);
    expect(screen.getByText(/run without sparse-data simulations/)).toBeInTheDocument();
    expect(screen.getAllByText(/not correctness/).length).toBeGreaterThan(0);
  });

  it("shows an empty state when no evaluation has run", async () => {
    mockFetch(defaultRoutes({ evaluationRuns: { snapshot_id: SID, items: [] } }));
    renderAt("/evaluation");
    expect(await screen.findByText("No evaluation has been run for this snapshot")).toBeInTheDocument();
  });
});

describe("System Status", () => {
  it("separates API health from research readiness", async () => {
    mockFetch(defaultRoutes({ status: status({ research_data: "missing", snapshots: [], latest_snapshot_id: null, snapshot_id: null, artifacts: [] }) }));
    renderAt("/status");
    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(await screen.findByText("Missing", { selector: ".badge *, .badge" })).toBeInTheDocument();
  });

  it("reports an unreachable API instead of simulating success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    renderAt("/status");
    expect(await screen.findByText("Unreachable")).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
  });
});

describe("privacy", () => {
  it("never renders commenter identifiers", async () => {
    const leaky = ranking(A);
    leaky.items[0].destination_channel_name = "anon_" + "f".repeat(64);
    mockFetch(defaultRoutes({ ranking: leaky }));
    const { container } = renderAt(`/bridges?source=${A}`);
    expect(await screen.findByRole("alert")).toHaveTextContent(/commenter identifiers/);
    expect(container.innerHTML).not.toContain("anon_");
    expect(B).toBeTruthy();
  });
});
