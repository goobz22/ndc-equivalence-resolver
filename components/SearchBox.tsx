"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export function SearchBox({ autoFocus = false }: { autoFocus?: boolean }) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const query = value.trim();
    if (!query) return;
    setBusy(true);
    setError(null);
    // NDC-shaped input goes straight to resolution; anything else to search.
    const looksLikeNdc = /^[\d-]{9,13}$/.test(query);
    try {
      if (looksLikeNdc) {
        await api.resolve(query); // validates + 404s early with a clear message
        router.push(`/ndc/${encodeURIComponent(query)}`);
      } else {
        router.push(`/browse?q=${encodeURIComponent(query)}`);
      }
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
      setBusy(false);
    }
  }

  return (
    <form className="search-box" onSubmit={submit}>
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="NDC (e.g. 0378-4642-26) or drug name (e.g. estradiol)"
        aria-label="NDC or drug name"
        autoFocus={autoFocus}
      />
      <button type="submit" disabled={busy}>
        {busy ? "Looking up…" : "Look up"}
      </button>
      {error ? <div className="error-box">{error}</div> : null}
    </form>
  );
}
