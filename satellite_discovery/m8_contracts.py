"""Normative M8 panel-role and execution-status vocabulary.

These contracts intentionally describe software states and reference-panel
roles. They do not classify candidate biology.
"""

PANEL_ROLES = frozenset({
    "satellite_subviral",
    "virus_helper",
    "host_nuclear",
    "host_organelle",
    "microbial",
    "vector",
    "plasmid",
    "adapter",
    "technical_contaminant",
    "mobile_element",
    "related_non_satellite",
})

PANEL_ROLE_SUBROLES = {
    "satellite_subviral": frozenset({
        "satellite_dna", "satellite_rna", "satellite_virus", "other_subviral",
    }),
    "virus_helper": frozenset({
        "declared_potential_helper", "segmented_helper_genome", "other_virus",
    }),
    "host_nuclear": frozenset({"nuclear_assembly", "transcript"}),
    "host_organelle": frozenset({
        "mitochondrial", "plastid", "other_organelle",
    }),
    "microbial": frozenset({
        "bacterial", "archaeal", "fungal", "other_microbe",
    }),
    "vector": frozenset({"cloning_vector", "viral_vector", "other_vector"}),
    "plasmid": frozenset({"plasmid", "construct"}),
    "adapter": frozenset({"sequencing_adapter"}),
    "technical_contaminant": frozenset({
        "reagent", "cell_line", "laboratory_control",
        "synthetic_control", "other_technical",
    }),
    "mobile_element": frozenset({
        "dna_transposon", "retroelements", "endogenous_viral_element",
        "other_mobile_element",
    }),
    "related_non_satellite": frozenset({
        "deltavirus_context", "viroid_context", "virophage_context",
        "polinton_like_context", "proviral_context", "other_related",
    }),
}

# Fixture vocabulary is resolved here, not treated as a second panel-role enum.
# Ambiguous aliases require an explicit subrole and never guess a biological
# distinction from the label alone.
FIXTURE_ROLE_ALIASES = {
    "host": "host_requires_nuclear_or_organelle",
    "host_nuclear": ("host_nuclear", None),
    "host_organelle": ("host_organelle", None),
    "organelle": ("host_organelle", None),
    "satellite_subviral": ("satellite_subviral", None),
    "virus_helper": ("virus_helper", None),
    "microbial": ("microbial", None),
    "vector_plasmid": "vector_requires_vector_or_plasmid",
    "vector": ("vector", None),
    "plasmid": ("plasmid", None),
    "adapter": ("adapter", "sequencing_adapter"),
    "sequencing_adapter": ("adapter", "sequencing_adapter"),
    "reagent": ("technical_contaminant", "reagent"),
    "technical_contaminant": ("technical_contaminant", None),
    "mobile_element": ("mobile_element", None),
    "related_non_satellite": ("related_non_satellite", None),
    "delta_related_subviral": (
        "related_non_satellite", "deltavirus_context",
    ),
    "deltavirus_context": ("related_non_satellite", "deltavirus_context"),
    "viroid": ("related_non_satellite", "viroid_context"),
    "viroid_context": ("related_non_satellite", "viroid_context"),
    "virophage": ("related_non_satellite", "virophage_context"),
    "virophage_context": ("related_non_satellite", "virophage_context"),
    "polinton_related": ("related_non_satellite", "polinton_like_context"),
    "polinton_like_context": ("related_non_satellite", "polinton_like_context"),
    "polinton_like_virus_context": (
        "related_non_satellite", "polinton_like_context",
    ),
    "polinton_related_and_virophage_label_conflict":
        "requires_separate_polinton_and_virophage_records",
}

FIXTURE_SUBROLE_ALIASES = {
    ("satellite_subviral", "plant_satellite_dna"): "satellite_dna",
    ("satellite_subviral", "plant_satellite_rna"): "satellite_rna",
    ("satellite_subviral", "plant_satellite_virus"): "satellite_virus",
    ("virus_helper", "documented_helper_context"): "declared_potential_helper",
    ("virus_helper", "segmented_helper_genome"): "segmented_helper_genome",
    ("related_non_satellite", "deltavirus_context"): "deltavirus_context",
    ("related_non_satellite", "viroid_context"): "viroid_context",
    ("related_non_satellite", "virophage_context"): "virophage_context",
    ("related_non_satellite", "polinton_related"): "polinton_like_context",
    ("related_non_satellite", "polinton_like_virus_context"):
        "polinton_like_context",
    ("related_non_satellite", "polinton_like_context"): "polinton_like_context",
    ("related_non_satellite",
     "polinton_related_and_virophage_label_conflict"):
        "requires_separate_polinton_and_virophage_records",
}

