"""GET /api/fuzzy/explain on a district's official inputs."""


def test_fuzzy_explain_runs_on_a_districts_official_inputs():
    from fastapi.testclient import TestClient
    from app.data import preprocessing as pp
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/fuzzy/explain", params={"location": "Salem", "season": "Rabi"})
    assert r.status_code == 200
    body = r.json()
    assert body["inputs_from"] == {"location": "Salem", "season": "Rabi", "year": 2024}
    p = pp.get_region_season_profile("Salem", "Rabi")
    by_inputs = client.get("/api/fuzzy/explain", params={"rainfall_dev": p.rainfall.avg_deviation_percent,
                                                         "water_storage": p.water.avg_storage_percent,
                                                         "soil_fert": p.soil.fertility_index}).json()
    assert body["outputs"] == by_inputs["outputs"]


def test_fuzzy_explain_says_when_a_district_has_no_official_input():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/fuzzy/explain", params={"location": "Salem", "season": "Kharif"})   # no reservoir reading
    assert r.status_code == 400 and "Official Data Not Available" in r.json()["detail"]
    assert client.get("/api/fuzzy/explain", params={"location": "Salem"}).status_code == 422
    assert client.get("/api/fuzzy/explain", params={"rainfall_dev": 1}).status_code == 422
