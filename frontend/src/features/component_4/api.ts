/** Component 4 API client. */

import { getJson, hasKeys, isList, type Params, type Validator } from "../../services/apiClient";
import type { BenchmarkResult, Component4Status, EmergingTopicSignal, TopicTrajectoryPoint } from "./types";

const BASE = "/api/v1/component-4";

const shape =
  <T>(keys: string[], lists: string[] = []): Validator<T> =>
  (d: unknown): d is T =>
    hasKeys(d, keys) && lists.every((k) => isList(d[k]));

export const component4Api = {
  getStatus: (signal?: AbortSignal) =>
    getJson<Component4Status>(
      `${BASE}/status`,
      {},
      shape(["has_videos", "has_trajectories", "has_emerging_signals", "total_signals_detected"]),
      signal
    ),

  getEmergingTopics: (params: { niche?: string; minScore?: number; channelId?: string } = {}, signal?: AbortSignal) => {
    const query: Params = {};
    if (params.niche && params.niche !== "All") query.niche = params.niche;
    if (params.minScore) query.min_score = params.minScore;
    if (params.channelId) query.channel_id = params.channelId;
    return getJson<EmergingTopicSignal[]>(
      `${BASE}/emerging-topics`,
      query,
      (d: unknown): d is EmergingTopicSignal[] => Array.isArray(d),
      signal
    );
  },

  getBenchmarks: (signal?: AbortSignal) =>
    getJson<BenchmarkResult[]>(
      `${BASE}/benchmarks`,
      {},
      (d: unknown): d is BenchmarkResult[] => Array.isArray(d),
      signal
    ),

  getTrajectories: (params: { channelId?: string; topicId?: number } = {}, signal?: AbortSignal) => {
    const query: Params = {};
    if (params.channelId) query.channel_id = params.channelId;
    if (params.topicId !== undefined) query.topic_id = params.topicId;
    return getJson<TopicTrajectoryPoint[]>(
      `${BASE}/trajectories`,
      query,
      (d: unknown): d is TopicTrajectoryPoint[] => Array.isArray(d),
      signal
    );
  },
};
