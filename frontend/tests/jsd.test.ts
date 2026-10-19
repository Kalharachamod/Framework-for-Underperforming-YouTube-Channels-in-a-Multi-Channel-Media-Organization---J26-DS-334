import { describe, expect, it } from "vitest";
import { calculateJsd, normalizeDistribution } from "../src/features/component_2/jsd";

describe("Jensen-Shannon divergence", () => {
  it("returns zero for identical distributions", () => {
    expect(calculateJsd([50, 30, 20], [50, 30, 20]).divergence).toBeCloseTo(0, 12);
  });

  it("returns one bit for disjoint support", () => {
    expect(calculateJsd([1, 0], [0, 1]).divergence).toBeCloseTo(1, 12);
  });

  it("is symmetric", () => {
    const forward = calculateJsd([50, 30, 20], [10, 70, 20]).divergence;
    const reverse = calculateJsd([10, 70, 20], [50, 30, 20]).divergence;
    expect(forward).toBeCloseTo(reverse, 12);
  });

  it("handles observed zero-probability categories without infinity", () => {
    const result = calculateJsd([0, 2, 3], [4, 0, 1]);
    expect(Number.isFinite(result.divergence)).toBe(true);
    expect(result.divergence).toBeGreaterThan(0);
  });

  it("makes per-topic contributions sum to global JSD", () => {
    const result = calculateJsd([50, 30, 20], [10, 70, 20]);
    const contributionTotal = result.topics.reduce((sum, topic) => sum + topic.jsdContribution, 0);
    expect(contributionTotal).toBeCloseTo(result.divergence, 12);
    expect(result.topics[0].signedDifference).toBeCloseTo(0.4, 12);
    expect(result.topics[1].signedDifference).toBeCloseTo(-0.4, 12);
    expect(result.topics[2].signedDifference).toBeCloseTo(0, 12);
  });

  it("normalizes arbitrary non-negative weights", () => {
    expect(normalizeDistribution([5, 3, 2])).toEqual([0.5, 0.3, 0.2]);
  });

  it("rejects invalid or zero-sum inputs", () => {
    expect(() => calculateJsd([0, 0], [1, 1])).toThrow(/Demand/);
    expect(() => calculateJsd([1, -1], [1, 1])).toThrow(/non-negative/);
    expect(() => calculateJsd([1, 2], [1])).toThrow(/same aligned topics/);
  });
});
