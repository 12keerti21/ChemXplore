"""Resolves compound names to SMILES with the PubChem PUG REST API."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

PUBCHEM_NAME_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/property/SMILES/JSON"


def name_to_smiles(name: str, timeout: float = 10.0) -> str | None:
    """Looks up a compound name on PubChem.

    :param name: A compound name, such as "ibuprofen".
    :param timeout: Request timeout in seconds.
    :return: The SMILES of the best match, or None when PubChem has no match.
    :raises ConnectionError: When PubChem cannot be reached.
    """
    try:
        with urlopen(PUBCHEM_NAME_URL.format(quote(name.strip(), safe="")), timeout=timeout) as response:
            properties = json.load(response)["PropertyTable"]["Properties"]
    except HTTPError as error:
        if error.code == 404:
            return None
        raise ConnectionError(f"PubChem returned HTTP {error.code}") from error
    except (URLError, TimeoutError) as error:
        raise ConnectionError("Could not reach PubChem") from error

    return properties[0].get("SMILES") if properties else None


def names_to_smiles(names: list[str], timeout: float = 10.0) -> tuple[list[str], list[str]]:
    """Resolves several names, keeping input order.

    :return: A tuple of the resolved SMILES and the names that had no match.
    """
    smiles, not_found = [], []
    for name in names:
        result = name_to_smiles(name, timeout=timeout)
        if result is None:
            not_found.append(name)
        else:
            smiles.append(result)

    return smiles, not_found
