# Service Layer Contract

The service layer is the *only* place where the **AI seam** lives. Views never know whether a recommendation came from a rule, a formula, or an LLM.

## Why a service layer

- **Bounded contexts**: a view in `workouts` can ask "what should this exercise's next set be?" without importing from `prs`, `routines`, or `exercises`.
- **Testability**: services are pure-Python around the ORM; they're trivial to unit-test, often without a DB hit.
- **Strategy swap**: today's `DeterministicProgression` becomes tomorrow's `LLMProgression` without touching the view that calls it.

## Layout

```
gymapp/services/
├── __init__.py
├── coaching/                 # the facade — views import from here
│   └── __init__.py
├── exercise_library/         # seed loader, alternatives lookup
│   └── __init__.py
├── progression/              # weight/rep recommendations
│   └── __init__.py
├── substitution/             # equipment-aware alternatives
│   └── __init__.py
├── nutrition/                # Phase 3
│   └── __init__.py
└── analytics/                # Phase 4
    └── __init__.py
```

## Contract for every service

Each service subpackage **must** export:

1. A **`Strategy` Protocol** (or ABC) defining the public interface.
2. A **`Deterministic*` implementation** of that Protocol (the default; works without external dependencies).
3. **Optionally**, an **`LLMStrategy` implementation** added in Phase 4. Strategy selection is driven by Django settings, e.g.:

   ```python
   PROGRESSION_STRATEGY = "deterministic"  # or "llm"
   ```

4. A **factory** in the facade module (`coaching/__init__.py`) that constructs the chosen strategy and exposes a ready-to-use instance.

Example skeleton:

```python
# gymapp/services/progression/__init__.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SetRecommendation:
    weight_kg: float
    reps: int
    rationale: str = ""


class ProgressionStrategy(Protocol):
    def recommend_next(
        self, exercise_slug: str, history: list[SetRecommendation]
    ) -> SetRecommendation: ...


class DeterministicProgression:
    def recommend_next(self, exercise_slug, history):
        if not history:
            return SetRecommendation(0.0, 0, rationale="no_history")
        return SetRecommendation(history[-1].weight_kg, history[-1].reps, rationale="repeat_last")
```

```python
# gymapp/services/coaching/__init__.py
from gymapp.services.progression import DeterministicProgression, SetRecommendation
from gymapp.services.substitution import DeterministicSubstitution

progression = DeterministicProgression()
substitution = DeterministicSubstitution()

__all__ = ["progression", "substitution", "SetRecommendation"]
```

And the consumer:

```python
# in some view
from gymapp.services.coaching import progression

rec = progression.recommend_next("bench-press", history=...)
```

## Why Protocol + Deterministic from day one

Adding the seam after the fact requires:

1. Renaming the existing function/class to `Deterministic*`.
2. Introducing the Protocol.
3. Adding the factory.
4. Rewriting every call site (which directly imported the original).

Doing it up front costs ~20 LOC per service and saves a multi-PR refactor later.

## What should NOT live in services

- Pure model methods that don't touch other apps. Keep them on the model.
- Form validation. That's on the form.
- HTTP response shaping (status codes, redirects). That's on the view.
- HTML rendering. That's on the template.

## When to extract a new service

When two apps' views start needing the same query/computation. Premature extraction is wasted abstraction; reactive extraction is healthy.

## LLM-strategy guidance (Phase 4)

When `LLMStrategy` lands:

- **Use prompt caching** (Anthropic supports cache control on system prompts and tool definitions). Cache the large parts (exercise library, conventions) so per-call cost is just the small variable suffix.
- **Pick the cheapest model that works**. Haiku 4.5 for classification / short reasoning, Sonnet 4.6 for multi-step coaching, Opus only when truly needed.
- **Always fall back to deterministic** on API error or cost-ceiling hit. The user shouldn't notice an AI outage.
- **Don't send PII**. Names, emails, body composition data — send slugs and IDs, not personal identifiers.
- **Daily token budget per user**. Configurable via settings. Drop to deterministic once the budget is exhausted.
