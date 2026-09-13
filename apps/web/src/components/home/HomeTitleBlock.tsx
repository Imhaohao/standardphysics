import { ScanShopButton } from "@/components/ScanShopButton";

export function HomeTitleBlock({ className = "" }: { className?: string }) {
  return (
    <section aria-label="Title block" className={`border border-ink bg-paper ${className}`}>
      <p className="heading-display border-b border-ink px-4 py-3 text-2xl">Standard Physics</p>
      <div className="p-4">
        <ScanShopButton />
      </div>
    </section>
  );
}
