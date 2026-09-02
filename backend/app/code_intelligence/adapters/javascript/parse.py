"""
Tree-sitter parse helpers for JavaScript and JSX.

The JavaScript grammar includes JSX, so `.js` and `.jsx` share one
parser. Offline, deterministic, no Node process.
"""

from tree_sitter import Language, Parser
import tree_sitter_javascript


_JS_LANGUAGE = Language(tree_sitter_javascript.language())
_JS_PARSER = Parser(_JS_LANGUAGE)


def parse(path, content):
    """
    Parse `content` as JavaScript or JSX.

    Returns the root node, or None when there is nothing to parse.
    """

    if not content:
        return None

    source = content if isinstance(content, bytes) else content.encode("utf-8")
    tree = _JS_PARSER.parse(source)
    if tree is None or tree.root_node is None:
        return None
    return tree.root_node
