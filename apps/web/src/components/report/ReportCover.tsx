import { InkedFloorPlan } from "@/components/blueprint/InkedFloorPlan";
import { SheetField, SHEET_GRID_CLASS } from "@/components/blueprint/SheetField";
import { SheetFrame } from "@/components/blueprint/SheetFrame";
import type { Assessment, LayoutPlan, SceneGraph, Scan } from "@/types/contracts";
import { longDate } from "./reportDates";

interface ReportCoverProps {
  scan: Scan;
  scene: SceneGraph | null;
  /** The room as the featured plan lays it out, or as scanned when there is no plan. */
  shown: SceneGraph | null;
  plan: LayoutPlan | null;
  assessment: Assessment | null;
}

function CoverDrawing({ drawing, plan }: { drawing: SceneGraph | null; plan: LayoutPlan | null }) {
  if (!drawing) return <div className="drafting-grid h-40" />;
  const moved = new Set(plan?.moves.map((move) => move.node_id) ?? []);
  return <InkedFloorPlan scene={drawing} emphasized={moved} className="drafting-grid h-80 sm:h-[30rem]" />;
}

function TitleFields({ scan, plan, assessment }: Pick<ReportCoverProps, "scan" | "plan" | "assessment">) {
  const checkedOn = new Date(assessment?.created_at ?? scan.created_at);
  return (
    <dl className={`${SHEET_GRID_CLASS} flex-1 grid-cols-2 *:bg-sheet`}>
      <SheetField label="Checked">{longDate.format(checkedOn)}</SheetField>
      <SheetField label="Drawing shows">{plan?.name ?? "As scanned"}</SheetField>
      <SheetField label="Standard">2010 ADA Standards</SheetField>
      <SheetField label="Rules checked">{assessment?.rules_checked ?? "None yet"}</SheetField>
      <SheetField label="Prepared by" className="col-span-2">Standard Physics</SheetField>
    </dl>
  );
}

/** The first sheet: the room drawn in ink, and a title block an architect can file it by. */
export function ReportCover({ scan, scene, shown, plan, assessment }: ReportCoverProps) {
  return (
    <SheetFrame columns={8} rows={5} className="break-inside-avoid bg-sheet">
      <div className="grid lg:grid-cols-[minmax(0,1fr)_20rem]">
        <CoverDrawing drawing={shown ?? scene} plan={plan} />
        <div className="flex flex-col border-t border-ink lg:border-t-0 lg:border-l">
          <div className="border-b border-ink px-4 py-4">
            <h1 className="heading-display text-4xl text-balance">{scan.name}</h1>
            <p className="mt-1 text-ink-muted">{plan ? "Accessibility review and layout" : "Accessibility review"}</p>
          </div>
          <TitleFields scan={scan} plan={plan} assessment={assessment} />
        </div>
      </div>
    </SheetFrame>
  );
}
