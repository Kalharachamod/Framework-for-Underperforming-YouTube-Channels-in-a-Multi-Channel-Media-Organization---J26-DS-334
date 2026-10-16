import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes, NAV } from "../src/routes/AppRoutes";
import { A, B, C, EID, EVID, PREV_SID, SID, XID, compare, defaultRoutes, mockFetch, pair, status } from "./fixtures";

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

describe("Research overview", () => {
  it("shows loading and then only values returned by the API", async () => {
    mockFetch(defaultRoutes());
    renderAt("/overview");
    expect(screen.getByRole("status")).toHaveTextContent(/Loading/);
    expect((await screen.findAllByText(EID, undefined, { timeout: 4000 })).length).toBeGreaterThan(0);
    expect(screen.getAllByText(SID).length).toBeGreaterThan(0);
    expect(screen.getByText("Provisional")).toBeInTheDocument();
    expect(screen.getByText("3 research channels in this snapshot.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Louvain baseline").parentElement).toHaveTextContent("Missing");
  });

  it("shows an empty state when no research data exists", async () => {
    mockFetch(defaultRoutes({ status: status({ research_data: "missing", snapshots: [], latest_snapshot_id: null, snapshot_id: null, artifacts: [] }) }));
    renderAt("/overview");
    expect(await screen.findByText("No research data yet")).toBeInTheDocument();
  });

  it("shows an error with no fabricated numbers when the API fails", async () => {
    mockFetch(() => ({ status: 503, body: { error: { code: "storage_unavailable", message: "research artifacts could not be read" } } }));
    renderAt("/overview");
    expect(await screen.findByRole("alert")).toHaveTextContent("research artifacts could not be read");
    expect(screen.queryByText(/\d+\.\d{3}/)).not.toBeInTheDocument();
  });
});

