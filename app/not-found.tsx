import Link from "next/link";

export default function NotFound() {
  return (
    <section className="tier-section">
      <h2>Not found</h2>
      <p className="tier-sub">
        No product or drug class lives at this address — the code may be
        mistyped, or the product may have left the current FDA directory
        (this site tracks the LATEST weekly data).
      </p>
      <p>
        <Link href="/browse">Search by name, strength, or NDC →</Link>
      </p>
    </section>
  );
}
