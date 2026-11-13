"""Whitelist for incomplete editor drafts. A draft never asserts catalog validity."""

import json
from dataclasses import dataclass, fields

from transmitracker.profiles.models import Leg, Profile, ProfileKind, Transfer


@dataclass(frozen=True)
class StoredDraft:
    profile_id: str
    kind: str
    payload: dict
    revision: int
    base_profile_revision: int


def check_draft(profile_id, kind, payload, base_revision):
    if not isinstance(profile_id, str) or not 1 <= len(profile_id) <= 100:
        raise ValueError("Invalid draft ID")
    ProfileKind(kind)
    if type(base_revision) is not int or base_revision < 0:
        raise ValueError("Invalid base revision")
    if not isinstance(payload, dict) or set(payload) != {"profile", "legs_ui", "consultation"}:
        raise ValueError("Invalid draft fields")
    profile = payload["profile"]
    if not isinstance(profile, dict) or set(profile) != {f.name for f in fields(Profile)}:
        raise ValueError("Unknown profile field")
    if profile.get("profile_id") != profile_id or profile.get("kind") != kind:
        raise ValueError("Draft identity differs")
    if not isinstance(profile.get("legs"), list) or not 1 <= len(profile["legs"]) <= 3:
        raise ValueError("Invalid draft legs")
    for key, cls in (("legs", Leg), ("transfers", Transfer)):
        if not isinstance(profile.get(key), list) or any(
            not isinstance(v, dict) or set(v) != {f.name for f in fields(cls)} for v in profile[key]
        ):
            raise ValueError("Unknown draft fields")
    ui = payload["legs_ui"]
    allowed = {
        "uid",
        "mode",
        "search_text",
        "route_search",
        "origin_label",
        "route_label",
        "pattern_label",
        "destination_label",
        "pending_origin",
        "origin_choice_label",
    }
    if not isinstance(ui, list) or len(ui) != len(profile["legs"]):
        raise ValueError("Invalid leg presentation")
    for row in ui:
        if (
            not isinstance(row, dict)
            or set(row) != allowed
            or any(not isinstance(v, str) for v in row.values())
            or row["mode"] not in ("Origen primero", "Ruta primero")
        ):
            raise ValueError("Invalid presentation fields")
    if len({row["uid"] for row in ui}) != len(ui):
        raise ValueError("Duplicate leg identity")
    consultation = payload["consultation"]
    if (
        not isinstance(consultation, dict)
        or set(consultation) != {"day", "clock"}
        or any(not isinstance(v, str) for v in consultation.values())
    ):
        raise ValueError("Invalid consultation fields")
    if len(json.dumps(payload)) > 100_000:
        raise ValueError("Draft too large")
