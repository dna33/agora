from app.services.model_service import ModelService


def test_positive_sentiment_overrides_deficit_future():
    service = ModelService()
    parsed = {
        "summary_line": "Lugar agradable y activo.",
        "primary_topic": "public_space",
        "desired_future": "cleaner_space",
        "tension_type": "none",
        "quote_snippet": "Me gusta como se usa este lugar.",
        "sentiment_score": 0.8,
        "sentiment_label": "positive",
    }

    result = service._sanitize_extract_payload(parsed, "Me gusta este lugar, funciona bien.")
    assert result.desired_future == "preserve_what_works"


def test_negative_sentiment_keeps_deficit_future():
    service = ModelService()
    parsed = {
        "summary_line": "Zona insegura de noche.",
        "primary_topic": "safety",
        "desired_future": "safer_nights",
        "tension_type": "security_vs_privacy",
        "quote_snippet": "Me da miedo pasar de noche.",
        "sentiment_score": -0.7,
        "sentiment_label": "negative",
    }

    result = service._sanitize_extract_payload(parsed, "Me da miedo pasar por aca de noche.")
    assert result.desired_future == "safer_nights"
