import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { resetInFlightRequests } from "../src/services/apiClient";

// No test may reach a real backend: any request that a test did not mock is refused.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => {
    throw new TypeError("network disabled in tests (mock fetch in the test)");
  }));
});

afterEach(() => {
  cleanup();
  resetInFlightRequests();
  vi.unstubAllGlobals();
});
