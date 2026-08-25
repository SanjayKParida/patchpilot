from app.utils.text_normalizer import TextNormalizer

class RepositorySearchService:

    EXCLUDED_PATH_PARTS = (
        "/test/",
        "/tests/",
        "/__tests__/",
        "/__mocks__/",
        "/mock/",
        "/mocks/",
    )

    EXCLUDED_FILE_SUFFIXES = (
        "_test.dart",
        "_test.py",
        "_test.js",
        "_test.ts",
        ".test.js",
        ".test.ts",
        ".spec.js",
        ".spec.ts",
    )

    EXCLUDED_FILE_NAMES = {
        "test",
        "tests",
    }

    def __init__(self):
        self.normalizer = TextNormalizer()

    def is_candidate_file(self, file):
        path = file.get("path", "").replace("\\", "/").lower()

        if not path:
            return False

        # Test directories
        for excluded_part in self.EXCLUDED_PATH_PARTS:
            if excluded_part in f"/{path}":
                return False

        # Test files
        for suffix in self.EXCLUDED_FILE_SUFFIXES:
            if path.endswith(suffix):
                return False

        # Standalone test directories/files
        parts = path.split("/")

        if any(
            part in self.EXCLUDED_FILE_NAMES
            for part in parts
        ):
            return False

        return True

    def search(self, files, query):
        """
        Files whose PATH mentions the query.

        Matching is delegated to TextNormalizer so that path search,
        content search and the language evidence analyzers all agree
        on what "mentions" means.
        """

        results = []

        for file in files:

            if not self.is_candidate_file(file):
                continue

            if not self.normalizer.matches(
                query,
                file["path"],
            ):
                continue

            results.append(file)

        return results

    def search_content(self, files, query):
        """
        Lines whose CONTENT mentions the query.

        Uses the same matcher as path search; see TextNormalizer.
        """

        results = []

        for file in files:

            if not self.is_candidate_file(file):
                continue

            content = file["content"]

            for line_number, line in enumerate(
                content.splitlines(),
                start=1
            ):

                if not self.normalizer.matches(
                    query,
                    line,
                ):
                    continue

                stripped = line.strip()

                if stripped.startswith("import "):
                    match_type = "import"

                elif stripped.startswith("//"):
                    match_type = "comment"

                else:
                    match_type = "code"

                results.append({
                    "file": file,
                    "line": line_number,
                    "text": stripped,
                    "match_type": match_type
                })

        return results