import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { SHEET_GRID_CLASS, SheetField } from "@/components/sheet/SheetField";
import { SheetPage } from "@/components/sheet/SheetPage";
import { ShopHeader } from "@/components/shop/ShopHeader";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: "What Standard Physics collects when you scan your shop, where it's kept, who else handles it and how to delete it.",
};

const CONTACT = "tyadgirkar@gmail.com";

const COLLECTED: { what: string; from: string; kept: string }[] = [
  { what: "Your email address and a scrambled (hashed) copy of your password", from: "Creating an account with an email", kept: "Our database" },
  { what: "An Apple account ID, plus an email if Apple shares one (it may be a private relay address)", from: "Sign in with Apple", kept: "Our database" },
  { what: "Sign-in sessions, stored as a hash of the session token, with when each was last used", from: "Signing in on the app or this website", kept: "Our database, for up to 90 days per session" },
  { what: "The names you give a scan and your shop", from: "You", kept: "Our database" },
  { what: "Room geometry from Apple's RoomPlan: walls, doors, windows, furniture boxes and their sizes", from: "Scanning with the app", kept: "Our database and our file storage" },
  { what: "The LiDAR mesh, a 3D surface of the space you scanned", from: "Scanning with the app", kept: "Our file storage" },
  { what: "Small photos (crops) of individual objects the app couldn't name on its own", from: "Scanning with the app", kept: "Our file storage" },
  { what: "Photos you take in the app to answer one of the report's questions", from: "You", kept: "Our file storage" },
  { what: "Your answers to the report's questions, and whether an answer came from you or was read from a photo", from: "You", kept: "Our database" },
  { what: "The findings we work out from all of the above", from: "Our rules engine", kept: "Our database" },
];

const PROVIDERS: { name: string; role: string }[] = [
  { name: "Neon", role: "Hosts our Postgres database, which holds your account, scan details, answers and findings." },
  { name: "Cloudflare R2", role: "Stores the files the app uploads: RoomPlan room files, LiDAR meshes and photos." },
  { name: "Modal", role: "Runs our server, which receives your scans and checks them against the rules." },
  { name: "An AI model provider", role: "When AI reading is switched on, we send it an object photo to ask what the object is, or a photo you took to answer a question. It gets the photo only, without your name or email." },
  { name: "Apple", role: "Handles Sign in with Apple if you use it, under Apple's own privacy policy." },
];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h2 id={id} className="heading-display text-3xl">
        {title}
      </h2>
      <div className="flex max-w-3xl flex-col gap-3 text-pretty">{children}</div>
    </section>
  );
}

