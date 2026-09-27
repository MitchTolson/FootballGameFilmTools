"""Load an opponent's Hudl game folders into one normalized play table.

Expected layout (one folder per opponent, one sub-folder per game):

    Opponents/<Team>/<game folder>/Wide - Clip 001.mp4 ...
    Opponents/<Team>/<game folder>/<breakdown>.xlsx

Each breakdown row has a PLAY # that matches the clip number. Rows are tagged
from the scouted team's point of view: ODK "O" = scouted team on offense,
"D" = on defense, "K" = kicking game. YARD LN is relative to the team with the
ball (-24 = its own 24, 24 = opponent's 24).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .playmap import play_family, formation_family

CLIP_RE = re.compile(r"clip\s*(\d+)", re.IGNORECASE)
DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")


@dataclass
class GameInfo:
    folder: Path
    date: pd.Timestamp | None
    opponent: str          # who the scouted team played in this game
    breakdown: Path
    clips: dict[int, Path]


def _parse_game_folder(folder: Path, team: str) -> tuple[pd.Timestamp | None, str]:
    name = folder.name
    m = DATE_RE.search(name)
    date = pd.Timestamp(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None
    core = DATE_RE.sub("", name)
    core = re.sub(r"\(\d+\)", "", core)                 # Hudl id
    sides = re.split(r"\s+vs\.?\s+", core, flags=re.IGNORECASE)
    opponent = "?"
    for side in sides:
        if team.lower() not in side.lower():
            opponent = re.sub(r"\(.*?\)", "", side).replace("_", " ").strip()
    return date, opponent


def find_games(team_dir: Path) -> list[GameInfo]:
    team = team_dir.name
    games = []
    for folder in sorted(p for p in team_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        sheets = [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")]
        if not sheets:
            continue
        clips = {}
        for mp4 in folder.glob("*.mp4"):
            m = CLIP_RE.search(mp4.stem)
            if m:
                clips[int(m.group(1))] = mp4
        date, opponent = _parse_game_folder(folder, team)
        games.append(GameInfo(folder, date, opponent, sheets[0], clips))
    games.sort(key=lambda g: (g.date is None, g.date))
    return games


def _dd_bucket(dn, dist) -> str | None:
    if pd.isna(dn) or pd.isna(dist):
        return None
    dn = int(dn)
    if dn == 1:
        return "1st & 10+" if dist >= 10 else "1st & <10"
    label = {2: "2nd", 3: "3rd", 4: "4th"}.get(dn)
    if label is None:
        return None
    if dist <= 2:
        return f"{label} & short (1-2)"
    if dist <= 6:
        return f"{label} & medium (3-6)"
    return f"{label} & long (7+)"


def _field_zone(ytg) -> str | None:
    if pd.isna(ytg):
        return None
    if ytg <= 5:
        return "Goal line (5-)"
    if ytg <= 20:
        return "Red zone (6-20)"
    if ytg <= 50:
        return "Opp territory (21-50)"
    if ytg <= 80:
        return "Own territory (own 20-49)"
    return "Backed up (inside own 20)"


def _successful(dn, dist, gain) -> bool | None:
    if pd.isna(dn) or pd.isna(dist) or pd.isna(gain):
        return None
    need = {1: 0.4, 2: 0.6}.get(int(dn), 1.0) * dist
    return gain >= need


def _relative(dir_, ref, same: str, other: str):
    if pd.isna(dir_) or pd.isna(ref) or dir_ not in ("L", "R") or ref not in ("L", "R"):
        return None
    return same if dir_ == ref else other


UNIT_NAMES = {"KO": "Kickoff", "KO Rec": "Kickoff", "Onside Kick": "Onside kick", "Punt": "Punt",
              "Punt Rec": "Punt", "Fake Punt": "Fake punt", "Extra Pt.": "PAT", "Extra Pt. Block": "PAT",
              "2 Pt.": "2-pt try", "FG": "Field goal"}


def _kicking_team(game: pd.DataFrame) -> pd.Series:
    """Who kicked on each K row: 'scouted' or 'opponent'.

    Hudl's KO / Onside / Fake Punt / Extra Pt. tags don't reliably say which team kicked, so use
    possession: the team that had the ball on the previous snap (it just scored or is punting) kicks.
    For a kick that opens a half, the receiving team gets the next snap unless the kick was recovered.
    Tags that name the receiving side ("... Rec", "... Block") are trusted as-is.
    """
    game = game.sort_values("PLAY #")
    scrim = game[game["ODK"].isin(["O", "D"])]
    half = (game["QTR"] > 2).astype(int)
    out = {}
    for idx, r in game[game["ODK"] == "K"].iterrows():
        pt = r["PLAY TYPE"] if pd.notna(r["PLAY TYPE"]) else ""
        if pt.endswith("Rec") or pt.endswith("Block"):
            out[idx] = "opponent"
            continue
        prev = scrim[(scrim["PLAY #"] < r["PLAY #"]) & (half[scrim.index] == half[idx])]
        if len(prev):
            out[idx] = "scouted" if prev.iloc[-1]["ODK"] == "O" else "opponent"
            continue
        nxt = scrim[scrim["PLAY #"] > r["PLAY #"]]
        if not len(nxt):
            out[idx] = None
            continue
        next_is_scouted = nxt.iloc[0]["ODK"] == "O"
        recovered = "Recovered" in str(r["RESULT"])
        out[idx] = "scouted" if next_is_scouted == recovered else "opponent"
    return pd.Series(out, dtype="object")


def load_team(team_dir: str | Path) -> tuple[pd.DataFrame, list[GameInfo], list[str]]:
    """Return (plays, games, warnings)."""
    team_dir = Path(team_dir)
    games = find_games(team_dir)
    warnings: list[str] = []
    frames = []
    for gi, g in enumerate(games, 1):
        df = pd.read_excel(g.breakdown)
        if len(df) != len(g.clips):
            warnings.append(f"{g.folder.name}: {len(df)} breakdown rows vs {len(g.clips)} clips")
        df["GAME_NUM"] = gi
        df["GAME"] = g.opponent
        df["GAME_DATE"] = g.date
        df["CLIP"] = df["PLAY #"].map(lambda n: g.clips.get(int(n)) if pd.notna(n) else None)
        missing = df["CLIP"].isna().sum()
        if missing:
            warnings.append(f"{g.folder.name}: {missing} rows without a matching clip")
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No game folders with a breakdown .xlsx under {team_dir}")
    p = pd.concat(frames, ignore_index=True)

    for c in ("ODK", "PLAY TYPE", "RESULT", "OFF STR", "OFF FORM", "OFF PLAY", "PLAY DIR", "MOTION DIR", "HASH"):
        if c in p:
            p[c] = p[c].astype("string").str.strip()
    p = p[p["ODK"].isin(["O", "D", "K"])].copy()

    p["SIDE"] = p["ODK"].map({"O": "offense", "D": "defense", "K": "special"})
    p["RESULT"] = p["RESULT"].fillna("")
    p["IS_PENALTY"] = p["RESULT"].str.contains("Penalty")
    p["IS_TIMEOUT"] = p["RESULT"].str.contains("Timeout")
    p["IS_TD"] = p["RESULT"].str.contains("TD")
    p["IS_TURNOVER"] = p["RESULT"].str.contains("Interception|Fumble") & ~p["RESULT"].str.contains("Recovered")

    # Scrambles and sacks are pass plays that ended as runs.
    kind = p["PLAY TYPE"].where(p["PLAY TYPE"].isin(["Run", "Pass"]))
    kind = kind.mask(p["RESULT"].str.contains("Scramble|Sack"), "Pass")
    p["KIND"] = kind

    p["GAIN"] = pd.to_numeric(p["GN/LS"], errors="coerce")
    yl = pd.to_numeric(p["YARD LN"], errors="coerce")
    p["YDS_TO_GOAL"] = yl.where(yl > 0, 100 + yl)
    p["FIELD_ZONE"] = p["YDS_TO_GOAL"].map(_field_zone)
    p["DD"] = [_dd_bucket(d, t) for d, t in zip(p["DN"], p["DIST"])]

    # "Scrimmage" = a real snap we can measure (not a penalty/timeout row).
    p["SCRIMMAGE"] = p["KIND"].notna() & ~p["IS_PENALTY"] & ~p["IS_TIMEOUT"]
    p["SUCCESS"] = [
        _successful(d, t, g) if s else None
        for d, t, g, s in zip(p["DN"], p["DIST"], p["GAIN"], p["SCRIMMAGE"])
    ]
    p["EXPLOSIVE"] = p["SCRIMMAGE"] & ~p["RESULT"].str.contains("Sack") & (
        ((p["KIND"] == "Run") & (p["GAIN"] >= 10)) | ((p["KIND"] == "Pass") & (p["GAIN"] >= 15))
    )

    p["FORMATION"] = p["OFF FORM"].str.upper()
    p["FORM_FAMILY"] = p["FORMATION"].map(formation_family)
    p["BACKFIELD"] = p["FORMATION"].map(
        lambda f: None if pd.isna(f) else ("Pistol" if "PISTOL" in f else "Gun/other"))
    p["PLAY"] = p["OFF PLAY"].str.upper()
    p["PLAY_FAMILY"] = p["PLAY"].map(play_family)

    p["HAS_MOTION"] = p["MOTION DIR"].isin(["L", "R"])
    p["DIR_VS_STRENGTH"] = [_relative(d, s, "To strength", "Away from strength")
                            for d, s in zip(p["PLAY DIR"], p["OFF STR"])]
    p["DIR_VS_MOTION"] = [_relative(d, m, "With motion", "Against motion")
                          for d, m in zip(p["PLAY DIR"], p["MOTION DIR"])]
    p["UNIT"] = p["PLAY TYPE"].map(UNIT_NAMES)
    p["KICKING_TEAM"] = None
    for _, g in p.groupby("GAME_NUM"):
        kt = _kicking_team(g)
        p.loc[kt.index, "KICKING_TEAM"] = kt

    field_side = p["HASH"].map({"L": "R", "R": "L"})
    p["DIR_VS_FIELD"] = [_relative(d, f, "To field", "To boundary")
                         for d, f in zip(p["PLAY DIR"], field_side)]
    return p.reset_index(drop=True), games, warnings
