"""
Extension → language adapter.

ContextBuilderService never imports Dart (or any other language). It
asks questions of whatever CodeIntelligence it was given. This registry
is that object when the caller has a real repository: it picks an
adapter per path, indexes each language's files separately, and
forwards every other call to the adapter that owns the file.

Unknown extensions resolve to NullCodeIntelligence. That is a normal
path, not an error.
"""

from app.code_intelligence.null_adapter import NullCodeIntelligence
from app.code_intelligence.protocol import supports


class RegistryIndex:
    """
    Opaque to the core: a per-adapter sub-index plus a path map.

    The registry is the only thing that unpacks this. Adapters never
    see another adapter's index.
    """

    __slots__ = ("parts", "by_path")

    def __init__(self, parts, by_path):
        self.parts = tuple(parts)
        self.by_path = dict(by_path)

    def subindex(self, adapter):
        for owned, index in self.parts:
            if owned is adapter:
                return index
        return None


class CodeIntelligenceRegistry:
    """
    Resolves a CodeIntelligence adapter from a file path.

    Registered adapters are tried in insertion order; the first whose
    `extensions` match wins. Everything else is the null fallback.
    """

    extensions = ()

    # Package-level name when the caller did not derive one from slices.
    # Mixed repositories overwrite this from the slices they actually
    # kept; a dart-only package is labelled "dart", not "mixed".
    name = "mixed"

    def __init__(self, adapters=None, fallback=None):
        self._adapters = tuple(adapters or ())
        self._fallback = fallback or NullCodeIntelligence()

    @classmethod
    def default(cls):
        """Production registry: Dart, then the null fallback."""

        from app.code_intelligence.dart_adapter import DartCodeIntelligence

        return cls(adapters=(DartCodeIntelligence(),))

    def for_path(self, path):
        for adapter in self._adapters:
            if supports(adapter, path):
                return adapter
        return self._fallback

    # =========================================================
    # CodeIntelligence — dispatch per file / per adapter
    # =========================================================

    def build_index(self, files):
        grouped = {}
        by_path = {}

        for file in files:
            path = file.get("path") or ""
            adapter = self.for_path(path)
            by_path[path] = adapter
            if id(adapter) not in grouped:
                grouped[id(adapter)] = (adapter, [])
            grouped[id(adapter)][1].append(file)

        parts = []
        for adapter in self._ordered_adapters():
            entry = grouped.get(id(adapter))
            if entry is None:
                continue
            owned, bucket = entry
            parts.append((owned, owned.build_index(bucket)))

        return RegistryIndex(parts, by_path)

    def analyze_structure(self, files):
        edges = []
        grouped = {}

        for file in files:
            adapter = self.for_path(file.get("path") or "")
            if id(adapter) not in grouped:
                grouped[id(adapter)] = (adapter, [])
            grouped[id(adapter)][1].append(file)

        for adapter in self._ordered_adapters():
            entry = grouped.get(id(adapter))
            if entry is None:
                continue
            owned, bucket = entry
            edges.extend(owned.analyze_structure(bucket))

        return edges

    def declaration_of(self, symbol, index):
        found = []
        for adapter, subindex in self._parts(index):
            location = adapter.declaration_of(symbol, subindex)
            if location is not None:
                found.append(location)

        if len(found) == 1:
            return found[0]

        # None or more than one language claimed it — same as
        # ambiguous within a language: do not guess.
        return None

    def declarations_in(self, path, index):
        adapter = self.for_path(path)
        return adapter.declarations_in(path, self._subindex(index, adapter))

    def references_to(self, symbol, index):
        references = []
        for adapter, subindex in self._parts(index):
            references.extend(adapter.references_to(symbol, subindex))
        return references

    def enclosing_span(self, path, line, index):
        adapter = self.for_path(path)
        return adapter.enclosing_span(
            path,
            line,
            self._subindex(index, adapter),
        )

    def header_end_line(self, path, content, index):
        adapter = self.for_path(path)
        return adapter.header_end_line(
            path,
            content,
            self._subindex(index, adapter),
        )

    def is_test_file(self, path):
        return self.for_path(path).is_test_file(path)

    def _ordered_adapters(self):
        seen = []
        for adapter in self._adapters:
            if adapter not in seen:
                seen.append(adapter)
        if self._fallback not in seen:
            seen.append(self._fallback)
        return seen

    def _parts(self, index):
        if isinstance(index, RegistryIndex):
            return index.parts
        return tuple(
            (adapter, index) for adapter in self._ordered_adapters()
        )

    def _subindex(self, index, adapter):
        if isinstance(index, RegistryIndex):
            sub = index.subindex(adapter)
            return sub if sub is not None else index
        return index
