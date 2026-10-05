import io
import json
import re

from admet_ai.web.app import utils as web_utils
from admet_ai.web.app import views
from tests.conftest import BENZOQUINONE, CAFFEINE, IBUPROFEN


def overview_rows(html):
    match = re.search(r'<script type="application/json" id="overview-data">(.*?)</script>', html, re.S)
    return json.loads(match.group(1))


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="name-radio"' in response.data


def test_text_prediction_shows_every_molecule_and_warns_on_invalid(client):
    response = client.post(
        "/", data={"input-type": "text", "text-smiles": f"{IBUPROFEN}\nnot_a_smiles\n\n{BENZOQUINONE}"}
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Invalid SMILES string: not_a_smiles" in html
    assert html.count('class="molecule-prediction"') == 2

    rows = overview_rows(html)
    assert [row["smiles"] for row in rows] == [IBUPROFEN, BENZOQUINONE]
    assert rows[0]["closest_drug"]["similarity"] == 1.0
    assert rows[1]["num_alerts"] == 2


def test_file_upload(client):
    response = client.post(
        "/",
        data={
            "input-type": "file",
            "smiles-column": "compound",
            "data": (io.BytesIO(f"compound\n{IBUPROFEN}\n{CAFFEINE}\n".encode()), "molecules.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.get_data(as_text=True).count('class="molecule-prediction"') == 2


def test_file_upload_with_missing_column(client):
    response = client.post(
        "/",
        data={"input-type": "file", "smiles-column": "smiles", "data": (io.BytesIO(b"other\nCCO\n"), "x.csv")},
        content_type="multipart/form-data",
    )
    assert "SMILES column &#39;smiles&#39; not found" in response.get_data(as_text=True)


def test_draw_input_ignores_leftover_text(client):
    response = client.post("/", data={"input-type": "draw", "draw-smiles": "c1ccccc1O", "text-smiles": IBUPROFEN})
    rows = overview_rows(response.get_data(as_text=True))
    assert [row["smiles"] for row in rows] == ["c1ccccc1O"]


def test_name_input(client, monkeypatch):
    monkeypatch.setattr(web_utils, "names_to_smiles", lambda names: ([IBUPROFEN], ["unobtainium"]))
    response = client.post("/", data={"input-type": "name", "text-names": "ibuprofen\nunobtainium"})
    html = response.get_data(as_text=True)

    assert "No PubChem match for name: unobtainium" in html
    assert [row["smiles"] for row in overview_rows(html)] == [IBUPROFEN]


def test_name_lookup_failure_is_reported(client, monkeypatch):
    def fail(names):
        raise ConnectionError("Could not reach PubChem")

    monkeypatch.setattr(web_utils, "names_to_smiles", fail)
    response = client.post("/", data={"input-type": "name", "text-names": "ibuprofen"})
    assert "Name lookup failed: Could not reach PubChem" in response.get_data(as_text=True)


def test_empty_input_is_an_error(client):
    response = client.post("/", data={"input-type": "text", "text-smiles": "  \n"})
    assert "No molecules given." in response.get_data(as_text=True)


def test_report_page(predicted_client):
    response = predicted_client.get("/show_results")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count('class="card molecule"') == 3
    assert "window.print()" in html


def test_pdf_falls_back_to_print_view_without_wkhtmltopdf(predicted_client, monkeypatch):
    monkeypatch.setattr(views, "pdf_export_available", lambda: False)
    response = predicted_client.get("/download_pdf")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/show_results?print=1")


def test_csv_download_has_predictions_and_medchem_columns(predicted_client):
    response = predicted_client.get("/download_predictions")
    lines = response.get_data(as_text=True).splitlines()

    assert response.mimetype == "text/csv"
    assert len(lines) == 4
    for column in ["smiles", "hERG", "PAINS_alerts", "synthetic_accessibility", "gi_absorption_boiled_egg"]:
        assert column in lines[0].split(",")


def test_compare(predicted_client):
    response = predicted_client.get("/compare?ids=1,3")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Molecule 1" in html and "Molecule 3" in html and "Molecule 2" not in html


def test_compare_validation(predicted_client):
    assert predicted_client.get("/compare?ids=1").status_code == 400
    assert predicted_client.get("/compare?ids=1,2,3,1,2,3,4,5").status_code == 400
    assert predicted_client.get("/compare?ids=1,99").status_code == 400
    assert predicted_client.get("/compare?ids=a,b").status_code == 400


def test_pages_need_predictions(client):
    for url in ["/show_results", "/download_pdf", "/download_predictions", "/compare?ids=1,2"]:
        assert client.get(url).status_code == 400
    assert client.get("/drugbank_plot").status_code == 400


def test_drugbank_plot_axes(predicted_client):
    response = predicted_client.get("/drugbank_plot", query_string={"x_task": "Mutagenicity"})
    assert response.status_code == 200
    assert response.get_json()["svg"].startswith("<?xml")

    assert predicted_client.get("/drugbank_plot", query_string={"x_task": "Nope"}).status_code == 400


def test_set_atc_code(client):
    response = client.post("/set_atc_code?atc_code=analgesics")
    assert response.get_json()["atc_code"] == "analgesics"
    assert int(response.get_json()["drugbank_size_string"].replace(",", "")) > 0

    assert client.post("/set_atc_code?atc_code=not-a-code").status_code == 400
    assert client.post("/set_atc_code?atc_code=all").get_json()["atc_code"] == "all"


def test_api_predict(client):
    response = client.post(
        "/api/predict",
        json={"smiles": [IBUPROFEN, "bad"], "atc_code": "analgesics", "similar_drugs": 2},
    )
    body = response.get_json()
    molecule = body["molecules"][0]

    assert response.status_code == 200
    assert body["invalid_smiles"] == ["bad"]
    assert body["atc_code"] == "analgesics"
    assert set(molecule) == {"smiles", "predictions", "drugbank_percentiles", "medchem", "risk", "similar_drugs"}
    assert 0 <= molecule["predictions"]["hERG"] <= 1
    assert 0 <= molecule["drugbank_percentiles"]["hERG"] <= 100
    assert len(molecule["similar_drugs"]) == 2
    assert molecule["medchem"]["rules"]["Lipinski"] == []


def test_api_predict_validation(client):
    assert client.post("/api/predict", data="not json").status_code == 400
    assert client.post("/api/predict", json={"smiles": []}).status_code == 400
    assert client.post("/api/predict", json={"smiles": [1]}).status_code == 400
    assert client.post("/api/predict", json={"smiles": ["CCO"], "atc_code": "nope"}).status_code == 400
    assert client.post("/api/predict", json={"smiles": ["CCO"], "similar_drugs": 99}).status_code == 400


def test_api_health(client):
    assert client.get("/api/health").get_json()["status"] == "ok"


def test_heartbeat(client):
    assert client.post("/heartbeat").status_code == 204
