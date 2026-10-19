import { ArrowRight, SignIn, SignOut } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { signOut } from "@/app/sign-in/actions";
import { buttonClassName } from "@/components/ui/Button";
import { SheetField } from "@/components/sheet/SheetField";

/** The title block in the sheet's corner. It carries the account, or the way in for someone without one. */
export function HomeTitleBlock({ signedIn, className = "" }: { signedIn: boolean; className?: string }) {
  return (
    <section aria-label="Title block" data-ink-avoid className={`border border-ink bg-paper ${className}`}>
      <p className="heading-display border-b border-ink px-4 py-3 text-2xl">Standard Physics</p>
      {signedIn ? <SignedInActions /> : <SignInCallToAction />}
    </section>
  );
}

function SignInCallToAction() {
  return (
    <>
      <p className="border-b border-ink px-4 py-3 text-ink-muted text-pretty">
        Scan your shop with an iPhone and we&rsquo;ll check every aisle, door and counter against the ADA and California
        rules.
      </p>
      <div className="flex flex-col items-start gap-3 p-4">
        <Link href="/sign-in" className={buttonClassName("primary")}>
          <SignIn size={18} aria-hidden />
          Sign in to see your shops
        </Link>
        <Link href="/shops" className={`-ms-3 ${buttonClassName("quiet")}`}>
          Look around the sample shop
          <ArrowRight size={16} aria-hidden />
        </Link>
      </div>
    </>
  );
}

function SignedInActions() {
  return (
    <>
      <dl>
        <SheetField label="Sheet set" className="border-b border-ink py-3">
          Your shops
        </SheetField>
      </dl>
      <div className="flex flex-col items-start gap-3 p-4">
        <Link href="/shops" className={buttonClassName("primary")}>
          See all your shops
          <ArrowRight size={18} aria-hidden />
        </Link>
        <form action={signOut}>
          <button type="submit" className={`-ms-3 ${buttonClassName("quiet")}`}>
            <SignOut size={18} aria-hidden />
            Sign out
          </button>
        </form>
      </div>
    </>
  );
}
