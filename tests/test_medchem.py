from rdkit import Chem

from admet_ai.medchem import (
    BOILED_EGG_WHITE,
    _inside_ellipse,
    analyze_molecule,
    boiled_egg,
    compute_medchem_properties,
    drug_likeness_rules,
    structural_alerts,
    synthetic_accessibility,
)
from tests.conftest import BENZOQUINONE, CAFFEINE, IBUPROFEN

# Cyclosporine: large and polar, so it breaks several rules
CYCLOSPORINE = (
    "CC[C@H]1C(=O)N(CC(=O)N([C@H](C(=O)N[C@H](C(=O)N([C@H](C(=O)N[C@H](C(=O)N[C@@H](C(=O)N([C@H](C(=O)N([C@H]"
    "(C(=O)N([C@H](C(=O)N([C@H](C(=O)N1)[C@@H]([C@H](C)C/C=C/C)O)C)C(C)C)C)CC(C)C)C)CC(C)C)C)C)C)CC(C)C)C)C(C)C)"
    "CC(C)C)C)C"
)


def mol(smiles):
    return Chem.MolFromSmiles(smiles)


def test_ibuprofen_passes_every_rule():
    assert drug_likeness_rules(mol(IBUPROFEN)) == {
        "Lipinski": [],
        "Ghose": [],
        "Veber": [],
        "Egan": [],
        "Muegge": [],
    }


def test_cyclosporine_breaks_lipinski_and_veber():
    rules = drug_likeness_rules(mol(CYCLOSPORINE))
    assert "MW > 500" in rules["Lipinski"]
    assert "TPSA > 140" in rules["Veber"]


def test_small_molecule_fails_ghose_size_limits():
    assert "MW outside 160-480" in drug_likeness_rules(mol(BENZOQUINONE))["Ghose"]


def test_quinone_triggers_pains_and_brenk_alerts_with_atoms():
    alerts = structural_alerts(mol(BENZOQUINONE))
    assert {alert["catalog"] for alert in alerts} == {"PAINS", "Brenk"}
    assert all(alert["atoms"] for alert in alerts)


def test_ibuprofen_has_no_alerts():
    assert structural_alerts(mol(IBUPROFEN)) == []


def test_synthetic_accessibility_is_easy_for_simple_drugs_and_harder_for_cyclosporine():
    assert 1 <= synthetic_accessibility(mol(IBUPROFEN)) < 3
    assert synthetic_accessibility(mol(CYCLOSPORINE)) > synthetic_accessibility(mol(IBUPROFEN))


def test_boiled_egg_matches_known_behaviour():
    ibuprofen = boiled_egg(mol(IBUPROFEN))
    assert ibuprofen["gi_absorption"] and ibuprofen["bbb_permeant"]

    cyclosporine = boiled_egg(mol(CYCLOSPORINE))
    assert not cyclosporine["gi_absorption"] and not cyclosporine["bbb_permeant"]


def test_inside_ellipse_center_and_far_point():
    assert _inside_ellipse(*BOILED_EGG_WHITE["center"], BOILED_EGG_WHITE)
    assert not _inside_ellipse(300, 10, BOILED_EGG_WHITE)


def test_analyze_molecule_has_every_section():
    assert set(analyze_molecule(mol(CAFFEINE))) == {"rules", "alerts", "sa_score", "boiled_egg"}


def test_compute_medchem_properties_keeps_order_and_duplicates():
    smiles = [IBUPROFEN, BENZOQUINONE, IBUPROFEN]
    table = compute_medchem_properties(smiles)

    assert list(table.index) == smiles
    assert table["PAINS_alerts"].tolist() == [0, 1, 0]
    assert table.loc[BENZOQUINONE, "Ghose_violations"] == 3
