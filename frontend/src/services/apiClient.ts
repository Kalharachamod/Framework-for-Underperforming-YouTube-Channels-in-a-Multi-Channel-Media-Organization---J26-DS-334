/**
 * Central HTTP client for the backend API.
 *
 * - Base URL from VITE_API_URL (no secrets are ever read from the frontend environment).
 * - GET only; identical in-flight requests are shared (no duplicate calls).
 * - Every failure becomes an ApiError; failed requests are never replaced by fallback data.
 * - Responses are checked for the expected shape and refused if they contain commenter
 *   identifiers (defence in depth; the backend never sends them).
 */

export const API_BASE_URL: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export type ApiErrorCode =
  | "not_found"
  | "artifact_unavailable"
  | "invalid_parameter"
  | "storage_unavailable"
  | "timeout"
  | "internal_error"
  | "network_error"
  | "invalid_response"
  | "aborted"
  | "http_error";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number | null;

  constructor(code: ApiErrorCode, message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export type Params = Record<string, string | number | boolean | null | undefined>;
export type Validator<T> = (data: unknown) => data is T;

const KNOWN_CODES = new Set<ApiErrorCode>([
  "not_found",
  "artifact_unavailable",
  "invalid_parameter",
  "storage_unavailable",
  "timeout",
  "internal_error",
]);
const IDENTIFIER_PATTERN = /anon_[0-9a-f]{8,}|commenter:/;
const inFlight = new Map<string, Promise<unknown>>();

export function buildUrl(path: string, params: Params = {}, base: string = API_BASE_URL): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return `${base}${path}${qs ? `?${qs}` : ""}`;
}

async function fetchJson(url: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("network_error", "The research API could not be reached. Is the backend running?");
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new ApiError("invalid_response", "The API returned a response that is not valid JSON.", response.status);
    }
  }
  if (!response.ok) {
    const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
    const code = err?.code && KNOWN_CODES.has(err.code as ApiErrorCode) ? (err.code as ApiErrorCode) : "http_error";
    throw new ApiError(code, err?.message ?? `The API answered with HTTP ${response.status}.`, response.status);
  }
  if (body === null) throw new ApiError("invalid_response", "The API returned an empty response.", response.status);
  if (IDENTIFIER_PATTERN.test(text)) {
    throw new ApiError("invalid_response", "The response was refused because it contained commenter identifiers.");
  }
  return body;
}

/** GET a JSON resource. Identical concurrent requests share one fetch; `signal` only detaches this caller. */
export async function getJson<T>(path: string, params: Params, validate: Validator<T>, signal?: AbortSignal): Promise<T> {
  const url = buildUrl(path, params);
  let shared = inFlight.get(url);
  if (!shared) {
    shared = fetchJson(url).finally(() => inFlight.delete(url));
    inFlight.set(url, shared);
  }
  const data = await abortable(shared, signal);
  if (!validate(data)) throw new ApiError("invalid_response", "The API response did not have the expected structure.");
  return data;
}

function abortable<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise;
  if (signal.aborted) return Promise.reject(new ApiError("aborted", "Request cancelled."));
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(new ApiError("aborted", "Request cancelled."));
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(
      (v) => {
        signal.removeEventListener("abort", onAbort);
        resolve(v);
      },
      (e) => {
        signal.removeEventListener("abort", onAbort);
        reject(e);
      },
    );
  });
}

/** Shape check helper: an object with the given keys (values may be null). */
export function hasKeys(data: unknown, keys: string[]): data is Record<string, unknown> {
  return typeof data === "object" && data !== null && !Array.isArray(data) && keys.every((k) => k in data);
}

export function isList(value: unknown): value is unknown[] {
  return Array.isArray(value);
}

/** Message suitable for display (never a stack trace). */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "An unexpected error occurred.";
}
