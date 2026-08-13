import { SourceRefs } from "@/lib/api";

// One muted line under a data block naming exactly where its numbers
// came from, linking out to the publisher (SPEC §9). `ids` are registry
// keys (ndc, orangebook, rxnorm, nadac, shortage, sdud, enforcement);
// an optional deep link points at the specific upstream record.
export function SourceTag({
  refs,
  ids,
  deepUrl,
  deepLabel,
}: {
  refs: SourceRefs | undefined;
  ids: string[];
  deepUrl?: string | null;
  deepLabel?: string;
}) {
  if (!refs) return null;
  const entries = ids
    .map((id) => ({ id, ref: refs[id] }))
    .filter((entry) => entry.ref);
  if (entries.length === 0) return null;
  const fetchedDates = Array.from(
    new Set(
      entries
        .map((entry) => entry.ref.fetched_at?.slice(0, 10))
        .filter(Boolean) as string[],
    ),
  );
  return (
    <div className="source-tag">
      Source{entries.length > 1 ? "s" : ""}:{" "}
      {entries.map((entry, index) => (
        <span key={entry.id}>
          {index > 0 ? " · " : ""}
          <a href={entry.ref.url} target="_blank" rel="noreferrer">
            {entry.ref.name}
          </a>
        </span>
      ))}
      {fetchedDates.length > 0 ? (
        <span> · data fetched {fetchedDates.join(", ")}</span>
      ) : null}
      {deepUrl ? (
        <span>
          {" · "}
          <a href={deepUrl} target="_blank" rel="noreferrer">
            {deepLabel ?? "view the upstream record"}
          </a>
        </span>
      ) : null}
    </div>
  );
}
