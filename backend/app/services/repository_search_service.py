from app.services.github_service import GithubService
from app.utils.text_normalizer import TextNormalizer

class RepositorySearchService:
    def __init__(self):
        self.normalizer = TextNormalizer()

    def search(self, files, query):
        results = []

        query_tokens = self.normalizer.tokenize(query)

        print("QUERY TOKENS:", query_tokens)

        for file in files:
            path_tokens = self.normalizer.tokenize(file["path"])

            matched = all(token in path_tokens for token in query_tokens)

            if matched:
                print("MATCH:", file["path"])
                results.append(file)

        return results
    
    def search_content(self, files, query):
        results = []

        query_tokens = self.normalizer.tokenize(query)

        for file in files:
            content = file["content"]

            for line_number, line in enumerate(content.splitlines(), start = 1):
                line_tokens = self.normalizer.tokenize(line)

                if not all(
                    token in line_tokens
                    for token in query_tokens
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
