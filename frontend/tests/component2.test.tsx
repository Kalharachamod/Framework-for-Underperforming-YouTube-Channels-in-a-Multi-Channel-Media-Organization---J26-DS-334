import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../src/routes/AppRoutes";
import { COMPONENT_TITLE, calibration } from "../src/features/component_2/researchData";
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
    expect(screen.getByRole("navigation", { name: "Component 2 sections" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: "Component 2 · Demand Mining" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("111 passing")).toBeVisible();
    expect(screen.getByText(/not classifier accuracy/)).toBeVisible();
  });

  it("opens diagnostic stages and explains confusion-matrix errors with the right denominators", async () => {
    await openPage();
    const stage = await openStage("Experiment 1 · 40-comment calibration");
    expect(stage).toHaveAttribute("open");
    for (const value of ["27.78%", "83.33%", "41.67%", "37.50%"]) expect(within(stage).getByText(value)).toBeVisible();
    await userEvent.click(within(stage).getByRole("button", { name: "False negative: 1" }));
    expect(within(stage).getByText(/^1 false negative:/)).toBeVisible();
    expect(within(stage).getByText(/not inter-annotator reliability/)).toBeVisible();
    expect(calibration.tp + calibration.fp + calibration.fn + calibration.tn).toBe(calibration.evaluated);
  });

  it("filters stages and expands and collapses the visible evidence", async () => {
    await openPage();
    await userEvent.selectOptions(screen.getByLabelText("Filter research stages"), "Pending");
    expect(screen.getByText("1 stage shown")).toBeVisible();
    expect(screen.queryByLabelText("Experiment 1 · 40-comment calibration")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Expand all stages" }));
    expect(screen.getByLabelText("Current limitations and next research stage")).toHaveAttribute("open");
    await userEvent.click(screen.getByRole("button", { name: "Collapse all stages" }));
    expect(screen.getByLabelText("Current limitations and next research stage")).not.toHaveAttribute("open");
  });

  it("switches partition units and preserves the unlabelled evaluation caveats", async () => {
    await openPage();
    const stage = await openStage("Experiment 2A.2 · Corrected video-grouped split");
    await userEvent.selectOptions(within(stage).getByLabelText("Partition measure"), "videos");
    expect(within(stage).getByText("255 videos · each video has exactly one role")).toBeVisible();
    expect(within(stage).getByText("43 videos")).toBeVisible();
    expect(within(stage).getByText(/86 also occur/)).toBeVisible();
    expect(within(stage).getByText(/Human-label fields are blank/)).toBeVisible();
  });

  it("demonstrates leakage without confusing the illustration with historical research", async () => {
    await openPage();
    const stage = await openStage("Experiment 2A.1 · Leakage investigation");
    expect(within(stage).getByText(/Illustrative teaching example/)).toBeVisible();
    expect(within(stage).getByText(/^Context crosses the boundary:/)).toBeVisible();
    await userEvent.click(within(stage).getByRole("button", { name: "Keep whole videos together" }));
    expect(within(stage).getByText(/^Video groups are disjoint:/)).toBeVisible();
    expect(within(stage).getByText(/does not resolve prior exposure/)).toBeVisible();
  });

  it("filters real examples and preserves UNCLEAR and illustrative provenance", async () => {
    await openPage();
    await userEvent.selectOptions(screen.getByLabelText("Example type"), "Ambiguous");
    const examples = screen.getByRole("region", { name: "Read the meaning beyond the keyword" });
    expect(within(examples).getByText("UNCLEAR")).toBeVisible();
    expect(within(examples).getByText("Candidate · CONTENT_CHANGE_PREFERENCE")).toBeVisible();
    expect(within(examples).queryByText("A specific re-upload request")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Example type"), "Non-demand reaction");
    expect(within(examples).getByText("Illustrative")).toBeVisible();
    expect(within(examples).getByText(/Not measured for this illustration/)).toBeVisible();
    expect(examples).not.toHaveTextContent(/Ugx|Ugy|Ugz|commenter:|anon_/);
  });

  it("changes methodology comparison and future-stage explanations without inventing outputs", async () => {
    await openPage();
    await userEvent.selectOptions(screen.getByLabelText("Compare methodology"), "4");
    expect(screen.getByText(/A single symmetric divergence value/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Jensen–Shannon Divergence/ }));
    expect(screen.getByText(/Quantify overall distribution mismatch; no research JSD value exists/)).toBeVisible();
    await openStage("Why are we not training XLM-R yet?");
    expect(screen.getByText(/There are only six actionable YES labels/)).toBeVisible();
  });

  it("navigates between the offline Component 2 view and the existing team workspace", async () => {
    mockFetch(defaultRoutes());
    await openPage();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    await userEvent.click(within(nav).getByRole("link", { name: /^Overview$/ }));
    await screen.findByLabelText("Snapshot");
    await userEvent.click(within(screen.getByRole("navigation", { name: "Primary" })).getByRole("link", { name: "Component 2 · Demand Mining" }));
    expect(await screen.findByRole("heading", { name: COMPONENT_TITLE })).toBeVisible();
  });
});
