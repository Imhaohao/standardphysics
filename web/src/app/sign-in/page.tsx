import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SheetPage } from "@/components/sheet/SheetPage";
import { sessionToken } from "@/lib/session";
import { SignInForm } from "./SignInForm";

export const metadata: Metadata = { title: "Sign in to Standard Physics" };

export default async function SignInPage() {
  if (await sessionToken()) redirect("/shops");
  return (
    <SheetPage className="grid gap-10 lg:min-h-full lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-center lg:gap-16">
      <div className="flex min-w-0 flex-col gap-6">
        <h1 className="heading-display text-5xl sm:text-7xl">Standard Physics</h1>
        <p className="max-w-lg text-lg text-ink-muted text-pretty">
          Walk your shop with an iPhone. We measure every aisle, doorway and counter against the accessibility rules that
          apply to it, and show you what to move when something is too tight.
        </p>
      </div>
      <SignInForm />
    </SheetPage>
  );
}
