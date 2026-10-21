import {
  config,
  fail,
  LIMITS,
  Stop,
  tokenEqual,
  validateConfig,
} from "./core.mjs";
const response = (status, code, extra = {}) =>
  new Response(JSON.stringify({ code, ...extra }), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
    },
  });
export async function boundedText(body, max, signal) {
  if (!body) return "";
  const reader = body.getReader();
  let size = 0;
  const parts = [];
  const abort = () => {
    reader.cancel().catch(() => {});
  };
  signal?.addEventListener("abort", abort, { once: true });
  try {
    while (true) {
      if (signal?.aborted) fail("REQUEST_TIMEOUT");
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > max) {
        await reader.cancel();
        fail("BODY_LIMIT");
      }
      parts.push(value);
    }
    if (signal?.aborted) fail("REQUEST_TIMEOUT");
  } finally {
    signal?.removeEventListener("abort", abort);
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let cursor = 0;
  for (const part of parts) {
    bytes.set(part, cursor);
    cursor += part.length;
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    fail("MALFORMED_RESPONSE");
  }
}
export function createHandler(
  { get, openStore, createTransport, collect, now = Date.now },
) {
  return async (request) => {
    let store;
    try {
      const c = config(get);
      const auth = request.headers.get("authorization") || "";
      // Never load the driver, open SQL or instantiate transport before auth.
      if (
        c.token.length < 32 || c.token.length > 512 || auth.length > 520 ||
        !auth.startsWith("Bearer ") || !await tokenEqual(auth.slice(7), c.token)
      ) return response(401, "UNAUTHORIZED");
      if (request.method !== "POST") return response(405, "METHOD");
      if (!c.active) return response(503, "DISABLED");
      validateConfig(c);
      const type = request.headers.get("content-type")?.split(";")[0];
      if (type !== "application/json") return response(400, "REQUEST");
      const deadline = now() + LIMITS.handlerMs;
      // A streaming body must not hold an authenticated worker indefinitely.
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      let raw;
      try {
        raw = await boundedText(
          request.body,
          LIMITS.requestBytes,
          controller.signal,
        );
      } finally {
        clearTimeout(timeout);
      }
      let body;
      try {
        body = JSON.parse(raw);
      } catch {
        return response(400, "REQUEST");
      }
      if (
        !body || Array.isArray(body) || Object.keys(body).length !== 1 ||
        !["daily-start", "continuation"].includes(body.action)
      ) return response(400, "REQUEST");
      store = await openStore(c);
      const result = await collect({
        store,
        transport: createTransport(c),
        config: c,
        action: body.action,
        deadline,
        now,
      });
      return response(200, "PROCESSED", result);
    } catch (error) {
      const code = error instanceof Stop ? error.code : "INTERNAL";
      return response(code === "BODY_LIMIT" ? 413 : 503, code);
    } finally {
      if (store) {
        try {
          await store.close();
        } catch { /* never expose driver errors */ }
      }
    }
  };
}
