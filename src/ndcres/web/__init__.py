"""Web tier — a thin, read-only FastAPI layer over the resolver.

No resolver logic lives here; every endpoint delegates to the same
functions the CLI uses and serializes through ndcres.serialize, so the
two surfaces can never drift apart.
"""
