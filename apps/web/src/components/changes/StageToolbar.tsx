import { ArrowCounterClockwise, EyeSlash, Path } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";

export type Showing = "before" | "both" | "after";

const SHOWING: { value: Showing; label: string }[] = [
  { value: "before", label: "Before" },
  { value: "both", label: "Both" },
  { value: "after", label: "After" },
];

/** One floating tray of controls over the 3D view. */
function Tray({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div role={label ? "group" : undefined} aria-label={label} className="flex items-center rounded-xl bg-sheet/95 p-1 shadow-float">
      {children}
    </div>
  );
}

/** Dashed for the before walk, solid for the after walk, matching the lines drawn in the room. */
function PathKey() {
  return (
    <div className="flex items-center gap-3 px-2 text-sm text-ink-muted">
      {(["before", "after"] as const).map((walk) => (
        <span key={walk} className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line x1="1" y1="3" x2="21" y2="3" stroke="currentColor" strokeWidth="1.5"
              strokeDasharray={walk === "before" ? "4 3" : undefined} />
          </svg>
          {walk === "before" ? "Before walk" : "After walk"}
        </span>
      ))}
    </div>
  );
}

type ToolbarProps = {
  showing: Showing;
  onShowing: (value: Showing) => void;
  paths: boolean;
  onPaths: () => void;
  blindSpots: boolean;
  onBlindSpots: () => void;
  onReset: () => void;
};

/** Which video's surfaces to draw, and the overlays that explain them. */
export function StageToolbar({ showing, onShowing, paths, onPaths, blindSpots, onBlindSpots, onReset }: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tray label="Which video to show">
        {SHOWING.map((option) => (
          <Button key={option.value} variant="toggle" aria-pressed={showing === option.value}
            onClick={() => onShowing(option.value)}>
            {option.label}
          </Button>
        ))}
      </Tray>
      <Tray>
        <Button variant="toggle" aria-pressed={paths} onClick={onPaths}>
          <Path size={16} aria-hidden />
          Camera paths
        </Button>
        <Button variant="toggle" aria-pressed={blindSpots} onClick={onBlindSpots}>
          <EyeSlash size={16} aria-hidden />
          Blind spots
        </Button>
        {paths && <PathKey />}
      </Tray>
      <Tray>
        <IconButton label="Reset the view" tooltipSide="below" onClick={onReset}>
          <ArrowCounterClockwise size={18} aria-hidden />
        </IconButton>
      </Tray>
    </div>
  );
}
