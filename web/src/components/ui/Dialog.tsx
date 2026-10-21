"use client";

import { useId, useState, useTransition, type ReactNode } from "react";
import { Button } from "./Button";
import { INPUT_CLASS } from "./Field";
import { Notice } from "./Notice";

/** A handle on a native modal dialog: focus moves in on open, Escape closes it and the page behind goes inert. */
export function useDialog() {
  const [element, setElement] = useState<HTMLDialogElement | null>(null);
  return { dialogProps: { ref: setElement },  open: () => element?.showModal(), close: () => element?.close() };
}

export type DialogHandle = ReturnType<typeof useDialog>;

/** A sheet of paper laid over the page, square like everything else on the drawing. */
export function Dialog({ dialog, title, onClose, children }: { dialog: DialogHandle; title: string; onClose?: () => void; children: ReactNode }) {
  const titleId = useId();
  return (
    <dialog {...dialog.dialogProps} aria-labelledby={titleId} onClose={onClose} className="m-auto w-[min(32rem,calc(100vw-2rem))] border-2 border-ink bg-paper p-0 text-ink shadow-float backdrop:bg-ink/40">
      <h2 id={titleId} className="heading-display border-b border-ink px-5 py-4 text-2xl">
        {title}
      </h2>
      <div className="flex flex-col gap-4 px-5 py-5">{children}</div>
    </dialog>
  );
}

/** Cancel on the left of the dialog's main action, the way the rest of the site reads. */
export function DialogActions({ dialog, children }: { dialog: DialogHandle; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-end gap-3 pt-1">
      <Button variant="outline" onClick={dialog.close}>
        Cancel
      </Button>
      {children}
    </div>
  );
}

interface ConfirmDialogProps {
  dialog: DialogHandle;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  pendingLabel: string;
  /** For an action that can't be undone: the confirm button stays off until this phrase is typed. */
  confirmPhrase?: string;
  /** Resolves to an error to show, or null when it worked. */
  onConfirm: () => Promise<string | null>;
}

/** Asks before something destructive, and says what went wrong if it didn't work. */
export function ConfirmDialog({ dialog, title, children, confirmLabel, pendingLabel, confirmPhrase, onConfirm }: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const ready = !confirmPhrase || typed.trim().toLowerCase() === confirmPhrase;

  const confirm = () => startTransition(async () => setError(await onConfirm()));
  const reset = () => {
    setTyped("");
    setError(null);
  };

  return (
    <Dialog dialog={dialog} title={title} onClose={reset}>
      <div className="flex flex-col gap-3 text-pretty">{children}</div>
      {confirmPhrase && (
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Type &ldquo;{confirmPhrase}&rdquo; to confirm</span>
          <input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" className={INPUT_CLASS} />
        </label>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <DialogActions dialog={dialog}>
        <Button variant="danger" onClick={confirm} disabled={!ready || pending}>
          {pending ? pendingLabel : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
