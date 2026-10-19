import type { ReactNode } from "react";
import { zoneRowLetter } from "@/lib/brush/sheet";
import { ZoneBand } from "./ZoneBand";

interface SheetFrameProps {
  columns?: number;
  rows?: number;
  className?: string;
  children: ReactNode;
}

function labels(count: number, label: (index: number) => string) {
  return Array.from({ length: count }, (_, index) => label(index));
}

/** A drawing sheet border: a heavy outer line, zone bands on all four sides and a hairline inner frame. */
export function SheetFrame({ columns = 8, rows = 6, className = "", children }: SheetFrameProps) {
  const columnLabels = labels(columns, (index) => String(index + 1));
  const rowLabels = labels(rows, zoneRowLetter);
  return (
    <div className={`grid grid-cols-[1.5rem_minmax(0,1fr)_1.5rem] grid-rows-[1.5rem_1fr_1.5rem] border-2 border-ink print:border-0 ${className}`}>
      <ZoneBand labels={columnLabels} orientation="horizontal" className="col-start-2 row-start-1 print:hidden" />
      <ZoneBand labels={rowLabels} orientation="vertical" className="col-start-1 row-start-2 print:hidden" />
      <ZoneBand labels={rowLabels} orientation="vertical" className="col-start-3 row-start-2 print:hidden" />
      <ZoneBand labels={columnLabels} orientation="horizontal" className="col-start-2 row-start-3 print:hidden" />
      <div className="relative col-start-2 row-start-2 min-h-0 border border-ink print:col-span-3 print:col-start-1 print:row-span-3 print:row-start-1 print:border-0">{children}</div>
    </div>
  );
}
