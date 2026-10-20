import {
  canonical,
  chunks,
  discoveryOrder,
  fail,
  gate,
  hash,
  LIMITS,
  normalize,
  REFRESH,
  refreshDue,
  replayCheck,
  reservation,
  schedule,
} from "./core.mjs";

const iso = (v) => v ? new Date(v).toISOString() : null;

// db: { transaction(async query => value), close() }; query(text, parameters).
// Only static SQL identifiers; all values are protocol parameters.
export class PostgresStore {
  constructor(
    db,
    config,
    {
      uuid = () => crypto.randomUUID(),
      active = () => config.active,
      scheduleClock = () => Date.now(),
    } = {},
  ) {
    this.db = db;
    this.config = config;
    this.uuid = uuid;
    this.active = active;
    this.scheduleClock = scheduleClock;
  }
  close() {
    return this.db.close();
  }
  async transaction(body) {
    return this.db.transaction(async (q) => {
      await q("SET LOCAL timezone = 'UTC'");
      await q("SET LOCAL statement_timeout = '5s'");
      await q("SET LOCAL lock_timeout = '1s'");
      await q("SET LOCAL idle_in_transaction_session_timeout = '10s'");
      const [identity] = await q("SELECT session_user, current_user");
      if (
        identity.session_user !== "c1_collector" ||
        identity.current_user !== "c1_collector"
      ) fail("DATABASE_IDENTITY");
      const [cohort] = await q(
        "SELECT * FROM c1.cohorts WHERE cohort_id=$1 AND version=$2",
        [this.config.cohort, this.config.version],
      );
      gate({ ...this.config, active: this.active() }, cohort);
      return body(q, cohort);
    });
  }
  async coordination(q) {
    const [coord] = await q(
      `SELECT *, clock_timestamp() AS db_now FROM c1.collection_coordination
      WHERE cohort_id=$1 AND version=$2 FOR UPDATE`,
      [this.config.cohort, this.config.version],
    );
    if (!coord) fail("COORDINATION_MISSING");
    return coord;
  }
  async fenced(q, lease) {
    const coord = await this.coordination(q);
    if (
      coord.active_run_id !== lease.run || coord.lease_owner !== lease.owner ||
      String(coord.fence) !== lease.fence ||
      !coord.lease_expires_at ||
      Date.parse(coord.lease_expires_at) <= Date.parse(coord.db_now)
    ) fail("LEASE_LOST");
    const [run] = await q("SELECT * FROM c1.collection_runs WHERE run_id=$1", [
      lease.run,
    ]);
    if (!run || !["pending", "running"].includes(run.status)) {
      fail("RUN_CLOSED");
    }
    return { coord, run };
  }
  async insertWork(
    q,
    run,
    {
      key,
      phase,
      ids = [],
      channel = null,
      cursor = null,
      order = 0,
      page = 0,
      seen = [],
    },
  ) {
    await q(
      `INSERT INTO c1.collection_work
      (work_id,run_id,cohort_id,version,work_key,phase,selected_ids,channel_id,input_cursor,dispatch_order,page_count,seen_tokens)
      VALUES ($1,$2,$3,$4,$5,$6,$7::text[],$8,$9,$10,$11,$12::text[]) ON CONFLICT (run_id,work_key) DO NOTHING`,
      [
        this.uuid(),
        run.run_id,
        run.cohort_id,
        run.version,
        key,
        phase,
        ids,
        channel,
        cursor,
        order,
        page,
        seen,
      ],
    );
  }
  async claim(config, action) {
    return this.transaction(async (q, cohort) => {
      const coord = await this.coordination(q);
      // Scheduling is internally injectable for deterministic tests only.
      // Lease expiry, fencing, and mutations remain database-time authoritative.
      const window = schedule(this.scheduleClock());
      const now = Date.parse(coord.db_now);
      let run;
      if (coord.active_run_id) {
        [run] = await q("SELECT * FROM c1.collection_runs WHERE run_id=$1", [
          coord.active_run_id,
        ]);
      }
      if (run && ["pending", "running"].includes(run.status)) {
        if (
          coord.lease_expires_at && Date.parse(coord.lease_expires_at) > now
        ) return { state: "busy" };
        if (Date.parse(run.deadline_at) <= now) {
          await q(
            `UPDATE c1.collection_runs SET status='partial',ended_at=clock_timestamp(),failure_code='WINDOW_EXPIRED'
            WHERE run_id=$1`,
            [run.run_id],
          );
          await q(
            `UPDATE c1.collection_coordination SET lease_owner=NULL,lease_expires_at=NULL WHERE cohort_id=$1 AND version=$2`,
            [config.cohort, config.version],
          );
          return { state: "expired_partial" };
        }
        if (
          run.scheduled_for.toISOString?.() !== window.start &&
          new Date(run.scheduled_for).toISOString() !== window.start
        ) return { state: "previous_run_blocked" };
      } else {
        if (action !== "daily-start" || !window.inWindow) {
          return { state: "no_active_run" };
        }
        const [existing] = await q(
          "SELECT run_id FROM c1.collection_runs WHERE cohort_id=$1 AND version=$2 AND scheduled_for=$3",
          [config.cohort, config.version, window.start],
        );
        if (existing) return { state: "already_finished" };
        const channels = await q(
          "SELECT channel_id FROM c1.cohort_channels WHERE cohort_id=$1 AND version=$2 ORDER BY channel_id",
          [config.cohort, config.version],
        );
        if (
          canonical(channels.map((x) => x.channel_id).sort()) !==
            canonical([...cohort.channel_ids].sort())
        ) fail("INVENTORY_CHANNELS");
        // The first run fixes the admission cutoff; the column is set-once.
        await q(
          `UPDATE c1.collection_coordination
          SET admission_published_after=$1::timestamptz - make_interval(days => $2::integer)
          WHERE cohort_id=$3 AND version=$4 AND admission_published_after IS NULL`,
          [
            window.start,
            cohort.admission_lookback_days,
            config.cohort,
            config.version,
          ],
        );
        // Refresh only videos due today: daily to day 30, weekly to day 365, plus
        // catch-up when the last observation is older than a week. Bounded.
        const due = await q(
          `SELECT video_id,published_at,metadata_observed_at FROM (
            SELECT v.video_id,v.published_at,v.metadata_observed_at,
              floor(extract(epoch FROM ($4::timestamptz - v.published_at)) / 86400) AS age_days
            FROM c1.videos v JOIN c1.cohort_channels m ON m.channel_id=v.channel_id
            WHERE m.cohort_id=$1 AND m.version=$2 AND v.inventory_revision <= $3
          ) d
          WHERE published_at IS NULL OR age_days <= $5 OR (age_days <= $6 AND (
            mod(age_days::bigint, $7) = 0 OR metadata_observed_at IS NULL OR
            metadata_observed_at < $4::timestamptz - make_interval(days => $7::integer)))
          ORDER BY video_id LIMIT $8`,
          [
            config.cohort,
            config.version,
            String(coord.inventory_revision),
            window.start,
            REFRESH.dailyDays,
            REFRESH.weeklyDays,
            REFRESH.weekDays,
            LIMITS.maxInventory + 1,
          ],
        );
        if (due.length > LIMITS.maxInventory) fail("INVENTORY_TOO_LARGE");
        const batches = chunks(
          due.filter((v) => refreshDue(v, window.start)).map((x) => x.video_id),
        );
        if (
          batches.length + chunks(cohort.channel_ids).length +
              cohort.candidate_attempt_reserve > cohort.total_attempt_budget
        ) fail("INITIAL_BUDGET");
        [run] = await q(
          `INSERT INTO c1.collection_runs
          (run_id,cohort_id,version,manifest_hash,scheduled_for,collection_date,inventory_revision,inventory_cutoff,started_at,deadline_at,phase,status,summary)
          VALUES ($1,$2,$3,$4,$5,$6,$7,clock_timestamp(),clock_timestamp(),$8,'refresh','running',$9::jsonb) RETURNING *`,
          [
            this.uuid(),
            config.cohort,
            config.version,
            config.manifest,
            window.start,
            window.date,
            String(coord.inventory_revision),
            window.end,
            JSON.stringify({
              discoverySeeded: false,
              candidatesSeeded: false,
              candidates_complete: false,
              rotation: coord.discovery_start_offset,
            }),
          ],
        );
        for (let i = 0; i < batches.length; i++) {
          await this.insertWork(q, run, {
            key: `refresh:${i}`,
            phase: "refresh",
            ids: batches[i],
            order: i,
          });
        }
        const channelBatches = chunks([...cohort.channel_ids].sort());
        for (let i = 0; i < channelBatches.length; i++) {
          await this.insertWork(q, run, {
            key: `channels:${i}`,
            phase: "channels",
            ids: channelBatches[i],
            order: i,
          });
        }
      }
      if (!window.inWindow) return { state: "outside_window" };
      const owner = this.uuid();
      const [updated] = await q(
        `UPDATE c1.collection_coordination SET active_run_id=$1,lease_owner=$2,
        lease_expires_at=clock_timestamp()+interval '75 seconds',fence=fence+1
        WHERE cohort_id=$3 AND version=$4 RETURNING fence`,
        [run.run_id, owner, config.cohort, config.version],
      );
      return {
        lease: { run: run.run_id, owner, fence: String(updated.fence) },
      };
    });
  }
  async work(q, lease, id) {
    const [work] = await q(
      "SELECT * FROM c1.collection_work WHERE work_id=$1 AND run_id=$2",
      [id, lease.run],
    );
    if (!work) fail("WORK_MISSING");
    return work;
  }
  async allWork(q, lease) {
    // <=200 refresh batches, discovery pages bounded by the discovery budget,
    // and candidate batches of 50 IDs across channels; never one run blob.
    const rows = await q(
      `SELECT work_id,work_key,phase,channel_id,selected_ids,dispatch_order,page_count,
      status,attempts,next_attempt_at,outcomes,(staged_response IS NOT NULL) AS staged_response
      FROM c1.collection_work WHERE run_id=$1 ORDER BY dispatch_order,work_key LIMIT $2`,
      [lease.run, LIMITS.maxWork + 1],
    );
    if (rows.length > LIMITS.maxWork) fail("WORK_LIMIT");
    return rows;
  }
  // Candidate owners come from immutable staged discovery responses of this run.
  async sources(q, w) {
    const rows = await q(
      `SELECT w.channel_id,i->'contentDetails'->>'videoId' AS video_id
      FROM c1.collection_work w CROSS JOIN LATERAL jsonb_array_elements(w.staged_response->'items') i
      WHERE w.run_id=$1 AND w.phase='discovery' AND w.status='committed'
      AND i->'contentDetails'->>'videoId'=ANY($2::text[])`,
      [w.run_id, w.selected_ids],
    );
    const owners = {};
    const ambiguous = new Set();
    for (const r of rows) {
      if (owners[r.video_id] && owners[r.video_id] !== r.channel_id) {
        ambiguous.add(r.video_id);
      }
      owners[r.video_id] = r.channel_id;
    }
    for (const id of ambiguous) delete owners[id];
    return owners;
  }
  async next(lease) {
    return this.transaction(async (q, cohort) => {
      const { run, coord } = await this.fenced(q, lease);
      if (Date.parse(coord.db_now) >= Date.parse(run.deadline_at)) {
        await this.finish(
          q,
          lease,
          run,
          await this.allWork(q, lease),
          "WINDOW_EXPIRED",
        );
        return null;
      }
      let works = await this.allWork(q, lease);
      for (const phase of ["refresh", "channels", "discovery", "candidates"]) {
        if (phase === "discovery" && !run.summary.discoverySeeded) {
          const channels = await q(
            `SELECT channel_id,uploads_playlist_id FROM c1.channels WHERE channel_id IN
            (SELECT channel_id FROM c1.cohort_channels WHERE cohort_id=$1 AND version=$2)`,
            [this.config.cohort, this.config.version],
          );
          const ordered = discoveryOrder(channels, run.summary.rotation);
          for (let i = 0; i < ordered.length; i++) {
            const c = ordered[i];
            await this.insertWork(q, run, {
              key: `discovery:${c.channel_id}:0`,
              phase: "discovery",
              channel: c.channel_id,
              order: i,
            });
            if (!c.uploads_playlist_id) {
              await q(
                `UPDATE c1.collection_work SET status='deferred',failure_code='MISSING_PLAYLIST'
              WHERE run_id=$1 AND work_key=$2`,
                [run.run_id, `discovery:${c.channel_id}:0`],
              );
            }
          }
          run.summary.discoverySeeded = true;
          await q(
            "UPDATE c1.collection_runs SET summary=$1::jsonb WHERE run_id=$2",
            [JSON.stringify(run.summary), lease.run],
          );
          await q(
            `UPDATE c1.collection_coordination SET discovery_start_offset=$1 WHERE cohort_id=$2 AND version=$3`,
            [
              (run.summary.rotation + 1) % cohort.channel_ids.length,
              this.config.cohort,
              this.config.version,
            ],
          );
          works = await this.allWork(q, lease);
        }
        if (phase === "candidates" && !run.summary.candidatesSeeded) {
          // After all discovery pages: batch new IDs across channels, 50 per call.
          const found = [
            ...new Set(
              works.filter((w) =>
                w.phase === "discovery" && w.status === "committed"
              ).flatMap((w) => w.outcomes.discovered ?? []),
            ),
          ].sort();
          const known = found.length
            ? await q(
              "SELECT video_id FROM c1.videos WHERE video_id=ANY($1::text[])",
              [found],
            )
            : [];
          const skip = new Set(known.map((x) => x.video_id));
          const batches = chunks(found.filter((id) => !skip.has(id)));
          for (let i = 0; i < batches.length; i++) {
            await this.insertWork(q, run, {
              key: `candidates:${i}`,
              phase: "candidates",
              ids: batches[i],
              order: i,
            });
          }
          run.summary.candidatesSeeded = true;
          await q(
            "UPDATE c1.collection_runs SET summary=$1::jsonb WHERE run_id=$2",
            [JSON.stringify(run.summary), lease.run],
          );
          works = await this.allWork(q, lease);
        }
        const pending = works.filter((w) =>
          w.phase === phase &&
          ["pending", "claimed", "staged"].includes(w.status)
        );
        if (!pending.length) continue;
        // Waiting on a retry blocks phase advance, but not other ready channels.
        const ready = pending.find((w) =>
          w.status === "staged" || !w.next_attempt_at ||
          Date.parse(w.next_attempt_at) <= Date.parse(coord.db_now)
        );
        if (!ready) return null;
        await q(
          "UPDATE c1.collection_runs SET phase=$1,heartbeat_at=clock_timestamp() WHERE run_id=$2",
          [phase, lease.run],
        );
        return ready;
      }
      await this.finish(q, lease, run, works);
      return null;
    });
  }
  async reserve(lease, id) {
    return this.transaction(async (q, cohort) => {
      const { run, coord } = await this.fenced(q, lease),
        work = await this.work(q, lease, id);
      if (Date.parse(run.deadline_at) - Date.parse(coord.db_now) < 15000) {
        await this.finish(
          q,
          lease,
          run,
          await this.allWork(q, lease),
          "WINDOW_EXPIRED",
        );
        return null;
      }
      if (
        !["pending", "claimed"].includes(work.status) || work.staged_response ||
        (work.next_attempt_at &&
          Date.parse(work.next_attempt_at) > Date.parse(coord.db_now))
      ) fail("WORK_STATE");
      const works = await this.allWork(q, lease);
      const untouched = works.filter((w) =>
        w.phase === "refresh" && w.attempts === 0 &&
        ["pending", "claimed"].includes(w.status)
      ).length;
      const reason = reservation(run, work, cohort, untouched);
      if (reason) {
        await q(
          `UPDATE c1.collection_work SET status='deferred',failure_code=$1 WHERE work_id=$2`,
          [reason, id],
        );
        return null;
      }
      await q(
        `UPDATE c1.collection_runs SET attempts_reserved=attempts_reserved+1,
        discovery_attempts=discovery_attempts+$1,heartbeat_at=clock_timestamp() WHERE run_id=$2`,
        [work.phase === "discovery" ? 1 : 0, lease.run],
      );
      const [ready] = await q(
        `UPDATE c1.collection_work SET status='claimed',attempts=attempts+1,
        lease_owner=$1,lease_expires_at=clock_timestamp()+interval '75 seconds',fence=$2,next_attempt_at=NULL
        WHERE work_id=$3 RETURNING *`,
        [lease.owner, lease.fence, id],
      );
      if (work.phase === "discovery") {
        const [c] = await q(
          "SELECT uploads_playlist_id FROM c1.channels WHERE channel_id=$1",
          [work.channel_id],
        );
        if (!c?.uploads_playlist_id) {
          fail("MISSING_PLAYLIST");
        }
        ready.playlist = c.uploads_playlist_id;
      }
      return ready;
    });
  }
  async stage(lease, id, payload, observed, digest) {
    // The normalized representation and raw staged response stay bounded.
    if (
      new TextEncoder().encode(canonical(payload)).length > LIMITS.responseBytes
    ) fail("BODY_LIMIT");
    return this.transaction(async (q) => {
      const { run, coord } = await this.fenced(q, lease),
        w = await this.work(q, lease, id);
      if (Date.parse(coord.db_now) >= Date.parse(run.deadline_at)) {
        fail("WINDOW_EXPIRED");
      }
      if (await hash(payload) !== digest) fail("STAGING_HASH");
      if (w.staged_response) {
        if (
          w.payload_hash !== digest ||
          new Date(w.observed_at).toISOString() !== observed
        ) fail("REPLAY_CONFLICT");
        return;
      }
      if (
        w.status !== "claimed" || w.lease_owner !== lease.owner ||
        String(w.fence) !== lease.fence
      ) fail("WORK_STATE");
      await q(
        `UPDATE c1.collection_work SET staged_response=$1::jsonb,observed_at=$2,payload_hash=$3,status='staged',
        outcomes=$4::jsonb WHERE work_id=$5`,
        [
          JSON.stringify(payload),
          observed,
          digest,
          JSON.stringify({
            received_at: observed,
            staged_at: new Date(coord.db_now).toISOString(),
          }),
          id,
        ],
      );
    });
  }
  async failed(lease, id, { code, retry, delayMs }) {
    return this.transaction(async (q, cohort) => {
      const { run } = await this.fenced(q, lease),
        w = await this.work(q, lease, id);
      if (
        w.status !== "claimed" || w.lease_owner !== lease.owner ||
        String(w.fence) !== lease.fence
      ) fail("WORK_STATE");
      const terminal = !retry || w.attempts >= 3;
      await q(
        `UPDATE c1.collection_work SET status=$1,failure_code=$2,
        next_attempt_at=CASE WHEN $3::boolean THEN NULL ELSE clock_timestamp()+$4::integer*interval '1 millisecond' END,
        outcomes=$5::jsonb WHERE work_id=$6`,
        [
          terminal ? "failed" : "pending",
          code,
          terminal,
          delayMs,
          JSON.stringify({
            unconfirmed: w.selected_ids,
            token_reset: code === "PAGE_TOKEN",
          }),
          id,
        ],
      );
      if (
        code === "PAGE_TOKEN" && w.phase === "discovery" &&
        w.page_count + 1 < cohort.max_pages_per_channel
      ) {
        await this.insertWork(q, run, {
          key: `discovery:${w.channel_id}:${w.page_count + 1}`,
          phase: "discovery",
          channel: w.channel_id,
          page: w.page_count + 1,
          order: Number(w.dispatch_order) + cohort.channel_ids.length,
          seen: [],
        });
      }
      if (["API_AUTH", "QUOTA"].includes(code)) {
        await this.finish(
          q,
          lease,
          run,
          await this.allWork(q, lease),
          code,
          true,
        );
      }
    });
  }
  async snapshot(q, work, record, observed, digest) {
    // History is keyed by entity and observation time; cohort/run are provenance.
    const channel = work.phase === "channels";
    const [old] = channel
      ? await q(
        `SELECT payload_hash FROM c1.channel_stats_history
      WHERE channel_id=$1 AND observed_at=$2`,
        [record.id, observed],
      )
      : await q(
        `SELECT payload_hash FROM c1.video_stats_history WHERE video_id=$1 AND observed_at=$2`,
        [record.id, observed],
      );
    if (await replayCheck(old?.payload_hash, digest) === "noop") return;
    const provenance = [
      work.cohort_id,
      work.version,
      work.run_id,
      work.work_id,
      ...record.counts,
      digest,
    ];
    if (channel) {
      await q(
        `INSERT INTO c1.channel_stats_history
      (channel_id,observed_at,cohort_id,version,run_id,work_id,subscriber_count,view_count,video_count,payload_hash)
      VALUES ($1,$2,$3,$4,$5,$6,$7::bigint,$8::bigint,$9::bigint,$10)`,
        [record.id, observed, ...provenance],
      );
    } else {await q(
        `INSERT INTO c1.video_stats_history
      (video_id,channel_id,observed_at,cohort_id,version,run_id,work_id,view_count,like_count,comment_count,payload_hash)
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8::bigint,$9::bigint,$10::bigint,$11)`,
        [record.id, record.channel, observed, ...provenance],
      );}
  }
  async rejectStaged(lease, id, code) {
    return this.transaction(async (q) => {
      await this.fenced(q, lease);
      const w = await this.work(q, lease, id);
      if (w.status !== "staged") fail("WORK_STATE");
      await q(
        `UPDATE c1.collection_work SET status='failed',failure_code=$1,outcomes=$2::jsonb WHERE work_id=$3`,
        [
          code,
          JSON.stringify({ ...w.outcomes, unconfirmed: w.selected_ids }),
          id,
        ],
      );
    });
  }
  async commit(lease, id) {
    return this.transaction(async (q, cohort) => {
      const { run, coord } = await this.fenced(q, lease),
        w = await this.work(q, lease, id);
      if (Date.parse(coord.db_now) >= Date.parse(run.deadline_at)) {
        fail("WINDOW_EXPIRED");
      }
      if (!w.staged_response || !["staged", "committed"].includes(w.status)) {
        fail("WORK_STATE");
      }
      if (await hash(w.staged_response) !== w.payload_hash) {
        fail("STAGING_HASH");
      }
      if (w.status === "committed") return;
      const observed = new Date(w.observed_at).toISOString();
      const inventory = w.selected_ids.length
        ? await q(
          `SELECT video_id,channel_id FROM c1.videos WHERE video_id=ANY($1::text[])`,
          [w.selected_ids],
        )
        : [];
      const stored = Object.fromEntries(
        inventory.map((r) => [r.video_id, r.channel_id]),
      );
      let owners = stored;
      if (w.phase === "candidates") {
        owners = await this.sources(q, w);
        for (const [video, channel] of Object.entries(stored)) {
          if (owners[video] !== channel) delete owners[video];
        }
      }
      const result = normalize(
        w,
        w.staged_response,
        cohort.channel_ids,
        owners,
        iso(coord.admission_published_after),
      );
      for (const record of result.records) {
        if (w.phase === "candidates" && !stored[record.id]) {
          const [rev] = await q(
            `UPDATE c1.collection_coordination SET inventory_revision=inventory_revision+1
            WHERE cohort_id=$1 AND version=$2 RETURNING inventory_revision`,
            [w.cohort_id, w.version],
          );
          await q(
            `INSERT INTO c1.videos (video_id,channel_id,admitted_at,admission_source,inventory_revision)
            VALUES ($1,$2,clock_timestamp(),'youtube_validated',$3)`,
            [record.id, record.channel, String(rev.inventory_revision)],
          );
        }
        if (
          w.phase !== "channels" && w.phase !== "candidates" &&
          !stored[record.id]
        ) fail("INVENTORY_MISSING");
        const digest = await hash(record);
        await this.snapshot(q, w, record, observed, digest);
        if (w.phase === "channels") {
          await q(
            `UPDATE c1.channels SET channel_name=$1,uploads_playlist_id=$2,published_at=$3,
          country=$4,default_language=$5,topic_categories=$6::text[],metadata_observed_at=$7
          WHERE channel_id=$8 AND (metadata_observed_at IS NULL OR metadata_observed_at<=$7)`,
            [
              record.title,
              record.playlist,
              record.published,
              record.country,
              record.language,
              record.topics,
              observed,
              record.id,
            ],
          );
        } else {await q(
            `UPDATE c1.videos SET title=$1,published_at=$2,duration_seconds=$3,category_id=$4,
          metadata_observed_at=$5
          WHERE video_id=$6 AND (metadata_observed_at IS NULL OR metadata_observed_at<=$5)`,
            [
              record.title,
              record.published,
              record.duration,
              record.category,
              observed,
              record.id,
            ],
          );}
      }
      let coverage = true;
      // Reaching the admission cutoff completes a channel's discovery; candidates
      // are seeded across channels in next() once every page has finished.
      if (w.phase === "discovery" && result.next && !result.reached) {
        const loop = w.seen_tokens.includes(result.next) ||
          result.next === w.input_cursor;
        coverage = false;
        if (!loop && w.page_count + 1 < cohort.max_pages_per_channel) {
          await this.insertWork(q, run, {
            key: `discovery:${w.channel_id}:${w.page_count + 1}`,
            phase: "discovery",
            channel: w.channel_id,
            cursor: result.next,
            order: Number(w.dispatch_order) + cohort.channel_ids.length,
            page: w.page_count + 1,
            seen: [...w.seen_tokens, result.next],
          });
        }
      }
      await q(
        `UPDATE c1.collection_work SET status='committed',output_cursor=$1,
        outcomes=$2::jsonb WHERE work_id=$3`,
        [
          result.next,
          JSON.stringify({
            ...w.outcomes,
            returned: result.records.map((r) => r.id),
            invalid: result.invalid,
            unavailable: result.unavailable,
            skipped: result.skipped,
            discovered: result.candidates,
            reached_cutoff: result.reached,
            coverage,
            committed_at: new Date(coord.db_now).toISOString(),
          }),
          id,
        ],
      );
      await q(
        "UPDATE c1.collection_runs SET heartbeat_at=clock_timestamp() WHERE run_id=$1",
        [lease.run],
      );
    });
  }
  summary(works) {
    const complete = (phase) =>
      works.filter((w) => w.phase === phase).every((w) =>
        w.status === "committed" &&
        !(w.outcomes.invalid?.length) && !(w.outcomes.unavailable?.length)
      );
    const pages = works.filter((w) => w.phase === "discovery");
    const channelCoverage = {};
    for (const page of pages) {
      channelCoverage[page.channel_id] = page.status === "committed" &&
        page.outcomes.coverage === true;
    }
    const endpointAttempts = { videos: 0, channels: 0, playlistItems: 0 };
    for (const w of works) {
      endpointAttempts[
        w.phase === "discovery"
          ? "playlistItems"
          : w.phase === "channels"
          ? "channels"
          : "videos"
      ] += w.attempts;
    }
    return {
      refresh_complete: complete("refresh"),
      channels_complete: complete("channels"),
      discovery_complete: pages.length > 0 &&
        Object.values(channelCoverage).every(Boolean),
      candidates_complete: complete("candidates"),
      discovery_channels: channelCoverage,
      unattempted: works.filter((w) => w.attempts === 0).length,
      unavailable: works.reduce(
        (n, w) => n + (w.outcomes.unavailable?.length ?? 0),
        0,
      ),
      invalid: works.reduce((n, w) => n + (w.outcomes.invalid?.length ?? 0), 0),
      selected: works.reduce((n, w) => n + w.selected_ids.length, 0),
      returned: works.reduce(
        (n, w) => n + (w.outcomes.returned?.length ?? 0),
        0,
      ),
      unconfirmed: works.reduce(
        (n, w) =>
          n +
          (["failed", "deferred"].includes(w.status) && w.attempts > 0
            ? w.selected_ids.length
            : 0),
        0,
      ),
      endpoint_attempts: endpointAttempts,
      retries: works.reduce((n, w) => n + Math.max(0, w.attempts - 1), 0),
    };
  }
  async finish(q, lease, run, works, code = null, fatal = false) {
    const summary = { ...run.summary, ...this.summary(works) };
    const done = summary.refresh_complete && summary.channels_complete &&
      summary.discovery_complete && summary.candidates_complete;
    await q(
      `UPDATE c1.collection_runs SET status=$1,phase='finished',ended_at=clock_timestamp(),heartbeat_at=clock_timestamp(),
      inventory_complete=$2,discovery_complete=$3,summary=$4::jsonb,failure_code=$5 WHERE run_id=$6`,
      [
        fatal ? "failed" : !code && done ? "complete" : "partial",
        summary.refresh_complete,
        summary.discovery_complete,
        JSON.stringify(summary),
        code,
        lease.run,
      ],
    );
  }
  async report(lease) {
    return this.transaction(async (q) => {
      // A terminal run can be reported, but never through a lost lease.
      const coord = await this.coordination(q);
      if (
        coord.active_run_id !== lease.run ||
        coord.lease_owner !== lease.owner ||
        String(coord.fence) !== lease.fence ||
        Date.parse(coord.lease_expires_at) <= Date.parse(coord.db_now)
      ) fail("LEASE_LOST");
      const [run] = await q(
        "SELECT status,attempts_reserved,discovery_attempts FROM c1.collection_runs WHERE run_id=$1",
        [lease.run],
      );
      return {
        state: run.status,
        attempts: run.attempts_reserved,
        discovery_attempts: run.discovery_attempts,
        ...this.summary(await this.allWork(q, lease)),
      };
    });
  }
  async release(lease) {
    return this.transaction(async (q) => {
      const coord = await this.coordination(q);
      if (
        coord.active_run_id !== lease.run ||
        coord.lease_owner !== lease.owner ||
        String(coord.fence) !== lease.fence ||
        Date.parse(coord.lease_expires_at) <= Date.parse(coord.db_now)
      ) return;
      await q(
        `UPDATE c1.collection_coordination SET lease_owner=NULL,lease_expires_at=NULL
        WHERE cohort_id=$1 AND version=$2`,
        [this.config.cohort, this.config.version],
      );
    });
  }
}
