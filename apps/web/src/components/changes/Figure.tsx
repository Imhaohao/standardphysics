/** A number inside a sentence or a fact: the body face with even-width digits, so it reads as part of the line. */
export function Figure({ children }: { children: string }) {
  return <span className="font-medium tabular-nums text-ink">{children}</span>;
}
