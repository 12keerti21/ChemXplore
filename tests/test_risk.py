import pytest

from admet_ai.risk import CYP_INHIBITION_IDS, HIGH, LOW, MEDIUM, risk_score, risk_summary


def safe_properties(**overrides):
    properties = {
        "hERG": 0.1,
        "AMES": 0.1,
        "DILI": 0.1,
        "ClinTox": 0.1,
        "HIA_Hou": 0.95,
        "Solubility_AqSolDB": -2.0,
        "Lipinski": 4.0,
        **{cyp: 0.1 for cyp in CYP_INHIBITION_IDS},
    }
    properties.update(overrides)
    return properties


def levels(flags):
    return {flag["key"]: flag["level"] for flag in flags}


def test_safe_molecule_is_all_low():
    flags = risk_summary(safe_properties())
    assert set(levels(flags).values()) == {LOW}
    assert risk_score(flags) == 0


@pytest.mark.parametrize("value, expected", [(0.39, LOW), (0.4, MEDIUM), (0.69, MEDIUM), (0.7, HIGH)])
def test_probability_thresholds(value, expected):
    assert levels(risk_summary(safe_properties(hERG=value)))["hERG"] == expected


def test_worst_cyp_is_reported():
    flags = risk_summary(safe_properties(CYP3A4_Veith=0.9))
    cyp = next(flag for flag in flags if flag["key"] == "CYP")
    assert cyp["level"] == HIGH
    assert cyp["value"].startswith("CYP3A4")


@pytest.mark.parametrize("hia, expected", [(0.9, LOW), (0.5, MEDIUM), (0.2, HIGH)])
def test_low_absorption_is_risky(hia, expected):
    assert levels(risk_summary(safe_properties(HIA_Hou=hia)))["HIA"] == expected


@pytest.mark.parametrize("log_s, expected", [(-3.0, LOW), (-5.0, MEDIUM), (-7.0, HIGH)])
def test_solubility_classes(log_s, expected):
    assert levels(risk_summary(safe_properties(Solubility_AqSolDB=log_s)))["Solubility"] == expected


@pytest.mark.parametrize("satisfied, expected", [(4.0, LOW), (3.0, MEDIUM), (2.0, HIGH)])
def test_lipinski_violations(satisfied, expected):
    assert levels(risk_summary(safe_properties(Lipinski=satisfied)))["Lipinski"] == expected


def test_alerts_flag_only_with_medchem_columns():
    assert "Alerts" not in levels(risk_summary(safe_properties()))
    assert levels(risk_summary(safe_properties(PAINS_alerts=1, Brenk_alerts=0)))["Alerts"] == HIGH
    assert levels(risk_summary(safe_properties(PAINS_alerts=0, Brenk_alerts=2)))["Alerts"] == MEDIUM


def test_risk_score_weights_levels():
    flags = risk_summary(safe_properties(hERG=0.9, AMES=0.5))
    assert risk_score(flags) == 3
