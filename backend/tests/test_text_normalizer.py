"""
Unit tests for TextNormalizer.

TextNormalizer is the shared vocabulary layer: path search, content
search and the language evidence analyzers all decide "does this text
mention this concept" through it. A disagreement between those channels
shows up here first, so these tests pin the matching contract rather
than the implementation.
"""

import pytest

from app.utils.text_normalizer import TextNormalizer


@pytest.fixture
def normalizer():
    return TextNormalizer()


# ============================================================
# TOKENIZATION
# ============================================================

@pytest.mark.parametrize(
    "text,expected",
    [
        ("getCars", ["get", "cars"]),
        ("CarRepositoryImpl", ["car", "repository", "impl"]),
        ("car_repository_impl", ["car", "repository", "impl"]),
        ("lib/data/models/car.dart", ["lib", "data", "models", "car", "dart"]),
        ("HTTPServer", ["http", "server"]),
        ("DefaultFirebaseOptions", ["default", "firebase", "options"]),
        ("_CardDetailsPageState", ["card", "details", "page", "state"]),
        ("", []),
    ],
)
def test_tokenize(normalizer, text, expected):
    assert normalizer.tokenize(text) == expected


# ============================================================
# SINGULARIZATION
# ============================================================

@pytest.mark.parametrize(
    "token,expected",
    [
        # ordinary plurals
        ("cars", "car"),
        ("options", "option"),
        ("details", "detail"),
        # -ies
        ("repositories", "repository"),
        ("cities", "city"),
        # -es where the singular ends in s/x/ch/sh
        ("classes", "class"),
        ("boxes", "box"),
        ("matches", "match"),
        ("brushes", "brush"),
        # plain -s wins over a bogus -es rule
        ("sizes", "size"),
        ("cases", "case"),
        # not plurals at all
        ("class", "class"),
        ("status", "status"),
        ("analysis", "analysis"),
        ("address", "address"),
        # too short to risk it
        ("is", "is"),
        ("as", "as"),
        ("gas", "gas"),
        ("css", "css"),
        # no trailing s
        ("firestore", "firestore"),
        ("bloc", "bloc"),
    ],
)
def test_singularize(normalizer, token, expected):
    assert normalizer.singularize(token) == expected


def test_singularize_is_stable_on_already_singular_words(normalizer):
    """
    Both sides of a match are normalized, so singularizing an already
    singular word must not change it or matching becomes asymmetric.
    """

    for token in ["car", "repository", "class", "box", "match"]:
        assert normalizer.singularize(token) == token


# ============================================================
# MATCHING
# ============================================================

@pytest.mark.parametrize(
    "term,text",
    [
        # whole-word matches
        ("car", "CarRepository"),
        ("car", "car_repository_impl.dart"),
        ("repository", "CarRepositoryImpl"),
        ("firebase", "FirebaseCarDataSource"),
        ("firestore", "FirebaseFirestore"),
        ("bloc", "CarBloc"),
        # plural code vocabulary against a singular issue term
        ("car", "getCars"),
        ("car", "fetchCars"),
        ("car", "LoadCars"),
        ("car", "CarsLoading"),
        ("car", "lib/domain/usecases/get_cars.dart"),
        # plural issue term against singular code
        ("cars", "Car"),
        # a compound that genuinely contains the concept
        ("car", "CarCard"),
        ("car", "directions_car"),
    ],
)
def test_matches(normalizer, term, text):
    assert normalizer.matches(term, text) is True


@pytest.mark.parametrize(
    "term,text",
    [
        # the substring trap: "car" inside "card"
        ("car", "MoreCard"),
        ("car", "CardDetailsPage"),
        ("car", "_CardDetailsPageState"),
        # "bloc" inside "block"
        ("bloc", "block"),
        ("bloc", "BlockScope"),
        # unrelated
        ("firebase", "CarRepository"),
    ],
)
def test_does_not_match(normalizer, term, text):
    assert normalizer.matches(term, text) is False


def test_multi_token_term_requires_every_concept(normalizer):
    assert normalizer.matches("car repository", "CarRepositoryImpl")
    assert not normalizer.matches("car repository", "CarBloc")


def test_empty_term_matches_nothing(normalizer):
    """
    A blank signal must not pull the whole repository into retrieval.
    """

    assert normalizer.matches("", "CarRepository") is False
    assert normalizer.matches("   ", "CarRepository") is False


def test_matching_is_symmetric_across_plural_forms(normalizer):
    """
    Whichever form the issue text and the code happen to use, the
    match must hold. This is the property that lets an issue saying
    "cars" reach a class named Car.
    """

    for term in ["car", "cars"]:
        for text in ["Car", "cars", "getCars", "CarRepository"]:
            assert normalizer.matches(term, text), (term, text)


def test_concepts_cache_returns_consistent_results(normalizer):
    first = normalizer.concepts("getCars")
    second = normalizer.concepts("getCars")

    assert first == second == ["get", "car"]
