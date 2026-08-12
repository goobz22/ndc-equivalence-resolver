# NDC Equivalence Resolver

> "My pharmacy says my drug is out. What is the same drug, from a different
> manufacturer, that they might actually have — and what does my prescriber
> need to write to unlock it?"

`ndcres` is an offline-first Python package + CLI that answers that question
from public data only: the FDA NDC Directory, the FDA Orange Book, RxNorm
(prescribable content), openFDA drug shortages, and NADAC weekly acquisition
costs.

**Status: under construction.** Full README with the worked real-world
example lands with the live acceptance run.

## Not medical advice

This tool surfaces *supply-chain* equivalence facts from public regulatory
data. It never recommends taking anything. Any result beyond a direct
pharmacist-substitutable equivalent explicitly requires prescriber
authorization, and is labeled as such.

## License

MIT. All ingested data sources are US-government public data; none are
redistributed with this repository.
