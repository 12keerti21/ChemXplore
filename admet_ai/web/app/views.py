"""Defines the routes of the ADMET-AI Flask app."""
from uuid import uuid4
from tempfile import NamedTemporaryFile
import os

# Configure static folder path
STATIC_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

from flask import (
    after_this_request,
    jsonify,
    render_template,
    request,
    Response,
    send_file,
    session,
)

from admet_ai._version import __version__
from admet_ai.admet_info import get_admet_info, get_admet_id_to_name, get_admet_id_to_units
from admet_ai.drugbank import (
    get_drugbank,
    get_drugbank_size,
    get_drugbank_task_names,
    get_drugbank_unique_atc_codes,
)
from admet_ai.plot import (
    plot_drugbank_reference,
    plot_molecule_svg,
    plot_radial_summary,
)
from admet_ai.utils import get_drugbank_suffix
from admet_ai.web.app import app
from admet_ai.web.app.models import get_admet_model
from admet_ai.web.app.storage import (
    get_user_preds,
    set_user_preds,
    update_user_activity,
)
from admet_ai.web.app.utils import (
    get_smiles_from_request,
    replace_svg_dimensions,
    smiles_to_mols,
    string_to_html_sup,
)
from admet_ai.analysis.results_analyzer import ResultsAnalyzer
import io
import base64
import pandas as pd
import pdfkit
from datetime import datetime
import matplotlib.pyplot as plt


def plot_to_base64(fig) -> str:
    """Convert matplotlib Figure to base64 string.
    
    :param fig: matplotlib Figure object
    :return: base64 encoded string of the plot
    """
    img = io.BytesIO()
    fig.savefig(img, format='png', bbox_inches='tight', dpi=300)
    img.seek(0)
    plot_base64 = base64.b64encode(img.getvalue()).decode()
    plt.close(fig)  # Close the figure to free memory
    return plot_base64


