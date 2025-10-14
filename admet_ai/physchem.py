"""Compute physicochemical properties using RDKit."""
import pandas as pd
from rdkit.Chem.Crippen import MolLogP
from rdkit.Chem.Descriptors import MolWt
from rdkit.Chem.rdchem import Mol
from rdkit import Chem
from rdkit.Chem import MolFromSmiles
from rdkit.Chem.QED import qed
from rdkit.Chem.rdMolDescriptors import (
    CalcNumAtomStereoCenters,
    CalcNumHBA,
    CalcNumHBD,
    CalcTPSA,
)
from tqdm import tqdm


def lipinski_rule_of_five(mol: Mol) -> float:
    """Determines how many of the Lipinski rules are satisfied by the molecule."""
    return float(
        sum([
            MolWt(mol) <= 500,
            MolLogP(mol) <= 5,
            CalcNumHBA(mol) <= 10,
            CalcNumHBD(mol) <= 5,
        ])
    )


PHYSCHEM_PROPERTY_TO_FUNCTION = {
    "molecular_weight": MolWt,
    "logP": MolLogP,
    "hydrogen_bond_acceptors": CalcNumHBA,
    "hydrogen_bond_donors": CalcNumHBD,
    "Lipinski": lipinski_rule_of_five,
    "QED": qed,
    "stereo_centers": CalcNumAtomStereoCenters,
    "tpsa": CalcTPSA,
}


def compute_physicochemical_properties(all_smiles: list[str], mols: list[Mol] | None = None) -> pd.DataFrame:
    """Compute physicochemical properties for a list of molecules."""
    if mols is None:
        mols = [Chem.MolFromSmiles(smiles) for smiles in all_smiles]

    # Filter out invalid molecules
    valid_data = [(s, m) for s, m in zip(all_smiles, mols) if m is not None]
    if not valid_data:
        return pd.DataFrame()  # return empty if all invalid

    smiles_list, valid_mols = zip(*valid_data)

    # Compute physicochemical properties
    physchem_properties = pd.DataFrame(
        data=[
            {
                prop: round(func(mol), 3)  # rounded for neat output
                for prop, func in PHYSCHEM_PROPERTY_TO_FUNCTION.items()
            }
            for mol in tqdm(valid_mols, desc="Computing physchem properties")
        ],
        index=smiles_list,
    )

    return physchem_properties