describe("Audience Bridges", () => {
  it("shows the stored pairs in the backend order and analyses the selected bridge", async () => {
    const fetchMock = mockFetch(defaultRoutes());
    renderAt("/bridges");
    const table = (await screen.findAllByRole("table")).at(-1)!;
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Test Channel A");
    expect(rows[1]).toHaveTextContent("Test Channel C");
    expect(rows[1]).toHaveTextContent("0.710");
    expect(rows[1]).toHaveTextContent("0.650");                                  // stored topic similarity
    await userEvent.click(within(rows[1]).getByRole("button", { name: /^Test Channel A\s+Test Channel C$/ }));
    const side = screen.getByRole("complementary", { name: "Selected bridge" });
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(`/bridge/${A}/destinations/${C}`))).toBe(true));
    expect((await within(side).findAllByText("0.432")).length).toBeGreaterThan(0);
    expect(within(side).getByText(/topic similarity is symmetric/)).toBeInTheDocument();
  });

  it("filters by source and score threshold without recalculating scores", async () => {
    mockFetch(defaultRoutes());
    renderAt("/bridges");
    await screen.findByText("6 of 6 pairs");
    const ranking = screen.getByRole("region", { name: "Ranking table" });
    await userEvent.selectOptions(within(ranking).getByRole("combobox", { name: "Source" }), B);
    expect(await screen.findByText("2 of 6 pairs")).toBeInTheDocument();
    const table = screen.getAllByRole("table").at(-1)!;
    expect(within(table).getByText("0.550")).toBeInTheDocument();
  });

  it("never shows an unscored pair as zero", async () => {
    mockFetch(defaultRoutes());
    renderAt("/bridges");
    const table = (await screen.findAllByRole("table")).at(-1)!;
    const rows = within(table).getAllByRole("row");
    const unscored = rows[rows.length - 1];
    expect(unscored).toHaveTextContent("Test Channel C");
    expect(unscored).toHaveTextContent("—");
    expect(unscored).not.toHaveTextContent("0.000");
  });

  it("shows an empty state when the scoring run has no pairs", async () => {
    mockFetch(defaultRoutes({ bridgePairs: { snapshot_id: SID, experiment_id: EID, items: [], note: "" } }));
    renderAt("/bridges");
    expect(await screen.findByText("No bridge relationships are available for this snapshot.")).toBeInTheDocument();
  });

  it("expands a ranking row to show its aggregate evidence", async () => {
    mockFetch(defaultRoutes());
    renderAt("/bridges");
    const toggle = await screen.findByRole("button", { name: "Show evidence for Test Channel A to Test Channel C" });
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide evidence for Test Channel A to Test Channel C" })).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("Temporal support")).toBeInTheDocument();
  });

  it("draws the bridge card graph around a source and opens a bridge from its card", async () => {
    const fetchMock = mockFetch(defaultRoutes());
    renderAt("/bridges");
    const controls = await screen.findByRole("group", { name: "Graph controls" });
    expect(within(controls).getByText("2 outbound · 2 inbound shown")).toBeInTheDocument();   // default: strongest pair's source (A)
    await userEvent.selectOptions(within(controls).getByRole("combobox", { name: "Source channel" }), B);
    expect(await within(controls).findByText("2 outbound · 1 inbound shown")).toBeInTheDocument();
    await userEvent.click(within(controls).getByRole("checkbox", { name: /Hide confidence below 0.5/ }));
    expect(within(controls).getByText("1 outbound · 1 inbound shown")).toBeInTheDocument();
    const graph = screen.getByRole("group", { name: "Audience bridges of Test Channel B" });
    await userEvent.click(within(graph).getByRole("button", { name: /^Test Channel B to Test Channel A: score 0.550/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(`/bridge/${B}/destinations/${A}`))).toBe(true));
  });

  it("shows a clear rate-limit error with a retry button", async () => {
    mockFetch((url) => (url.pathname.endsWith("/bridge/pairs") ? { status: 429, body: { detail: "slow down" } } : defaultRoutes()(url)));
    renderAt("/bridges");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Research API rate limit reached. Please retry later.");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows a skeleton while the scored pairs load", () => {
    mockFetch(defaultRoutes());
    renderAt("/bridges");
    expect(screen.getAllByRole("status").some((el) => /Loading scored pairs/.test(el.textContent ?? ""))).toBe(true);
  });

  it("passes the selected experiment to the API", async () => {
    const fetchMock = mockFetch(defaultRoutes());
    renderAt("/bridges");
    const exp = await screen.findByLabelText("Scoring experiment");
    await waitFor(() => expect(exp).toBeEnabled());
    await userEvent.selectOptions(exp, EID);
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("/bridge/pairs") && String(c[0]).includes(`experiment_id=${EID}`))).toBe(true));
  });
});

