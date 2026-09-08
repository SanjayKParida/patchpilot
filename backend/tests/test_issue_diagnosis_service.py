import json

from app.services.issue_diagnosis_service import IssueDiagnosisService


# ============================================================
# FAKE LLM SERVICE
# ============================================================

class FakeLLMService:
    """
    Deterministic fake LLM used for unit testing.

    It records the prompt it receives and returns a fixed
    diagnosis response.
    """

    def __init__(self, response=None):
        self.prompt = None

        self.response = response or """
{
    "root_cause": "The car loading flow is not completing successfully.",
    "confidence": 0.82,
    "relevant_files": [
        "lib/presentation/bloc/car_bloc.dart",
        "lib/data/repositories/car_repository_impl.dart",
        "lib/data/datasources/firebase_car_data_source.dart"
    ],
    "explanation": "The loading state is emitted before the asynchronous car retrieval flow completes.",
    "suggested_fix": "Inspect the asynchronous getCars flow and verify that CarsLoaded or CarsError is always reached."
}
"""

    def ask(self, prompt):
        self.prompt = prompt
        return self.response


# ============================================================
# SAMPLE ANALYSIS PACKAGE
# ============================================================

def build_analysis():
    """
    Minimal AnalysisResult matching the output contract of
    AnalyzeIssueService.

    This intentionally contains only the information the
    diagnosis layer should consume.
    """

    return {
        "issue": {
            "title": "Cars keep loading indefinitely on the home screen",
            "body": (
                "The car list never appears and the loading indicator "
                "remains visible."
            ),
        },

        "signals": [
            {
                "term": "firebase",
                "type": "technology",
            },
            {
                "term": "firestore",
                "type": "technology",
            },
            {
                "term": "loading",
                "type": "behavior",
            },
            {
                "term": "car",
                "type": "domain",
            },
            {
                "term": "repository",
                "type": "architecture",
            },
            {
                "term": "bloc",
                "type": "architecture",
            },
        ],

        "ranked": [
            {
                "rank": 1,
                "path": "lib/presentation/pages/car_list_screen.dart",
                "total_score": 4.9738,
            },
            {
                "rank": 2,
                "path": "lib/presentation/bloc/car_bloc.dart",
                "total_score": 4.4797,
            },
            {
                "rank": 3,
                "path": "lib/data/repositories/car_repository_impl.dart",
                "total_score": 4.3258,
            },
            {
                "rank": 4,
                "path": "lib/data/datasources/firebase_car_data_source.dart",
                "total_score": 4.0528,
            },
            {
                "rank": 5,
                "path": "lib/presentation/bloc/car_state.dart",
                "total_score": 4.0439,
            },
            {
                "rank": 6,
                "path": "lib/domain/repositories/car_repository.dart",
                "total_score": 4.0154,
            },
            {
                "rank": 7,
                "path": "lib/domain/usecases/get_cars.dart",
                "total_score": 3.1122,
            },
            {
                "rank": 8,
                "path": "lib/main.dart",
                "total_score": 2.8801,
            },
            {
                "rank": 9,
                "path": "lib/injection_container.dart",
                "total_score": 2.3142,
            },
            {
                "rank": 10,
                "path": "lib/presentation/bloc/car_event.dart",
                "total_score": 2.2376,
            },
        ],

        "primary_files": [
            {
                "path": "lib/presentation/pages/car_list_screen.dart",
                "content": """
class CarListScreen extends StatelessWidget {
    @override
    Widget build(BuildContext context) {
        return BlocBuilder<CarBloc, CarState>(
            builder: (context, state) {
                if (state is CarsLoading) {
                    return const CircularProgressIndicator();
                }

                if (state is CarsLoaded) {
                    return ListView.builder(
                        itemCount: state.cars.length,
                        itemBuilder: (_, index) {
                            return CarCard(
                                car: state.cars[index],
                            );
                        },
                    );
                }

                return const SizedBox();
            },
        );
    }
}
""",
            },

            {
                "path": "lib/presentation/bloc/car_bloc.dart",
                "content": """
class CarBloc extends Bloc<CarEvent, CarState> {
    final GetCars getCars;

    CarBloc({required this.getCars})
        : super(CarsLoading()) {

        on<LoadCars>((event, emit) async {
            emit(CarsLoading());

            try {
                final cars = await getCars.call();
                emit(CarsLoaded(cars));
            } catch (e) {
                emit(CarsError(e.toString()));
            }
        });
    }
}
""",
            },

            {
                "path": "lib/data/repositories/car_repository_impl.dart",
                "content": """
class CarRepositoryImpl implements CarRepository {
    final FirebaseCarDataSource dataSource;

    CarRepositoryImpl(this.dataSource);

    @override
    Future<List<Car>> fetchCars() async {
        return await dataSource.getCars();
    }
}
""",
            },

            {
                "path": "lib/data/datasources/firebase_car_data_source.dart",
                "content": """
class FirebaseCarDataSource {
    final FirebaseFirestore firestore;

    FirebaseCarDataSource({
        required this.firestore,
    });

    Future<List<Car>> getCars() async {
        var snapshot = await firestore
            .collection('cars')
            .get();

        return snapshot.docs
            .map((doc) => Car.fromMap(doc.data()))
            .toList();
    }
}
""",
            },

            {
                "path": "lib/presentation/bloc/car_state.dart",
                "content": """
abstract class CarState {}

class CarsLoading extends CarState {}

class CarsLoaded extends CarState {
    final List<Car> cars;

    CarsLoaded(this.cars);
}

class CarsError extends CarState {
    final String message;

    CarsError(this.message);
}
""",
            },
        ],

        "available_files": [
            "lib/domain/repositories/car_repository.dart",
            "lib/domain/usecases/get_cars.dart",
            "lib/main.dart",
            "lib/injection_container.dart",
            "lib/presentation/bloc/car_event.dart",
        ],

        "direct_evidence": [
            {
                "file": {
                    "path": "lib/presentation/bloc/car_bloc.dart",
                },
                "evidence_type": "class",
                "concept": "bloc",
                "strength": 1.0,
                "line": 1,
                "identifier": "CarBloc",
            },
            {
                "file": {
                    "path": "lib/presentation/bloc/car_state.dart",
                },
                "evidence_type": "class",
                "concept": "loading",
                "strength": 1.0,
                "line": 3,
                "identifier": "CarsLoading",
            },
            {
                "file": {
                    "path": "lib/data/datasources/firebase_car_data_source.dart",
                },
                "evidence_type": "property_access",
                "concept": "firestore",
                "strength": 0.7,
                "line": 8,
                "identifier": "firestore",
            },
        ],

        "structural_results": [
            {
                "source": "lib/presentation/bloc/car_bloc.dart",
                "target": "lib/domain/usecases/get_cars.dart",
                "relationship": "imports",
                "distance": 1,
            },
            {
                "source": "lib/data/repositories/car_repository_impl.dart",
                "target": "lib/domain/repositories/car_repository.dart",
                "relationship": "implements",
                "distance": 1,
            },
            {
                "source": "lib/data/repositories/car_repository_impl.dart",
                "target": "lib/data/datasources/firebase_car_data_source.dart",
                "relationship": "imports",
                "distance": 1,
            },
        ],

        "seed_paths": [
            "lib/data/datasources/firebase_car_data_source.dart",
            "lib/data/repositories/car_repository_impl.dart",
            "lib/presentation/bloc/car_bloc.dart",
            "lib/presentation/bloc/car_state.dart",
        ],
    }


