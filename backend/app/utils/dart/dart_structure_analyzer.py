import posixpath
import re
from collections import defaultdict


class DartStructureAnalyzer:
    """Build file relationships from real Dart language constructs."""

    IMPORT_PATTERN = re.compile(
        r"^\s*import\s+(['\"])(?P<uri>[^'\"]+)\1",
        re.MULTILINE,
    )
    TYPE_DECLARATION_PATTERN = re.compile(
        r"\b(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+)*"
        r"(?:class|mixin\s+class|mixin)\s+"
        r"(?P<name>[A-Za-z_]\w*)\b"
    )
    CLASS_DECLARATION_PATTERN = re.compile(
        r"\b(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+)*"
        r"(?:class|mixin\s+class)\s+"
        r"(?P<name>[A-Za-z_]\w*)"
        r"(?:\s*<[^>{}]*>)?"
        r"(?P<clauses>[^{};]*)\{",
        re.DOTALL,
    )
    CLAUSE_PATTERNS = {
        "extends": re.compile(
            r"\bextends\s+(?P<types>.*?)(?=\bwith\b|\bimplements\b|$)",
            re.DOTALL,
        ),
        "mixes_in": re.compile(
            r"\bwith\s+(?P<types>.*?)(?=\bimplements\b|$)",
            re.DOTALL,
        ),
        "implements": re.compile(
            r"\bimplements\s+(?P<types>.*?)$",
            re.DOTALL,
        ),
    }
    TYPE_REFERENCE_PATTERN = re.compile(
        r"^\s*(?:[A-Za-z_]\w*\.)?(?P<name>[A-Za-z_]\w*)"
    )

    def extract_imports(self, content):
        code = self._strip_comments(content)
        return [
            match.group("uri")
            for match in self.IMPORT_PATTERN.finditer(code)
        ]

    def extract_implementations(self, content):
        return self._extract_relationship_types(
            content,
            "implements",
        )

    def extract_extensions(self, content):
        return self._extract_relationship_types(
            content,
            "extends",
        )

    def extract_mixins(self, content):
        return self._extract_relationship_types(
            content,
            "mixes_in",
        )

    def analyze_file(
        self,
        file,
        files,
        *,
        file_by_path=None,
        symbol_index=None,
    ):
        source_path = self._normalize_path(file.get("path", ""))
        if not source_path.endswith(".dart"):
            return []

        file_by_path = file_by_path or self._build_file_index(files)
        symbol_index = symbol_index or self._build_symbol_index(files)
        relationships = []

        resolved_imports = []
        for import_path in self.extract_imports(
            file.get("content", "")
        ):
            resolved = self.resolve_import(
                import_path,
                files,
                source_path=source_path,
                file_by_path=file_by_path,
            )
            if resolved is None:
                continue

            target_path = self._normalize_path(resolved["path"])
            if target_path == source_path:
                continue

            resolved_imports.append(target_path)
            relationships.append({
                "source": source_path,
                "target": target_path,
                "relationship": "imports",
            })

        relationship_extractors = (
            ("implements", self.extract_implementations),
            ("extends", self.extract_extensions),
            ("mixes_in", self.extract_mixins),
        )
        for relationship_type, extractor in relationship_extractors:
            for type_name in extractor(file.get("content", "")):
                resolved = self.find_class(
                    type_name,
                    files,
                    source_path=source_path,
                    imported_paths=resolved_imports,
                    symbol_index=symbol_index,
                )
                if resolved is None:
                    continue

                target_path = self._normalize_path(resolved["path"])
                if target_path == source_path:
                    continue

                relationships.append({
                    "source": source_path,
                    "target": target_path,
                    "relationship": relationship_type,
                })

        return self._deduplicate(relationships)

    def resolve_import(
        self,
        import_path,
        files,
        source_path=None,
        file_by_path=None,
    ):
        """Resolve a Dart import only when its target is in the repository."""
        file_by_path = file_by_path or self._build_file_index(files)
        import_path = import_path.split("#", 1)[0].split("?", 1)[0]

        if import_path.startswith("dart:"):
            return None

        if import_path.startswith("package:"):
            package_path = import_path[len("package:"):]
            if "/" not in package_path:
                return None

            _, relative_path = package_path.split("/", 1)
            target_path = self._normalize_path(
                posixpath.join("lib", relative_path)
            )
            return file_by_path.get(target_path)

        if not source_path or import_path.startswith("/"):
            return None

        target_path = self._normalize_path(
            posixpath.join(
                posixpath.dirname(source_path),
                import_path,
            )
        )
        if target_path == ".." or target_path.startswith("../"):
            return None

        return file_by_path.get(target_path)

    def find_class(
        self,
        class_name,
        files,
        *,
        source_path=None,
        imported_paths=None,
        symbol_index=None,
    ):
        """Resolve a type declaration, refusing ambiguous global matches."""
        symbol_index = symbol_index or self._build_symbol_index(files)
        candidates = symbol_index.get(class_name, [])
        if not candidates:
            return None

        imported_paths = set(imported_paths or [])
        imported_candidates = [
            candidate
            for candidate in candidates
            if self._normalize_path(candidate["path"]) in imported_paths
        ]
        if len(imported_candidates) == 1:
            return imported_candidates[0]
        if len(imported_candidates) > 1:
            return None

        # A matching name elsewhere in the repository is not enough
        # evidence that Dart resolves this reference to that declaration.
        # Without a direct import, remain conservative instead of creating
        # a keyword-based structural edge.
        return None

    def analyze_repository(self, files):
        dart_files = [
            file
            for file in files
            if self._normalize_path(
                file.get("path", "")
            ).endswith(".dart")
        ]
        file_by_path = self._build_file_index(dart_files)
        symbol_index = self._build_symbol_index(dart_files)
        relationships = []

        for file in dart_files:
            relationships.extend(
                self.analyze_file(
                    file,
                    dart_files,
                    file_by_path=file_by_path,
                    symbol_index=symbol_index,
                )
            )

        return self._deduplicate(relationships)

    def _extract_relationship_types(self, content, relationship_type):
        code = self._mask_comments_and_strings(content)
        names = []

        for declaration in self.CLASS_DECLARATION_PATTERN.finditer(code):
            clauses = declaration.group("clauses")
            clause_match = self.CLAUSE_PATTERNS[
                relationship_type
            ].search(clauses)
            if not clause_match:
                continue

            for type_reference in self._split_type_references(
                clause_match.group("types")
            ):
                type_match = self.TYPE_REFERENCE_PATTERN.match(
                    type_reference
                )
                if type_match:
                    names.append(type_match.group("name"))

        return names

    @staticmethod
    def _split_type_references(type_list):
        references = []
        start = 0
        depth = 0
        opening = {"<", "(", "["}
        closing = {">", ")", "]"}

        for index, character in enumerate(type_list):
            if character in opening:
                depth += 1
            elif character in closing:
                depth = max(0, depth - 1)
            elif character == "," and depth == 0:
                references.append(type_list[start:index])
                start = index + 1

        references.append(type_list[start:])
        return references

    def _build_file_index(self, files):
        return {
            self._normalize_path(file.get("path", "")): file
            for file in files
            if file.get("path")
        }

    def _build_symbol_index(self, files):
        symbol_index = defaultdict(list)

        for file in files:
            code = self._mask_comments_and_strings(
                file.get("content", "")
            )
            for match in self.TYPE_DECLARATION_PATTERN.finditer(code):
                symbol_index[match.group("name")].append(file)

        return symbol_index

    @staticmethod
    def _normalize_path(path):
        normalized = posixpath.normpath(path.replace("\\", "/"))
        return "" if normalized == "." else normalized

    @staticmethod
    def _deduplicate(relationships):
        unique = []
        seen = set()

        for relationship in relationships:
            key = (
                relationship["source"],
                relationship["target"],
                relationship["relationship"],
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(relationship)

        return unique

    @classmethod
    def _strip_comments(cls, content):
        return cls._scan_source(content, mask_strings=False)

    @classmethod
    def _mask_comments_and_strings(cls, content):
        return cls._scan_source(content, mask_strings=True)

    @staticmethod
    def _scan_source(content, *, mask_strings):
        """Mask comments and optionally strings while preserving positions."""
        result = list(content)
        index = 0
        length = len(content)

        while index < length:
            if content.startswith("//", index):
                end = content.find("\n", index)
                end = length if end == -1 else end
                for position in range(index, end):
                    result[position] = " "
                index = end
                continue

            if content.startswith("/*", index):
                end = content.find("*/", index + 2)
                end = length if end == -1 else end + 2
                for position in range(index, end):
                    if result[position] != "\n":
                        result[position] = " "
                index = end
                continue

            quote_index = index
            if (
                content[index] in ("r", "R")
                and index + 1 < length
                and content[index + 1] in ("'", '"')
            ):
                quote_index = index + 1

            if content[quote_index] in ("'", '"'):
                quote = content[quote_index]
                triple = content.startswith(quote * 3, quote_index)
                delimiter_length = 3 if triple else 1
                end = quote_index + delimiter_length

                while end < length:
                    if content.startswith(
                        quote * delimiter_length,
                        end,
                    ):
                        end += delimiter_length
                        break
                    if not triple and content[end] == "\\":
                        end += 2
                    else:
                        end += 1

                if mask_strings:
                    for position in range(index, min(end, length)):
                        if result[position] != "\n":
                            result[position] = " "
                index = end
                continue

            index += 1

        return "".join(result)