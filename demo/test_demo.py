from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def payload() -> dict:
    return {
        "text": "Quiero promocionar una bebida fría nueva para esta semana",
        "business": {
            "name": "Café Central",
            "category": "Gastronomía",
            "city": "Tegucigalpa",
            "primary_product": "una bebida fría de café",
            "target_audience": "Estudiantes universitarios",
            "platform": "instagram",
            "objective": "store_visits",
            "tone": "youthful",
        },
    }


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["provider"] == "demo"


def test_generation_is_structured_and_personalized() -> None:
    response = client.post("/api/demo/generate", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["artifact_type"] == "social_post"
    assert body["platform"] == "instagram"
    assert "Café Central" in body["caption"]
    assert "Tegucigalpa" in body["caption"]
    assert len(body["hashtags"]) <= 5


def test_does_not_invent_price_or_discount() -> None:
    response = client.post("/api/demo/generate", json=payload())
    body = response.json()
    combined = " ".join([body["hook"], body["caption"], body["call_to_action"]]).lower()
    assert "2x1" not in combined
    assert "$" not in combined
    assert "descuento" not in combined


def test_rejects_guaranteed_results_claim() -> None:
    data = payload()
    data["text"] = "Garantiza que esto duplicará mis ventas"
    response = client.post("/api/demo/generate", json=data)
    assert response.status_code == 422