describe("Explainability", () => {
  it("shows decomposition, evidence states, reasons and uncertainty", async () => {
    mockFetch(defaultRoutes());
    renderAt(`/explainability?source=${A}&destination=${C}`);
    expect((await screen.findAllByText("0.4321")).length).toBeGreaterThan(0);
    expect(screen.getByText("0.500 = 0.500 × 1.000")).toBeInTheDocument();
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
    expect(await screen.findByText(/Ground-truth relevance labels unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Methods compared" })).toHaveTextContent(/Structural baseline/);
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
    expect(await within(screen.getByRole("main")).findByText("Unreachable")).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
  });
});

describe("privacy", () => {
  it("never renders commenter identifiers", async () => {
    const leaky = { snapshot_id: SID, experiment_id: EID, note: "", items: [{ source_channel_id: A, source_channel_name: "Test Channel A",
      destination_channel_id: B, destination_channel_name: "anon_" + "f".repeat(64), rank: 1, audience_bridge_score: 0.5, base_score: 0.5,
      diffusion_component: 0.2, embedding_component: 0.2, topic_component: 0.1, confidence_component: 1, evidence_confidence: 1,
      topic_coverage_confidence: 1, shared_commenters: 3, score_status: "ok" }] };
    mockFetch(defaultRoutes({ bridgePairs: leaky }));
    const { container } = renderAt("/bridges");
    expect(await screen.findByRole("alert")).toHaveTextContent(/commenter identifiers/);
    expect(container.innerHTML).not.toContain("anon_");
    expect(B).toBeTruthy();
  });
});


describe("Overview", () => {
  it("shows research status from the API: snapshot, totals, graph size and strongest bridge", async () => {
    mockFetch(defaultRoutes());
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Audience bridge research" })).toBeInTheDocument();
    const metrics = await screen.findByRole("region", { name: "Research metrics" });
    expect(await within(metrics).findByText("23")).toBeInTheDocument();                  // graph nodes
    expect(within(metrics).getByText("46 edges · 4 node types")).toBeInTheDocument();
    expect(within(metrics).getByText("40")).toBeInTheDocument();                         // collected comments
    expect(await within(metrics).findByText("5")).toBeInTheDocument();                   // scored bridge pairs
    expect(within(metrics).getByRole("img", { name: /Stored scores per 0.1 bin/ })).toBeInTheDocument();
    const spotlight = screen.getByRole("region", { name: "Strongest bridge" });
    expect(within(spotlight).getByRole("img", { name: "Audience Bridge Score 0.710 of 1" })).toBeInTheDocument();
    expect(within(spotlight).getByText("Test Channel A")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Research models" })).toHaveTextContent(/HGT/);
    expect(screen.queryByText(/demographic|sentiment|AI Insight|geograph|device/i)).not.toBeInTheDocument();
  });

  it("shows public channel icons when stored, and initials otherwise", async () => {
    mockFetch(defaultRoutes({ channelIcons: { fetched_at: null, note: "", items: [{ channel_id: A, icon_url: "https://yt3.ggpht.com/test-a" }] } }));
    renderAt("/");
    const audience = await screen.findByRole("region", { name: "Channels by audience" });
    await waitFor(() => expect(audience.querySelector('img[src="https://yt3.ggpht.com/test-a"]')).not.toBeNull());
    expect(within(audience).getAllByText("TC").length).toBeGreaterThan(0);              // channels without an icon keep initials
  });

  it("derives research status from stored artifacts and never claims a running job", async () => {
    mockFetch(defaultRoutes());
    renderAt("/");
    const box = await screen.findByRole("region", { name: "Research status" });
    expect((await within(box).findByRole("link", { name: "Scoring" })).closest("li")).toHaveTextContent("Ready");
    expect(within(box).getByRole("link", { name: "Evaluation" }).closest("li")).toHaveTextContent("Incomplete");
    expect(within(box).queryByText("Running", { selector: ".pill" })).not.toBeInTheDocument();
  });

  it("opens a ranked bridge in the bridge graph with its inspection panel", async () => {
    const fetchMock = mockFetch(defaultRoutes());
    renderAt("/");
    const ranked = await screen.findByRole("region", { name: "Ranked opportunities" });
    await userEvent.click(await within(ranked).findByRole("button", { name: /Test Channel A.*Test Channel C/ }));
    const readout = await screen.findByRole("complementary", { name: "Selected bridge" });
    expect((await within(readout).findAllByText("0.432")).length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(`/bridge/${A}/destinations/${C}`))).toBe(true);
  });

  it("states clearly when the snapshot has no research data", async () => {
    mockFetch(defaultRoutes({ status: status({ research_data: "missing", snapshots: [], latest_snapshot_id: null, snapshot_id: null, artifacts: [] }) }));
    renderAt("/");
    expect(await screen.findByText("No research data available for this snapshot.")).toBeInTheDocument();
  });

  it("shows the page title and live API status in the top bar", async () => {
    mockFetch(defaultRoutes());
    renderAt("/");
    const live = screen.getByRole("group", { name: "Live status" });
    expect(await within(live).findByText("Connected")).toBeInTheDocument();
    expect(await within(live).findByText("Available")).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: /Overview/ })).toHaveClass("active");
    expect(screen.getByRole("img", { name: "Growth Intelligence" })).toHaveAttribute("src", "/brand/logo-mark.png");
    expect(screen.getByLabelText("Search channels")).toHaveAttribute("list", "channel-search-options");
  });
});

