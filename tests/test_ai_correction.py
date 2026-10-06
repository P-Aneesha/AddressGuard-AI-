import sys
import types


def test_ai_contextual_spelling_correction(monkeypatch):
    class Message:
        content = '''{"corrections":[
          {"field":"city","original":"Hydrabad","suggested":"Hyderabad","confidence":99,"reason":"city spelling"},
          {"field":"locality","original":"Jublee Hils","suggested":"Jubilee Hills","confidence":96,"reason":"locality spelling"}
        ]}'''

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]

    class Completions:
        def create(self, **kwargs):
            return Response()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeClient))

    from services.ai_correction_service import generate_ai_corrections

    corrections, meta = generate_ai_corrections(
        "Jublee Hils, Hydrabad, Telangana, 500033",
        {"city": "Hydrabad", "locality": "Jublee Hils"},
        "test-key",
        "https://example.invalid/v1",
        "test-model",
        5,
    )

    assert meta["source"] == "ai"
    assert any(c["original"] == "Hydrabad" and c["suggested"] == "Hyderabad" for c in corrections)
    assert any(c["original"] == "Jublee Hils" and c["suggested"] == "Jubilee Hills" for c in corrections)


def test_ai_correction_does_not_rewrite_numeric_values():
    from services.ai_correction_service import generate_ai_corrections

    # No key means the service must safely fall back without making any changes.
    corrections, meta = generate_ai_corrections(
        "H.No 12-3-45, Hyderabad, 500033, 9876543210",
        {},
        "",
        "",
        "",
        5,
    )
    assert corrections == []
    assert meta["source"] == "fallback"
