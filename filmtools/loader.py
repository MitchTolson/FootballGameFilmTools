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
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from .playmap import play_family, formation_family

CLIP_RE = re.compile(r"clip\s*(\d+)", re.IGNORECASE)
DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4}|\d{2})\b")


@dataclass
class GameInfo:
    folder: Path
    date: pd.Timestamp | None
    opponent: str          # who the scouted team played in this game
    breakdown: Path
    clips: dict[int, Path]
    perspective: str = ""  # how ODK was oriented when loading


def _parse_game_folder(folder: Path, team: str) -> tuple[pd.Timestamp | None, str]:
    name = folder.name
    m = DATE_RE.search(name)
    date = None
    if m:
        year = int(m.group(3))
        date = pd.Timestamp(year + 2000 if year < 100 else year, int(m.group(1)), int(m.group(2)))
    core = DATE_RE.sub("", name)
    core = re.sub(r"\(\d+\)", "", core)                 # Hudl id
    sides = [re.sub(r"\(.*?\)|[()]", "", s).replace("_", " ").strip()
             for s in re.split(r"\s+vs\.?\s+", core, flags=re.IGNORECASE)]
    # The opponent is the side least like the scouted team's name (tolerates typos like "Sammaimsh").
    opponent = min(sides, key=lambda s: _name_similarity(s, team)) if len(sides) > 1 else "?"
    return date, opponent


def _name_similarity(a: str, team: str) -> float:
    words = re.findall(r"[a-z]+", a.lower())
    target = re.sub(r"[^a-z]", "", team.lower())
    # school initials: "OHS" = Orting High School, "CSHS" = Chief Sealth High School
    caps = re.findall(r"[A-Z][a-z]*", team) or [team]
    initials = {"".join(w[0] for w in caps).lower() + "hs", target[0] + "hs"}
    if any(w in initials for w in words):
        return 1.0
    # compare single words and adjacent word pairs, so "Chief Sealth" matches folder "ChiefSealth"
    cands = words + ["".join(words[i:i + 2]) for i in range(len(words) - 1)]
    return max((SequenceMatcher(None, w, target).ratio() for w in cands), default=0.0)


def _tagged_from_scouted_side(df: pd.DataFrame, team: str) -> bool | None:
    """Is this breakdown's ODK from the scouted team's point of view?

    Hudl fills TEAM on every row (the team that owns the breakdown), or only on the rows where a
    given team has the ball. Used only as a cross-check; tagging.txt decides.
    Returns None when TEAM is empty and the perspective can't be checked.
    """
    def named(rows):
        names = rows["TEAM"].dropna().astype(str)
        return names.mode().iloc[0] if len(names) else None

    o_name, d_name = named(df[df["ODK"] == "O"]), named(df[df["ODK"] == "D"])
    if o_name and d_name:            # owner-style: same school on every row
        return _name_similarity(named(df), team) >= 0.8
    if o_name:                       # names the team with the ball on O rows
        return _name_similarity(o_name, team) >= 0.8
    if d_name:                       # names the team with the ball on D rows = the other school
        return _name_similarity(d_name, team) < 0.8
    return None


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
              "2 Pt.": "2-pt try", "2 Pt. Defend": "2-pt try", "FG": "Field goal", "FG Block": "Field goal",
              "Fake FG": "Fake FG"}


def _kicking_team(game: pd.DataFrame) -> pd.Series:
    """Who kicked on each K row: 'scouted' or 'opponent'.

    Hudl's kick tags don't reliably say which team kicked (and "KO Rec" / "Punt Rec" flip meaning
    with the tagger's perspective), so track who owns the ball after each play: the offense, unless
    the defense scored ("Def TD"); after a kick, the receiving team, unless the kick was recovered by
    the kicker; a return TD means the receiving team scored and kicks next. Whoever owns the ball
    when a kick comes up is the kicking team. For a kick that opens a half, the receiving team gets
    the next snap unless the kick was recovered.
    """
    other = {"scouted": "opponent", "opponent": "scouted"}
    rows = game.sort_values("PLAY #")
    scrim = rows[rows["ODK"].isin(["O", "D"])]
    out, owner, half = {}, None, None
    for idx, r in rows.iterrows():
        h = int(r["QTR"] > 2) if pd.notna(r["QTR"]) else half
        if h != half:
            owner, half = None, h
        res = str(r["RESULT"])
        if r["ODK"] in ("O", "D"):
            offense = "scouted" if r["ODK"] == "O" else "opponent"
            owner = other[offense] if "Def TD" in res else offense
            continue
        if r["ODK"] != "K":
            continue
        kicker = owner
        if kicker is None:  # opening kick of a half: infer from the next snap
            nxt = scrim[scrim["PLAY #"] > r["PLAY #"]]
            if len(nxt):
                next_team = "scouted" if nxt.iloc[0]["ODK"] == "O" else "opponent"
                kicker = next_team if "Recovered" in res else other[next_team]
        out[idx] = kicker
        if kicker is None:
            continue
        unit = UNIT_NAMES.get(r["PLAY TYPE"])
        if unit in ("Kickoff", "Onside kick", "Punt"):
            receiver = other[kicker]
            # recovered onside or a penalty (re-kick): kicker keeps it; a return TD: receiver scored and kicks next
            owner = kicker if ("Recovered" in res or "Penalty" in res) else receiver
        else:
            owner = kicker                                       # PAT / FG / fake: kicker keeps it
    return pd.Series(out, dtype="object")


