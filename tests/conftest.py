import pytest

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
BENZOQUINONE = "O=C1C=CC(=O)C=C1"
CAFFEINE = "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"


@pytest.fixture(scope="session")
def app():
    """The Flask app with the real models loaded once for the whole test run."""
    from admet_ai.web.app import app as flask_app
    from admet_ai.web.run import setup_web

    setup_web(secret_key="test-secret")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def predicted_client(client):
    """A client whose session already holds predictions for three molecules."""
    response = client.post(
        "/", data={"input-type": "text", "text-smiles": "\n".join([IBUPROFEN, BENZOQUINONE, CAFFEINE])}
    )
    assert response.status_code == 200
    return client
