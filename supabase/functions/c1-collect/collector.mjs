import { hash, LIMITS, Stop } from "./core.mjs";
// Each store method is its own short transaction. Transport is always outside it.
export async function collect(
  {
    store,
    transport,
    config,
    action,
    deadline,
    now = Date.now,
    random = Math.random,
  },
) {
  const claim = await store.claim(config, action);
  if (!claim.lease) return { state: claim.state };
  const lease = claim.lease;
  let attempts = 0, steps = 0;
  const commit = async (id) => {
    try {
      await store.commit(lease, id);
    } catch (error) {
      if (
        !(error instanceof Stop) ||
        ![
          "INVALID_METRIC",
          "INVALID_ID",
          "INVALID_TIME",
          "INVALID_DURATION",
          "MALFORMED_RESPONSE",
          "UNREQUESTED_RESPONSE",
          "OWNERSHIP",
          "REPLAY_CONFLICT",
          "STAGING_HASH",
          "INVENTORY_MISSING",
        ].includes(error.code)
      ) throw error;
      await store.rejectStaged(lease, id, error.code);
    }
  };
  try {
    while (
      attempts < LIMITS.attempts && steps++ < 12 &&
      deadline - now() >= LIMITS.marginMs
    ) {
      const work = await store.next(lease);
      if (!work) break;
      if (work.staged_response) {
        await commit(work.work_id);
        continue;
      }
      const ready = await store.reserve(lease, work.work_id);
      if (!ready) continue;
      attempts++;
      let payload;
      try {
        payload = await transport.request(ready);
      } catch (error) {
        const code = error instanceof Stop ? error.code : "TRANSPORT";
        await store.failed(lease, ready.work_id, {
          code,
          retry: error.retry === true,
          delayMs: Math.min(8000, 1000 * 2 ** Math.max(0, ready.attempts - 1)) +
            Math.floor(random() * 500),
        });
        if (["API_AUTH", "QUOTA"].includes(code)) break;
        continue;
      }
      // Successful response completion, never schedule time; persist once.
      const observed = new Date(now()).toISOString();
      await store.stage(
        lease,
        ready.work_id,
        payload,
        observed,
        await hash(payload),
      );
      await commit(ready.work_id);
    }
    return await store.report(lease);
  } finally {
    await store.release(lease);
  }
}
