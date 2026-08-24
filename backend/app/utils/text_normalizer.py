import re


class TextNormalizer:
    """
    Shared vocabulary layer for every matcher in the pipeline.

    Retrieval has two channels that ask the same question in different
    places: path/content search asks "does this text mention the
    concept", and the language evidence analyzer asks "does this
    identifier mention the concept". If they answer differently, one
    channel invents candidates the other cannot see, and no amount of
    ranking calibration can fix the disagreement.

    So both go through here.

    Matching happens on tokens, never on substrings:

        "car" matches CarRepository      -> [car, repository]
        "car" matches getCars            -> [get, car]     (plural)
        "car" does NOT match MoreCard    -> [more, card]

    Substring matching cannot make that last distinction, and strict
    token matching without singularization cannot make the middle one.
    A codebase names things `getCars` / `fetchCars` / `LoadCars` while
    an issue says "car", so both rules are needed together.
    """

    # ---------------------------------------------------------
    # Token boundaries
    # ---------------------------------------------------------

    # getCars -> get|Cars
    CASE_BOUNDARY = re.compile(
        r"(?<=[a-z0-9])(?=[A-Z])"
    )

    # HTTPServer -> HTTP|Server
    ACRONYM_BOUNDARY = re.compile(
        r"(?<=[A-Z])(?=[A-Z][a-z])"
    )

    SEPARATORS = re.compile(
        r"[^a-zA-Z0-9]+"
    )

    # ---------------------------------------------------------
    # Singularization
    # ---------------------------------------------------------
    #
    # Deliberately conservative. A wrong singularization is a false
    # match, and false matches contaminate ranking more than misses.
    #
    # Anything shorter than this is left alone, so "is", "as", "gas"
    # and "css" survive intact.
    # ---------------------------------------------------------

    MIN_SINGULAR_LENGTH = 4

    # Endings that look plural but are not.
    NON_PLURAL_ENDINGS = (
        "ss",   # class, address
        "us",   # status, radius
        "is",   # analysis, axis
    )

    # Endings where the plural added "es" rather than "s".
    #
    # English is genuinely ambiguous here: "-ches" is "match" + es
    # but also "cache" + s. These four cover the forms that actually
    # show up in code; the ambiguous remainder degrades into a MISS
    # rather than a false match, which is the safe direction.
    #
    # Known imperfection: "caches" -> "cach", so it will not meet
    # "cache". Accepted, because the alternative rule breaks
    # "classes", "boxes" and "matches", which are far more common.
    ES_ENDINGS = (
        "sses",  # classes -> class
        "xes",   # boxes   -> box
        "ches",  # matches -> match
        "shes",  # brushes -> brush
    )

    def __init__(self):
        # Identifier vocabularies are asked about repeatedly, once
        # per signal per occurrence. Cache the split.
        self._concept_cache = {}

    # =========================================================
    # TOKENIZATION
    # =========================================================

    def tokenize(self, text):
        """
        Split text into lowercase word tokens.

        Handles camelCase, PascalCase, acronym runs, and any
        punctuation or path separator.
        """

        if not text:
            return []

        text = self.ACRONYM_BOUNDARY.sub(" ", text)
        text = self.CASE_BOUNDARY.sub(" ", text)
        text = self.SEPARATORS.sub(" ", text)

        return text.lower().split()

    # =========================================================
    # SINGULARIZATION
    # =========================================================

    def singularize(self, token):
        """
        Reduce an obvious English plural to its singular form.

        This is not a general stemmer. It only needs to make issue
        vocabulary ("car") meet code vocabulary ("cars", "getCars")
        without merging unrelated words.
        """

        if len(token) < self.MIN_SINGULAR_LENGTH:
            return token

        if token.endswith(self.NON_PLURAL_ENDINGS):
            return token

        # repositories -> repository
        if token.endswith("ies"):
            return token[:-3] + "y"

        if token.endswith(self.ES_ENDINGS):
            return token[:-2]

        if token.endswith("s"):
            return token[:-1]

        return token

    # =========================================================
    # CONCEPTS
    # =========================================================

    def concepts(self, text):
        """
        Tokenize and singularize.

        This is the canonical vocabulary of a piece of text. Every
        matcher in the pipeline compares these, not raw strings.
        """

        cached = self._concept_cache.get(text)

        if cached is not None:
            return cached

        concepts = [
            self.singularize(token)
            for token in self.tokenize(text)
        ]

        self._concept_cache[text] = concepts

        return concepts

    # =========================================================
    # MATCHING
    # =========================================================

    def matches(self, term, text):
        """
        Does `text` mention every concept in `term`?

        An empty term matches nothing. Matching everything would let
        a blank signal pull in the entire repository.
        """

        term_concepts = self.concepts(term)

        if not term_concepts:
            return False

        text_concepts = set(
            self.concepts(text)
        )

        return all(
            concept in text_concepts
            for concept in term_concepts
        )

    # =========================================================
    # BACKWARD COMPATIBILITY
    # =========================================================

    def normalize(self, text):
        return self.tokenize(text)
