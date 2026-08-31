"""Deterministic, reviewable Phase 3 semantic inference."""

from .confidence import (
    SOURCE_WEIGHTS,
    calculate_confidence,
    confidence_breakdown,
    confidence_from_evidence,
    evidence_confidence,
    evidence_weight,
    score_evidence,
)
from .engine import (
    Engine,
    InferenceEngine,
    InferenceResult,
    SemanticInferenceEngine,
    analyze_semantics,
    infer,
    infer_semantics,
)
from .semantics import (
    SemanticCandidate,
    SemanticConflict,
    behavior_candidates,
    description_candidates,
    detect_conflicts,
    infer_candidates,
    make_candidate,
    make_evidence,
    name_candidates,
    role_from_text,
)

__all__ = [
    "Engine",
    "InferenceEngine",
    "InferenceResult",
    "SOURCE_WEIGHTS",
    "SemanticCandidate",
    "SemanticConflict",
    "SemanticInferenceEngine",
    "analyze_semantics",
    "behavior_candidates",
    "calculate_confidence",
    "confidence_breakdown",
    "confidence_from_evidence",
    "description_candidates",
    "detect_conflicts",
    "evidence_confidence",
    "evidence_weight",
    "infer",
    "infer_candidates",
    "infer_semantics",
    "make_candidate",
    "make_evidence",
    "name_candidates",
    "role_from_text",
    "score_evidence",
]
