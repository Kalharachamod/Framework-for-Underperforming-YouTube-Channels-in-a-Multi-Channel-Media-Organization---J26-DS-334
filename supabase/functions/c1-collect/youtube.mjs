import { fail, LIMITS, Stop } from "./core.mjs";
import { boundedText } from "./handler.mjs";
export class YouTubeError extends Stop {
  constructor(code, retry = false) {
    super(code);
    this.retry = retry;
  }
}
export function createYouTube({ apiKey, fetcher = fetch }) {
  return {
    async request(work) {
      const channel = work.phase === "channels",
        page = work.phase === "discovery";
      const url = new URL(
        `https://www.googleapis.com/youtube/v3/${
          page ? "playlistItems" : channel ? "channels" : "videos"
        }`,
      );
      // Every list call costs one quota unit regardless of parts/fields.
      url.searchParams.set(
        "part",
        page
          ? "contentDetails,snippet"
          : channel
          ? "snippet,statistics,contentDetails,topicDetails"
          : "snippet,statistics,contentDetails",
      );
      // Key in a header, never in URL/logs/errors.
      if (page) {
        url.searchParams.set("playlistId", work.playlist);
        url.searchParams.set("maxResults", "50");
        url.searchParams.set(
          "fields",
          "items(contentDetails(videoId,videoPublishedAt),snippet/channelId),nextPageToken",
        );
        if (work.input_cursor) {
          url.searchParams.set(
            "pageToken",
            work.input_cursor,
          );
        }
      } else {
        url.searchParams.set("id", work.selected_ids.join(","));
        url.searchParams.set(
          "fields",
          channel
            ? "items(id,snippet(title,publishedAt,country,defaultLanguage),statistics,contentDetails/relatedPlaylists/uploads,topicDetails/topicCategories)"
            : "items(id,snippet(channelId,title,publishedAt,categoryId),statistics,contentDetails/duration)",
        );
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), LIMITS.httpMs);
      try {
        const res = await fetcher(url, {
          headers: { "X-Goog-Api-Key": apiKey },
          signal: controller.signal,
          redirect: "error",
        });
        if (Number(res.headers.get("content-length")) > LIMITS.responseBytes) {
          await res.body?.cancel();
          fail("BODY_LIMIT");
        }
        const text = await boundedText(
          res.body,
          LIMITS.responseBytes,
          controller.signal,
        );
        let body;
        try {
          body = JSON.parse(text);
        } catch {
          fail("MALFORMED_RESPONSE");
        }
        if (!res.ok) {
          const reasons = body?.error?.errors?.map((x) => x.reason) ?? [];
          if (
            reasons.some((x) =>
              ["quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"]
                .includes(x)
            )
          ) throw new YouTubeError("QUOTA");
          if (
            res.status === 401 || res.status === 403 ||
            reasons.includes("keyInvalid")
          ) throw new YouTubeError("API_AUTH");
          if (
            res.status === 400 && reasons.includes("invalidPageToken") && page
          ) throw new YouTubeError("PAGE_TOKEN");
          throw new YouTubeError(
            res.status === 429 || res.status >= 500
              ? "TRANSIENT"
              : "API_REJECTED",
            res.status === 429 || res.status >= 500,
          );
        }
        return body;
      } catch (error) {
        if (controller.signal.aborted) {
          throw new YouTubeError("TRANSPORT", true);
        }
        if (error instanceof Stop) throw error;
        throw new YouTubeError("TRANSPORT", true);
      } finally {
        clearTimeout(timer);
      }
    },
  };
}
