"use client";

import { useState } from "react";

interface Pharmacy {
  name: string;
  kind: string;
  address: string;
  city: string | null;
  state: string | null;
  zip: string;
  phone: string | null;
}

interface PharmaciesPayload {
  zip: string;
  widened: boolean;
  pharmacies: Pharmacy[];
  attribution: string;
  note: string;
}

export interface CallScriptAlternative {
  ndc: string;
  name: string | null;
}

// PRIVACY: the ZIP goes into ONE API query (server proxies a single
// public NPI Registry call) and is never stored or logged (SPEC §17).
export function GetItFilled({
  alternatives,
}: {
  alternatives: CallScriptAlternative[];
}) {
  const [zip, setZip] = useState("");
  const [payload, setPayload] = useState<PharmaciesPayload | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [copied, setCopied] = useState(false);

  const scriptAlternatives = alternatives.slice(0, 6);
  const callScript =
    "My prescription is out of stock. Do you have any of these FDA-rated " +
    "equivalent NDCs in stock, or orderable from your wholesaler today: " +
    scriptAlternatives
      .map((alt) => `${alt.name ?? "equivalent"} (NDC ${alt.ndc})`)
      .join("; ") +
    "?";

  async function lookup() {
    if (!/^\d{5}$/.test(zip)) return;
    setStatus("loading");
    setPayload(null);
    try {
      const response = await fetch(`/api/pharmacies?zip=${zip}`);
      if (!response.ok) throw new Error(String(response.status));
      setPayload((await response.json()) as PharmaciesPayload);
      setStatus("idle");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section className="tier-section">
      <h2>Get it filled near you</h2>
      <p className="tier-sub">
        Pharmacies from the public CMS NPI Registry — a registration list,
        not a stock claim. Call first; the script below is the
        conversation.
      </p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <input
          inputMode="numeric"
          pattern="\d{5}"
          maxLength={5}
          placeholder="ZIP code"
          value={zip}
          onChange={(event) =>
            setZip(event.target.value.replace(/\D/g, "").slice(0, 5))
          }
          onKeyDown={(event) => {
            if (event.key === "Enter") void lookup();
          }}
          aria-label="ZIP code"
        />
        <button
          type="button"
          onClick={() => void lookup()}
          disabled={!/^\d{5}$/.test(zip) || status === "loading"}
        >
          {status === "loading" ? "Searching…" : "Find pharmacies"}
        </button>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(callScript).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            });
          }}
        >
          {copied ? "Copied" : "Copy call script"}
        </button>
      </div>
      <p className="tier-sub" style={{ marginTop: "0.5rem" }}>
        “{callScript}”
      </p>
      {status === "error" ? (
        <p className="tier-sub">
          The registry lookup is unavailable right now — try again in a
          minute.
        </p>
      ) : null}
      {payload ? (
        payload.pharmacies.length === 0 ? (
          <p className="tier-sub">
            No pharmacy registrations found for {payload.zip}
            {payload.widened ? " (even after widening the search area)" : ""}.
          </p>
        ) : (
          <>
            {payload.widened ? (
              <p className="tier-sub">
                No exact-ZIP results — showing the wider {zip.slice(0, 3)}xx
                area.
              </p>
            ) : null}
            <ul>
              {payload.pharmacies.slice(0, 15).map((pharmacy) => (
                <li key={`${pharmacy.name}-${pharmacy.address}`}>
                  <b>{pharmacy.name}</b>
                  {pharmacy.kind !== "retail" && pharmacy.kind !== "pharmacy"
                    ? ` (${pharmacy.kind})`
                    : ""}{" "}
                  — {pharmacy.address}, {pharmacy.city}, {pharmacy.state}{" "}
                  {pharmacy.zip}
                  {pharmacy.phone ? (
                    <>
                      {" · "}
                      <a href={`tel:${pharmacy.phone}`}>{pharmacy.phone}</a>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
            <p className="tier-sub" style={{ fontSize: "0.75rem" }}>
              {payload.attribution} {payload.note}
            </p>
          </>
        )
      ) : null}
    </section>
  );
}
