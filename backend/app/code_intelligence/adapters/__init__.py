"""
Language-specific CodeIntelligence adapters.

Add a language by creating adapters/<language>/adapter.py and
registering it in CodeIntelligenceRegistry.default(). Callers stay
on the protocol; they never import these packages.
"""

from app.code_intelligence.adapters.dart import DartCodeIntelligence
from app.code_intelligence.adapters.javascript import JavaScriptCodeIntelligence
from app.code_intelligence.adapters.python import PythonCodeIntelligence
from app.code_intelligence.adapters.typescript import TypeScriptCodeIntelligence

__all__ = [
    "DartCodeIntelligence",
    "JavaScriptCodeIntelligence",
    "PythonCodeIntelligence",
    "TypeScriptCodeIntelligence",
]
