import { createHandler } from "./handler.mjs";
import { createYouTube } from "./youtube.mjs";
import { collect } from "./collector.mjs";
import { postgresFactory } from "./driver.mjs";

// No environment-file loader, admin client, or privileged credential reads.
Deno.serve(createHandler({
  get: (name) => Deno.env.get(name),
  createTransport: (c) => createYouTube({ apiKey: c.apiKey }),
  collect,
  openStore: postgresFactory(
    () => import("postgres"),
    () => Deno.env.get("C1_ACTIVATED") === "true",
  ),
}));
