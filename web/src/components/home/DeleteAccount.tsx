"use client";

import { Trash } from "@phosphor-icons/react";
import Link from "next/link";
import { deleteAccount } from "@/app/sign-in/actions";
import { buttonClassName } from "@/components/ui/Button";
import { ConfirmDialog, useDialog } from "@/components/ui/Dialog";

/** Deleting the account for good, behind a typed confirmation. */
export function DeleteAccount() {
  const dialog = useDialog();
  return (
    <>
      <button type="button" onClick={dialog.open} className={`-ms-3 ${buttonClassName("quiet")} hover:text-problem`}>
        <Trash size={18} aria-hidden />
        Delete account
      </button>
      <ConfirmDialog dialog={dialog} title="Delete your account?" confirmLabel="Delete my account" pendingLabel="Deleting your account" confirmPhrase="delete" onConfirm={deleteAccount}>
        <p>
          This deletes your account and every scan in it: floor plans, 3D models, photos, reports, your answers and any read-only links you&rsquo;ve
          shared. You&rsquo;ll be signed out on the web and in the iPhone app.
        </p>
        <p className="font-semibold">You can&rsquo;t undo this, and we can&rsquo;t bring any of it back.</p>
        <p className="text-sm text-ink-muted">
          Our{" "}
          <Link href="/privacy" className="underline underline-offset-4">
            privacy policy
          </Link>{" "}
          says what we keep and for how long.
        </p>
      </ConfirmDialog>
    </>
  );
}
