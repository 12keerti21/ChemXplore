"""Traffic-light risk summary built from ADMET predictions and medchem checks.

The thresholds are screening heuristics for triage, not regulatory cut-offs.
"""
LOW, MEDIUM, HIGH = "low", "medium", "high"
CYP_INHIBITION_IDS = ["CYP1A2_Veith", "CYP2C19_Veith", "CYP2C9_Veith", "CYP2D6_Veith", "CYP3A4_Veith"]
PROBABILITY_RISKS = [
    ("hERG", "hERG", "Cardiotoxicity (hERG blocking)"),
    ("AMES", "AMES", "Mutagenicity (Ames)"),
    ("DILI", "DILI", "Liver injury (DILI)"),
    ("ClinTox", "ClinTox", "Clinical toxicity"),
]


def _level(value: float, medium: float, high: float, higher_is_worse: bool = True) -> str:
    if not higher_is_worse:
        value, medium, high = -value, -medium, -high
    if value >= high:
        return HIGH
    if value >= medium:
        return MEDIUM
    return LOW


def _flag(key: str, label: str, level: str, value: str) -> dict[str, str]:
    return {"key": key, "label": label, "level": level, "value": value}


def risk_summary(properties: dict[str, float]) -> list[dict[str, str]]:
    """Builds risk flags for one molecule.

    :param properties: Property ID to value, holding the ADMET predictions and, when available,
                       the medchem summary columns (PAINS_alerts, Brenk_alerts).
    :return: A list of flags with key, label, level (low/medium/high) and a display value.
    """
    flags = [
        _flag(key, label, _level(properties[prop], 0.4, 0.7), f"{properties[prop]:.2f}")
        for key, prop, label in PROBABILITY_RISKS
    ]

    worst_cyp = max(CYP_INHIBITION_IDS, key=lambda prop: properties[prop])
    flags.append(
        _flag(
            "CYP",
            "Drug-drug interactions (CYP inhibition)",
            _level(properties[worst_cyp], 0.4, 0.7),
            f"{worst_cyp.split('_')[0]} {properties[worst_cyp]:.2f}",
        )
    )

    hia = properties["HIA_Hou"]
    flags.append(_flag("HIA", "Oral absorption", _level(hia, 0.7, 0.4, higher_is_worse=False), f"{hia:.2f}"))

    log_s = properties["Solubility_AqSolDB"]
    flags.append(
        _flag("Solubility", "Aqueous solubility", _level(log_s, -4, -6, higher_is_worse=False), f"logS {log_s:.2f}")
    )

    lipinski_violations = round(4 - properties["Lipinski"])
    flags.append(
        _flag("Lipinski", "Drug-likeness (Lipinski)", _level(lipinski_violations, 1, 2), f"{lipinski_violations} violations")
    )

    if "PAINS_alerts" in properties:
        pains, brenk = int(properties["PAINS_alerts"]), int(properties["Brenk_alerts"])
        level = HIGH if pains else MEDIUM if brenk else LOW
        flags.append(_flag("Alerts", "Structural alerts", level, f"{pains} PAINS, {brenk} Brenk"))

    return flags


def risk_score(flags: list[dict[str, str]]) -> int:
    """Scores flags as 2 per high and 1 per medium, so higher means riskier."""
    return sum({LOW: 0, MEDIUM: 1, HIGH: 2}[flag["level"]] for flag in flags)
