import re

class TextNormalizer:
    def tokenize(self, text):
        # Split camelCase / PascalCase
        text = re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])",
            " ",
            text
        )

        # Replace punctuation / separators with spaces
        text = re.sub(
            r"[^a-zA-Z0-9]+",
            " ",
            text
        )

        # Normalize case
        text = text.lower()

        return text.split()

    def normalize(self, text):
        return self.tokenize(text)