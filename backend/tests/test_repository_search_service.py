"""
Unit tests for RepositorySearchService.

Search and the language evidence analyzers must agree on what
"mentions a concept" means, so the matching cases here deliberately
mirror those in test_dart_evidence_analyzer.py.
"""

import pytest

from app.services.repository_search_service import (
    RepositorySearchService,
)


@pytest.fixture
def search():
    return RepositorySearchService()


def _file(path, content=""):
    return {
        "path": path,
        "sha": path,
        "content": content,
    }


def _paths(files):
    return {file["path"] for file in files}


# ============================================================
# PATH SEARCH
# ============================================================

def test_path_search_matches_whole_tokens(search):
    files = [
        _file("lib/data/repositories/car_repository_impl.dart"),
        _file("lib/presentation/widgets/more_card.dart"),
    ]

    assert _paths(search.search(files, "car")) == {
        "lib/data/repositories/car_repository_impl.dart",
    }


def test_path_search_matches_plural_filenames(search):
    """
    An issue says "car"; the file is named get_cars.dart. Without
    singularization this file is never retrieved, even though it sits
    in the middle of the call chain.
    """

    files = [_file("lib/domain/usecases/get_cars.dart")]

    assert _paths(search.search(files, "car")) == {
        "lib/domain/usecases/get_cars.dart",
    }


def test_path_search_requires_every_query_token(search):
    files = [
        _file("lib/data/repositories/car_repository_impl.dart"),
        _file("lib/presentation/bloc/car_bloc.dart"),
    ]

    assert _paths(search.search(files, "car repository")) == {
        "lib/data/repositories/car_repository_impl.dart",
    }


def test_path_search_skips_test_files(search):
    files = [
        _file("test/widget_test.dart"),
        _file("lib/data/models/car.dart"),
    ]

    assert _paths(search.search(files, "car")) == {
        "lib/data/models/car.dart",
    }


# ============================================================
# CONTENT SEARCH
# ============================================================

def test_content_search_matches_plural_identifiers(search):
    files = [
        _file(
            "lib/domain/usecases/get_cars.dart",
            "Future<List<Car>> fetchCars() => repo.getCars();",
        )
    ]

    results = search.search_content(files, "car")

    assert len(results) == 1
    assert results[0]["line"] == 1
    assert results[0]["match_type"] == "code"


def test_content_search_rejects_substring_lookalikes(search):
    files = [
        _file(
            "lib/presentation/widgets/more_card.dart",
            "class MoreCard extends StatelessWidget {}",
        )
    ]

    assert search.search_content(files, "car") == []


@pytest.mark.parametrize(
    "line,expected",
    [
        ("import 'package:rentapp/data/models/car.dart';", "import"),
        ("// the car list", "comment"),
        ("final car = Car();", "code"),
    ],
)
def test_content_search_classifies_match_type(search, line, expected):
    files = [_file("lib/example.dart", line)]

    results = search.search_content(files, "car")

    assert len(results) == 1
    assert results[0]["match_type"] == expected


def test_search_and_content_search_agree_on_a_concept(search):
    """
    The two channels feed different score components. If they disagree
    about whether a file mentions a concept, ranking cannot be
    calibrated, because one channel invents candidates the other
    cannot see.
    """

    mentions = _file(
        "lib/domain/usecases/get_cars.dart",
        "class GetCars {}",
    )

    lookalike = _file(
        "lib/presentation/widgets/more_card.dart",
        "class MoreCard {}",
    )

    files = [mentions, lookalike]

    path_hits = _paths(search.search(files, "car"))

    content_hits = {
        result["file"]["path"]
        for result in search.search_content(files, "car")
    }

    assert path_hits == content_hits == {mentions["path"]}
