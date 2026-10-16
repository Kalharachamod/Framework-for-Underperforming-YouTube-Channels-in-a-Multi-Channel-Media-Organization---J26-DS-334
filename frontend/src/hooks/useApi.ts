import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../services/apiClient";

export type LoadState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: T | null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: ApiError };

/**
 * Fetch data for the current inputs. When inputs change, the previous request is cancelled and
 * its late result is ignored, so an old response can never overwrite a newer selection.
 * Pass `enabled = false` to wait (e.g. until a channel is selected). Errors are never replaced
 * by fallback data.
 */
export function useApi<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  enabled = true,
): LoadState<T> & { reload: () => void } {
  const [state, setState] = useState<LoadState<T>>({ status: "idle", data: null, error: null });
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", data: null, error: null });
      return undefined;
    }
    const id = ++requestId.current;
    const controller = new AbortController();
    setState({ status: "loading", data: null, error: null });
    loadRef
      .current(controller.signal)
      .then((data) => {
        if (id === requestId.current) setState({ status: "success", data, error: null });
      })
      .catch((err: unknown) => {
        if (id !== requestId.current) return; // stale: a newer request owns the state
        if (err instanceof ApiError && err.code === "aborted") return;
        const error = err instanceof ApiError ? err : new ApiError("http_error", "An unexpected error occurred.");
        setState({ status: "error", data: null, error });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}
