import { PostgresStore } from "./store.mjs";
import { validateConfig } from "./core.mjs";

// Loader is injected; only runtime.mjs supplies the pinned third-party import.
export function postgresFactory(load, active, options = {}) {
  return async (config) => {
    validateConfig(config);
    const { default: postgres } = await load();
    const url = new URL(config.dbUrl);
    url.search = ""; // TLS options cannot be overridden by URL query parameters.
    const sql = postgres(url.toString(), {
      max: 1,
      prepare: false,
      ssl: { rejectUnauthorized: true },
      connect_timeout: 5,
      idle_timeout: 5,
      max_lifetime: 60,
      onnotice: () => {},
      debug: false,
    });
    return new PostgresStore(
      {
        transaction: (body) =>
          sql.begin(async (tx) =>
            body((text, values = []) =>
              tx.unsafe(
                text,
                values.map((v) => Array.isArray(v) ? sql.array(v, 25) : v),
              )
            )
          ),
        close: () => sql.end({ timeout: 1 }),
      },
      config,
      { active, scheduleClock: options.scheduleClock },
    );
  };
}