describe("Graph Intelligence", () => {
  it("shows graph counts on a clickable graph map with details in a drawer", async () => {
    mockFetch(defaultRoutes());
    renderAt("/graph?node=ppr");
    const summary = await screen.findByRole("region", { name: "Graph summary" });
    expect(within(summary).getByText("12")).toBeInTheDocument();                         // commenter nodes
    const drawer = screen.getByRole("region", { name: "Personalized PageRank" });
    expect(within(drawer).getByText("3 / 3 sources converged")).toBeInTheDocument();
    expect(within(drawer).getByText("1e-10")).toBeInTheDocument();
    const map = screen.getByRole("group", { name: "Research graph map" });
    expect(within(map).getByRole("button", { name: /HGT: Not run/ })).toBeInTheDocument();
    await userEvent.click(within(map).getByRole("button", { name: /^Commenter: 12 nodes/ }));
    expect(await screen.findByLabelText(/Commenter degree distribution/)).toHaveAttribute("aria-label", expect.stringContaining("degree 1: 8"));
    await userEvent.click(within(map).getByRole("button", { name: /^Channel overlap/ }));
    expect((await screen.findAllByText("isolated")).length).toBeGreaterThan(0);
  });

  it("explains a missing graph instead of inventing one", async () => {
    mockFetch((url) => (url.pathname.endsWith("/graph/summary")
      ? { status: 404, body: { error: { code: "artifact_unavailable", message: "the heterogeneous graph (STEP 13) has not been built" } } }
      : defaultRoutes()(url)));
    renderAt("/graph");
    expect(await screen.findByText(/has not been built/)).toBeInTheDocument();
  });
});

describe("Topic Intelligence", () => {
  it("renders the similarity matrix with stored values and dashes where a profile is missing", async () => {
    mockFetch(defaultRoutes());
    renderAt(`/topics?channel=${A}`);
    const matrix = await screen.findByRole("table", { name: "Topic similarity between research channels" });
    expect(within(matrix).getAllByText("0.81").length).toBe(2);
    expect(within(matrix).getAllByText("—").length).toBeGreaterThan(2);
    expect(screen.getByRole("region", { name: "Most similar to Test Channel A" })).toBeInTheDocument();
  });

  it("explains an unavailable topic run", async () => {
    mockFetch((url) => (url.pathname.endsWith("/topics/similarity")
      ? { status: 404, body: { error: { code: "artifact_unavailable", message: "no topic similarity run (STEP 18) exists" } } }
      : defaultRoutes()(url)));
    renderAt("/topics");
    expect(await screen.findByText(/no topic similarity run/)).toBeInTheDocument();
  });
});

describe("Experiments", () => {
  it("lists stored runs and shows the recorded configuration of the selected run", async () => {
    mockFetch(defaultRoutes());
    renderAt("/experiments?run=ppr-eeeeeeeeeeee");
    const runs = await screen.findByRole("region", { name: "Research runs (3)" });
    expect(within(runs).getByText(EVID)).toBeInTheDocument();
    expect(await screen.findByText("1.00e-10")).toBeInTheDocument();
    expect(screen.getByText("not recorded by this step")).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: "Snapshots" })[0]).toHaveTextContent(SID);
  });
});

