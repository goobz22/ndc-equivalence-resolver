"use client";

import { useEffect, useState } from "react";
import { api, MetaSource } from "@/lib/api";

export function MetaFooter() {
  const [sources, setSources] = useState<MetaSource[] | null>(null);

  useEffect(() => {
    api
      .meta()
      .then((meta) => setSources(meta.sources))
      .catch(() => setSources(null));
  }, []);

  if (!sources) return null;
  return (
    <div className="meta-footer">
      <span>Reference data vintage:</span>
      {sources
        .filter((s) => s.source !== "link")
        .map((s) => (
          <span key={s.source}>
            {s.source} {s.fetched_at?.slice(0, 10)}
          </span>
        ))}
    </div>
  );
}
