import { ScanShopButton } from "@/components/ScanShopButton";
import { SHEET_GRID_CLASS, SheetField } from "@/components/blueprint/SheetField";

const issuedFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

export function HomeTitleBlock({ className = "" }: { className?: string }) {
  return (
    <section aria-label="Title block" className={`border border-ink bg-paper ${className}`}>
      <div className="border-b border-ink px-4 py-3">
        <p className="heading-display text-2xl">Standard Physics</p>
        <p className="mt-1 text-ink-muted text-pretty">Walk your shop with an iPhone and we measure it against the ADA.</p>
      </div>
      <dl className={`${SHEET_GRID_CLASS} grid-cols-2 border-b border-ink *:bg-paper`}>
        <SheetField label="Standard">2010 ADA</SheetField>
        <SheetField label="Issued">{issuedFormat.format(new Date())}</SheetField>
      </dl>
      <div className="p-4">
        <ScanShopButton />
      </div>
    </section>
  );
}
