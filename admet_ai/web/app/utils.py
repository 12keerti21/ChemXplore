"""Utility functions related to the ADMET-AI web server."""
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from chemprop.data.data import SMILES_TO_MOL
from flask import request
from rdkit import Chem
from werkzeug.utils import secure_filename

from admet_ai.pubchem import names_to_smiles
from admet_ai.web.app import app


SVG_WIDTH_PATTERN = re.compile(r"width=['\"]\d+(\.\d+)?[a-z]+['\"]")
SVG_HEIGHT_PATTERN = re.compile(r"height=['\"]\d+(\.\d+)?[a-z]+['\"]")


def split_lines(text: str) -> list[str]:
    """Splits text into stripped, non-empty lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def get_smiles_from_request() -> tuple[list[str] | None, list[str], str | None]:
    """Gets SMILES from the form, using the input type the user picked.

    :return: A tuple of the SMILES (or None), warnings, and an error message (or None).
    """
    input_type = request.form.get("input-type", "text")
    warnings = []

    if input_type == "draw":
        smiles = split_lines(request.form.get("draw-smiles", ""))
    elif input_type == "name":
        names = split_lines(request.form.get("text-names", ""))
        if not names:
            return None, warnings, "Enter at least one compound name."
        if len(names) > app.config["MAX_NAME_LOOKUPS"]:
            return None, warnings, f"Name lookup is limited to {app.config['MAX_NAME_LOOKUPS']} names at a time."
        try:
            smiles, not_found = names_to_smiles(names)
        except ConnectionError as error:
            return None, warnings, f"Name lookup failed: {error}. Try again or enter SMILES instead."
        warnings.extend(f"No PubChem match for name: {name}" for name in not_found)
    elif input_type == "file":
        data = request.files.get("data")
        if data is None or data.filename == "":
            return None, warnings, "Choose a CSV file to upload."
        smiles_column = request.form.get("smiles-column", "smiles")

        with TemporaryDirectory() as temp_dir:
            data_path = str(Path(temp_dir) / secure_filename(data.filename))
            data.save(data_path)
            try:
                df = pd.read_csv(data_path)
            except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
                return None, warnings, "Could not read the uploaded file as CSV."

        if smiles_column not in df:
            return None, warnings, f"SMILES column '{smiles_column}' not found in data file."
        smiles = [str(smile).strip() for smile in df[smiles_column].dropna()]
    else:
        smiles = split_lines(request.form.get("text-smiles", ""))

    smiles = [smile for smile in smiles if smile != ""]
    if not smiles:
        return None, warnings, "No molecules given."

    return smiles, warnings, None


def smiles_to_mols(smiles: list[str]) -> list[Chem.Mol]:
    """Convert a list of SMILES to a list of RDKit molecules with caching if turned on.

    :param smiles: A list of SMILES.
    :return: A list of RDKit molecules.
    """
    mols = []
    for smile in smiles:
        if smile in SMILES_TO_MOL:
            mol = SMILES_TO_MOL[smile]
        else:
            mol = Chem.MolFromSmiles(smile)

        mols.append(mol)

        if app.config["CACHE_MOLECULES"]:
            SMILES_TO_MOL[smile] = mol

    return mols


def string_to_html_sup(string: str) -> str:
    """Converts a string with an exponential to HTML superscript.

    :param string: A string.
    :return: The string with an exponential in HTML superscript.
    """
    return re.sub(r"\^(-?\d+)", r"<sup>\1</sup>", string)


def replace_svg_dimensions(svg_content: str) -> str:
    """Replace the SVG width and height with 100%.

    :param svg_content: The SVG content.
    :return: The SVG content with the width and height replaced with 100%.
    """
    # Replacing the width and height with 100%
    svg_content = SVG_WIDTH_PATTERN.sub('width="100%"', svg_content)
    svg_content = SVG_HEIGHT_PATTERN.sub('height="100%"', svg_content)

    return svg_content
