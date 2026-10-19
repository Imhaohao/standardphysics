import { ArrowRight, ArrowUp } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { InkedPlan } from "@/components/plan/InkedPlan";
import { SHEET_GRID_CLASS, SheetField } from "@/components/sheet/SheetField";
import { scanStatusCopy, shopName, toFixCount, type ShopSheet } from "@/lib/shopSheet";

const dateFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

/** The lead drawing on the home sheet: the shop's inked plan with its title strip underneath. */
export function FeaturedSheet({ sheet, sheetNumber, actionLabel = "Open the shop" }: { sheet: ShopSheet; sheetNumber: string; actionLabel?: string }) {
  const { scan, scene, report } = sheet;
  const toFix = toFixCount(sheet);
  return (
    <Link href={sheet.href} data-ink-avoid className="group block border border-ink bg-paper transition-colors duration-150 hover:bg-sheet">
      <div className="flex items-center justify-between border-b border-ink px-4 py-2">
        <span className="font-semibold tabular-nums">{sheetNumber}</span>
        <span className="flex items-center gap-1 text-sm text-ink-muted">
          <ArrowUp size={14} weight="bold" aria-hidden />
          Plan view
        </span>
      </div>
      {scene ? (
        <InkedPlan scene={scene} name={`featured-${scan.id}`} className="drafting-grid h-80 sm:h-[28rem]" />
      ) : (
        <div className="flex h-72 items-center justify-center px-6 text-center text-ink-muted sm:h-[26rem]">{scanStatusCopy(sheet)}</div>
      )}
      <dl className={`${SHEET_GRID_CLASS} border-t border-ink *:bg-paper group-hover:*:bg-sheet sm:grid-cols-[minmax(0,2fr)_1fr_1fr_auto]`}>
        <SheetField label="Shop">
          <span className="heading-display block truncate text-2xl">{shopName(scan)}</span>
          <span className="block text-sm font-normal text-ink-muted text-pretty">{scanStatusCopy(sheet)}</span>
        </SheetField>
        <SheetField label={report ? "Checked" : "Scanned"}>{dateFormat.format(new Date(report?.created_at ?? scan.created_at))}</SheetField>
        <SheetField label="To look at">{toFix === null ? "Not checked yet" : toFix}</SheetField>
        <div className="flex items-center gap-2 px-4 py-3 font-semibold">
          {actionLabel}
          <ArrowRight size={18} weight="bold" aria-hidden className="transition-transform duration-150 group-hover:translate-x-1" />
        </div>
      </dl>
    </Link>
  );
}
