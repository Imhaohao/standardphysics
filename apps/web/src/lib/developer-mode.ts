"use client";

import { useStoredSwitch } from "./stored-switch";

/**
 * Whether to show the tools this team built for itself.
 *
 * The server renders the shop owner's view, so the first paint is always the
 * plain one and the extra panels appear only once the browser reports that this
 * person asked for them.
 */
export function useDeveloperMode(): [boolean, (on: boolean) => void] {
  return useStoredSwitch("sp_developer_mode");
}
