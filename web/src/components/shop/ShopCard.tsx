import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { PlanSvg } from "@/components/plan/PlanSvg";
import { squaredToSheet } from "@/lib/scene/plan";
import { scanStatusCopy, shopName, type ShopSheet } from "@/lib/shopSheet";

/** One shop in the list: a small plan, its name and where it stands. */
export function ShopCard({ sheet, sheetNumber }: { sheet: ShopSheet; sheetNumber: string }) {
  return (
    <li>
      <Link href={sheet.href} data-ink-avoid className="group grid h-full grid-rows-[auto_1fr_auto] border border-ink bg-paper transition-colors duration-150 hover:bg-sheet">
        <span className="border-b border-ink px-4 py-2 font-semibold tabular-nums">{sheetNumber}</span>
        <span className="drafting-grid flex h-48 items-center justify-center p-6">
          {sheet.scene ? <PlanSvg scene={squaredToSheet(sheet.scene).scene} name={`card-${sheet.scan.id}`} className="size-full" /> : <span className="text-ink-muted">No plan yet</span>}
        </span>
        <span className="flex items-center justify-between gap-4 border-t border-ink px-4 py-3">
          <span className="min-w-0">
            <span className="heading-display block truncate text-xl">{shopName(sheet.scan)}</span>
            <span className="block truncate text-sm text-ink-muted">{scanStatusCopy(sheet)}</span>
          </span>
          <ArrowRight size={18} weight="bold" aria-hidden className="shrink-0 transition-transform duration-150 group-hover:translate-x-1" />
        </span>
      </Link>
    </li>
  );
}