def read_tagging_overrides(team_dir: Path) -> list[tuple[str, str, str]]:
    """Staff overrides in <team>/_scouting/tagging.txt, one per line:

        Centralia = scouted      # O rows are <team>'s offense
        Foster = opponent        # O rows are the other team's offense
        Foster = opponent | verified on film: black team scores on FOS-18

    Text before '=' is matched against the game folder name (case-insensitive). Anything after
    '|' is kept as a note for the report.
    """
    path = team_dir / "_scouting" / "tagging.txt"
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" not in line:
                continue
            key, rest = (s.strip() for s in line.split("=", 1))
            value, _, note = (s.strip() for s in rest.partition("|"))
            if value.lower() in ("scouted", "opponent") and key:
                out.append((key.lower(), value.lower(), note))
    return out


FILM_COLS = ["FILM_FRONT", "FILM_SHELL", "FILM_COVERAGE", "FILM_PRESSURE", "FILM_PLAYERS", "FILM_CONF", "FILM_NOTE"]


def read_film_tags(team_dir: Path, games: list[GameInfo]) -> pd.DataFrame:
    """Film-reviewed tags in <team>/_scouting/film_tags.csv.

    Columns: game (text matching part of the game folder name), play (PLAY #), then any of
    front, shell, coverage, pressure, players, conf, note. Returns rows keyed by GAME_NUM / PLAY #.
    """
    path = team_dir / "_scouting" / "film_tags.csv"
    if not path.exists():
        return pd.DataFrame(columns=["GAME_NUM", "PLAY #"] + FILM_COLS)
    import io
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
    ft = pd.read_csv(io.StringIO("\n".join(lines)), dtype=str).fillna("")   # '#' inside cells = jersey numbers
    ft.columns = [c.strip().lower() for c in ft.columns]
    rows = []
    for _, r in ft.iterrows():
        key = r.get("game", "").strip().lower()
        gnum = next((i for i, g in enumerate(games, 1) if key and key in g.folder.name.lower()), None)
        if gnum is None or not str(r.get("play", "")).strip().isdigit():
            continue
        rows.append({"GAME_NUM": gnum, "PLAY #": int(r["play"]),
                     **{c: (r.get(c[5:].lower(), "").strip() or None) for c in FILM_COLS}})
    return pd.DataFrame(rows, columns=["GAME_NUM", "PLAY #"] + FILM_COLS)


def read_roster(team_dir: Path) -> pd.DataFrame:
    """Roster from <team>/roster*.txt: lines like '24 Dameon Ellis LB, RB Sr. 5'11" 240'."""
    files = sorted(team_dir.glob("[Rr]oster*.txt"))
    rows = []
    pat = re.compile(r"^(\d{1,2})\s+(.+?)\s+((?:[A-Z]{1,2}(?:,\s*)?)+)\s+(Fr|So|Jr|Sr)\.?\s*"
                     r"(\d'\s*\d{1,2}\")?\s*(\d{2,3})?\s*$")
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = pat.match(line.strip())
            if m:
                rows.append({"NO": int(m.group(1)), "NAME": m.group(2).strip(), "POS": m.group(3).strip(),
                             "GR": m.group(4), "HT": (m.group(5) or "").replace(" ", ""),
                             "WT": int(m.group(6)) if m.group(6) else None})
    df = pd.DataFrame(rows, columns=["NO", "NAME", "POS", "GR", "HT", "WT"]).drop_duplicates("NO")
    # Staff-confirmed roles: _scouting/positions.txt lines like "9 = Will / Mike"
    staff = {}
    pos_file = team_dir / "_scouting" / "positions.txt"
    if pos_file.exists():
        for line in pos_file.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            m = re.match(r"^(\d{1,2})\s*=\s*(.+)$", line)
            if m:
                staff[int(m.group(1))] = m.group(2).strip()
    df.attrs["staff"] = staff
    return df


