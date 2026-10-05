"""Finds the approved DrugBank drugs most similar to a molecule."""
from functools import lru_cache

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

from admet_ai.constants import (
    DEFAULT_DRUGBANK_PATH,
    DRUGBANK_ID_COLUMN,
    DRUGBANK_NAME_COLUMN,
    DRUGBANK_SMILES_COLUMN,
)

DRUGBANK_URL = "https://go.drugbank.com/drugs/{}"


@lru_cache(maxsize=1)
def _fingerprint_generator():
    return rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)


def morgan_fingerprint(mol: Chem.Mol) -> DataStructs.ExplicitBitVect:
    return _fingerprint_generator().GetFingerprint(mol)


@lru_cache()
def _drugbank_fingerprints(drugbank_path: str) -> tuple[pd.DataFrame, list]:
    drugbank = pd.read_csv(
        drugbank_path, usecols=[DRUGBANK_NAME_COLUMN, DRUGBANK_ID_COLUMN, DRUGBANK_SMILES_COLUMN]
    )
    mols = [Chem.MolFromSmiles(smiles) for smiles in drugbank[DRUGBANK_SMILES_COLUMN]]
    keep = [mol is not None for mol in mols]
    drugbank = drugbank[keep].reset_index(drop=True)
    fingerprints = [morgan_fingerprint(mol) for mol in mols if mol is not None]

    return drugbank, fingerprints


def find_similar_drugs(mol: Chem.Mol, top_k: int = 5, drugbank_path=DEFAULT_DRUGBANK_PATH) -> list[dict]:
    """Returns the top_k approved drugs by Tanimoto similarity of Morgan fingerprints.

    :param mol: An RDKit molecule.
    :param top_k: Number of drugs to return.
    :param drugbank_path: Path to the DrugBank approved CSV.
    :return: A list of dicts with name, id, smiles, similarity and url, most similar first.
    """
    drugbank, fingerprints = _drugbank_fingerprints(str(drugbank_path))
    similarities = np.array(DataStructs.BulkTanimotoSimilarity(morgan_fingerprint(mol), fingerprints))
    top_indices = np.argsort(-similarities, kind="stable")[:top_k]

    return [
        {
            "name": drugbank.at[index, DRUGBANK_NAME_COLUMN],
            "id": drugbank.at[index, DRUGBANK_ID_COLUMN],
            "smiles": drugbank.at[index, DRUGBANK_SMILES_COLUMN],
            "similarity": round(float(similarities[index]), 3),
            "url": DRUGBANK_URL.format(drugbank.at[index, DRUGBANK_ID_COLUMN]),
        }
        for index in top_indices
    ]