# ============================================================
# BASIC CONTRACT
# ============================================================

def test_diagnosis_returns_expected_fields():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    analysis = build_analysis()

    diagnosis = service.diagnose(
        analysis
    )

    assert "root_cause" in diagnosis
    assert "confidence" in diagnosis
    assert "relevant_files" in diagnosis
    assert "explanation" in diagnosis
    assert "suggested_fix" in diagnosis


# ============================================================
# LLM IS ACTUALLY USED
# ============================================================

def test_diagnosis_calls_llm():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    analysis = build_analysis()

    service.diagnose(
        analysis
    )

    assert fake_llm.prompt is not None
    assert fake_llm.prompt.strip()
    assert "Do not prescribe" in fake_llm.prompt
    assert "issue does not mention" in fake_llm.prompt


# ============================================================
# ISSUE IS INCLUDED IN PROMPT
# ============================================================

def test_prompt_contains_issue():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    analysis = build_analysis()

    service.diagnose(
        analysis
    )

    prompt = fake_llm.prompt

    assert (
        "Cars keep loading indefinitely"
        in prompt
    )

    assert (
        "loading indicator"
        in prompt
    )


# ============================================================
# SIGNALS ARE INCLUDED
# ============================================================

def test_prompt_contains_signals():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    assert "firebase" in prompt
    assert "firestore" in prompt
    assert "loading" in prompt
    assert "car" in prompt
    assert "repository" in prompt
    assert "bloc" in prompt


