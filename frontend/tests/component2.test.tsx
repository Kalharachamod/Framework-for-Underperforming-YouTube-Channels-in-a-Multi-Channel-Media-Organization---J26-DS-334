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
    const flow = screen.getByRole("region", { name: /How 84,002 comments become the gap chart/ });
    expect(within(flow).getByText("84,002")).toBeVisible();
    expect(within(flow).getByText("10,104")).toBeVisible();
    expect(within(flow).getByText("70,184")).toBeVisible();
    expect(within(flow).getByText("11,710")).toBeVisible();
    expect(within(flow).getByText("0.54")).toBeVisible();
    expect(within(flow).getByText("44,070")).toBeVisible();
    expect(within(flow).getByText("13,249")).toBeVisible();
    expect(within(flow).getByText("12,239")).toBeVisible();
    expect(within(flow).getByText(/these scores are not the accuracy on all comments/)).toBeVisible();
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
      expect(within(examples).getAllByRole("article")).toHaveLength(1);
    }
    await userEvent.selectOptions(select, "UNCLEAR");
    expect(within(examples).getByText("A comment that cannot be interpreted")).toBeVisible();
    expect(within(examples).queryByText("Request for the full performance")).not.toBeInTheDocument();
    await userEvent.selectOptions(select, "SPAM_OR_IRRELEVANT");
    expect(within(examples).getByText("Self-promotion phrased as a request")).toBeVisible();
    expect(examples).not.toHaveTextContent(/illustrative|Earn Rs/);
    await userEvent.selectOptions(select, "INFORMATION_NEED");
    expect(within(examples).getByText(/repeated information need points to real demand/)).toBeVisible();
    await userEvent.selectOptions(select, "all");
    expect(within(examples).getAllByRole("article")).toHaveLength(8);
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

  it("shows the Dream Star Season 2025 gap with a JSD scale and time-based validation", async () => {
    await openPage();
    const nav = screen.getByRole("navigation", { name: "Component 2 sections" });
    expect(within(nav).getByRole("link", { name: "Gap analysis" })).toHaveAttribute("href", "#c2-gap");
    expect(within(nav).getByRole("link", { name: "Validation" })).toHaveAttribute("href", "#c2-validation");
    const gap = screen.getByRole("region", { name: "Where audience attention and published content differ" });
    expect(within(gap).getByLabelText(/0 to 1 scale.*Season 2025: 0.155\./)).toBeInTheDocument();
    expect(within(gap).getByText(/Dream Star · Season 2025 \(Apr 2025 – Jan 2026\)/)).toBeVisible();
    expect(within(gap).queryByRole("group", { name: "Analysis period" })).not.toBeInTheDocument();
    expect(within(gap).getByLabelText(/Voting: audience interest 6.1%, published supply 0.4%, 13.6% of the JSD/)).toBeInTheDocument();
    expect(within(gap).getByLabelText(/Songs and lyrics: audience interest 4.6%, published supply 16%, 15.6% of the JSD/)).toBeInTheDocument();
    expect(within(gap).queryByText(/Largest attention gap/)).not.toBeInTheDocument();
    expect(within(gap).queryByText(/pp$/)).not.toBeInTheDocument();
    expect(within(gap).getByText("0.155", { selector: ".stat-card *, [class*=stat] *" })).toBeVisible();
    await userEvent.click(within(gap).getByRole("button", { name: "Show data table" }));
    expect(within(gap).getByRole("region", { name: "Season 2025 topic shares" })).toHaveTextContent("Songs and lyrics");
    await userEvent.click(within(gap).getByText("How these numbers were produced"));
    expect(within(gap).getByText(/890 of 967 videos fell into one topic/)).toBeVisible();
    expect(within(gap).getByText(/which is 15.6%/)).toBeVisible();
    await userEvent.click(within(gap).getByText("What the checks showed"));
    expect(within(gap).getByText(/Video placement is the weak step/)).toBeVisible();
    await userEvent.click(within(gap).getByText("Terms and methods compared"));
    expect(within(gap).getByRole("region", { name: "Methods compared" })).toHaveTextContent("HDBSCAN vs k-means");
    expect(within(gap).getByText(/request-vs-supply JSD is 0.140/)).toBeVisible();
    const validation = screen.getByRole("region", { name: "Usefulness over time: do highlighted gaps matter later?" });
    expect(within(validation).getByText("Attention rose towards the finals")).toBeVisible();
    expect(within(validation).getByText(/195 of 567 meaningful comments still discussed Season 12 contestants/)).toBeVisible();
    expect(within(validation).getAllByRole("listitem")).toHaveLength(3);
  });

  it("demo view shows only the demo sections and links back to the full view", async () => {
    await openPage("/component-2?view=demo");
    const nav = screen.getByRole("navigation", { name: "Component 2 sections" });
    expect(within(nav).getAllByRole("link").map((link) => link.textContent)).toEqual(["Gap and novelty", "Data flow", "Annotated examples", "Viewer requests", "Gap analysis", "Validation"]);
    const requests = screen.getByRole("region", { name: "What viewers asked for, and whether the channel can supply it" });
    expect(within(requests).getByLabelText("Upload missing songs and performances: 27 requests")).toBeInTheDocument();
    expect(within(requests).getAllByText("Channel can supply")).toHaveLength(4); // legend + three themes
    expect(within(requests).getByText(/85 comments labelled as actionable requests/)).toBeVisible();
    expect(screen.getByRole("region", { name: "Where audience attention and published content differ" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Usefulness over time: do highlighted gaps matter later?" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /How the methodology evolved/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Methodology questions and evidence-based answers" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: /How 84,002 comments become the gap chart/ })).toBeVisible();
    const why = screen.getByRole("region", { name: "What is missing, and what this component adds" });
    expect(within(why).getByText(/A script-normalised, demand-anchored divergence method/)).toBeVisible();
    expect(within(why).getByText("Unstudied population")).toBeVisible();
    expect(document.body).not.toHaveTextContent(/integrated demand-to-supply|Supply topic coherence/);
    await userEvent.click(screen.getByRole("link", { name: "Show full research view" }));
    expect(await screen.findByRole("region", { name: /How the methodology evolved/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Demo view/ })).toHaveAttribute("href", "/component-2?view=demo");
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