function CollectedTable() {
  return (
    <div data-ink-avoid className="overflow-x-auto border border-ink bg-paper">
      <table className="w-full min-w-[40rem] border-collapse text-left">
        <thead>
          <tr className="border-b border-ink text-sm text-ink-muted">
            <th scope="col" className="w-1/2 px-3 py-2 font-medium">What</th>
            <th scope="col" className="px-3 py-2 font-medium">Where it comes from</th>
            <th scope="col" className="px-3 py-2 font-medium">Where it&rsquo;s kept</th>
          </tr>
        </thead>
        <tbody>
          {COLLECTED.map((row) => (
            <tr key={row.what} className="border-b border-ink/20 last:border-b-0">
              <td className="px-3 py-3 align-top text-pretty">{row.what}</td>
              <td className="px-3 py-3 align-top text-ink-muted">{row.from}</td>
              <td className="px-3 py-3 align-top text-ink-muted">{row.kept}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderList() {
  return (
    <dl data-ink-avoid className="max-w-3xl divide-y divide-ink/20 border border-ink bg-paper">
      {PROVIDERS.map((provider) => (
        <div key={provider.name} className="grid gap-1 px-4 py-3 sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-4">
          <dt className="font-semibold">{provider.name}</dt>
          <dd className="text-pretty">{provider.role}</dd>
        </div>
      ))}
    </dl>
  );
}

const linkClass = "font-medium underline decoration-ink/30 underline-offset-4 hover:decoration-ink";

export default function PrivacyPage() {
  return (
    <SheetPage className="flex flex-col gap-10">
      <ShopHeader backHref="/" backLabel="Home" title="Privacy policy" />
      <dl data-ink-avoid className={`${SHEET_GRID_CLASS} max-w-xl border border-ink *:bg-paper sm:grid-cols-2`}>
        <SheetField label="Last updated">21 October 2026</SheetField>
        <SheetField label="Questions">
          <a href={`mailto:${CONTACT}`} className={linkClass}>
            {CONTACT}
          </a>
        </SheetField>
      </dl>
      <p className="-mt-4 max-w-3xl text-lg text-pretty">
        Standard Physics measures your shop with an iPhone and checks it against the ADA and California accessibility rules. To do that we need
        your scans, and this page explains what that means for your data. We&rsquo;ve tried to write it plainly.
      </p>

      <Section id="collected" title="What we collect">
        <p>We only collect what the app and this website need to make and show your report.</p>
        <CollectedTable />
        <p>
          The app uses the camera and LiDAR scanner while you scan. The camera feed is processed on your iPhone to recognise objects, and we
          don&rsquo;t upload video or full photos of your shop. The only images that leave your phone are the object crops and the answer photos in the table above.
          To let you pick up an interrupted scan, the app keeps a map of the room and one small snapshot on your phone, protected by iOS file
          encryption. Those stay on the device.
        </p>
      </Section>

      <Section id="not-collected" title="What we don't do">
        <p>
          We don&rsquo;t show ads, and we don&rsquo;t sell or rent your data to anyone. We don&rsquo;t use analytics or tracking tools in the app or on
          this website. The website sets one cookie, which keeps you signed in, and it can&rsquo;t be read by scripts on the page.
        </p>
      </Section>

      <Section id="use" title="How we use it">
        <p>
          We use your scans to build the floor plan and 3D model, measure each element and check it against the 2010 ADA Standards and California
          Building Code Chapter 11B. Your answers to the report&rsquo;s questions fill in what the scan couldn&rsquo;t measure. We use your email to
          sign you in, and we don&rsquo;t send marketing email.
        </p>
      </Section>

      <Section id="providers" title="Who else handles it">
        <p>These companies process data on our behalf to run the service. None of them gets your data to use for their own purposes.</p>
        <ProviderList />
      </Section>

      <Section id="sharing" title="Read-only links">
        <p>
          If you make a read-only link to a report, anyone with that link can see the shop and scan names, the floor plan, the findings and the
          open questions, without signing in. They can&rsquo;t see your email, your answers list or your other scans. Choosing Stop sharing turns
          the link off straight away.
        </p>
      </Section>

      <Section id="deleting" title="Deleting your data">
        <p>
          You can delete a single scan from its page. That removes its database records and the files we stored for it. To delete everything,
          sign in on the <Link href="/" className={linkClass}>home page</Link> and choose Delete account. That removes your account, your
          sign-in sessions, every scan, your answers, your read-only links and all stored files. You can also email us and we&rsquo;ll do it for you.
        </p>
        <p>
          Otherwise we keep your data for as long as you have an account. Our database provider keeps a short rolling history for recovery, so a
          deleted record can linger there until that history rolls over.
        </p>
      </Section>

      <Section id="children" title="Children">
        <p>Standard Physics is a tool for businesses. It isn&rsquo;t meant for children, and we don&rsquo;t knowingly collect data from anyone under 13.</p>
      </Section>

      <Section id="changes" title="Changes and contact">
        <p>
          If we change what we collect or who handles it, we&rsquo;ll update this page and its date. Questions, or a request to see or delete your data,
          can go to{" "}
          <a href={`mailto:${CONTACT}`} className={linkClass}>
            {CONTACT}
          </a>
          .
        </p>
      </Section>
    </SheetPage>
  );
}
