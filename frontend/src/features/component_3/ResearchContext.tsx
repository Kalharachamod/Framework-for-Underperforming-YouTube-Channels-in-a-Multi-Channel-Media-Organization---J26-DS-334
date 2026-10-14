/**
 * Snapshot / experiment selection shared by all Component 3 screens. Defaults follow the API
 * (latest snapshot, latest experiment); every screen also shows the ids the API actually used.
 */
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useApi } from "../../hooks/useApi";
import { component3Api } from "./api";
import type { BridgeExperiment, ChannelSummary, ResearchStatusResponse } from "./types";

interface ResearchContextValue {
  snapshotId: string | null; // null = latest (API default)
  experimentId: string | null; // null = latest of the snapshot
  setSnapshotId: (id: string | null) => void;
  setExperimentId: (id: string | null) => void;
  status: ReturnType<typeof useApi<ResearchStatusResponse>>;
  experiments: ReturnType<typeof useApi<{ items: BridgeExperiment[] }>>;
  channels: ReturnType<typeof useApi<{ snapshot_id: string; items: ChannelSummary[]; features_status: string }>>;
}

const Ctx = createContext<ResearchContextValue | null>(null);

export function ResearchProvider({ children }: { children: ReactNode }) {
  const [snapshotId, setSnapshot] = useState<string | null>(null);
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const status = useApi((s) => component3Api.status({ snapshotId }, s), [snapshotId]);
  const hasData = status.status === "success" && status.data.research_data === "available";
  const experiments = useApi((s) => component3Api.experiments({ snapshotId }, s), [snapshotId], hasData);
  const channels = useApi((s) => component3Api.channels({ snapshotId }, s), [snapshotId], hasData);

  const value = useMemo<ResearchContextValue>(
    () => ({
      snapshotId,
      experimentId,
      setSnapshotId: (id) => {
        setSnapshot(id);
        setExperimentId(null); // experiments belong to one snapshot
      },
      setExperimentId,
      status,
      experiments,
      channels,
    }),
    [snapshotId, experimentId, status, experiments, channels],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useResearch(): ResearchContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useResearch must be used inside ResearchProvider");
  return v;
}

export function channelName(channels: ChannelSummary[] | undefined, id: string | null | undefined): string {
  if (!id) return "—";
  return channels?.find((c) => c.channel_id === id)?.channel_name ?? id;
}