SEARCH_STATUSES = frozenset({
    "SEARCH_COMPLETED_MATCHES_REPORTED",
    "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
    "INSUFFICIENT_INFORMATION",
    "DEPENDENCY_UNAVAILABLE",
    "SEARCH_FAILED",
    "SEARCH_INTERRUPTED",
    "SEARCH_TRUNCATED",
    "REFERENCE_PANEL_INVALID",
    "REFERENCE_PANEL_INCOMPLETE",
    "INPUT_INVALID",
})
LIFECYCLE_STATUSES = frozenset({
    "NOT_SELECTED", "NOT_APPLICABLE", "NOT_STARTED", "RUNNING",
})
AGGREGATE_STATUSES = frozenset({"COMPLETE", "PARTIAL"})

_UNAVAILABLE_CAUSES = {
    "dependency": "DEPENDENCY_UNAVAILABLE",
    "invalid_candidate": "INPUT_INVALID",
    "invalid_panel": "REFERENCE_PANEL_INVALID",
    "incomplete_panel": "REFERENCE_PANEL_INCOMPLETE",
    "interrupted": "SEARCH_INTERRUPTED",
    "execution": "SEARCH_FAILED",
}


def normalize_panel_role(role, subrole=None, *, accession_version=None):
    """Resolve canonical or fixture terminology to one role/subrole pair."""
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Panel role must be non-empty text")
    key = "_".join(role.strip().lower().replace("-", " ").split())
    alias = FIXTURE_ROLE_ALIASES.get(key)
    if alias == "requires_separate_polinton_and_virophage_records":
        raise ValueError(
            "Fixture role conflict must be split into explicit Polinton-like "
            "and virophage-context records")
    if alias == "host_requires_nuclear_or_organelle":
        if subrole in {"nuclear", "nuclear_assembly", "transcript"}:
            return {
                "role": "host_nuclear",
                "subrole": None if subrole == "nuclear" else subrole,
            }
        if subrole in {"organelle", "mitochondrial", "plastid", "other_organelle"}:
            return {
                "role": "host_organelle",
                "subrole": None if subrole == "organelle" else subrole,
            }
        raise ValueError("Fixture role 'host' requires a nuclear or organelle subrole")
    if alias == "vector_requires_vector_or_plasmid":
        if subrole == "vector":
            return {"role": "vector", "subrole": None}
        if subrole == "plasmid":
            return {"role": "plasmid", "subrole": None}
        raise ValueError("Fixture role 'vector_plasmid' requires vector or plasmid")
    if isinstance(alias, tuple):
        canonical, alias_subrole = alias
        if subrole is not None and alias_subrole is not None and subrole != alias_subrole:
            raise ValueError(f"Fixture role {key!r} conflicts with its mapped subrole")
        subrole = alias_subrole if subrole is None else subrole
        role = canonical
    else:
        role = key
    if role not in PANEL_ROLES:
        raise ValueError(f"Unknown M8 panel role: {role!r}")
    if isinstance(subrole, str):
        subrole_key = "_".join(subrole.strip().lower().replace("-", " ").split())
        if (role, subrole_key) in FIXTURE_SUBROLE_ALIASES:
            subrole = FIXTURE_SUBROLE_ALIASES[(role, subrole_key)]
            if subrole == "requires_separate_polinton_and_virophage_records":
                raise ValueError(
                    "Fixture subrole conflict must be split into explicit "
                    "Polinton-like and virophage-context records")
        elif subrole_key == "virophage_and_proviral_context":
            if role == "related_non_satellite" and accession_version == "KU052222.1":
                # The curator-approved accession is specifically proviral
                # context, not a free-virus virophage. Keep this exception
                # accession-scoped; the raw alias is ambiguous elsewhere.
                subrole = "proviral_context"
            else:
                raise ValueError(
                    "Fixture subrole conflates virophage and proviral context; "
                    "only the reviewed KU052222.1 accession maps to "
                    "proviral_context")
        else:
            subrole = subrole_key
    allowed_subroles = PANEL_ROLE_SUBROLES[role]
    if subrole is not None and subrole not in allowed_subroles:
        raise ValueError(f"Subrole {subrole!r} is not valid for panel role {role!r}")
    return {"role": role, "subrole": subrole}


