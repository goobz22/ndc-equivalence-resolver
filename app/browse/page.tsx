"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, SearchResult } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";

function BrowseResults() {
  const searchParams = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    api
      .search(query)
      .then((payload) => setResults(payload.results))
      .catch((problem: Error) => setError(problem.message));
  }, [query]);

  if (error) return <div className="error-box">{error}</div>;
  if (!query) {
    return (
      <p className="tier-sub">
        Search by drug name (brand or generic) or NDC fragment to browse the
        products this database knows about.
      </p>
    );
  }
  if (!results) return <div className="loading">Searching…</div>;
  if (results.length === 0) {
    return (
      <p className="tier-sub">
        Nothing matched &quot;{query}&quot;. Try the generic name, or an NDC
        with hyphens as printed on the package.
      </p>
    );
  }

  return (
    <>
      <p className="tier-sub">
        {results.length} package{results.length === 1 ? "" : "s"} matching
        &quot;{query}&quot; — click one to resolve its equivalents.
      </p>
      {results.map((result) => (
        <div className="card" key={result.ndc11}>
          <h3>
            <Link href={`/ndc/${result.ndc11}`}>
              {[result.name, result.name_suffix].filter(Boolean).join(" ") ||
                result.generic_name ||
                "(unnamed)"}
            </Link>{" "}
            <span className="sub">{result.ndc_as_filed}</span>
          </h3>
          <div className="sub">
            {result.generic_name} · {result.labeler}
          </div>
          <div className="row">
            {result.strength ? (
              <span className="badge">{result.strength}</span>
            ) : null}
            {result.dosage_form ? (
              <span className="badge">{result.dosage_form.toLowerCase()}</span>
            ) : null}
            {result.pack_count ? (
              <span className="badge">{result.pack_count}-count</span>
            ) : null}
          </div>
        </div>
      ))}
    </>
  );
}

export default function BrowsePage() {
  return (
    <section className="tier-section">
      <h2>Browse products</h2>
      <SearchBox />
      <div style={{ marginTop: "1.25rem" }}>
        <Suspense fallback={<div className="loading">Loading…</div>}>
          <BrowseResults />
        </Suspense>
      </div>
    </section>
  );
}
