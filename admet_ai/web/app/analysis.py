"""Builds per-molecule results shared by the results page, report, comparison view and API."""
import math
import threading

import numpy as np
import pandas as pd
from rdkit import Chem

from admet_ai.medchem import analyze_molecule, compute_medchem_properties
from admet_ai.plot import plot_molecule_svg, plot_radial_summary
from admet_ai.risk import risk_score, risk_summary
from admet_ai.similarity import find_similar_drugs
from admet_ai.utils import get_drugbank_suffix
from admet_ai.web.app.models import get_admet_model
from admet_ai.web.app.utils import replace_svg_dimensions

# The model is shared and its ATC code is per request, so predictions run one at a time
PREDICT_LOCK = threading.Lock()


def predict_all(all_smiles: list[str], mols: list[Chem.Mol], atc_code: str | None) -> pd.DataFrame:
    """Predicts ADMET properties and DrugBank percentiles, then appends the medchem columns.

    :param all_smiles: Valid SMILES.
    :param mols: RDKit molecules matching all_smiles.
    :param atc_code: ATC code for the DrugBank reference, or None for all drugs.
    :return: A DataFrame indexed by SMILES, one row per input molecule in input order.
    """
    with PREDICT_LOCK:
        admet_model = get_admet_model()
        admet_model.atc_code = atc_code
        preds = admet_model.predict(smiles=all_smiles)

    medchem = compute_medchem_properties(all_smiles=all_smiles, mols=mols)
    for column in medchem.columns:
        preds[column] = medchem[column].values

    return preds


def build_molecule_details(
    number: int,
    smiles: str,
    properties: dict[str, float],
    atc_code: str | None,
    num_similar: int = 5,
    with_plots: bool = True,
) -> dict:
    """Builds the full analysis of one molecule.

    :param number: 1-based molecule number shown to the user.
    :param smiles: The molecule's SMILES.
    :param properties: Property ID to value for this molecule (one row of the predictions).
    :param atc_code: ATC code the percentiles were computed against.
    :param num_similar: Number of similar approved drugs to include.
    :param with_plots: Whether to render the SVG images.
    """
    mol = Chem.MolFromSmiles(smiles)
    medchem = analyze_molecule(mol)
    flags = risk_summary(properties)
    details = {
        "number": number,
        "smiles": smiles,
        "properties": properties,
        "medchem": medchem,
        "risk_flags": flags,
        "risk_score": risk_score(flags),
        "similar_drugs": find_similar_drugs(mol, top_k=num_similar),
    }

    if with_plots:
        details["mol_svg"] = replace_svg_dimensions(plot_molecule_svg(mol))
        details["radial_svg"] = replace_svg_dimensions(
            plot_radial_summary(
                property_id_to_percentile=properties,
                percentile_suffix=get_drugbank_suffix(atc_code),
            ).decode("utf-8")
        )
        for alert in medchem["alerts"]:
            alert["svg"] = replace_svg_dimensions(plot_molecule_svg(mol, highlight_atoms=alert["atoms"]))

    return details


def overview_row(details: dict) -> dict:
    """Condenses one molecule's details into a row of the overview table."""
    properties = details["properties"]
    closest = details["similar_drugs"][0] if details["similar_drugs"] else None

    return to_json_value(
        {
            "number": details["number"],
            "smiles": details["smiles"],
            "molecular_weight": properties["molecular_weight"],
            "logP": properties["logP"],
            "QED": properties["QED"],
            "sa_score": details["medchem"]["sa_score"],
            "rules_passed": sum(not violations for violations in details["medchem"]["rules"].values()),
            "num_rules": len(details["medchem"]["rules"]),
            "num_alerts": len(details["medchem"]["alerts"]),
            "risk_score": details["risk_score"],
            "risk_flags": details["risk_flags"],
            "high_risks": sum(flag["level"] == "high" for flag in details["risk_flags"]),
            "closest_drug": closest,
        }
    )


def preds_to_property_dicts(preds: pd.DataFrame) -> list[tuple[str, dict[str, float]]]:
    """Converts predictions to (SMILES, properties) pairs, keeping duplicate SMILES."""
    return list(zip(preds.index, preds.to_dict(orient="records")))


def to_json_value(value):
    """Converts numpy and NaN values so they serialize as JSON."""
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
