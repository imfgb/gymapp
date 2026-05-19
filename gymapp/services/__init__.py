"""Runtime service layer.

Cross-context business logic lives here, not in views or models. Each
subpackage defines a `Strategy` Protocol and a `DeterministicStrategy`
implementation. A future `LLMStrategy` can replace any deterministic one via a
settings flag without touching call sites.

See `docs/service_layer.md` for the contract.
"""
