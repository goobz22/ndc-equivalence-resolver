"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

// Stateless by design (SPEC §17: no accounts, no storage): the chosen
// state lives in the URL, so the note stays shareable and printable
// with its state rule attached, and nothing is remembered.
function PickerInner({ states }: { states: { state: string; name: string }[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const current = searchParams.get("state") ?? "";
  return (
    <label style={{ fontSize: "0.85rem" }}>
      Your state:{" "}
      <select
        value={current}
        onChange={(event) => {
          const next = new URLSearchParams(searchParams.toString());
          if (event.target.value) next.set("state", event.target.value);
          else next.delete("state");
          router.replace(`?${next.toString()}`, { scroll: false });
        }}
      >
        <option value="">— choose —</option>
        {states.map((entry) => (
          <option key={entry.state} value={entry.state}>
            {entry.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function StatePicker({
  states,
}: {
  states: { state: string; name: string }[];
}) {
  return (
    <Suspense fallback={null}>
      <PickerInner states={states} />
    </Suspense>
  );
}
