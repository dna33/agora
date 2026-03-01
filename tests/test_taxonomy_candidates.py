from app.core.config import get_settings
from app.services.model_service import ExtractionResult, ModelService


def _admin_headers():
    return {"X-Admin-Api-Key": "admin-secret"}


def test_taxonomy_candidate_created_and_approved(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    def fake_extract(self, db, text, message_id=None):  # noqa: ANN001
        _ = (self, db, text, message_id)
        return ExtractionResult(
            summary_line="Mensaje dificil de clasificar con taxonomia actual",
            primary_topic="other",
            desired_future="other",
            tension_type="other",
            quote_snippet="No existe categoria para esto",
            raw={
                "summary_line": "Mensaje dificil de clasificar con taxonomia actual",
                "primary_topic": "other",
                "desired_future": "other",
                "tension_type": "other",
                "quote_snippet": "No existe categoria para esto",
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "taxonomy_fit_score": 0.22,
                "taxonomy_gap_type": "primary_topic",
                "taxonomy_candidate_label": "vida nocturna barrial",
                "taxonomy_candidate_reason": "falta eje para dinamicas nocturnas locales",
            },
        )

    monkeypatch.setattr(ModelService, "extract", fake_extract)

    r1 = client.post("/ingest", json={"text": "Falta categoria de vida nocturna barrial", "place_code": "alameda-santiago"})
    assert r1.status_code == 200

    r2 = client.post("/ingest", json={"text": "Otra senal de vida nocturna barrial", "place_code": "alameda-santiago"})
    assert r2.status_code == 200

    listed = client.get("/admin/taxonomy/candidates?status=pending&limit=50", headers=_admin_headers())
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] >= 1
    first = payload["items"][0]
    assert first["taxonomy_type"] == "primary_topic"
    assert first["candidate_label"] == "vida nocturna barrial"
    assert first["support_count"] >= 2

    decision = client.post(
        f"/admin/taxonomy/candidates/{first['id']}/approve",
        headers=_admin_headers(),
        json={"review_note": "Aprobada para proxima version"},
    )
    assert decision.status_code == 200
    d = decision.json()
    assert d["status"] == "approved"
    assert d["review_note"] == "Aprobada para proxima version"

    get_settings.cache_clear()

