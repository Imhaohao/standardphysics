import type { ReactNode } from "react";
import { SheetFrame } from "./SheetFrame";

/** The paper margin and sheet frame every page sits in. */
export function SheetPage({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <main className="flex min-h-dvh px-3 py-3 sm:px-5 sm:py-5 print:p-0">
      <SheetFrame className="flex-1">
        <div className={`px-4 py-6 sm:px-8 sm:py-8 print:p-0 ${className}`}>{children}</div>
      </SheetFrame>
    </main>
  );
}
