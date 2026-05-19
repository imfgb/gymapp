"""Coaching facade.

Single import surface for views. Phase 0 just re-exports the deterministic
strategies; Phase 2/4 may wire in alternatives.
"""
from gymapp.services.progression import DeterministicProgression, SetRecommendation
from gymapp.services.substitution import DeterministicSubstitution

progression = DeterministicProgression()
substitution = DeterministicSubstitution()

__all__ = ["progression", "substitution", "SetRecommendation"]
