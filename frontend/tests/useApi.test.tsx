import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useApi } from "../src/hooks/useApi";
import { ApiError } from "../src/services/apiClient";

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function Probe({ id, loaders }: { id: string; loaders: Record<string, Promise<string>> }) {
  const s = useApi(() => loaders[id], [id]);
  return <p data-testid="out">{s.status}:{s.status === "success" ? s.data : s.status === "error" ? s.error.code : ""}</p>;
}

describe("useApi", () => {
  it("never lets an older response overwrite a newer selection", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const loaders = { a: first.promise, b: second.promise };
    const { rerender } = render(<Probe id="a" loaders={loaders} />);
    rerender(<Probe id="b" loaders={loaders} />);
    await act(async () => second.resolve("result-b"));
    expect(screen.getByTestId("out")).toHaveTextContent("success:result-b");
    await act(async () => first.resolve("result-a")); // late, stale response
    expect(screen.getByTestId("out")).toHaveTextContent("success:result-b");
  });

  it("exposes errors instead of fallback data", async () => {
    const d = deferred<string>();
    render(<Probe id="a" loaders={{ a: d.promise }} />);
    expect(screen.getByTestId("out")).toHaveTextContent("loading:");
    await act(async () => d.reject(new ApiError("storage_unavailable", "x", 503)));
    expect(screen.getByTestId("out")).toHaveTextContent("error:storage_unavailable");
  });
});
