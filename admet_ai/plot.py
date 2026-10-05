"""Defines functions for ADMET-AI plots."""
import re
import threading
from functools import wraps
from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Ellipse
from rdkit import Chem
from rdkit.Chem.Draw.rdMolDraw2D import MolDraw2DSVG

from admet_ai.admet_info import (
    get_admet_id_to_units,
    get_admet_name_to_id,
)
from admet_ai.medchem import BOILED_EGG_WHITE, BOILED_EGG_YOLK, boiled_egg_coordinates

# pyplot keeps global state, so plots from concurrent web requests must not interleave
PLOT_LOCK = threading.Lock()


def locked_plot(func: callable) -> callable:
    """Decorator that serializes calls to a pyplot-based function."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with PLOT_LOCK:
            return func(*args, **kwargs)

    return wrapper


def string_to_latex_sup(string: str) -> str:
    """Converts a string with an exponential to LaTeX superscript.

    :param string: A string.
    :return: The string with an exponential in LaTeX superscript.
    """
    return re.sub(r"\^(\d+)", r"$^{\1}$", string)


@locked_plot
def plot_drugbank_reference(
    preds_df: pd.DataFrame,
    drugbank_df: pd.DataFrame,
    x_property_name: str | None = None,
    y_property_name: str | None = None,
    max_molecule_num: int | None = None,
    image_type: str = "svg",
) -> bytes:
    """Creates a 2D scatter plot of the DrugBank reference set vs the new set of molecules on two properties.

    :param preds_df: A DataFrame containing the predictions on the new molecules.
    :param drugbank_df: A DataFrame containing the DrugBank reference set.
    :param x_property_name: The name of the property to plot on the x-axis.
    :param y_property_name: The name of the property to plot on the y-axis.
    :param max_molecule_num: If provided, will display molecule numbers up to this number.
    :param image_type: The image type for the plot (e.g., svg).
    :return: Bytes containing the plot.
    """
    # Set default values
    if x_property_name is None:
        x_property_name = "Human Intestinal Absorption"

    if y_property_name is None:
        y_property_name = "Clinical Toxicity"

    # Map property names to IDs
    admet_name_to_id = get_admet_name_to_id()
    x_property_id = admet_name_to_id[x_property_name]
    y_property_id = admet_name_to_id[y_property_name]

    # Scatter plot of DrugBank molecules with histogram marginals
    sns.jointplot(
        x=drugbank_df[x_property_id],
        y=drugbank_df[y_property_id],
        kind="scatter",
        marginal_kws=dict(bins=50, fill=True),
        label="DrugBank Reference",
    )

    # Scatter plot of new molecules
    if len(preds_df) > 0:
        sns.scatterplot(
            x=preds_df[x_property_id],
            y=preds_df[y_property_id],
            color="red",
            marker="*",
            s=200,
            label="Input Molecule" + ("s" if len(preds_df) > 1 else ""),
        )

    # Add molecule numbers
    if max_molecule_num is not None:
        # Create buffer around scatter plot points
        x_min, x_max = plt.xlim()
        x_range = x_max - x_min
        x_buffer = x_range * 0.01

        y_min, y_max = plt.ylim()
        y_range = y_max - y_min
        y_buffer = y_range * 0.01

        # Get x and y values for first max_molecule_num molecules
        x_vals = preds_df[x_property_id].values[:max_molecule_num]
        y_vals = preds_df[y_property_id].values[:max_molecule_num]

        # Add molecule numbers for first max_molecule_num molecules
        for i, (x_val, y_val) in enumerate(zip(x_vals, y_vals)):
            plt.text(
                x_val - x_buffer,
                y_val + y_buffer,
                str(i + 1),
                horizontalalignment="right",
                verticalalignment="bottom",
                c="red",
            )

    # Get ADMET property units
    admet_id_to_units = get_admet_id_to_units()

    x_property_units = admet_id_to_units[x_property_id]
    y_property_units = admet_id_to_units[y_property_id]

    x_property_units = x_property_units if x_property_units != "-" else "probability"
    y_property_units = y_property_units if y_property_units != "-" else "probability"

    # Set axis labels
    plt.xlabel(f"{x_property_name} ({string_to_latex_sup(x_property_units)})")
    plt.ylabel(f"{y_property_name} ({string_to_latex_sup(y_property_units)})")

    # Save plot as svg to pass to frontend
    buf = BytesIO()
    plt.savefig(buf, format=image_type, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    plot = buf.getvalue()

    return plot


@locked_plot
def plot_radial_summary(
    property_id_to_percentile: dict[str, float],
    percentile_suffix: str = "",
    image_type: str = "svg",
) -> bytes:
    """Creates a radial plot summary of important properties of a molecule in terms of DrugBank approved percentiles.

    :param property_id_to_percentile: A dictionary mapping property IDs to their DrugBank approved percentiles.
                                      Keys are the property name along with the percentile_suffix.
    :param percentile_suffix: The suffix to add to the property names to get the DrugBank approved percentiles.
    :param image_type: The image type for the plot (e.g., svg).
    :return: Bytes containing the plot.
    """
    # Set max percentile
    max_percentile = 100

    # Set up properties
    properties = {
        "Blood-Brain Barrier Safe": {
            "percentile": max_percentile
            - property_id_to_percentile[f"BBB_Martins_{percentile_suffix}"],
        },
        "Non-\nToxic": {
            "percentile": max_percentile
            - property_id_to_percentile[f"ClinTox_{percentile_suffix}"],
            "vertical_alignment": "bottom",
        },
        "Soluble": {
            "percentile": property_id_to_percentile[
                f"Solubility_AqSolDB_{percentile_suffix}"
            ],
            "vertical_alignment": "top",
        },
        "Bioavailable": {
            "percentile": property_id_to_percentile[
                f"Bioavailability_Ma_{percentile_suffix}"
            ],
            "vertical_alignment": "top",
        },
        "hERG\nSafe": {
            "percentile": max_percentile
            - property_id_to_percentile[f"hERG_{percentile_suffix}"],
            "vertical_alignment": "bottom",
        },
    }
    property_names = [property_name for property_name in properties]
    percentiles = [
        properties[property_name]["percentile"] for property_name in properties
    ]

    # Calculate the angles of the plot (angles start at pi / 2 and go counter-clockwise)
    angles = (
        (np.linspace(0, 2 * np.pi, len(properties), endpoint=False) + np.pi / 2)
        % (2 * np.pi)
    ).tolist()

    # Complete the loop
    percentiles += percentiles[:1]
    angles += angles[:1]

    # Create a plot
    fig, ax = plt.subplots(figsize=(3, 3), subplot_kw=dict(polar=True))

    # Plot the data
    ax.fill(angles, percentiles, color="red", alpha=0.25)
    ax.plot(angles, percentiles, color="red", linewidth=2)

    # Set y limits
    ax.set_ylim(0, 100)

    # Labels for radial lines
    yticks = [0, 25, 50, 75, 100]
    yticklabels = [str(ytick) for ytick in yticks]
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticklabels)
    ax.set_rlabel_position(335)

    # Labels for categories
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(property_names)

    # Adjust xticklabels so they don't overlap the plot
    for label, property_name in zip(ax.get_xticklabels(), property_names):
        if "vertical_alignment" in properties[property_name]:
            label.set_verticalalignment(properties[property_name]["vertical_alignment"])

    # Make the plot square (to match square molecule images)
    ax.set_aspect("equal", "box")

    # Ensure no text labels are cut off
    plt.tight_layout()

    # Save plot
    buf = BytesIO()
    plt.savefig(buf, format=image_type)
    plt.close()
    buf.seek(0)
    plot = buf.getvalue()

    return plot


def plot_molecule_svg(mol: str | Chem.Mol, highlight_atoms: list[int] | None = None) -> str:
    """Plots a molecule as an SVG image.

    :param mol: A SMILES string or RDKit molecule.
    :param highlight_atoms: Atom indices to highlight, such as the atoms of a structural alert.
    :return: An SVG image of the molecule.
    """
    # Convert SMILES to Mol if needed
    if isinstance(mol, str):
        mol = Chem.MolFromSmiles(mol)

    # Highlight bonds between highlighted atoms too
    highlight_bonds = None
    if highlight_atoms:
        atom_set = set(highlight_atoms)
        highlight_bonds = [
            bond.GetIdx()
            for bond in mol.GetBonds()
            if bond.GetBeginAtomIdx() in atom_set and bond.GetEndAtomIdx() in atom_set
        ]

    # Convert Mol to SVG
    d = MolDraw2DSVG(200, 200)
    d.DrawMolecule(mol, highlightAtoms=highlight_atoms or [], highlightBonds=highlight_bonds or [])
    d.FinishDrawing()
    smiles_svg = d.GetDrawingText()

    return smiles_svg


@locked_plot
def plot_boiled_egg(mols: list[Chem.Mol], image_type: str = "svg") -> bytes:
    """Plots molecules on the BOILED-Egg (TPSA vs. WLOGP) with numbered points.

    :param mols: RDKit molecules, numbered from 1 in the plot.
    :param image_type: The image type for the plot (e.g., svg).
    :return: Bytes containing the plot.
    """
    fig, ax = plt.subplots(figsize=(7, 5.5))
    ax.set_facecolor("#9e9e9e")

    for ellipse, color, label in [
        (BOILED_EGG_WHITE, "#ffffff", "GI absorption (white)"),
        (BOILED_EGG_YOLK, "#f5c242", "Brain penetration (yolk)"),
    ]:
        ax.add_patch(
            Ellipse(
                xy=ellipse["center"],
                width=ellipse["width"],
                height=ellipse["height"],
                angle=ellipse["angle"],
                facecolor=color,
                edgecolor="#555555",
                label=label,
            )
        )

    coordinates = [boiled_egg_coordinates(mol) for mol in mols]
    if coordinates:
        tpsas, wlogps = zip(*coordinates)
        ax.scatter(tpsas, wlogps, c="#c0392b", edgecolors="white", s=60, zorder=3, label="Input molecules")
        for number, (tpsa, wlogp) in enumerate(coordinates, start=1):
            ax.annotate(str(number), (tpsa, wlogp), xytext=(4, 4), textcoords="offset points", fontsize=8, zorder=4)

    ax.set_xlim(-10, max([200] + [tpsa + 10 for tpsa, _ in coordinates]))
    ax.set_ylim(min([-4] + [wlogp - 1 for _, wlogp in coordinates]), max([8] + [wlogp + 1 for _, wlogp in coordinates]))
    ax.set_xlabel("TPSA (Å$^2$)")
    ax.set_ylabel("WLOGP")
    ax.legend(loc="upper right", fontsize=8)

    buf = BytesIO()
    plt.savefig(buf, format=image_type, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    return buf.getvalue()
