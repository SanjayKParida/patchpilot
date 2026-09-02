"""
Tree-sitter parse helpers for TypeScript and TSX.

Offline, deterministic, no Node process. `.tsx` uses the TSX
grammar; everything else with a TypeScript extension uses the
TypeScript grammar.

Node decoding helpers live in tree_sitter_util and are re-exported
here so existing TypeScript imports stay stable.
"""

from tree_sitter import Language, Parser
import tree_sitter_typescript


_TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
_TSX_LANGUAGE = Language(tree_sitter_typescript.language_tsx())

_TS_PARSER = Parser(_TS_LANGUAGE)
_TSX_PARSER = Parser(_TSX_LANGUAGE)


def parser_for(path):
    lowered = (path or "").replace("\\", "/").lower()
    if lowered.endswith(".tsx"):
        return _TSX_PARSER
    return _TS_PARSER


def parse(path, content):
    """
    Parse `content` as TypeScript or TSX.

    Returns the root node, or None when there is nothing to parse.
    """

    if not content:
        return None

    source = content if isinstance(content, bytes) else content.encode("utf-8")
    tree = parser_for(path).parse(source)
    if tree is None or tree.root_node is None:
        return None
    return tree.root_node