def generate_pdf_report(all_smiles, smiles_to_property_id_to_pred, all_preds, atc_code, drugbank_size, warnings):
    """Generate PDF report for ADMET predictions.
    
    :param all_smiles: List of SMILES strings
    :param smiles_to_property_id_to_pred: Dictionary mapping SMILES to predictions
    :param all_preds: DataFrame with all predictions
    :param atc_code: ATC code for DrugBank filtering
    :param drugbank_size: Size of DrugBank reference set
    :param warnings: List of warnings
    :return: PDF file response
    """
    try:
        # Limit to first 25 molecules for PDF
        max_pdf_molecules = min(25, len(all_smiles))
        pdf_smiles = all_smiles[:max_pdf_molecules]
        
        # Get ADMET info for property names and units
        admet_info = get_admet_info()
        admet_id_to_name = get_admet_id_to_name()
        admet_id_to_units = get_admet_id_to_units()
        
        # Physicochemical property units mapping
        physchem_units = {
            'molecular_weight': 'Da',
            'logP': '',
            'hydrogen_bond_acceptors': '',
            'hydrogen_bond_donors': '',
            'Lipinski': '',
            'QED': '',
            'stereo_centers': '',
            'tpsa': 'Å²'
        }
        
        # Generate summary plot (DrugBank reference plot)
        drugbank_plot_svg = plot_drugbank_reference(
            preds_df=all_preds,
            drugbank_df=get_drugbank(atc_code=atc_code),
            x_property_name=session.get("drugbank_x_task_name"),
            y_property_name=session.get("drugbank_y_task_name"),
            max_molecule_num=app.config["MAX_VISIBLE_MOLECULES"],
        ).decode("utf-8")
        
        # Convert SVG to base64 for PDF
        summary_plot_b64 = base64.b64encode(drugbank_plot_svg.encode()).decode()
        
        # Prepare molecules data for template
        molecules = {}
        percentile_suffix = get_drugbank_suffix(atc_code)
        
        for idx, smiles in enumerate(pdf_smiles):
            # Get physicochemical properties
            physchem_props = {}
            for prop in physchem_units.keys():
                if prop in smiles_to_property_id_to_pred[smiles]:
                    physchem_props[prop] = smiles_to_property_id_to_pred[smiles][prop]
            
            # Get ADMET predictions with units and percentiles
            admet_props = {}
            for prop_id, value in smiles_to_property_id_to_pred[smiles].items():
                if prop_id not in physchem_units:  # Skip physchem properties
                    prop_name = admet_id_to_name.get(prop_id, prop_id)
                    units = admet_id_to_units.get(prop_id, '-')
                    
                    # Get percentile if available
                    percentile_key = f"{prop_id}_{percentile_suffix}"
                    percentile = smiles_to_property_id_to_pred[smiles].get(percentile_key, 0.0)
                    
                    admet_props[prop_name] = {
                        'prediction': value,
                        'units': units if units != '-' else 'probability',
                        'percentile': percentile
                    }
            
            # Generate radial plot for this molecule
            radial_plot_svg = plot_radial_summary(
                property_id_to_percentile=smiles_to_property_id_to_pred[smiles],
                percentile_suffix=percentile_suffix,
            ).decode("utf-8")
            radial_plot_b64 = base64.b64encode(radial_plot_svg.encode()).decode()
            
            molecules[idx] = {
                'smiles': smiles,
                'physchem': physchem_props,
                'admet': admet_props,
                'radial_plot_b64': radial_plot_b64
            }
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Render HTML template
        html = render_template('admet_report.html',
                             timestamp=timestamp,
                             atc_code=atc_code,
                             drugbank_size=drugbank_size,
                             summary_plot_b64=summary_plot_b64,
                             molecules=molecules,
                             physchem_units=physchem_units,
                             is_web_display=False)
        
        # Configure pdfkit options
        options = {
            'page-size': 'A4',
            'margin-top': '0.75in',
            'margin-right': '0.75in',
            'margin-bottom': '0.75in',
            'margin-left': '0.75in',
            'encoding': "UTF-8",
            'no-outline': None,
            'enable-local-file-access': None
        }
        
        # Generate PDF
        pdf_buffer = io.BytesIO()
        pdfkit.from_string(html, pdf_buffer, options=options)
        pdf_buffer.seek(0)
        
        # Generate filename
        filename = f"admet_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.pdf"
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        # Fallback to CSV download if PDF generation fails
        return render_template('error.html', 
                             message=f"PDF generation failed: {str(e)}. Please try downloading CSV instead.")


