import { ArrowCounterClockwise, EyeSlash, Path } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { IconButton } from "@/components/ui/IconButton";

export type Showing = "before" | "both" | "after";

const SHOWING: { value: Showing; label: string }[] = [
  { value: "before", label: "Before" },
  { value: "both", label: "Both" },
  { value: "after", label: "After" },
];

function Toggle({ pressed, onToggle, children }: { pressed: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={pressed} onClick={onToggle}
      className="pressable flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-muted hover:bg-ink/5 hover:text-ink aria-pressed:bg-ink aria-pressed:text-paper">
      {children}
    </button>
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
      <div role="group" aria-label="Which video to show" className="flex rounded-xl bg-sheet/95 p-1 shadow-float">
        {SHOWING.map((option) => (
          <button key={option.value} type="button" aria-pressed={showing === option.value}
            onClick={() => onShowing(option.value)}
            className="pressable rounded-lg px-3 py-2 text-sm font-medium text-ink-muted hover:text-ink aria-pressed:bg-ink aria-pressed:text-paper">
            {option.label}
          </button>
        ))}
      </div>
      <div className="flex rounded-xl bg-sheet/95 p-1 shadow-float">
        <Toggle pressed={paths} onToggle={onPaths}>
          <Path size={16} aria-hidden />
          Camera paths
        </Toggle>
        <Toggle pressed={blindSpots} onToggle={onBlindSpots}>
          <EyeSlash size={16} aria-hidden />
          Blind spots
        </Toggle>
      </div>
      <div className="rounded-xl bg-sheet/95 p-1 shadow-float">
        <IconButton label="Reset the view" tooltipSide="below" onClick={onReset}>
          <ArrowCounterClockwise size={18} aria-hidden />
        </IconButton>
      </div>
    </div>
  );
}
