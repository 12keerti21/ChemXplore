"""Defines the routes of the ADMET-AI Flask app."""
import io
import shutil
from datetime import datetime
from uuid import uuid4

from flask import (
    jsonify,
    redirect,
    render_template,
    request,
    Response,
    send_file,
    session,
    url_for,
)
from rdkit import Chem

from admet_ai._version import __version__
from admet_ai.admet_info import get_admet_info
from admet_ai.drugbank import (
    get_drugbank,
    get_drugbank_size,
    get_drugbank_task_names,
    get_drugbank_unique_atc_codes,
)
from admet_ai.medchem import RULE_NAMES
from admet_ai.plot import plot_boiled_egg, plot_drugbank_reference
from admet_ai.utils import get_drugbank_suffix
from admet_ai.web.app import app
from admet_ai.web.app.analysis import (
    build_molecule_details,
    overview_row,
    predict_all,
    preds_to_property_dicts,
    to_json_value,
)
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

ADMET_CATEGORIES = ["Physicochemical", "Absorption", "Distribution", "Metabolism", "Excretion", "Toxicity"]
MAX_COMPARE = 4


@app.context_processor
def inject_version() -> dict[str, str]:
    return {"version": __version__}


def render(**kwargs) -> str:
    """Renders the page with specified kwargs."""
    return render_template(
        "index.html",
        admet_info=get_admet_info(),
        admet_categories=ADMET_CATEGORIES,
        rule_names=RULE_NAMES,
        drugbank_atc_codes=["all"] + get_drugbank_unique_atc_codes(),
        drugbank_tasks=get_drugbank_task_names(),
        max_molecules=app.config["MAX_MOLECULES"],
        max_visible_molecules=app.config["MAX_VISIBLE_MOLECULES"],
        max_compare=MAX_COMPARE,
        low_performance_threshold=app.config["LOW_PERFORMANCE_THRESHOLD"],
        drugbank_approved_percentile_suffix=get_drugbank_suffix(session.get("atc_code")),
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


def render_error(message: str, status: int = 400) -> tuple[str, int]:
    return render_template("error.html", message=message), status


def drugbank_plot_svg(preds, atc_code: str | None) -> str:
    """Renders the DrugBank reference plot with the user's chosen axes."""
    return replace_svg_dimensions(
        plot_drugbank_reference(
            preds_df=preds,
            drugbank_df=get_drugbank(atc_code=atc_code),
            x_property_name=session.get("drugbank_x_task_name"),
            y_property_name=session.get("drugbank_y_task_name"),
            max_molecule_num=app.config["MAX_VISIBLE_MOLECULES"],
        ).decode("utf-8")
    )


def boiled_egg_svg(all_smiles: list[str]) -> str:
    mols = [Chem.MolFromSmiles(smiles) for smiles in all_smiles[: app.config["MAX_VISIBLE_MOLECULES"]]]
    return replace_svg_dimensions(plot_boiled_egg(mols).decode("utf-8"))


def get_stored_preds():
    """Returns the current user's stored predictions, or None if there are none."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    preds = get_user_preds(user_id)
    if preds is None or preds.empty:
        return None

    update_user_activity(user_id)
    return preds


def build_report_context(preds, numbers: list[int] | None = None, with_overview: bool = True) -> dict:
    """Builds the template data for the report and comparison pages.

    :param preds: The user's stored predictions.
    :param numbers: 1-based molecule numbers to include. Defaults to the first visible molecules.
    :param with_overview: Whether to include the summary plots.
    """
    atc_code = session.get("atc_code")
    rows = preds_to_property_dicts(preds)
    if numbers is None:
        numbers = list(range(1, min(len(rows), app.config["MAX_VISIBLE_MOLECULES"]) + 1))

    context = {
        "molecules": [
            build_molecule_details(number, *rows[number - 1], atc_code=atc_code) for number in numbers
        ],
        "num_molecules": len(rows),
        "admet_info": get_admet_info(),
        "admet_categories": ADMET_CATEGORIES,
        "rule_names": RULE_NAMES,
        "atc_code": atc_code or "all",
        "drugbank_size": get_drugbank_size(atc_code),
        "percentile_suffix": get_drugbank_suffix(atc_code),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "string_to_html_sup": string_to_html_sup,
        "version": __version__,
    }
    if with_overview:
        context["drugbank_plot"] = drugbank_plot_svg(preds, atc_code)
        context["boiled_egg_plot"] = boiled_egg_svg(list(preds.index))

    return context


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """Renders the page and makes predictions if the method is POST."""
    # Assign user ID to session
    if "user_id" not in session:
        session["user_id"] = uuid4().hex

    # If GET request, simply return the page; otherwise if POST request, make predictions
    if request.method == "GET":
        return render()

    # Save the user's text box input
    session["text_smiles"] = request.form.get("text-smiles", "")

    all_smiles, warnings, error = get_smiles_from_request()
    if error is not None:
        return render(errors=[error], warnings=warnings)

    if app.config["MAX_MOLECULES"] is not None and len(all_smiles) > app.config["MAX_MOLECULES"]:
        return render(
            errors=[f"Received too many molecules. Maximum number of molecules is {app.config['MAX_MOLECULES']:,}."]
        )

    # Remove invalid molecules
    mols = smiles_to_mols(all_smiles)
    warnings += [f"Invalid SMILES string: {smiles}" for smiles, mol in zip(all_smiles, mols) if mol is None]
    all_smiles = [smiles for smiles, mol in zip(all_smiles, mols) if mol is not None]
    mols = [mol for mol in mols if mol is not None]

    if len(all_smiles) == 0:
        return render(errors=["No valid SMILES strings given."], warnings=warnings)

    atc_code = session.get("atc_code")
    all_preds = predict_all(all_smiles, mols, atc_code)
    set_user_preds(user_id=session["user_id"], preds_df=all_preds)
    session["has_predictions"] = True
    session["num_molecules"] = len(all_smiles)

    rows = preds_to_property_dicts(all_preds)
    num_display_molecules = min(len(rows), app.config["MAX_VISIBLE_MOLECULES"])
    molecules = [
        build_molecule_details(number, smiles, properties, atc_code=atc_code)
        for number, (smiles, properties) in enumerate(rows[:num_display_molecules], start=1)
    ]

    return render(
        predicted=True,
        molecules=molecules,
        overview_rows=[overview_row(molecule) for molecule in molecules],
        drugbank_plot=drugbank_plot_svg(all_preds, atc_code),
        boiled_egg_plot=boiled_egg_svg(all_smiles),
        num_molecules=len(all_smiles),
        num_display_molecules=num_display_molecules,
        warnings=warnings,
    )


@app.route("/set_atc_code", methods=["POST"])
def set_atc_code() -> Response:
    """Sets the ATC code to filter the DrugBank reference set by.

    :return: A JSON response containing the new DrugBank size.
    """
    atc_code = request.args.get("atc_code", "all").strip().lower()
    if atc_code != "all" and atc_code not in get_drugbank_unique_atc_codes():
        return jsonify({"error": f"Unknown ATC code: {atc_code}"}), 400

    session["atc_code"] = None if atc_code == "all" else atc_code
    drugbank_size = get_drugbank_size(session["atc_code"])

    return jsonify({"atc_code": atc_code, "drugbank_size_string": f"{drugbank_size:,}"})


@app.route("/drugbank_plot", methods=["GET"])
def drugbank_plot() -> Response:
    """Creates a DrugBank reference plot.

    :return: A JSON response containing the SVG of the plot.
    """
    preds = get_stored_preds()
    if preds is None:
        return jsonify({"error": "No predictions available"}), 400

    task_names = get_drugbank_task_names()
    for axis in ["x", "y"]:
        task = request.args.get(f"{axis}_task")
        if task is not None:
            if task not in task_names:
                return jsonify({"error": f"Unknown property: {task}"}), 400
            session[f"drugbank_{axis}_task_name"] = task

    return jsonify({"svg": drugbank_plot_svg(preds, session.get("atc_code"))})


@app.route("/download_predictions")
def download_predictions() -> Response:
    """Downloads predictions as a CSV file."""
    preds = get_stored_preds()
    if preds is None:
        return render_error("No prediction data found. Please run predictions first.")

    buffer = io.BytesIO(preds.to_csv(index_label="smiles").encode("utf-8"))
    return send_file(buffer, as_attachment=True, download_name="chemxplore_predictions.csv", mimetype="text/csv")


@app.route("/show_results", methods=["GET"])
def show_results():
    """Shows the printable report. With ?print=1 the browser print dialog opens on load."""
    preds = get_stored_preds()
    if preds is None:
        return render_error("No predictions available. Please run predictions first.")

    return render_template("report.html", auto_print=request.args.get("print") == "1", **build_report_context(preds))


def pdf_export_available() -> bool:
    try:
        import pdfkit  # noqa: F401
    except ImportError:
        return False

    return shutil.which("wkhtmltopdf") is not None


@app.route("/download_pdf", methods=["GET"])
def download_pdf() -> Response:
    """Downloads the report as a PDF, or falls back to the browser's print-to-PDF without wkhtmltopdf."""
    preds = get_stored_preds()
    if preds is None:
        return render_error("No prediction data found. Please run predictions first.")

    if not pdf_export_available():
        return redirect(url_for("show_results", print=1))

    import pdfkit

    html = render_template("report.html", auto_print=False, **build_report_context(preds))
    try:
        pdf = pdfkit.from_string(
            html,
            False,
            options={"page-size": "A4", "margin-top": "12mm", "margin-bottom": "12mm", "encoding": "UTF-8", "quiet": ""},
        )
    except OSError:
        app.logger.exception("PDF generation failed")
        return redirect(url_for("show_results", print=1))

    filename = f"chemxplore_report_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.pdf"
    return send_file(io.BytesIO(pdf), as_attachment=True, download_name=filename, mimetype="application/pdf")


@app.route("/compare", methods=["GET"])
def compare():
    """Compares 2 to 4 molecules side by side, chosen by 1-based number (?ids=1,3)."""
    preds = get_stored_preds()
    if preds is None:
        return render_error("No predictions available. Please run predictions first.")

    try:
        numbers = [int(number) for number in request.args.get("ids", "").split(",") if number.strip()]
    except ValueError:
        return render_error("Molecule numbers must be integers.")

    numbers = list(dict.fromkeys(numbers))
    if not 2 <= len(numbers) <= MAX_COMPARE:
        return render_error(f"Pick between 2 and {MAX_COMPARE} molecules to compare.")
    if any(not 1 <= number <= len(preds) for number in numbers):
        return render_error(f"Molecule numbers must be between 1 and {len(preds)}.")

    return render_template("compare.html", **build_report_context(preds, numbers=numbers, with_overview=False))


@app.route("/api/health", methods=["GET"])
def api_health() -> Response:
    return jsonify({"status": "ok", "version": __version__})


@app.route("/api/predict", methods=["POST"])
def api_predict() -> Response:
    """Predicts ADMET properties for a JSON body like {"smiles": ["CCO"], "atc_code": "analgesics", "similar_drugs": 3}.

    :return: JSON with one entry per valid molecule and the list of invalid SMILES.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Send a JSON object with a 'smiles' list."}), 400

    all_smiles = body.get("smiles")
    if isinstance(all_smiles, str):
        all_smiles = [all_smiles]
    if not isinstance(all_smiles, list) or not all_smiles or not all(isinstance(s, str) for s in all_smiles):
        return jsonify({"error": "'smiles' must be a non-empty list of strings."}), 400
    if app.config["MAX_MOLECULES"] is not None and len(all_smiles) > app.config["MAX_MOLECULES"]:
        return jsonify({"error": f"At most {app.config['MAX_MOLECULES']:,} molecules per request."}), 400

    atc_code = body.get("atc_code")
    if atc_code is not None:
        atc_code = str(atc_code).lower()
        if atc_code == "all":
            atc_code = None
        elif atc_code not in get_drugbank_unique_atc_codes():
            return jsonify({"error": f"Unknown ATC code: {atc_code}"}), 400

    num_similar = body.get("similar_drugs", 3)
    if isinstance(num_similar, bool) or not isinstance(num_similar, int) or not 0 <= num_similar <= 20:
        return jsonify({"error": "'similar_drugs' must be an integer from 0 to 20."}), 400

    all_smiles = [smiles.strip() for smiles in all_smiles]
    mols = smiles_to_mols(all_smiles)
    invalid = [smiles for smiles, mol in zip(all_smiles, mols) if mol is None]
    valid_smiles = [smiles for smiles, mol in zip(all_smiles, mols) if mol is not None]
    valid_mols = [mol for mol in mols if mol is not None]

    molecules = []
    if valid_smiles:
        preds = predict_all(valid_smiles, valid_mols, atc_code)
        suffix = "_" + get_drugbank_suffix(atc_code)
        for number, (smiles, properties) in enumerate(preds_to_property_dicts(preds), start=1):
            details = build_molecule_details(
                number, smiles, properties, atc_code=atc_code, num_similar=num_similar, with_plots=False
            )
            molecules.append(
                {
                    "smiles": smiles,
                    "predictions": {key: value for key, value in properties.items() if not key.endswith(suffix)},
                    "drugbank_percentiles": {
                        key[: -len(suffix)]: value for key, value in properties.items() if key.endswith(suffix)
                    },
                    "medchem": details["medchem"],
                    "risk": {"score": details["risk_score"], "flags": details["risk_flags"]},
                    "similar_drugs": details["similar_drugs"],
                }
            )

    return jsonify(
        to_json_value({"atc_code": atc_code or "all", "molecules": molecules, "invalid_smiles": invalid})
    )


@app.route("/heartbeat", methods=["POST"])
def heartbeat() -> tuple[str, int]:
    """Registers that the client is still using the site.

    :return: A tuple containing an empty string and a 204 status code.
    """
    session.modified = True

    if "user_id" in session:
        update_user_activity(session["user_id"])

    return "", 204
