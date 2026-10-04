"use client";

import { ArrowsOutLineHorizontal, Check, CircleNotch } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import type { ClearanceBands } from "@/types/contracts";
import type { ClearanceControls } from "./useClearanceOverlay";

/** The one control for the clearance map, the same in every view that offers it. */
export function ClearanceToggle({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <Button variant="chip" aria-pressed={on} onClick={() => onChange(!on)}>
      {on ? <Check size={16} weight="bold" aria-hidden /> : <ArrowsOutLineHorizontal size={16} weight="bold" aria-hidden />}
      Show clearance
    </Button>
  );
}

/**
 * The switch and, while the map is on, its legend, kept together wherever a view puts them: over the model on a
 * wide screen, and under it on a phone, where the legend would otherwise cover the gaps it explains.
 */
export function ClearanceKey({ clearance, offered = true, className }: { clearance: ClearanceControls; offered?: boolean; className: string }) {
  if (!offered) return null;
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <ClearanceToggle on={clearance.on} onChange={clearance.setOn} />
      {clearance.on && <ClearanceLegend bands={clearance.bands} failed={clearance.failed} />}
    </div>
  );
}

/**
 * The legend's footprint over the model on a wide screen: its `lg:w-84` and its inset from the edge, which the plan
 * keeps clear with `lg:pr-88` and the 3D view by sliding its picture half as far the other way.
 */
export const LEGEND_INSET_PX = 336 + 16;

type Row = { swatch: ReactNode; inches: string; meaning: string };

function rowsFor(bands: ClearanceBands): Row[] {
  return [
    { swatch: <Fill className="bg-clearance-turning" />, inches: `${bands.turning_inches} in or more`, meaning: "Room to turn around" },
    { swatch: <Fill className="bg-clearance-route" />, inches: `${bands.route_inches} to ${bands.turning_inches} in`, meaning: "A wheelchair fits" },
    { swatch: <Fill className="bg-clearance-reduced" />, inches: `${bands.reduced_inches} to ${bands.route_inches} in`, meaning: `OK for stretches up to ${bands.reduced_run_inches} in long` },
    { swatch: <TightEdge />, inches: `Under ${bands.reduced_inches} in`, meaning: "Too tight to get through" },
  ];
}

/**
 * What the map's colours mean, in inches. The numbers are the rule pack's, sent with the map, so the legend and the
 * map split the floor in the same places.
 */
export function ClearanceLegend({ bands, failed }: { bands: ClearanceBands | null; failed: boolean }) {
  return <div className="w-max max-w-[calc(100vw-2rem)] rounded-xl bg-sheet/95 p-3 text-sm shadow-float lg:w-84">{legendBody(bands, failed)}</div>;
}

function legendBody(bands: ClearanceBands | null, failed: boolean): ReactNode {
  if (failed) return <p role="status" className="max-w-56 text-pretty">The clearance map didn&rsquo;t load. Turn it off and on again to retry.</p>;
  if (!bands) {
    return (
      <p role="status" className="flex items-center gap-2 text-ink-muted">
        <CircleNotch size={16} className="motion-safe:animate-spin" aria-hidden />
        Measuring clearance
      </p>
    );
  }
  return (
    <table className="border-separate border-spacing-x-2 border-spacing-y-1">
      <caption className="sr-only">What the clearance colours mean</caption>
      <tbody>
        {rowsFor(bands).map((row) => (
          <tr key={row.inches}>
            <td aria-hidden>{row.swatch}</td>
            <th scope="row" className="whitespace-nowrap text-left font-medium tabular-nums">{row.inches}</th>
            <td className="whitespace-nowrap text-ink-muted">{row.meaning}</td>
          </tr>
        ))}
        <tr>
          <td aria-hidden><PinchRing /></td>
          <td colSpan={2} className="whitespace-nowrap text-ink-muted">A gap a route doesn&rsquo;t fit through, and its width</td>
        </tr>
      </tbody>
    </table>
  );
}

function Fill({ className }: { className: string }) {
  return <span className={`block h-3 w-5 rounded-sm ring-1 ring-inset ring-ink/10 ${className}`} />;
}

/** The edge as the map draws it: floor a route fits on one side, a red line, and the floor past it left bare. */
function TightEdge() {
  return (
    <svg viewBox="0 0 20 12" className="block h-3 w-5">
      <rect width={10} height={12} className="fill-clearance-route" />
      <line x1={10} y1={0} x2={10} y2={12} className="stroke-clearance-tight" strokeWidth={1.5} />
    </svg>
  );
}

function PinchRing() {
  return (
    <svg viewBox="0 0 20 12" className="block h-3 w-5">
      <circle cx={10} cy={6} r={4.5} className="fill-sheet stroke-clearance-tight" strokeWidth={1.5} />
      <circle cx={10} cy={6} r={1.5} className="fill-clearance-tight" />
    </svg>
  );
}
