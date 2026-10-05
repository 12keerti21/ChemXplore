from rdkit import Chem

from admet_ai.similarity import find_similar_drugs
from tests.conftest import IBUPROFEN


def test_ibuprofen_finds_itself_first():
    drugs = find_similar_drugs(Chem.MolFromSmiles(IBUPROFEN), top_k=5)

    assert len(drugs) == 5
    assert "Ibuprofen" in {drug["name"] for drug in drugs[:2]}
    assert drugs[0]["similarity"] == 1.0
    assert drugs[0]["url"] == f"https://go.drugbank.com/drugs/{drugs[0]['id']}"


def test_results_are_sorted_by_similarity():
    similarities = [drug["similarity"] for drug in find_similar_drugs(Chem.MolFromSmiles("c1ccccc1O"), top_k=10)]
    assert similarities == sorted(similarities, reverse=True)