def render(**kwargs) -> str:
    """Renders the page with specified kwargs."""
    return render_template(
        "index.html",
        admet_info=get_admet_info(),
        drugbank_atc_codes=["all"] + get_drugbank_unique_atc_codes(),
        drugbank_tasks=get_drugbank_task_names(),
        max_molecules=app.config["MAX_MOLECULES"],
        max_visible_molecules=app.config["MAX_VISIBLE_MOLECULES"],
        low_performance_threshold=app.config["LOW_PERFORMANCE_THRESHOLD"],
        drugbank_approved_percentile_suffix=get_drugbank_suffix(
            session.get("atc_code")
        ),
        drugbank_size=get_drugbank_size(session.get("atc_code")),
        drugbank_total_size=get_drugbank_size(),
        atc_code=session.get("atc_code") or "all",
        heartbeat_frequency=app.config["HEARTBEAT_FREQUENCY"],
        string_to_html_sup=string_to_html_sup,
        min=min,
        max=max,
        text_smiles=session.get("text_smiles", ""),
        version=__version__,
        **kwargs,
    )


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """Renders the page and makes predictions if the method is POST."""
    # Set up warnings
    warnings = []

    # Assign user ID to session
    if "user_id" not in session:
        session["user_id"] = uuid4().hex

    # If GET request, simply return the page; otherwise if POST request, make predictions
    if request.method == "GET":
        return render()

    # Save the user's text box input
    session["text_smiles"] = request.form.get("text-smiles", "")

    # Get the SMILES from the request
    all_smiles, error = get_smiles_from_request()

    # Return any errors
    if error is not None:
        return render(errors=[error])

    # Error if too many molecules
    if (
        app.config["MAX_MOLECULES"] is not None
        and len(all_smiles) > app.config["MAX_MOLECULES"]
    ):
        return render(
            errors=[
                f"Received too many molecules. Maximum number of molecules is {app.config['MAX_MOLECULES']:,}."
            ]
        )

    # Convert SMILES to RDKit molecules
    mols = smiles_to_mols(all_smiles)

    # Warn about invalid SMILES
    for smiles, mol in zip(all_smiles, mols):
        if mol is None or " " in smiles:
            warnings.append(f"Invalid SMILES string: {smiles}")

    # Remove invalid molecules
    all_smiles = [smile for smile, mol in zip(all_smiles, mols) if mol is not None]
    mols = [mol for mol in mols if mol is not None]

    # Error if no valid molecules
    if len(all_smiles) == 0:
        return render(errors=["No valid SMILES strings given."])

    # Make physicochemical and ADMET predictions (with DrugBank percentiles)
    admet_model = get_admet_model()
    admet_model.atc_code = session.get("atc_code")
    all_preds = admet_model.predict(smiles=all_smiles)

    # Convert predictions to a dictionary mapping SMILES to property name to value
    smiles_to_property_id_to_pred: dict[str, dict[str, float]] = all_preds[
        ~all_preds.index.duplicated(keep="first")  # drop duplicate SMILES indices
    ].to_dict(orient="index")

    # Store predictions in memory
    set_user_preds(user_id=session["user_id"], preds_df=all_preds)

    # Store only essential data in session to avoid cookie size limits
    session["has_predictions"] = True
    session["num_molecules"] = len(all_smiles)

    # Create DrugBank reference plot
    drugbank_plot_svg = plot_drugbank_reference(
        preds_df=all_preds,
        drugbank_df=get_drugbank(atc_code=session.get("atc_code")),
        x_property_name=session.get("drugbank_x_task_name"),
        y_property_name=session.get("drugbank_y_task_name"),
        max_molecule_num=app.config["MAX_VISIBLE_MOLECULES"],
    ).decode("utf-8")
    drugbank_plot_svg = replace_svg_dimensions(drugbank_plot_svg)

    # Get maximum number of molecules to display
    num_display_molecules = min(len(all_smiles), app.config["MAX_VISIBLE_MOLECULES"])

    # Create molecule SVG images
    mol_svgs = [plot_molecule_svg(mol) for mol in mols[:num_display_molecules]]
    mol_svgs = [replace_svg_dimensions(plot) for plot in mol_svgs]

    # Create molecule radial plots for DrugBank approved percentiles
    radial_svgs = [
        plot_radial_summary(
            property_id_to_percentile=smiles_to_property_id_to_pred[smiles],
            percentile_suffix=get_drugbank_suffix(session.get("atc_code")),
        ).decode("utf-8")
        for smiles in all_smiles[:num_display_molecules]
    ]
    radial_svgs = [replace_svg_dimensions(plot) for plot in radial_svgs]

    return render(
        predicted=True,
        all_smiles=all_smiles,
        smiles_to_property_id_to_pred=smiles_to_property_id_to_pred,
        mol_svgs=mol_svgs,
        radial_svgs=radial_svgs,
        drugbank_plot=drugbank_plot_svg,
        num_molecules=len(all_smiles),
        num_display_molecules=num_display_molecules,
        warnings=warnings,
    )


@app.route("/set_atc_code", methods=["POST"])
def set_atc_code() -> Response:
    """Sets the ATC code to filter the DrugBank reference set by.

    :return: A JSON response containing the new DrugBank size.
    """
    # Get ATC code
    atc_code = request.args.get("atc_code")

    # Handle "all" ATC code
    if atc_code == "all":
        atc_code = None

    # Store ATC code in session
    session["atc_code"] = atc_code

    # Get new DrugBank size
    drugbank_size = get_drugbank_size(session.get("atc_code"))

    # Send new DrugBank size
    return jsonify({"drugbank_size_string": f"{drugbank_size:,}",})


