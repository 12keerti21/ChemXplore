"""Medicinal chemistry filters: drug-likeness rules, structural alerts, synthetic accessibility and BOILED-Egg."""
import math
import os
import sys
from functools import lru_cache

import pandas as pd
from rdkit import Chem, RDConfig
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
from tqdm import tqdm

sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
import sascorer  # noqa: E402

# Ellipses from Daina & Zoete, ChemMedChem 2016 (TPSA on x, WLOGP on y, axes are full lengths, angle in degrees)
BOILED_EGG_WHITE = {"center": (71.051, 2.292), "width": 142.081, "height": 8.740, "angle": -1.031325}
BOILED_EGG_YOLK = {"center": (38.117, 3.177), "width": 82.061, "height": 5.557, "angle": -0.171887}

RULE_NAMES = ["Lipinski", "Ghose", "Veber", "Egan", "Muegge"]
ALERT_CATALOGS = {
    "PAINS": FilterCatalogParams.FilterCatalogs.PAINS,
    "Brenk": FilterCatalogParams.FilterCatalogs.BRENK,
}


def _violations(checks: dict[str, bool]) -> list[str]:
    return [name for name, passed in checks.items() if not passed]


def drug_likeness_rules(mol: Chem.Mol) -> dict[str, list[str]]:
    """Checks the molecule against common drug-likeness rules.

    :param mol: An RDKit molecule.
    :return: A dictionary mapping rule name to the list of violated criteria (empty if the rule passes).
    """
    mw = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    mr = Crippen.MolMR(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    hba = Lipinski.NumHAcceptors(mol)
    hbd = Lipinski.NumHDonors(mol)
    rot_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
    num_atoms = Chem.AddHs(mol).GetNumAtoms()
    num_rings = rdMolDescriptors.CalcNumRings(mol)
    num_carbons = sum(atom.GetAtomicNum() == 6 for atom in mol.GetAtoms())
    num_heteroatoms = rdMolDescriptors.CalcNumHeteroatoms(mol)

    return {
        "Lipinski": _violations(
            {"MW > 500": mw <= 500, "LogP > 5": logp <= 5, "HBA > 10": hba <= 10, "HBD > 5": hbd <= 5}
        ),
        "Ghose": _violations(
            {
                "MW outside 160-480": 160 <= mw <= 480,
                "LogP outside -0.4-5.6": -0.4 <= logp <= 5.6,
                "MR outside 40-130": 40 <= mr <= 130,
                "Atoms outside 20-70": 20 <= num_atoms <= 70,
            }
        ),
        "Veber": _violations({"Rotatable bonds > 10": rot_bonds <= 10, "TPSA > 140": tpsa <= 140}),
        "Egan": _violations({"LogP > 5.88": logp <= 5.88, "TPSA > 131.6": tpsa <= 131.6}),
        "Muegge": _violations(
            {
                "MW outside 200-600": 200 <= mw <= 600,
                "LogP outside -2-5": -2 <= logp <= 5,
                "TPSA > 150": tpsa <= 150,
                "Rings > 7": num_rings <= 7,
                "Carbons < 5": num_carbons > 4,
                "Heteroatoms < 2": num_heteroatoms > 1,
                "Rotatable bonds > 15": rot_bonds <= 15,
                "HBA > 10": hba <= 10,
                "HBD > 5": hbd <= 5,
            }
        ),
    }


@lru_cache()
def _filter_catalog(catalog_name: str) -> FilterCatalog:
    params = FilterCatalogParams()
    params.AddCatalog(ALERT_CATALOGS[catalog_name])
    return FilterCatalog(params)


def structural_alerts(mol: Chem.Mol) -> list[dict]:
    """Finds PAINS and Brenk structural alerts in the molecule.

    :param mol: An RDKit molecule.
    :return: A list of alerts, each with its catalog, description and matched atom indices.
    """
    alerts = []
    for catalog_name in ALERT_CATALOGS:
        for entry in _filter_catalog(catalog_name).GetMatches(mol):
            atoms = sorted(
                {mol_atom for match in entry.GetFilterMatches(mol) for _, mol_atom in match.atomPairs}
            )
            alerts.append({"catalog": catalog_name, "description": entry.GetDescription(), "atoms": atoms})

    return alerts


def synthetic_accessibility(mol: Chem.Mol) -> float:
    """Ertl & Schuffenhauer synthetic accessibility score, from 1 (easy) to 10 (hard)."""
    return float(sascorer.calculateScore(mol))


def _inside_ellipse(x: float, y: float, ellipse: dict) -> bool:
    cx, cy = ellipse["center"]
    theta = math.radians(ellipse["angle"])
    dx, dy = x - cx, y - cy
    u = dx * math.cos(theta) + dy * math.sin(theta)
    v = -dx * math.sin(theta) + dy * math.cos(theta)
    return (u / (ellipse["width"] / 2)) ** 2 + (v / (ellipse["height"] / 2)) ** 2 <= 1


def boiled_egg_coordinates(mol: Chem.Mol) -> tuple[float, float]:
    """Returns (TPSA with S and P, WLOGP) as used by the BOILED-Egg model."""
    return rdMolDescriptors.CalcTPSA(mol, includeSandP=True), Crippen.MolLogP(mol)


def boiled_egg(mol: Chem.Mol) -> dict[str, float | bool]:
    """Predicts passive gastrointestinal absorption and brain penetration with the BOILED-Egg model."""
    tpsa, wlogp = boiled_egg_coordinates(mol)

    return {
        "tpsa": tpsa,
        "wlogp": wlogp,
        "gi_absorption": _inside_ellipse(tpsa, wlogp, BOILED_EGG_WHITE),
        "bbb_permeant": _inside_ellipse(tpsa, wlogp, BOILED_EGG_YOLK),
    }


def analyze_molecule(mol: Chem.Mol) -> dict:
    """Runs every medicinal chemistry check on one molecule."""
    return {
        "rules": drug_likeness_rules(mol),
        "alerts": structural_alerts(mol),
        "sa_score": synthetic_accessibility(mol),
        "boiled_egg": boiled_egg(mol),
    }


def summarize_medchem(analysis: dict) -> dict[str, float | int | bool | str]:
    """Flattens a medicinal chemistry analysis into table columns."""
    summary = {f"{rule}_violations": len(violations) for rule, violations in analysis["rules"].items()}
    for catalog_name in ALERT_CATALOGS:
        summary[f"{catalog_name}_alerts"] = sum(alert["catalog"] == catalog_name for alert in analysis["alerts"])
    summary["structural_alerts"] = "; ".join(alert["description"] for alert in analysis["alerts"])
    summary["synthetic_accessibility"] = round(analysis["sa_score"], 3)
    summary["gi_absorption_boiled_egg"] = analysis["boiled_egg"]["gi_absorption"]
    summary["bbb_permeant_boiled_egg"] = analysis["boiled_egg"]["bbb_permeant"]

    return summary


def compute_medchem_properties(all_smiles: list[str], mols: list[Chem.Mol] | None = None) -> pd.DataFrame:
    """Computes flattened medicinal chemistry properties for a list of valid molecules.

    :param all_smiles: A list of SMILES.
    :param mols: RDKit molecules matching all_smiles. If None, they are built from the SMILES.
    :return: A DataFrame with one row per molecule, indexed by SMILES.
    """
    if mols is None:
        mols = [Chem.MolFromSmiles(smiles) for smiles in all_smiles]

    return pd.DataFrame(
        [summarize_medchem(analyze_molecule(mol)) for mol in tqdm(mols, desc="Computing medchem properties")],
        index=all_smiles,
    )
