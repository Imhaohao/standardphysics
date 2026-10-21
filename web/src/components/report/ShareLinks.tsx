"use client";

import { Copy, LinkSimple, LinkBreak } from "@phosphor-icons/react";
import { useState, useTransition } from "react";
import { createShare, stopSharing } from "@/app/shops/actions";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import type { Share } from "@/lib/api/types";
import { sharePath } from "@/lib/share";

const dateFormat = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

type Result = { tone: "error" | "done"; text: string } | null;

const shareUrl = (token: string) => new URL(sharePath(token), window.location.origin).toString();

async function copied(token: string): Promise<Result> {
  try {
    await navigator.clipboard.writeText(shareUrl(token));
    return { tone: "done", text: "Link copied. Anyone you send it to can read the report without signing in." };
  } catch {
    return { tone: "error", text: "Your browser didn’t let us copy the link. Open it below and copy it from the address bar." };
  }
}

function ShareRow({ share, onCopy, onStop, pending }: { share: Share; onCopy: () => void; onStop: () => void; pending: boolean }) {
  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <span className="flex min-w-0 flex-col">
        <a href={sharePath(share.token)} className="measurement truncate text-sm underline decoration-ink/30 underline-offset-4 hover:decoration-ink">
          {sharePath(share.token)}
        </a>
        <span className="text-sm text-ink-muted">Shared {dateFormat.format(new Date(share.created_at))}</span>
      </span>
      <span className="flex shrink-0 gap-1 sm:-me-3">
        <Button onClick={onCopy} className="-ms-3 sm:ms-0">
          <Copy size={16} aria-hidden />
          Copy link
        </Button>
        <Button onClick={onStop} disabled={pending} className="hover:text-problem">
          <LinkBreak size={16} aria-hidden />
          Stop sharing
        </Button>
      </span>
    </li>
  );
}

/** Read-only links to the report: make one and copy it, or turn an old one off. */
export function ShareLinks({ scanId, initialShares }: { scanId: string; initialShares: Share[] }) {
  const [shares, setShares] = useState(initialShares);
  const [result, setResult] = useState<Result>(null);
  const [pending, startTransition] = useTransition();

  const share = () =>
    startTransition(async () => {
      const created = await createShare(scanId);
      if (!created.share) return setResult({ tone: "error", text: created.error });
      setShares((current) => [created.share, ...current]);
      setResult(await copied(created.share.token));
    });

  const stop = (token: string) =>
    startTransition(async () => {
      const error = await stopSharing(scanId, token);
      if (!error) setShares((current) => current.filter((candidate) => candidate.token !== token));
      setResult(error ? { tone: "error", text: error } : { tone: "done", text: "That link no longer opens the report." });
    });

  return (
    <section aria-label="Read-only links" data-ink-avoid className="border border-ink bg-paper print:hidden">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <Button variant="outline" onClick={share} disabled={pending}>
          <LinkSimple size={18} aria-hidden />
          {pending ? "Making a link" : "Share a read-only link"}
        </Button>
        {result && <Notice tone={result.tone}>{result.text}</Notice>}
      </div>
      {shares.length > 0 && (
        <ul className="divide-y divide-ink/20 border-t border-ink">
          {shares.map((entry) => (
            <ShareRow key={entry.token} share={entry} pending={pending} onCopy={() => copied(entry.token).then(setResult)} onStop={() => stop(entry.token)} />
          ))}
        </ul>
      )}
    </section>
  );
}
