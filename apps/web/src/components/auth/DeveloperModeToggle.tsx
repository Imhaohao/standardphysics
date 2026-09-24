"use client";

import { useDeveloperMode } from "@/lib/developer-mode";

/**
 * The tools the team built for itself, off by default.
 *
 * A shop owner opening a scan should see what is wrong with their shop and
 * nothing about how it was worked out. The evidence ledger, the measurement
 * loop, the scoped-check matrix and the revision comparison all answer
 * questions only the people building this ask, so they wait behind here.
 */
export function DeveloperModeToggle() {
  const [on, setOn] = useDeveloperMode();

  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-sm">
      <input
        type="checkbox"
        checked={on}
        onChange={(event) => setOn(event.target.checked)}
        className="mt-0.5 size-4 shrink-0 accent-ink"
      />
      <span>
        <span className="block font-medium text-ink">Developer mode</span>
        <span className="block text-ink-muted">
          Adds the evidence ledger, the measurement loop, scoped checks and scan comparison to
          every shop you open.
        </span>
      </span>
    </label>
  );
}
