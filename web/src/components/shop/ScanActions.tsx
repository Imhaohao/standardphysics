"use client";

import { PencilSimple, Trash } from "@phosphor-icons/react";
import { useState, useTransition, type FormEvent } from "react";
import { deleteScan, renameScan } from "@/app/shops/actions";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog, DialogActions, useDialog, type DialogHandle } from "@/components/ui/Dialog";
import { TextField } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

interface ScanNames {
  scanId: string;
  name: string;
  siteName: string | null;
}

function RenameDialog({ dialog, scan }: { dialog: DialogHandle; scan: ScanNames }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    startTransition(async () => {
      const failure = await renameScan(scan.scanId, String(form.get("name") ?? ""), String(form.get("site_name") ?? ""));
      setError(failure);
      if (!failure) dialog.close();
    });
  }

  return (
    <Dialog dialog={dialog} title="Rename this scan" onClose={() => setError(null)}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextField label="Shop name" hint="Shown on your list of shops and at the top of the report." name="site_name" defaultValue={scan.siteName ?? ""} autoComplete="organization" />
        <TextField label="Scan name" hint="Helps tell scans apart when you scan the same shop more than once." name="name" defaultValue={scan.name} required />
        {error && <Notice tone="error">{error}</Notice>}
        <DialogActions dialog={dialog}>
          <Button type="submit" variant="primary" disabled={pending}>
            {pending ? "Saving" : "Save names"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

/** Renaming and deleting a scan, from the top of its page. */
export function ScanActions(scan: ScanNames) {
  const rename = useDialog();
  const remove = useDialog();
  return (
    <>
      <Button variant="outline" onClick={rename.open}>
        <PencilSimple size={18} aria-hidden />
        Rename
      </Button>
      <Button variant="danger" onClick={remove.open}>
        <Trash size={18} aria-hidden />
        Delete scan
      </Button>
      <RenameDialog dialog={rename} scan={scan} />
      <ConfirmDialog dialog={remove} title="Delete this scan?" confirmLabel="Delete scan" pendingLabel="Deleting" onConfirm={() => deleteScan(scan.scanId)}>
        <p>This removes the floor plan, the 3D model, the report, your answers and any read-only links to it.</p>
        <p className="font-semibold">You can&rsquo;t undo this.</p>
      </ConfirmDialog>
    </>
  );
}
