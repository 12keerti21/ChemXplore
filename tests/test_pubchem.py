import io
import json
from urllib.error import HTTPError, URLError

import pytest

from admet_ai import pubchem


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(responses):
    """Returns a urlopen stand-in mapping a name to a SMILES, None (404) or an exception."""

    def urlopen(url, timeout):
        name = url.split("/name/")[1].split("/")[0]
        result = responses[name]
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise HTTPError(url, 404, "Not Found", None, None)
        return FakeResponse(json.dumps({"PropertyTable": {"Properties": [{"CID": 1, "SMILES": result}]}}).encode())

    return urlopen


def test_name_to_smiles(monkeypatch):
    monkeypatch.setattr(pubchem, "urlopen", fake_urlopen({"ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O"}))
    assert pubchem.name_to_smiles("ibuprofen") == "CC(C)Cc1ccc(cc1)C(C)C(=O)O"


def test_unknown_name_returns_none(monkeypatch):
    monkeypatch.setattr(pubchem, "urlopen", fake_urlopen({"nothing": None}))
    assert pubchem.name_to_smiles("nothing") is None


def test_network_failure_raises_connection_error(monkeypatch):
    monkeypatch.setattr(pubchem, "urlopen", fake_urlopen({"x": URLError("down")}))
    with pytest.raises(ConnectionError):
        pubchem.name_to_smiles("x")


def test_names_are_url_encoded(monkeypatch):
    seen = []

    def urlopen(url, timeout):
        seen.append(url)
        raise HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(pubchem, "urlopen", urlopen)
    pubchem.name_to_smiles("acetylsalicylic acid/x")
    assert "acetylsalicylic%20acid%2Fx" in seen[0]


def test_names_to_smiles_splits_found_and_missing(monkeypatch):
    monkeypatch.setattr(pubchem, "urlopen", fake_urlopen({"a": "CCO", "b": None, "c": "CCN"}))
    assert pubchem.names_to_smiles(["a", "b", "c"]) == (["CCO", "CCN"], ["b"])