def load_team(team_dir: str | Path) -> tuple[pd.DataFrame, list[GameInfo], list[str]]:
    """Return (plays, games, warnings)."""
    team_dir = Path(team_dir)
    games = find_games(team_dir)
    overrides = read_tagging_overrides(team_dir)
    warnings: list[str] = []
    frames = []
    for gi, g in enumerate(games, 1):
        df = pd.read_excel(g.breakdown)
        if len(df) != len(g.clips):
            warnings.append(f"{g.folder.name}: {len(df)} breakdown rows vs {len(g.clips)} clips")
        # Standard (agent.md): ODK is the side of the ball the scouted team is on. Only a
        # _scouting/tagging.txt entry flips a game; the TEAM column is just a cross-check.
        team_hint = _tagged_from_scouted_side(df, team_dir.name)
        override = next((o for o in overrides if o[0] in g.folder.name.lower()), None)
        ours = (override[1] == "scouted") if override else True
        if team_hint is False and ours:
            warnings.append(f"{g.folder.name}: TEAM column names another school - check on film that "
                            f"'O' rows are {team_dir.name} on offense, then record it in _scouting/tagging.txt")
        if not override:
            warnings.append(f"{g.folder.name}: not yet confirmed in _scouting/tagging.txt")
        if not ours:
            df["ODK"] = df["ODK"].map({"O": "D", "D": "O"}).fillna(df["ODK"])
        g.perspective = (f"{team_dir.name}'s side" if ours else "other team's side (flipped)")
        g.perspective += (" - per tagging.txt" + (f" ({override[2]})" if override[2] else "")) if override \
            else " - default, not confirmed"
        df["GAME_NUM"] = gi
        df["GAME"] = g.opponent
        df["GAME_DATE"] = g.date
        # Some exports number rows k..N+k-1 for clips 1..N (e.g. 2..N+1 or 4..N+3). Renumber so
        # PLAY # = clip number again, and say so.
        nums = sorted(int(n) for n in df["PLAY #"].dropna())
        shift = nums[0] - 1 if nums else 0
        if shift > 0 and len(nums) == len(g.clips) and nums == list(range(nums[0], nums[0] + len(nums))):
            df["PLAY #"] = df["PLAY #"] - shift
            g.perspective += f" - PLAY # shifted by {shift} to match clips"
            warnings.append(f"{g.folder.name}: breakdown numbered {nums[0]}..{nums[-1]} for clips 1..{len(nums)}; "
                            f"renumbered PLAY # down by {shift} - spot-check a clip")
        dupes = sorted({int(n) for n in df.loc[df["PLAY #"].duplicated(), "PLAY #"].dropna()})
        if dupes:
            warnings.append(f"{g.folder.name}: PLAY # used twice: {dupes} - check which row matches the clip")
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
    blank_kick = (p["ODK"] == "K") & p["PLAY TYPE"].isna() & p["RESULT"].isna()
    p = p[~blank_kick].copy()   # empty dead-ball clips tagged K

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

    # Jersey numbers of the offense's ball carrier / passer / target. Depending on who tagged the
    # game they sit in RUSHER_Jersey etc. or OPP RUSHER etc.; either way they describe the offense.
    for role, own, opp in (("RUSHER_NO", "RUSHER_Jersey", "OPP RUSHER"), ("PASSER_NO", "PASSER_Jersey", "OPP PASSER"),
                           ("RECEIVER_NO", "RECEIVER_Jersey", "OPP RECEIVER")):
        a = pd.to_numeric(p.get(own), errors="coerce") if own in p else pd.Series(index=p.index, dtype=float)
        b = pd.to_numeric(p.get(opp), errors="coerce") if opp in p else pd.Series(index=p.index, dtype=float)
        p[role] = a.fillna(b).astype("Int64")

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

    ft = read_film_tags(team_dir, games)
    p = p.merge(ft, on=["GAME_NUM", "PLAY #"], how="left")
    if len(ft):
        unmatched = len(ft) - int(p[FILM_COLS].notna().any(axis=1).sum())
        if unmatched > 0:
            warnings.append(f"film_tags.csv: {unmatched} rows didn't match a play")

    field_side = p["HASH"].map({"L": "R", "R": "L"})
    p["DIR_VS_FIELD"] = [_relative(d, f, "To field", "To boundary")
                         for d, f in zip(p["PLAY DIR"], field_side)]
    return p.reset_index(drop=True), games, warnings
