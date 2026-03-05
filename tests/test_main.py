from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_recipes():
    res = client.get("/recipes")
    assert res.status_code == 200
    recipes = res.json()
    assert len(recipes) >= 2
    assert any(r["id"] == "kung_pao_chicken" for r in recipes)


def test_start_and_step_session_to_complete():
    start = client.post(
        "/sessions/start",
        json={"recipe_id": "tomato_egg", "servings": 2, "flavor_level": "normal"},
    )
    assert start.status_code == 200
    session = start.json()
    assert session["status"] == "running"
    session_id = session["session_id"]

    # tomato_egg has 4 steps; call next enough times to finish
    for _ in range(5):
        step_res = client.post(f"/sessions/{session_id}/next")
        assert step_res.status_code == 200

    final = client.get(f"/sessions/{session_id}")
    assert final.status_code == 200
    final_data = final.json()
    assert final_data["status"] == "completed"


def test_seasoning_calculation_basic():
    payload = {
        "base_amount": 3,
        "base_main_weight": 300,
        "actual_main_weight": 450,
        "base_servings": 2,
        "actual_servings": 2,
        "flavor_level": "light",
        "cooking_method": "stir_fry",
        "alpha": 0.9,
        "min_amount": 0,
        "max_amount": 10,
    }
    res = client.post("/seasoning/calculate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert 3.7 <= data["recommended_amount"] <= 4.0
    assert data["note"] == "normal"
