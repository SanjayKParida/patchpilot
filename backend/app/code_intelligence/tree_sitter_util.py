"""
Shared tree-sitter helpers.

Language grammars and declaration rules stay in each adapter.
These functions only decode nodes, skip ERROR subtrees, and
resolve relative import paths.
"""

import posixpath


def normalize_path(path):
    normalized = posixpath.normpath((path or "").replace("\\", "/"))
    return "" if normalized == "." else normalized


def node_text(node):
    if node is None:
        return ""
    raw = node.text
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw


def start_line(node):
    return node.start_point[0] + 1


def end_line(node):
    """Inclusive 1-based last line of `node`."""

    row, column = node.end_point
    line = row + 1
    if column == 0 and line > start_line(node):
        return line - 1
    return line


def string_literal(node):
    """Unquoted contents of a tree-sitter string node, or None."""

    if node is None:
        return None
    if node.type != "string":
        return None
    for child in node.children:
        if child.type == "string_fragment":
            return node_text(child)
    text = node_text(node).strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        return text[1:-1]
    return None


def skip_error(nodes):
    return [node for node in nodes if node.type != "ERROR"]


def first_child(node, type_name):
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def is_identifier(name):
    if not name:
        return False
    first = name[0]
    if not (first.isalpha() or first == "_" or first == "$"):
        return False
    return all(ch.isalnum() or ch in "_$" for ch in name)


def resolve_relative_import(
    source_path,
    specifier,
    by_path,
    extensions,
    *,
    map_javascript_specifiers=False,
):
    """
    Resolve a relative import to exactly one snapshot path.

    Package specifiers and path aliases are declined. Multiple
    matching files are also declined.
    """

    if not specifier or not source_path:
        return None
    if not specifier.startswith("."):
        return None

    directory = posixpath.dirname(source_path)
    joined = normalize_path(posixpath.join(directory, specifier))
    candidates = [joined]
    if not _has_extension(joined, extensions):
        for extension in extensions:
            candidates.append(joined + extension)
        for extension in extensions:
            candidates.append(posixpath.join(joined, "index" + extension))

    if map_javascript_specifiers:
        if specifier.endswith(".js"):
            stem = joined[:-3]
            candidates.extend(stem + extension for extension in extensions)
        elif specifier.endswith(".jsx"):
            stem = joined[:-4]
            candidates.extend(stem + extension for extension in extensions)

    found = []
    for candidate in candidates:
        path = normalize_path(candidate)
        if path in by_path and path not in found:
            found.append(path)
    if len(found) == 1:
        return found[0]
    return None


def _has_extension(path, extensions):
    lowered = path.lower()
    return any(lowered.endswith(extension) for extension in extensions)