# ============================================================
# PRIMARY FILES ARE INCLUDED
# ============================================================

def test_prompt_contains_primary_files():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    expected_files = [
        "lib/presentation/pages/car_list_screen.dart",
        "lib/presentation/bloc/car_bloc.dart",
        "lib/data/repositories/car_repository_impl.dart",
        "lib/data/datasources/firebase_car_data_source.dart",
        "lib/presentation/bloc/car_state.dart",
    ]

    for path in expected_files:

        assert path in prompt


# ============================================================
# FULL FILE CONTENT IS INCLUDED
# ============================================================

def test_prompt_contains_full_primary_file_content():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    assert "CircularProgressIndicator" in prompt
    assert "CarsLoading" in prompt
    assert "CarsLoaded" in prompt
    assert "Firestore" in prompt
    assert "collection('cars')" in prompt


# ============================================================
# AVAILABLE FILE PATHS ARE INCLUDED
# ============================================================

def test_prompt_contains_available_file_paths():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    assert (
        "lib/domain/usecases/get_cars.dart"
        in prompt
    )

    assert (
        "lib/domain/repositories/car_repository.dart"
        in prompt
    )


# ============================================================
# EVIDENCE IS INCLUDED
# ============================================================

def test_prompt_contains_evidence():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    assert "CarsLoading" in prompt
    assert "firestore" in prompt
    assert "CarBloc" in prompt


# ============================================================
# STRUCTURAL RELATIONSHIPS ARE INCLUDED
# ============================================================

def test_prompt_contains_structural_relationships():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    assert "imports" in prompt
    assert "implements" in prompt

    assert (
        "car_repository_impl.dart"
        in prompt
    )

    assert (
        "firebase_car_data_source.dart"
        in prompt
    )


# ============================================================
# RANK IS PRESENT
# ============================================================

def test_prompt_contains_rank_information():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt

    assert "Rank 1" in prompt
    assert "Rank 2" in prompt
    assert "Rank 3" in prompt


# ============================================================
# LLM IS TOLD NOT TO BLAME RANK 1 AUTOMATICALLY
# ============================================================

def test_prompt_contains_non_causality_instruction():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    service.diagnose(
        build_analysis()
    )

    prompt = fake_llm.prompt.lower()

    assert (
        "do not assume"
        in prompt
    )

    assert (
        "ranking"
        in prompt
    )


# ============================================================
# PARSING
# ============================================================

def test_json_response_is_parsed():

    response = json.dumps({
        "root_cause": "Firestore request does not complete.",
        "confidence": 0.91,
        "relevant_files": [
            "lib/data/datasources/firebase_car_data_source.dart"
        ],
        "explanation": "The data source awaits Firestore.",
        "suggested_fix": "Inspect the Firestore query."
    })

    fake_llm = FakeLLMService(
        response=response
    )

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    diagnosis = service.diagnose(
        build_analysis()
    )

    assert (
        diagnosis["root_cause"]
        == "Firestore request does not complete."
    )

    assert (
        diagnosis["confidence"]
        == 0.91
    )

    assert (
        diagnosis["relevant_files"]
        == [
            "lib/data/datasources/"
            "firebase_car_data_source.dart"
        ]
    )


# ============================================================
# INVALID INPUT
# ============================================================

def test_missing_analysis_is_rejected():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    try:
        service.diagnose(None)

    except (ValueError, TypeError):
        return

    assert False, (
        "IssueDiagnosisService should reject "
        "missing analysis input"
    )


# ============================================================
# DETERMINISTIC FAKE RESPONSE
# ============================================================

def test_same_analysis_produces_same_result():

    fake_llm = FakeLLMService()

    service = IssueDiagnosisService(
        llm_service=fake_llm
    )

    analysis = build_analysis()

    first = service.diagnose(
        analysis
    )

    second = service.diagnose(
        analysis
    )

    assert first == second