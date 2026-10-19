export interface JsdTopicResult {
  demand: number;
  supply: number;
  midpoint: number;
  signedDifference: number;
  demandContribution: number;
  supplyContribution: number;
  jsdContribution: number;
}

export interface JsdResult {
  demand: number[];
  supply: number[];
  midpoint: number[];
  klDemandToMidpoint: number;
  klSupplyToMidpoint: number;
  divergence: number;
  topics: JsdTopicResult[];
}

function validate(values: number[], label: string) {
  if (values.length === 0) throw new Error(`${label} must contain at least one value.`);
  if (values.some((value) => !Number.isFinite(value) || value < 0)) {
    throw new Error(`${label} values must be finite and non-negative.`);
  }
  if (values.reduce((sum, value) => sum + value, 0) <= 0) {
    throw new Error(`${label} must contain at least one positive value.`);
  }
}

export function normalizeDistribution(values: number[], label = "Distribution") {
  validate(values, label);
  const total = values.reduce((sum, value) => sum + value, 0);
  return values.map((value) => value / total);
}

function klTerm(p: number, q: number) {
  if (p === 0) return 0;
  if (q === 0) return Number.POSITIVE_INFINITY;
  return p * Math.log2(p / q);
}

export function calculateJsd(demandValues: number[], supplyValues: number[]): JsdResult {
  if (demandValues.length !== supplyValues.length) {
    throw new Error("Demand and supply must use the same aligned topics.");
  }
  const demand = normalizeDistribution(demandValues, "Demand");
  const supply = normalizeDistribution(supplyValues, "Supply");
  const midpoint = demand.map((value, index) => (value + supply[index]) / 2);
  const topics = demand.map((value, index) => {
    const demandContribution = klTerm(value, midpoint[index]);
    const supplyContribution = klTerm(supply[index], midpoint[index]);
    return {
      demand: value,
      supply: supply[index],
      midpoint: midpoint[index],
      signedDifference: value - supply[index],
      demandContribution,
      supplyContribution,
      jsdContribution: (demandContribution + supplyContribution) / 2,
    };
  });
  const klDemandToMidpoint = topics.reduce((sum, topic) => sum + topic.demandContribution, 0);
  const klSupplyToMidpoint = topics.reduce((sum, topic) => sum + topic.supplyContribution, 0);
  return {
    demand,
    supply,
    midpoint,
    klDemandToMidpoint,
    klSupplyToMidpoint,
    divergence: (klDemandToMidpoint + klSupplyToMidpoint) / 2,
    topics,
  };
}