@app.route("/drugbank_plot", methods=["GET"])
def drugbank_plot() -> Response:
    """Creates a DrugBank reference plot.

    :return: A JSON response containing the SVG of the plot.
    """
    # Get user_id from session
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No user session found"}), 400
        
    # Get requested X and Y axes and store in session
    session["drugbank_x_task_name"] = request.args.get(
        "x_task", default=session.get("drugbank_x_task_name"), type=str
    )
    session["drugbank_y_task_name"] = request.args.get(
        "y_task", default=session.get("drugbank_y_task_name"), type=str
    )

    # Get user predictions
    user_preds = get_user_preds(user_id)
    if user_preds is None or user_preds.empty:
        return jsonify({"error": "No predictions available"}), 400

    # Create DrugBank reference plot with ATC code
    drugbank_plot_svg = plot_drugbank_reference(
        preds_df=user_preds,
        drugbank_df=get_drugbank(atc_code=session.get("atc_code")),
        x_property_name=session["drugbank_x_task_name"],
        y_property_name=session["drugbank_y_task_name"],
        max_molecule_num=app.config["MAX_VISIBLE_MOLECULES"],
    ).decode("utf-8")
    drugbank_plot_svg = replace_svg_dimensions(drugbank_plot_svg)

    return jsonify({"svg": drugbank_plot_svg})


@app.route("/download_predictions")
def download_predictions() -> Response:
    """Downloads predictions as a CSV file.

    :return: A CSV file containing the predictions.
    """
    # Check if user_id exists in session
    user_id = session.get("user_id")
    if not user_id:
        return render_template('error.html', 
                             message="Session not found. Please run predictions first.")
    
    # Get user predictions
    user_preds = get_user_preds(user_id)
    if user_preds is None or user_preds.empty:
        return render_template('error.html', 
                             message="No prediction data found. Please run predictions first.")
    
    # Create a temporary file that can be reopened by Pandas/Flask
    preds_file = NamedTemporaryFile(delete=False, suffix=".csv")
    preds_file.close()  # close immediately to release Windows lock

    # Set up cleanup after response is sent
    @after_this_request
    def remove_file(response: Response) -> Response:
        try:
            os.remove(preds_file.name)
        except OSError:
            pass
        return response

    # Save predictions to temporary file
    user_preds.to_csv(preds_file.name, index_label="smiles")

    # Return the file as a response
    return send_file(
        preds_file.name, as_attachment=True, download_name="predictions.csv"
    )


