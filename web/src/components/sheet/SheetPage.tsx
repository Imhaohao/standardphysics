import Link from "next/link";
import type { ReactNode } from "react";
import { SheetFrame } from "./SheetFrame";

/** The paper margin and sheet frame every page sits in, with the site's few standing links underneath. */
export function SheetPage({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <main className="flex min-h-dvh flex-col gap-2 px-3 pt-3 pb-2 sm:px-5 sm:pt-5 print:p-0">
      <SheetFrame className="flex-1">
        <div className={`px-4 py-6 sm:px-8 sm:py-8 print:p-0 ${className}`}>{children}</div>
      </SheetFrame>
      <footer className="flex justify-end px-1 text-sm text-ink-muted print:hidden">
        <Link href="/privacy" className="px-2 py-1 underline decoration-ink/30 underline-offset-4 hover:text-ink hover:decoration-ink">
          Privacy policy
        </Link>
      </footer>
    </main>
  );
}
