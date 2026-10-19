import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../src/routes/AppRoutes";
import { COMPONENT_TITLE } from "../src/features/component_2/researchData";

async function openMethodology() {
  render(<MemoryRouter initialEntries={["/component-2/methodology"]}><AppRoutes /></MemoryRouter>);
  await screen.findByRole("heading", { name: COMPONENT_TITLE });
}

describe("Component 2 Methodology Explorer", () => {
  it("loads as a separate offline route with its own active navigation", async () => {
    await openMethodology();
    expect(fetch).not.toHaveBeenCalled();
    const primary = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primary).getByRole("link", { name: "Methodology Explorer" })).toHaveAttribute("aria-current", "page");
    expect(within(primary).getByRole("link", { name: COMPONENT_TITLE })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Open the separate progress page" })).toHaveAttribute("href", "/component-2");
    expect(screen.getByText(/Proposed architecture/)).toBeVisible();
  });

  it("drills into connected methodology nodes and supports sequential navigation", async () => {
    await openMethodology();
    await userEvent.click(screen.getByRole("button", { name: "Open Jensen-Shannon Divergence" }));
    expect(screen.getByRole("heading", { name: "Jensen-Shannon Divergence", level: 3 })).toBeVisible();
    expect(screen.getByText(/implemented and unit-tested/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Next method" }));
    expect(screen.getByRole("heading", { name: "Topic-level directional interpretation", level: 3 })).toBeVisible();
  });

  it("compares demand models with their measured results", async () => {
    await openMethodology();
    await userEvent.click(screen.getByRole("tab", { name: /XLM-RoBERTa classification/ }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/Next comparison once more labelled positives/);
    await userEvent.click(screen.getByRole("tab", { name: /Multilingual sentence embeddings/ }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent("F1 0.54");
    await userEvent.click(screen.getByRole("tab", { name: /Rule-based screening/ }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent("27.78%");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("83.33%");
  });

  it("recalculates JSD and explains identical distributions safely", async () => {
    await openMethodology();
    await userEvent.click(screen.getByRole("button", { name: "Identical distributions" }));
    expect(screen.getAllByText("0.0000 bits")[0]).toBeVisible();
    expect(screen.getByText(/does not prove every request is satisfied/i)).toBeVisible();
    expect(screen.getAllByText("Balanced share")).toHaveLength(3);
  });

  it("reports invalid zero-sum demand instead of producing a fake score", async () => {
    await openMethodology();
    for (const topic of ["Physics", "Chemistry", "Mathematics"]) {
      const input = screen.getByRole("spinbutton", { name: `Demand ${topic}` });
      await userEvent.clear(input);
      await userEvent.type(input, "0");
    }
    expect(screen.getByText(/Demand must contain at least one positive value/)).toBeVisible();
  });

  it("steps through request evidence without presenting the illustration as a finding", async () => {
    await openMethodology();
    await userEvent.click(screen.getByRole("button", { name: /Coverage verification/ }));
    expect(screen.getByRole("heading", { name: "Coverage verification" })).toBeVisible();
    expect(screen.getByText(/Search for full performances/)).toBeVisible();
    expect(screen.getAllByText(/hypothetical/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Illustrative example")[0]).toBeVisible();
    expect(document.body).not.toHaveTextContent(/supervisor|macOS|cross-check/i);
  });
});
