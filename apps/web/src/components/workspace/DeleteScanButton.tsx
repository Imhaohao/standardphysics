"use client";

import { Trash } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";

/**
 * Removing one shop, from the page that shows it.
 *
 * The phone could already do this and the workspace could not, so a scan taken
 * on a phone that is no longer to hand could only be removed by deleting the
 * whole account.
 *
 * Asks in place rather than in a dialog, so the consequence is on screen beside
 * the button that carries it out. A room still being measured cannot be
 * deleted, and the server says so in its own words rather than ours, because it
 * knows which job is holding it.
 */
export function DeleteScanButton({ scanId, name }: { scanId: string; name: string }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [failure, setFailure] = useState("");

  async function deleteScan() {
    setDeleting(true);
    setFailure("");
    const response = await fetch(`/api/scans/${scanId}`, { method: "DELETE" });
    if (!response.ok) {
      setDeleting(false);
      setFailure(await refusal(response));
      return;
    }
    router.replace("/");
    router.refresh();
  }

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-ink-muted hover:bg-problem/10 hover:text-problem"
      >
        <Trash size={16} weight="bold" aria-hidden />
        Delete
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <p className="text-sm text-ink-muted">
        Delete {name}? The room, the walkthrough and every finding go with it.
      </p>
      <Button squared variant="danger" onClick={deleteScan} disabled={deleting}>
        <Trash size={18} aria-hidden />
        {deleting ? "Deleting" : "Delete it"}
      </Button>
      <Button squared onClick={() => setConfirming(false)} disabled={deleting}>
        Keep it
      </Button>
      {failure ? (
        <p className="w-full text-sm text-problem" role="alert">
          {failure}
        </p>
      ) : null}
    </div>
  );
}

/** What the server said, when it said anything a person can act on. */
async function refusal(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string" && body.detail) return body.detail;
    if (typeof body?.error === "string" && body.error) return body.error;
  } catch {
    // A refusal with no readable body still has to say something.
  }
  return "Unable to delete this shop. Check your connection and try again.";
}
