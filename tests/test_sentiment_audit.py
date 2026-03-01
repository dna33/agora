from app.core.config import get_settings


def _admin_headers():
    return {"X-Admin-Api-Key": "admin-secret"}


def test_sentiment_audit_sample_and_evaluate(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    get_settings.cache_clear()

    client.post("/ingest", json={"text": "Me gusta este lugar, esta mejor y mas tranquilo.", "place_code": "alameda-santiago"})
    client.post("/ingest", json={"text": "Da miedo caminar aqui de noche por lo oscuro.", "place_code": "alameda-santiago"})

    sample_res = client.get("/admin/sentiment/audit/sample?sample_size=10", headers=_admin_headers())
    assert sample_res.status_code == 200
    sample = sample_res.json()
    assert sample["sample_size"] >= 2
    assert len(sample["items"]) >= 2
    assert "model_label" in sample["items"][0]
    assert "heuristic_label" in sample["items"][0]

    payload = {
        "items": [
            {"message_id": item["message_id"], "manual_label": item["heuristic_label"]}
            for item in sample["items"]
        ]
    }
    eval_res = client.post("/admin/sentiment/audit/evaluate", headers=_admin_headers(), json=payload)
    assert eval_res.status_code == 200
    out = eval_res.json()
    assert out["compared_count"] >= 2
    assert "model_accuracy_pct" in out
    assert "heuristic_accuracy_pct" in out

    page = client.get("/admin/sentiment/audit/view?admin_api_key=admin-secret")
    assert page.status_code == 200
    assert "Chequeo Manual de Sentimiento" in page.text
    assert "/admin/sentiment/audit/sample" in page.text
    assert "/admin/sentiment/audit/evaluate" in page.text

    get_settings.cache_clear()
