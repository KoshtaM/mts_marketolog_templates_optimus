"""Аналитика: выгода, сегментация, матчинг, поиск кандидатов, метрики."""

from mts_templates.domain.analytics.activity import (
    OperatorTrigger,
    TemplateActivity,
    TemplateMetrics,
)
from mts_templates.domain.analytics.analysis import AnalysisRun, CandidateGroup
from mts_templates.domain.analytics.baseline import (
    ObservedRates,
    build_observed_rates,
)
from mts_templates.domain.analytics.benefit import (
    CandidateBenefit,
    TemplateBenefit,
    calculate_candidate_benefit,
    calculate_template_benefit,
)
from mts_templates.domain.analytics.canonical import (
    CanonicalSignature,
    ElementKind,
    SignatureElement,
    Token,
    TokenKind,
    signature_of,
    tokenize,
)
from mts_templates.domain.analytics.csg import (
    CandidateStatus,
    CsgCandidate,
    CsgConfig,
    CsgExtraction,
    Issue,
    SignatureGroup,
    build_signature_groups,
    emit_template,
    extract_candidates,
    lint_template,
    merge_signature_groups,
)
from mts_templates.domain.analytics.drift import (
    DriftFragment,
    DriftFragmentKind,
    TemplateDrift,
    detect_template_drifts,
)
from mts_templates.domain.analytics.import_aggregation import (
    AggregationResult,
    QualityIssue,
    RawSmsRow,
    aggregate_rows,
    classify_message,
)
from mts_templates.domain.analytics.matching import (
    CompiledTemplate,
    compile_template,
    compile_templates,
    match_message,
)
from mts_templates.domain.analytics.normalization import (
    DEFAULT_NORMALIZATION,
    NormalizationPolicy,
    mask_phone,
    normalize,
    normalize_text,
    sender_key,
)
from mts_templates.domain.analytics.segmentation import count_segments
from mts_templates.domain.analytics.template_syntax import (
    compile_pattern,
    normalize_for_matching,
    parse_operators,
)

__all__ = [
    "DEFAULT_NORMALIZATION",
    "AggregationResult",
    "AnalysisRun",
    "CandidateBenefit",
    "CandidateGroup",
    "CandidateStatus",
    "CanonicalSignature",
    "CompiledTemplate",
    "CsgCandidate",
    "CsgConfig",
    "CsgExtraction",
    "DriftFragment",
    "DriftFragmentKind",
    "ElementKind",
    "Issue",
    "NormalizationPolicy",
    "ObservedRates",
    "OperatorTrigger",
    "QualityIssue",
    "RawSmsRow",
    "SignatureElement",
    "SignatureGroup",
    "TemplateActivity",
    "TemplateBenefit",
    "TemplateDrift",
    "TemplateMetrics",
    "Token",
    "TokenKind",
    "aggregate_rows",
    "build_observed_rates",
    "build_signature_groups",
    "calculate_candidate_benefit",
    "calculate_template_benefit",
    "classify_message",
    "compile_pattern",
    "compile_template",
    "compile_templates",
    "count_segments",
    "detect_template_drifts",
    "emit_template",
    "extract_candidates",
    "lint_template",
    "mask_phone",
    "match_message",
    "merge_signature_groups",
    "normalize",
    "normalize_for_matching",
    "normalize_text",
    "parse_operators",
    "sender_key",
    "signature_of",
    "tokenize",
]