describe("Experiment explorer and snapshot comparison", () => {
  const twoSnapshots = () => status({ snapshots: [
    { snapshot_id: PREV_SID, created_at: "2025-12-01T00:00:00Z", extracted_at: "2025-12-01T00:00:00Z", channels: 3, videos: 5, comments: 30 },
    { snapshot_id: SID, created_at: "2026-01-01T00:00:00Z", extracted_at: "2026-01-01T00:00:00Z", channels: 3, videos: 6, comments: 40 },
  ] });

  it("opens configuration, artifacts, evaluation and results of the selected scoring experiment", async () => {
    mockFetch(defaultRoutes());
    renderAt(`/experiments?experiment=${EID}`);
    const detail = await screen.findByRole("region", { name: "Selected experiment" });
    expect(within(detail).getByRole("region", { name: "Configuration" })).toHaveTextContent("1.0-provisional (provisional)");
    expect(within(detail).getByRole("region", { name: "Artifacts" })).toHaveTextContent(XID);
    expect(within(detail).getByRole("region", { name: "Evaluation" })).toHaveTextContent(EVID);
    expect(await within(within(detail).getByRole("region", { name: "Results" })).findByText("0.710")).toBeInTheDocument();
  });

  it("compares compatible snapshots with signed changes of stored values", async () => {
    const fetchMock = mockFetch(defaultRoutes({ status: twoSnapshots() }));
    renderAt("/experiments");
    expect(await screen.findByText("Same method version and weights")).toBeInTheDocument();
    expect(screen.getAllByText("+0.100").length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls.some((c) => String(c[0]).includes(`base_snapshot_id=${PREV_SID}`))).toBe(true);
  });

  it("explains why an incompatible comparison is unavailable", async () => {
    mockFetch(defaultRoutes({ status: twoSnapshots(), compare: { ...compare, compatible: false, items: [], same_configuration: null,
      reason: "The snapshots cover different channel sets, so their rankings are not comparable." } }));
    renderAt("/experiments");
    expect(await screen.findByText("Snapshot comparison unavailable for this selection.")).toBeInTheDocument();
    expect(screen.getByText(/different channel sets/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Pair-level changes" })).not.toBeInTheDocument();
  });
});

describe("Channel Explorer", () => {
  it("adds bridge, topic and connectivity context for the selected channel", async () => {
    mockFetch(defaultRoutes());
    renderAt(`/channels?channel=${A}`);
    const profile = await screen.findByRole("region", { name: "Research profile" });
    expect(await within(profile).findByText("0.565")).toBeInTheDocument();
    expect(await within(profile).findByText("2")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Bridge position" })).toHaveTextContent("Test Channel C");
    expect(screen.getByRole("region", { name: "Channels sharing commenters" })).toBeInTheDocument();
  });
});

describe("Pipeline Graph", () => {
  it("shows each pipeline step with the status reported by the API and opens its recorded configuration", async () => {
    mockFetch(defaultRoutes());
    renderAt("/pipeline?step=ppr");
    const graph = await screen.findByRole("group", { name: "Component 3 research pipeline" });
    expect(within(graph).getByRole("button", { name: /Louvain baseline, STEP 20: Not run/ })).toBeInTheDocument();
    expect(await within(graph).findByRole("button", { name: /Audience Bridge Score, STEP 19 · confidence weighted: Stored · validated/ })).toBeInTheDocument();
    expect(await within(graph).findByRole("button", { name: /Personalized PageRank, STEP 17: Stored · validated/ })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("1.00e-10")).toBeInTheDocument();
  });
});

describe("Neural Models", () => {
  it("draws the HGT architecture from the run configuration and plots the recorded training history", async () => {
    mockFetch(defaultRoutes());
    renderAt("/neural");
    const summary = await screen.findByRole("region", { name: "Model summary" });
    expect(within(summary).getByText("2 × 2")).toBeInTheDocument();            // layers x heads from the config
    expect(within(summary).getByText("0.700")).toBeInTheDocument();            // final recorded ROC-AUC, not the best
    expect(screen.getByLabelText(/HGT on the research graph: .*features; type projection to .*; 2 layers with 2 attention heads/)).toBeInTheDocument();
    expect(screen.getByText(/Lowest validation loss: 0.950 at epoch 2/)).toBeInTheDocument();
    expect(screen.getByText(/Best ROC-AUC 0.720 at epoch 2/)).toBeInTheDocument();
    expect(screen.getByText("No metapath2vec run is stored for this snapshot.")).toBeInTheDocument();
    const filter = screen.getByRole("group", { name: "Highlight a node type" });
    const channelBtn = within(filter).getByRole("button", { name: /channel/ });
    await userEvent.click(channelBtn);
    expect(channelBtn).toHaveAttribute("aria-pressed", "true");
    expect(within(filter).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
  });
});
