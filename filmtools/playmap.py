"""Group raw Hudl play/formation names into families for tendency tables.

Rules are keyword checks in order; edit PLAY_RULES as new opponents bring
new terminology. Anything unmatched keeps its raw name.
"""
from __future__ import annotations

import re

import pandas as pd

# (family, [keywords that must ALL appear]) - first match wins.
PLAY_RULES: list[tuple[str, list[str]]] = [
    ("Screen", ["SCREEN"]),
    ("Play-action", ["P/A"]),
    ("Buck Sweep", ["BUCK", "SWEEP"]),
    ("Fly Counter", ["FLY", "COUNTER"]),
    ("QB run / option", ["OPTION"]),
    ("QB run / option", ["QB"]),
    ("Fly Sweep", ["FLY", "SWEEP"]),
    ("Inside Zone Read", ["ZONE"]),
    ("Power", ["POWER"]),
    ("Counter", ["COUNTER"]),
    ("Dive", ["DIVE"]),
    ("Quick screen (Key)", ["KEY"]),
]
IGNORE = {"BAD SNAP"}
# Route strings: digits, or route names like DRAG / SEAM / CURL / POST / VERTS.
ROUTE_WORDS = {"DRAG", "SEAM", "CURL", "POST", "WHEEL", "DIG", "CORNER", "HITCHES", "VERTS",
               "SLANT", "OUT", "FLAT", "PIVOT", "HITCH"}


def play_family(play) -> str | None:
    if pd.isna(play):
        return None
    p = str(play).upper().strip()
    if p in IGNORE:
        return None
    for family, words in PLAY_RULES:
        if all(w in p for w in words):
            return family
    tokens = set(re.split(r"[\s/]+", p))
    if re.fullmatch(r"[\d\s]+", p) or tokens & ROUTE_WORDS:
        return "Dropback pass"
    return p.title()


def formation_family(form) -> str | None:
    if pd.isna(form):
        return None
    f = " " + str(form).upper() + " "
    for w in (" LEFT ", " RIGHT ", " OPEN "):
        f = f.replace(w, " ")
    return " ".join(f.split()).title()
