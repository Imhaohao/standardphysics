import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import type { ReactNode } from "react";
import { buttonClassName } from "@/components/ui/Button";

/** The top of every page about one shop: a way back, the page's title and its actions. */
export function ShopHeader({ backHref, backLabel, title, children }: { backHref: string; backLabel: string; title: string; children?: ReactNode }) {
  return (
    <header className="flex flex-col gap-4">
      <Link href={backHref} className={`-ms-3 w-fit print:hidden ${buttonClassName("quiet")}`}>
        <ArrowLeft size={16} aria-hidden />
        {backLabel}
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="heading-display text-4xl sm:text-6xl">{title}</h1>
        {children && <div className="flex flex-wrap items-center gap-3 print:hidden">{children}</div>}
      </div>
    </header>
  );
}
