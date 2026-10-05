"""Runs the development web interface for ADMET-AI (Flask)."""
import argparse
import os
import secrets
import warnings
from datetime import timedelta
from threading import Thread

import matplotlib
from tap import tapify

from admet_ai.admet_info import load_admet_info
from admet_ai.drugbank import load_drugbank
from admet_ai.web.app import app
from admet_ai.web.app.models import load_admet_model
from admet_ai.web.app.storage import cleanup_storage

matplotlib.use("Agg")

# Suppress noisy warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, message="to-Python converter.*")
warnings.filterwarnings("ignore", category=FutureWarning, message="You are using `torch.load`.*")


def setup_web(
    secret_key: str | None = None,
    session_lifetime: int = 5 * 60,
    heartbeat_frequency: int = 60,
    max_molecules: int = 1000,
    max_visible_molecules: int = 25,
    no_cache_molecules: bool = False,
    max_name_lookups: int = 25,
) -> None:
    """Sets up the ADMET-AI website.

    :param secret_key: Secret key for Flask app. Defaults to the CHEMXPLORE_SECRET_KEY environment variable,
                       or a random key, which logs everyone out on restart.
    :param session_lifetime: Session lifetime in seconds.
    :param heartbeat_frequency: Frequency of client heartbeat in seconds.
    :param max_molecules: Maximum number of molecules to allow predictions for.
    :param max_visible_molecules: Maximum number of molecules to display.
    :param no_cache_molecules: Whether to turn off molecule caching (reduces memory but slows down predictions).
    :param max_name_lookups: Maximum number of compound names to resolve with PubChem per request.
    """
    secret_key = secret_key or os.environ.get("CHEMXPLORE_SECRET_KEY")
    if secret_key is None:
        print("CHEMXPLORE_SECRET_KEY is not set, using a random secret key")
        secret_key = secrets.token_hex(32)

    # Set up Flask app variables
    app.secret_key = secret_key
    app.permanent_session_lifetime = timedelta(seconds=session_lifetime)
    app.config["SESSION_LIFETIME"] = session_lifetime
    app.config["HEARTBEAT_FREQUENCY"] = heartbeat_frequency
    app.config["MAX_MOLECULES"] = max_molecules
    app.config["MAX_VISIBLE_MOLECULES"] = max_visible_molecules
    app.config["CACHE_MOLECULES"] = not no_cache_molecules
    app.config["MAX_NAME_LOOKUPS"] = max_name_lookups

    # Load ADMET info, DrugBank, and models into memory
    with app.app_context():
        print("Loading ADMET INFO")
        load_admet_info()

        print("Loading DrugBank")
        load_drugbank()

        print("Loading models")
        load_admet_model()

    # Set up garbage collection
    Thread(target=cleanup_storage, daemon=True).start()


def admet_web(host: str = "127.0.0.1", port: int = 5000) -> None:
    """Runs the ADMET-AI website locally.

    :param host: Host to run the website on.
    :param port: Port to run the website on.
    """
    # Take --host and --port here and pass the remaining arguments to setup_web
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", default=host)
    parser.add_argument("--port", type=int, default=port)
    args, setup_args = parser.parse_known_args()

    tapify(setup_web, command_line_args=setup_args)

    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    admet_web()
