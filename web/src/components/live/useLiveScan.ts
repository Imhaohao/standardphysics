"use client";

import { useEffect, useReducer } from "react";
import { connectLive, fixtureMessages, INITIAL_LIVE_STATE, reduceLive, replayMessages, type LiveConnection } from "@/lib/api/live";
import type { Report, ServerMessage } from "@/lib/api/types";
import type { Scene } from "@/lib/scene/types";

const REPLAY_STEP_MS = 900;

export type LiveSource =
  /** Plays a finished scan back from its saved scene and report. */
  | { kind: "replay"; scanId: string; scene: Scene; report: Report }
  /** Follows a scan in progress on sp-server's live socket. */
  | { kind: "socket"; scanId: string };

type Dispatch = (message: ServerMessage) => void;

/** Asks this app's own route for a fresh ticketed socket URL; the session cookie stays httpOnly. */
export async function fetchLiveSocketUrl(scanId: string) {
  const response = await fetch(`/api/scans/${encodeURIComponent(scanId)}/live-ticket`, { method: "POST", cache: "no-store" });
  if (!response.ok) throw new Error(`live-ticket answered ${response.status}`);
  return ((await response.json()) as { url: string }).url;
}

function followSocket(scanId: string, dispatch: Dispatch): LiveConnection {
  return connectLive(() => fetchLiveSocketUrl(scanId), {
    onMessage: dispatch,
    onClosed: (reason) => dispatch({ type: "error", message: reason }),
  });
}

/** The live state of a scan: rooms and findings folded together as messages arrive. */
export function useLiveScan(source: LiveSource) {
  const [state, dispatch] = useReducer(reduceLive, INITIAL_LIVE_STATE);
  useEffect(() => {
    const connection =
      source.kind === "replay"
        ? replayMessages(fixtureMessages(source.scanId, source.scene, source.report), { onMessage: dispatch }, REPLAY_STEP_MS)
        : followSocket(source.scanId, dispatch);
    return () => connection.close();
  }, [source]);
  return state;
}
