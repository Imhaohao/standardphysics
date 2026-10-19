"use client";

import { useEffect, useReducer } from "react";
import { apiBaseUrl, liveSocketUrl } from "@/lib/api/config";
import { connectLive, fixtureMessages, INITIAL_LIVE_STATE, reduceLive, replayMessages, type LiveConnection } from "@/lib/api/live";
import type { Report, ServerMessage } from "@/lib/api/types";
import type { Scene } from "@/lib/scene/types";

const REPLAY_STEP_MS = 900;

export type LiveSource =
  /** Plays a finished scan back from its saved scene and report. */
  | { kind: "replay"; scanId: string; scene: Scene; report: Report }
  /** Follows a scan in progress on sp-server's live socket. */
  | { kind: "socket"; scanId: string; token: string };

type Dispatch = (message: ServerMessage) => void;

function followSocket(source: Extract<LiveSource, { kind: "socket" }>, dispatch: Dispatch): LiveConnection {
  return connectLive(liveSocketUrl(apiBaseUrl(), source.scanId, source.token), {
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
        : followSocket(source, dispatch);
    return () => connection.close();
  }, [source]);
  return state;
}