def completed_search_status(*, hit_count, accounting_complete,
                            candidate_valid=True, dependency_available=True,
                            panel_state="VALID", execution_state="COMPLETED",
                            output_truncated=False,
                            method_informative=True):
    """Serialize one branch outcome without turning failure into a no-hit."""
    if not candidate_valid:
        return "INPUT_INVALID"
    if not dependency_available:
        return "DEPENDENCY_UNAVAILABLE"
    if panel_state not in {"VALID", "INVALID", "INCOMPLETE"}:
        return "REFERENCE_PANEL_INVALID"
    if panel_state == "INVALID":
        return "REFERENCE_PANEL_INVALID"
    if panel_state == "INCOMPLETE":
        return "REFERENCE_PANEL_INCOMPLETE"
    if execution_state == "INTERRUPTED":
        return "SEARCH_INTERRUPTED"
    if execution_state != "COMPLETED":
        return "SEARCH_FAILED"
    if output_truncated:
        return "SEARCH_TRUNCATED"
    if not accounting_complete:
        return "SEARCH_FAILED"
    if type(hit_count) is not int or hit_count < 0:
        return "SEARCH_FAILED"
    if hit_count:
        return "SEARCH_COMPLETED_MATCHES_REPORTED"
    if not method_informative:
        return "INSUFFICIENT_INFORMATION"
    return "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"


def aggregate_search_status(branch_statuses, *, required_branch_count=None):
    """Return COMPLETE only when every required branch completed without truncation."""
    if not isinstance(branch_statuses, (list, tuple)):
        raise ValueError("Branch statuses must be a list or tuple")
    if required_branch_count is None:
        required_branch_count = len(branch_statuses)
    if type(required_branch_count) is not int or required_branch_count < 0:
        raise ValueError("required_branch_count must be a non-negative integer")
    if not branch_statuses or len(branch_statuses) != required_branch_count:
        return "PARTIAL"
    if any(
        not isinstance(status, str) or status not in SEARCH_STATUSES
        for status in branch_statuses
    ):
        raise ValueError("Aggregate contains an unknown or non-search branch status")
    completed = {
        "SEARCH_COMPLETED_MATCHES_REPORTED",
        "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
    }
    return "COMPLETE" if all(status in completed for status in branch_statuses) else "PARTIAL"


def map_fixture_status(label, *, hit_count=None, accounting_complete=False,
                       cause=None):
    """Map fixture-only labels only when the software evidence supports it."""
    if not isinstance(label, str):
        raise ValueError("Fixture status must be text")
    key = label.strip().upper()
    if key == "PARTIAL":
        return "PARTIAL"
    if key == "UNAVAILABLE":
        status = _UNAVAILABLE_CAUSES.get(cause)
        if status is None:
            raise ValueError("UNAVAILABLE requires a specific software cause")
        return status
    if key == "FAILED":
        if cause == "interrupted":
            return "SEARCH_INTERRUPTED"
        if cause in {"dependency", "invalid_candidate", "invalid_panel",
                     "incomplete_panel"}:
            return _UNAVAILABLE_CAUSES[cause]
        return "SEARCH_FAILED" if cause == "execution" else _raise_status_error(
            "FAILED requires an execution or interruption cause")
    if key in {"COMPLETE", "AMBIGUOUS", "KNOWN", "SIMILAR"}:
        if key != "COMPLETE" and not (accounting_complete and hit_count):
            raise ValueError(
                f"{key} is not a software status; complete hit accounting is required")
        if not accounting_complete:
            raise ValueError("COMPLETE requires complete branch accounting")
        if type(hit_count) is not int or hit_count < 0:
            raise ValueError("COMPLETE requires a non-negative hit count")
        return (
            "SEARCH_COMPLETED_MATCHES_REPORTED"
            if hit_count
            else "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
        )
    if key in SEARCH_STATUSES or key in LIFECYCLE_STATUSES or key in AGGREGATE_STATUSES:
        return key
    raise ValueError(f"Unknown fixture status: {label!r}")


def _raise_status_error(message):
    raise ValueError(message)