import Link from "next/link";
import type { ReactNode } from "react";

export const LEGAL_CONTACT = "privacy@standardphysics.app";

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="heading-display text-2xl">{heading}</h2>
      <div className="mt-3 flex flex-col gap-3 text-ink-muted">{children}</div>
    </section>
  );
}

export function ContactLink() {
  return (
    <a className="underline decoration-rule underline-offset-2" href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a>
  );
}

/** A plain-language policy page: its title, when it last changed, and its sections. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <main className="mx-auto max-w-3xl px-5 py-10">
      <h1 className="heading-display text-4xl">{title}</h1>
      <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-ink-muted">
        <dt>Last updated</dt>
        <dd className="text-ink">{updated}</dd>
      </dl>
      {children}
      <p className="mt-12 text-ink-muted">
        <Link className="underline decoration-rule underline-offset-2" href="/">Back to your shops</Link>
      </p>
    </main>
  );
}