@app.route('/show_results', methods=['GET'])
def show_results():
    """Shows comprehensive analysis results with detailed breakdown.
    
    :return: Rendered comprehensive results template with all data and plots.
    """
    try:
        # Check if user_id exists in session
        user_id = session.get("user_id")
        if not user_id:
            return render_template('error.html', 
                                 message="Session not found. Please run predictions first.")
        
        # Check if predictions exist
        if not session.get("has_predictions", False):
            return render_template('error.html', 
                                message="No predictions available. Please run predictions first.")

        # Get stored predictions DataFrame
        all_preds = get_user_preds(user_id)

        if all_preds is None or all_preds.empty:
            return render_template('error.html', 
                                message="No prediction data available. Please run predictions first.")

        # Reconstruct the predictions dictionary from stored DataFrame
        all_smiles = all_preds.index.unique().tolist()
        smiles_to_property_id_to_pred = all_preds[
            ~all_preds.index.duplicated(keep="first")
        ].to_dict(orient="index")
        
        # Get ADMET info for property names and units
        admet_id_to_name = get_admet_id_to_name()
        admet_id_to_units = get_admet_id_to_units()
        
        # Physicochemical property units mapping
        physchem_units = {
            'molecular_weight': 'Da',
            'logP': '',
            'hydrogen_bond_acceptors': '',
            'hydrogen_bond_donors': '',
            'Lipinski': '',
            'QED': '',
            'stereo_centers': '',
            'tpsa': 'Å²'
        }
        
        # Generate summary plot (DrugBank reference plot)
        drugbank_plot_svg = plot_drugbank_reference(
            preds_df=all_preds,
            drugbank_df=get_drugbank(atc_code=session.get("atc_code")),
            x_property_name=session.get("drugbank_x_task_name"),
            y_property_name=session.get("drugbank_y_task_name"),
            max_molecule_num=app.config["MAX_VISIBLE_MOLECULES"],
        ).decode("utf-8")
        
        # Convert SVG to base64 for display
        summary_plot_b64 = base64.b64encode(drugbank_plot_svg.encode()).decode()
        
        # Prepare molecules data for template (limit to visible molecules)
        molecules = {}
        percentile_suffix = get_drugbank_suffix(session.get("atc_code"))
        max_display = min(app.config["MAX_VISIBLE_MOLECULES"], len(all_smiles))
        
        for idx, smiles in enumerate(all_smiles[:max_display]):
            # Get physicochemical properties
            physchem_props = {}
            for prop in physchem_units.keys():
                if prop in smiles_to_property_id_to_pred[smiles]:
                    physchem_props[prop] = smiles_to_property_id_to_pred[smiles][prop]
            
            # Get ADMET predictions with units and percentiles
            admet_props = {}
            for prop_id, value in smiles_to_property_id_to_pred[smiles].items():
                if prop_id not in physchem_units:  # Skip physchem properties
                    prop_name = admet_id_to_name.get(prop_id, prop_id)
                    units = admet_id_to_units.get(prop_id, '-')
                    
                    # Get percentile if available
                    percentile_key = f"{prop_id}_{percentile_suffix}"
                    percentile = smiles_to_property_id_to_pred[smiles].get(percentile_key, 0.0)
                    
                    admet_props[prop_name] = {
                        'prediction': value,
                        'units': units if units != '-' else 'probability',
                        'percentile': percentile
                    }
            
            # Generate radial plot for this molecule
            radial_plot_svg = plot_radial_summary(
                property_id_to_percentile=smiles_to_property_id_to_pred[smiles],
                percentile_suffix=percentile_suffix,
            ).decode("utf-8")
            radial_plot_b64 = base64.b64encode(radial_plot_svg.encode()).decode()
            
            molecules[idx] = {
                'smiles': smiles,
                'physchem': physchem_props,
                'admet': admet_props,
                'radial_plot_b64': radial_plot_b64
            }
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Render comprehensive results template
        return render_template('admet_report.html',
                             timestamp=timestamp,
                             atc_code=session.get("atc_code"),
                             drugbank_size=get_drugbank_size(session.get("atc_code")),
                             summary_plot_b64=summary_plot_b64,
                             molecules=molecules,
                             physchem_units=physchem_units,
                             is_web_display=True)  # Flag to indicate web display vs PDF
        
    except Exception as e:
        return render_template('error.html', 
                             message=f"Error displaying results: {str(e)}")


@app.route("/download_pdf", methods=["GET"])
def download_pdf() -> Response:
    """Downloads predictions as a PDF report.

    :return: A PDF file containing the predictions report.
    """
    try:
        # Check if user_id exists in session
        user_id = session.get("user_id")
        if not user_id:
            return render_template('error.html', 
                                   message="Session not found. Please run predictions first.")
        
        # Get predictions from storage
        all_preds = get_user_preds(user_id)
        
        # Check if the retrieved data is empty
        if all_preds is None or all_preds.empty:
            return render_template('error.html', 
                                   message="No prediction data found. Please run predictions first.")

        # Reconstruct the data as the template needs it
        all_smiles = all_preds.index.unique().tolist()
        smiles_to_property_id_to_pred = all_preds[
            ~all_preds.index.duplicated(keep="first")
        ].to_dict(orient="index")
        
        # Call the existing PDF generator with the correct data
        return generate_pdf_report(
            all_smiles=all_smiles,
            smiles_to_property_id_to_pred=smiles_to_property_id_to_pred,
            all_preds=all_preds,
            atc_code=session.get("atc_code"),
            drugbank_size=get_drugbank_size(session.get("atc_code")),
            warnings=[]
        )
        
    except Exception as e:
        return render_template('error.html', 
                               message=f"PDF generation failed: {str(e)}. Please try downloading CSV instead.")


@app.route("/heartbeat", methods=["POST"])
def heartbeat() -> tuple[str, int]:
    """Registers that the client is still using the site.

    :return: A tuple containing an empty string and a 204 status code.
    """
    # Update user's last activity
    session.modified = True

    if "user_id" in session:
        update_user_activity(session["user_id"])

    # Send no content response
    return "", 204