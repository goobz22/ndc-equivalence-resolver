import Link from "next/link";
import { SearchBox } from "@/components/SearchBox";

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <h1>
          Your pharmacy says your drug is out. Here is the rest of the
          picture.
        </h1>
        <p className="lede">
          US pharmacies stock medications by NDC — a code tied to one
          manufacturer&apos;s product. When that exact code is on back order,
          FDA-rated equivalents from other manufacturers often are not — and
          the official shortage list is voluntary and lagging, so real supply
          strain often never appears on it. For any drug, this tool shows
          both: the substitutable alternatives (what a pharmacist can swap on
          the spot, and what a prescriber could authorize), and independent
          supply-stress evidence drawn from public price, survey, demand, and
          recall data — whether or not the official list has caught up. Built
          entirely from public FDA, NLM, and CMS data, with every number
          traced to its source.
        </p>
        <SearchBox autoFocus />
        <div className="example-chips">
          <span style={{ fontSize: "0.85rem", color: "var(--ink-soft)" }}>
            Try:
          </span>
          <Link href="/ndc/0378-4642-26">0378-4642-26 (estradiol patch, Mylan)</Link>
          <Link href="/compare/00378464226/65162014908">
            why Lyllana is NOT a direct swap
          </Link>
          <Link href="/browse?q=estradiol">browse estradiol products</Link>
        </div>
      </section>

      <section className="tier-section">
        <h2>How to read the results</h2>
        <div className="card">
          <h3>Tier 1 — Direct substitutes</h3>
          <p className="sub">
            Same FDA therapeutic-equivalence subgroup (the full three-character
            Orange Book code), same strength, same schedule, same package. In
            most states a pharmacist can substitute these without calling your
            prescriber. This is the list to read to the pharmacy over the
            counter: &quot;do you have any of these?&quot;
          </p>
        </div>
        <div className="card">
          <h3>Tier 2 — Same drug, different package</h3>
          <p className="sub">
            Therapeutically equivalent, but the prescription quantity needs
            adjusting (for example an 8-count versus a 24-count carton).
          </p>
        </div>
        <div className="card">
          <h3>Tier 3 — Requires prescriber authorization</h3>
          <p className="sub">
            Same medicine family, but a different equivalence subgroup,
            schedule, or strength. A prescriber must write a new or amended
            prescription naming the product — each result explains exactly why
            and links to a printable note you can hand them.
          </p>
        </div>
        <div className="card">
          <h3>Tier 4 — Different delivery form</h3>
          <p className="sub">
            Same molecule as a gel, spray, or tablet. Informational only —
            switching routes is a clinical decision for your prescriber.
          </p>
        </div>
      </section>

      <section className="tier-section">
        <h2>What this is (and is not)</h2>
        <div className="card">
          <p className="sub">
            This resolver holds the public equivalence and supply graph — the
            FDA NDC Directory, FDA Orange Book therapeutic-equivalence codes,
            RxNorm, openFDA shortage records, NADAC weekly pharmacy
            acquisition costs, Medicaid state drug utilization volumes, and
            FDA recall enforcement reports — joined the way no retail system
            exposes. It does NOT know any store&apos;s live inventory, and its
            supply-stress indicators are inferences from public signals —
            evidence consistent with strain, never availability claims and
            never a confirmed shortage. No account, no tracking, no patient
            data.
          </p>
        </div>
      </section>
    </>
  );
}
