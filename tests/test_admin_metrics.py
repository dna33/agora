from urllib.parse import urlparse

from app.core.config import get_settings


def _admin_headers():
    return {"X-Admin-Api-Key": "admin-secret"}


def _token_from_feedback_link(link: str) -> str:
    parts = [part for part in urlparse(link).path.split("/") if part]
    if len(parts) >= 3 and parts[-1] == "edit" and parts[-3] == "feedback":
        return parts[-2]
    if len(parts) >= 2 and parts[-2] == "feedback":
        return parts[-1]
    raise AssertionError(f"Unexpected feedback link format: {link}")


def _ingest_and_optionally_correct(client, text: str, correct: bool = False) -> None:
    ingest_res = client.post(
        "/ingest",
        json={"text": text, "place_code": "alameda-santiago"},
    )
    assert ingest_res.status_code == 200
    body = ingest_res.json()

    if correct:
        token = _token_from_feedback_link(body["feedback_link"])
        patch = client.patch(
            f"/feedback/{token}",
            json={"summary_line": "Correccion humana para test de calidad."},
        )
        assert patch.status_code == 200


def test_admin_pipeline_metrics_and_review(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    _ingest_and_optionally_correct(client, "Mensaje base uno", correct=False)
    _ingest_and_optionally_correct(client, "Mensaje base dos", correct=True)

    metrics = client.get("/admin/metrics/pipeline", headers=_admin_headers())
    assert metrics.status_code == 200
    metrics_body = metrics.json()
    assert metrics_body["total_messages"] >= 2
    assert metrics_body["correction_rate_pct"] >= 0
    assert "avg_cost_per_message_usd" in metrics_body

    review = client.get("/admin/messages/review?limit=10&offset=0", headers=_admin_headers())
    assert review.status_code == 200
    review_body = review.json()
    assert review_body["total"] >= 2
    assert len(review_body["items"]) >= 2
    assert review_body["items"][0]["final_primary_topic"] in {
        "Movilidad",
        "Seguridad",
        "Espacio publico",
        "Medioambiente",
        "Comercio",
        "Cuidados",
        "Cultura",
        "Otro",
        None,
    }

    csv_export = client.get("/admin/messages/review.csv?limit=10", headers=_admin_headers())
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers["content-type"]
    assert "message_id" in csv_export.text

    convo_metrics = client.get("/admin/metrics/conversation?period_days=7", headers=_admin_headers())
    assert convo_metrics.status_code == 200
    convo_body = convo_metrics.json()
    assert "threads_total" in convo_body
    assert "close_rate_pct" in convo_body
    assert "second_turn_response_rate_pct" in convo_body

    get_settings.cache_clear()
