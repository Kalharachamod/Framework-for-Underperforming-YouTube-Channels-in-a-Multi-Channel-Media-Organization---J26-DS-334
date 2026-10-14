import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, buildUrl, getJson, hasKeys } from "../src/services/apiClient";
import { component3Api } from "../src/features/component_3/api";
import { mockFetch } from "./fixtures";

const anyObject = (d: unknown): d is Record<string, unknown> => hasKeys(d, []);

afterEach(() => vi.unstubAllGlobals());

describe("apiClient", () => {
  it("builds urls without empty parameters", () => {
    expect(buildUrl("/x", { a: 1, b: null, c: undefined, d: "", e: false }, "http://api")).toBe("http://api/x?a=1&e=false");
  });

  it("returns validated data on success", async () => {
    mockFetch(() => ({ body: { status: "ok", version: "1" } }));
    await expect(getJson("/health", {}, anyObject)).resolves.toEqual({ status: "ok", version: "1" });
  });

  it("maps backend error bodies to ApiError codes", async () => {
    mockFetch(() => ({ status: 404, body: { error: { code: "artifact_unavailable", message: "no evaluation yet" } } }));
    const err = await getJson("/x1", {}, anyObject).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("artifact_unavailable");
    expect(err.status).toBe(404);
    expect(err.message).toBe("no evaluation yet");
  });

  it("reports network failures without fallback data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await getJson("/x2", {}, anyObject).catch((e) => e);
    expect(err.code).toBe("network_error");
  });

  it("rejects invalid JSON, empty bodies and unexpected shapes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 200 })));
    expect((await getJson("/x3", {}, anyObject).catch((e) => e)).code).toBe("invalid_response");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 200 })));
    expect((await getJson("/x4", {}, anyObject).catch((e) => e)).code).toBe("invalid_response");
    mockFetch(() => ({ body: { unexpected: true } }));
    expect((await component3Api.channels({}).catch((e) => e)).code).toBe("invalid_response");
  });

  it("refuses responses containing commenter identifiers", async () => {
    mockFetch(() => ({ body: { channel_name: "anon_" + "a".repeat(64) } }));
    const err = await getJson("/x5", {}, anyObject).catch((e) => e);
    expect(err.code).toBe("invalid_response");
    expect(err.message).toMatch(/commenter identifiers/);
  });

  it("shares identical in-flight requests and supports cancellation", async () => {
    const fn = mockFetch(() => ({ body: { status: "ok" } }));
    const [a, b] = await Promise.all([getJson("/same", {}, anyObject), getJson("/same", {}, anyObject)]);
    expect(a).toEqual(b);
    expect(fn).toHaveBeenCalledTimes(1);
    const controller = new AbortController();
    const pending = getJson("/slow", {}, anyObject, controller.signal);
    controller.abort();
    expect((await pending.catch((e) => e)).code).toBe("aborted");
  });

  it("uses the documented endpoint paths and parameters", async () => {
    const fn = mockFetch(() => ({ body: { items: [], total: 0, experiment_id: "e", snapshot_id: "s" } }));
    await component3Api.ranking("UC_x", { snapshotId: "rs-1", experimentId: "abs-1" }, 10, 20, true);
    const url = new URL(String(fn.mock.calls[0][0]));
    expect(url.pathname).toBe("/api/v1/component-3/bridge/UC_x/destinations");
    expect(Object.fromEntries(url.searchParams)).toEqual({ snapshot_id: "rs-1", experiment_id: "abs-1", limit: "10", offset: "20", include_unscored: "true" });
  });
});
