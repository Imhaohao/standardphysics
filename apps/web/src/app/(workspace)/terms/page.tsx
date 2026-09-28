import type { Metadata } from "next";
import Link from "next/link";
import { ContactLink, LegalPage, LegalSection } from "@/components/legal/LegalPage";

export const metadata: Metadata = {
  title: "Terms of use for Standard Physics",
  description: "What Standard Physics checks, what it cannot promise, and what you agree to when you use it.",
};

const UPDATED = "September 28, 2026";

export default function TermsPage() {
  return (
    <LegalPage title="Terms of use" updated={UPDATED}>
      <LegalSection heading="What Standard Physics does">
        <p>
          You walk your shop with the app. We measure the scan, compare what we measured against the 2010 ADA
          Standards for Accessible Design, and show you what fails and what you could move to fix it. Using the app
          or the workspace means you agree to these terms.
        </p>
      </LegalSection>

      <LegalSection heading="What a report can and cannot tell you">
        <p>
          A report covers what the scan could see and the rules we check. Anything out of the phone&apos;s view, and
          any rule we do not check yet, is not in it. Where we could not measure something, the report asks you for a
          photo or a number instead of guessing.
        </p>
        <p>
          A report is not an inspection, a certification or legal advice. Only a Certified Access Specialist can
          inspect your shop in person, and only their report carries legal weight. The money and time figures in a
          report come from the sources it names, and they describe what the law and published turnarounds say, not
          what will happen to your shop.
        </p>
      </LegalSection>

      <LegalSection heading="Layouts and 3D models">
        <p>
          A layout you save is a plan. It never changes the shop as scanned, and it is checked against the same rules
          as the scan. Before you move anything built in, or start construction, check the plan with an architect or
          contractor.
        </p>
        <p>
          The report, its drawings and the 3D model files are yours to use for your shop, including handing them to an
          architect, a contractor or an inspector. The 3D model is every measured piece drawn as a box at its measured
          size, so it is a starting point for drawings, not a survey.
        </p>
      </LegalSection>

      <LegalSection heading="What you agree to">
        <p>
          Only scan a space you have the right to scan. The photos a scan takes show whoever is in the room, so choose
          a time when that is fine with them. Keep your account&apos;s password to yourself, and only send us photos and
          measurements of your own shop.
        </p>
        <p>
          When you share a report, anyone with the link can open it and download its model for 30 days. You decide who
          gets the link, and you can stop it sooner.
        </p>
      </LegalSection>

      <LegalSection heading="Your data">
        <p>
          How we store, use and delete your scans and your account is on the{" "}
          <Link className="underline decoration-rule underline-offset-2" href="/privacy">privacy page</Link>.
        </p>
      </LegalSection>

      <LegalSection heading="Changes and questions">
        <p>
          When these terms change, the date at the top changes with them. Write to <ContactLink /> with any question
          about them.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
