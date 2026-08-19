from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer


def _file(path, content):
    return {
        "path": path,
        "content": content,
    }


def test_resolves_local_imports_and_ignores_external_packages():
    files = [
        _file(
            "lib/presentation/bloc/car_state.dart",
            """
            import '../../data/models/car.dart';
            import 'package:flutter_bloc/flutter_bloc.dart';
            import 'package:cloud_firestore/cloud_firestore.dart';
            """,
        ),
        _file("lib/data/models/car.dart", "class Car {}"),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert relationships == [
        {
            "source": "lib/presentation/bloc/car_state.dart",
            "target": "lib/data/models/car.dart",
            "relationship": "imports",
        }
    ]


def test_resolves_internal_package_import_when_target_exists():
    files = [
        _file(
            "lib/presentation/bloc/car_state.dart",
            "import 'package:rentapp/data/models/car.dart';",
        ),
        _file("lib/data/models/car.dart", "class Car {}"),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert relationships == [
        {
            "source": "lib/presentation/bloc/car_state.dart",
            "target": "lib/data/models/car.dart",
            "relationship": "imports",
        }
    ]


def test_detects_implements_extends_and_mixins_from_declarations():
    files = [
        _file(
            "lib/domain/repositories/car_repository.dart",
            "abstract class CarRepository {}",
        ),
        _file(
            "lib/data/repositories/car_repository_impl.dart",
            """
            import '../../domain/repositories/car_repository.dart';
            class CarRepositoryImpl implements CarRepository {}
            """,
        ),
        _file(
            "lib/presentation/bloc/car_state.dart",
            """
            abstract class CarState {}
            mixin EquatableMixin {}
            """,
        ),
        _file(
            "lib/presentation/bloc/cars_loading.dart",
            """
            import 'car_state.dart';
            class CarsLoading extends CarState with EquatableMixin {}
            """,
        ),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert {
        (
            relationship["source"],
            relationship["target"],
            relationship["relationship"],
        )
        for relationship in relationships
    } == {
        (
            "lib/data/repositories/car_repository_impl.dart",
            "lib/domain/repositories/car_repository.dart",
            "imports",
        ),
        (
            "lib/data/repositories/car_repository_impl.dart",
            "lib/domain/repositories/car_repository.dart",
            "implements",
        ),
        (
            "lib/presentation/bloc/cars_loading.dart",
            "lib/presentation/bloc/car_state.dart",
            "imports",
        ),
        (
            "lib/presentation/bloc/cars_loading.dart",
            "lib/presentation/bloc/car_state.dart",
            "extends",
        ),
        (
            "lib/presentation/bloc/cars_loading.dart",
            "lib/presentation/bloc/car_state.dart",
            "mixes_in",
        ),
    }


def test_does_not_create_relationships_from_keywords_or_comments():
    files = [
        _file(
            "lib/data/models/car.dart",
            """
            // import '../../presentation/bloc/car_state.dart';
            class Car {
              final String description =
                  'class Fake implements CarState';
            }
            """,
        ),
        _file(
            "lib/presentation/bloc/car_state.dart",
            "class CarState {}",
        ),
        _file(
            "lib/presentation/pages/car_details_page.dart",
            "class CarDetailsPage {}",
        ),
        _file(
            "lib/presentation/widgets/car_card.dart",
            "class CarCard {}",
        ),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert relationships == []


def test_refuses_ambiguous_type_relationship_without_a_resolving_import():
    files = [
        _file("lib/a/base.dart", "abstract class Base {}"),
        _file("lib/b/base.dart", "abstract class Base {}"),
        _file("lib/feature/child.dart", "class Child extends Base {}"),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert relationships == []


def test_does_not_resolve_a_unique_type_by_name_without_an_import():
    files = [
        _file("lib/domain/base.dart", "abstract class Base {}"),
        _file("lib/feature/child.dart", "class Child extends Base {}"),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert relationships == []


def test_generic_type_arguments_do_not_become_relationship_targets():
    files = [
        _file("lib/domain/contract.dart", "abstract class Contract<T, U> {}"),
        _file("lib/domain/value.dart", "class Value {}"),
        _file(
            "lib/data/implementation.dart",
            """
            import '../domain/contract.dart';
            import '../domain/value.dart';
            class Implementation implements Contract<String, Value> {}
            """,
        ),
    ]

    relationships = DartStructureAnalyzer().analyze_repository(files)

    assert {
        relationship["target"]
        for relationship in relationships
        if relationship["relationship"] == "implements"
    } == {"lib/domain/contract.dart"}
