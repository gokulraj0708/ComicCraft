from app.schemas import ComicPrompt
from app.services.llm import DemoStoryProvider


def test_demo_story_is_structured_and_sequential():
    request = ComicPrompt(
        story_prompt="A scientist receives a radio message from a friendly moon colony.",
        character_name="Asha",
        setting="a rooftop observatory",
        tone="Hopeful",
        art_style="Anime",
        panel_count=5,
    )
    result = DemoStoryProvider().generate(request)
    assert result.provider == "demo"
    assert [panel.panel_number for panel in result.script.panels] == [1, 2, 3, 4, 5]
    assert all("no written words" in panel.image_prompt for panel in result.script.panels)

class _FakeResponse:
    def __init__(self, text='{}'):
        self.text = text


class _FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append((model, config))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes):
        self.models = _FakeModels(outcomes)


def test_gemini_503_retries_then_switches_model(monkeypatch):
    from app.config import Settings
    from app.services.llm import GeminiStoryProvider

    settings = Settings(
        app_env="test",
        gemini_api_key="test-key",
        gemini_outline_model="primary-model",
        gemini_outline_fallback_models="fallback-model",
        gemini_retry_attempts=2,
        gemini_retry_base_seconds=0.1,
        gemini_retry_max_seconds=0.5,
    )
    provider = GeminiStoryProvider.__new__(GeminiStoryProvider)
    provider.settings = settings
    provider.client = _FakeClient([
        Exception("503 UNAVAILABLE: high demand"),
        Exception("503 UNAVAILABLE: high demand"),
        _FakeResponse('{"panels": []}'),
    ])
    monkeypatch.setattr("app.services.llm.time.sleep", lambda _: None)

    response, model = provider._generate_json(
        primary_model=settings.gemini_outline_model,
        fallback_models=settings.gemini_outline_fallback_models,
        prompt="test",
        stage="outline",
    )

    assert model == "fallback-model"
    assert response.text == '{"panels": []}'
    assert [model for model, _ in provider.client.models.calls] == ["primary-model", "primary-model", "fallback-model"]
    assert all(config == {"response_mime_type": "application/json"} for _, config in provider.client.models.calls)


def test_gemini_404_switches_model_without_retry(monkeypatch):
    from app.config import Settings
    from app.services.llm import GeminiStoryProvider

    settings = Settings(
        app_env="test",
        gemini_api_key="test-key",
        gemini_outline_model="missing-model",
        gemini_outline_fallback_models="fallback-model",
        gemini_retry_attempts=3,
        gemini_retry_base_seconds=0.1,
        gemini_retry_max_seconds=0.5,
    )
    provider = GeminiStoryProvider.__new__(GeminiStoryProvider)
    provider.settings = settings
    provider.client = _FakeClient([
        Exception("404 NOT_FOUND: model missing-model is not found"),
        _FakeResponse('{"panels": []}'),
    ])

    response, model = provider._generate_json(
        primary_model=settings.gemini_outline_model,
        fallback_models=settings.gemini_outline_fallback_models,
        prompt="test",
        stage="outline",
    )

    assert model == "fallback-model"
    assert [model for model, _ in provider.client.models.calls] == ["missing-model", "fallback-model"]
