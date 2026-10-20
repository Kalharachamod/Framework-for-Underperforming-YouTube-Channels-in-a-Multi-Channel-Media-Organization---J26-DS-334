import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../src/routes/AppRoutes";
import { COMPONENT_TITLE, calibration, taxonomy } from "../src/features/component_2/researchData";
import { defaultRoutes, mockFetch } from "./fixtures";

async function openPage(path = "/component-2") {
  render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);
  await screen.findByRole("heading", { name: COMPONENT_TITLE });
}

async function openStage(title: string) {
  const stage = screen.getByLabelText(title);
  await userEvent.click(stage.querySelector("summary")!);
  return stage;
}

describe("Component 2 research evidence", () => {
  it("loads the deep link and shared navigation without making any API requests", async () => {
    await openPage("/component-2/");
    expect(fetch).not.toHaveBeenCalled();
    const sectionNav = screen.getByRole("navigation", { name: "Component 2 sections" });
    expect(sectionNav).toBeInTheDocument();
    expect(within(sectionNav).getByRole("link", { name: "Annotated examples" })).toHaveAttribute("href", "#c2-examples");
    expect(within(sectionNav).getByRole("link", { name: "Research Q&A" })).toHaveAttribute("href", "#c2-questions");
    expect(sectionNav).not.toHaveTextContent(/viva/i);
    expect(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: COMPONENT_TITLE })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Open Methodology Explorer/ })).toHaveAttribute("href", "/component-2/methodology");
    expect(screen.getByText("84,002")).toBeVisible();
    expect(screen.getByText("0.54")).toBeVisible();
    expect(document.body).not.toHaveTextContent(/supervisor|ethics|macOS|awaiting validation/i);
  });

  it("opens diagnostic stages and explains confusion-matrix errors with the right denominators", async () => {
    await openPage();
    const stage = await openStage("Experiment 1 · 40-comment calibration");
    expect(stage).toHaveAttribute("open");
    for (const value of ["27.78%", "83.33%", "41.67%", "37.50%"]) expect(within(stage).getByText(value)).toBeVisible();
    await userEvent.click(within(stage).getByRole("button", { name: "False negative: 1" }));
    expect(within(stage).getByText(/^1 false negative:/)).toBeVisible();
    expect(within(stage).getByText(/chosen to expose the strengths and errors/)).toBeVisible();
    expect(calibration.tp + calibration.fp + calibration.fn + calibration.tn).toBe(calibration.evaluated);
  });

  it("filters stages and expands and collapses the visible evidence", async () => {
    await openPage();
    await userEvent.selectOptions(screen.getByLabelText("Filter research stages"), "In progress");
    expect(screen.getByText("1 stage shown")).toBeVisible();
    expect(screen.queryByLabelText("Experiment 1 · 40-comment calibration")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Expand all stages" }));
    expect(screen.getByLabelText("Next stage · Demand topics and divergence")).toHaveAttribute("open");
    await userEvent.click(screen.getByRole("button", { name: "Collapse all stages" }));
    expect(screen.getByLabelText("Next stage · Demand topics and divergence")).not.toHaveAttribute("open");
  });

  it("switches partition units and describes the held-out and queue roles", async () => {
    await openPage();
    const stage = await openStage("Experiment 2A.2 · Corrected video-grouped split");
    await userEvent.selectOptions(within(stage).getByLabelText("Partition measure"), "videos");
    expect(within(stage).getByText("255 videos · each video has exactly one role")).toBeVisible();
    expect(within(stage).getByText("43 videos")).toBeVisible();
    expect(within(stage).getByText(/Frozen final-evaluation set/)).toBeVisible();
    expect(within(stage).getByText(/labelled in annotation batch 1/)).toBeVisible();
  });

  it("demonstrates leakage without confusing the illustration with historical research", async () => {
    await openPage();
    const stage = await openStage("Experiment 2A.1 · Leakage investigation");
    expect(within(stage).getByText(/Illustrative teaching example/)).toBeVisible();
    expect(within(stage).getByText(/^Context crosses the boundary:/)).toBeVisible();
    await userEvent.click(within(stage).getByRole("button", { name: "Keep whole videos together" }));
    expect(within(stage).getByText(/^Video groups are disjoint:/)).toBeVisible();
    expect(within(stage).getByText(/keeps evaluation independent/)).toBeVisible();
  });

  it("filters examples by exactly the eight audience signals", async () => {
    await openPage();
    const select = screen.getByLabelText("Audience signal") as HTMLSelectElement;
    const values = Array.from(select.options).map((option) => option.value);
    expect(values).toEqual(["all", ...taxonomy.map(([code]) => code)]);
    expect(select).not.toHaveTextContent(/False positive|False negative|Ambiguous/);
    const examples = screen.getByRole("region", { name: "Annotated examples for each of the eight audience signals" });
    for (const [code] of taxonomy) {
      await userEvent.selectOptions(select, code);
      expect(within(examples).getAllByRole("article").length).toBeGreaterThan(0);
    }
    await userEvent.selectOptions(select, "UNCLEAR");
    expect(within(examples).getByText("An ambiguous short question")).toBeVisible();
    expect(within(examples).queryByText("A specific re-upload request")).not.toBeInTheDocument();
    await userEvent.selectOptions(select, "SPAM_OR_IRRELEVANT");
    expect(within(examples).getByText(/illustrative example/)).toBeVisible();
    expect(examples).not.toHaveTextContent(/Ugx|Ugy|Ugz|commenter:|anon_/);
  });

  it("changes methodology comparison and pipeline explanations", async () => {
    await openPage();
    await userEvent.selectOptions(screen.getByLabelText("Compare methodology"), "4");
    expect(screen.getByText(/A single symmetric divergence value/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Jensen–Shannon Divergence/ }));
    expect(screen.getByText(/Overall demand–supply mismatch per channel and season/)).toBeVisible();
    await openStage("How well do the classifiers work?");
    expect(screen.getByText(/e5 embeddings \+ logistic regression reach F1 0.54/)).toBeVisible();
  });

  it("shows the Dream Star gap with a JSD scale, season switch and validation example", async () => {
    await openPage();
    const nav = screen.getByRole("navigation", { name: "Component 2 sections" });
    expect(within(nav).getByRole("link", { name: "Gap analysis" })).toHaveAttribute("href", "#c2-gap");
    expect(within(nav).getByRole("link", { name: "Validation" })).toHaveAttribute("href", "#c2-validation");
    const gap = screen.getByRole("region", { name: "Where audience attention and published content differ" });
    expect(within(gap).getByLabelText(/0 to 1 scale.*Season 2025: 0.155.*New season 2026: 0.426/)).toBeInTheDocument();
    expect(within(gap).getByLabelText(/Voting: audience interest 6.1%, published supply 0.4%, gap \+5.7 pp/)).toBeInTheDocument();
    await userEvent.click(within(gap).getByRole("button", { name: /New season 2026/ }));
    expect(within(gap).getByRole("button", { name: /New season 2026/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(gap).getByText("0.426", { selector: ".stat-card *, [class*=stat] *" })).toBeVisible();
    await userEvent.click(within(gap).getByRole("button", { name: "Show data table" }));
    expect(within(gap).getByRole("table")).toHaveTextContent("Voice and group songs");
    const validation = screen.getByRole("region", { name: "Usefulness over time: do highlighted gaps matter later?" });
    expect(within(validation).getByText("Still uncovered · gap widened")).toBeVisible();
    expect(within(validation).getAllByRole("listitem")).toHaveLength(3);
  });

  it("navigates between the offline Component 2 view and the existing team workspace", async () => {
    mockFetch(defaultRoutes());
    await openPage();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    await userEvent.click(within(nav).getByRole("link", { name: /^Overview$/ }));
    await screen.findByLabelText("Snapshot");
    await userEvent.click(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: COMPONENT_TITLE }));
    expect(await screen.findByRole("heading", { name: COMPONENT_TITLE })).toBeVisible();
  });
});
