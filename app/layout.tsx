import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { MetaFooter } from "@/components/MetaFooter";

export const metadata: Metadata = {
  title: "NDC Equivalence Resolver",
  description:
    "When your pharmacy is out of your medication: the same drug from other manufacturers, what a pharmacist can swap directly, and what your prescriber needs to write to unlock the rest. Built entirely from public FDA, NLM, and CMS data.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="inner">
            <Link href="/" className="brand">
              NDC Equivalence Resolver
            </Link>
            <nav>
              <Link href="/browse">Browse</Link>
              <Link href="/gaps">Supply gaps</Link>
              <Link href="/sources">Sources</Link>
              <a
                href="https://github.com/goobz22/ndc-equivalence-resolver"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main>
          {children}
          <p className="disclaimer">
            This tool surfaces supply-chain equivalence facts from public
            FDA/NLM/CMS data. It is not medical advice; substitution decisions
            belong to your pharmacist and prescriber. Supply-stress indicators
            are inferences from public signals — evidence consistent with
            strain, never statements of availability and never a confirmed
            shortage. Every figure shown is traceable to a public federal
            dataset with its fetch date and checksum — see{" "}
            <Link href="/sources">Sources</Link>. All source data is the work
            of U.S. government agencies (public domain / open data); this
            site&apos;s code is open source under the MIT license and provided
            as-is, without warranty. This product uses publicly available data
            from the U.S. National Library of Medicine (NLM), National
            Institutes of Health; NLM is not responsible for the product and
            does not endorse or recommend it. No account, no tracking, no
            patient data.
          </p>
          <MetaFooter />
        </main>
      </body>
    </html>
  );
}
