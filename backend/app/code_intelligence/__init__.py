from app.code_intelligence.protocol import CodeIntelligence, supports
from app.code_intelligence.types import Location, Reference, Span
from app.code_intelligence.null_adapter import NullCodeIntelligence
from app.code_intelligence.registry import CodeIntelligenceRegistry

__all__ = [
    "CodeIntelligence",
    "CodeIntelligenceRegistry",
    "Location",
    "NullCodeIntelligence",
    "Reference",
    "Span",
    "supports",
]
