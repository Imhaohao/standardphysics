import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { scanStatusCopy, sheetNumber, shopName, type ShopSheet } from "@/lib/shopSheet";

/** The drawing list: every other sheet in the set, one row each. */
export function SheetIndex({ sheets, firstIndex, title }: { sheets: ShopSheet[]; firstIndex: number; title: string }) {
  return (
    <section aria-labelledby="sheet-index">
      <h2 id="sheet-index" className="heading-display text-xl">
        {title}
      </h2>
      <ul className="mt-3 border-t border-ink">
        {sheets.map((sheet, index) => (
          <li key={sheet.scan.id} className="border-b border-ink">
            <Link href={sheet.href} className="group grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-4 px-2 py-3 transition-colors duration-150 hover:bg-sheet">
              <span className="font-semibold tabular-nums">{sheetNumber(firstIndex + index)}</span>
              <span className="min-w-0">
                <span className="block truncate font-semibold">{shopName(sheet.scan)}</span>
                <span className="block truncate text-sm text-ink-muted">{scanStatusCopy(sheet)}</span>
              </span>
              <ArrowRight size={18} weight="bold" aria-hidden className="transition-transform duration-150 group-hover:translate-x-1" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
