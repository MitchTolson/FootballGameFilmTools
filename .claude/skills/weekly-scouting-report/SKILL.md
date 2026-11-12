---
name: weekly-scouting-report
description: Build the weekly CHS football opponent scouting package from Hudl film and breakdowns - tagging checks, scouting report, defensive run/pass likelihood (by down, formation, red zone), game plan, opponent offensive playbook and player call-outs. Use when the user names this week's opponent or points at F:\CHSFootball\Opponents\<Team>.
---

# Weekly scouting report

Builds the scouting package for this week's opponent. It's for the whole Cedarcrest (CHS) staff, so cover
every position group. Read `agent.md` first; its rules (ODK orientation, week isolation, never guessing
jersey numbers) override anything here.

## Inputs (the coach provides)

- `F:\CHSFootball\Opponents\<Team>\<game folder>\`: `Wide - Clip NNN.mp4` per play plus `breakdown.xlsx`,
  exported from Hudl. The folder names usually carry jersey colors, e.g. `OHS (red) vs. Franklin Pierce`.
- Optional: `roster*.txt` in the team folder (MaxPreps copy/paste, one player per line:
  `0 Shiron Seniours RB, DB Sr. 5'8" 180`). A roster PDF printed from MaxPreps is usually an image with
  no text layer. Read it and transcribe it into `roster2026.txt` (skip "null Player" rows), then use the
  roster in the game plan: sizes of their OL / LBs, two-way players, QBs, tall receivers, kicker.
- Optional: a mapping file in the team folder (e.g. `filmmapping.md`) giving each game's jersey color and whose
  side the ODK is from. Use it for `tagging.txt`, but still confirm each game on film.
- Optional: `Stats\` with a MaxPreps roster/season-stats PDF and a links file. The PDFs are usually images: render
  the pages (pymupdf) and read them. MaxPreps' stats page only serves team leaders and the schedule to a fetch
  (game-by-game and totals tabs load in the browser). Put the season summary in `_scouting\notes.md` (shown under
  Key facts) and cite it in the game plan.
- What the coach asked for this week (e.g. "dudes", "coverages", "red zone").

## Steps

1. **Start fresh.** Look only at this week's team folder. Don't open or cite other opponents' `_scouting` folders.

2. **Survey the data.** For each game, check the row count against the clip count, which columns are
   filled, the ODK split, the TEAM column, and the formation/play vocabulary. The loader handles these
   automatically, but report them to the coach:
   - breakdowns numbered k..N+k-1 for clips 1..N, e.g. 2..N+1 or 4..N+3 (renumbered, with a warning; confirm
     on film with a clip whose down/distance or scoreboard you can read)
   - a PLAY # used twice (warned; check which row matches the clip)
   - `S` rows in ODK (blank dead-ball clips; ignored)
   - empty breakdowns (ask the coach to re-export, or tag from film)
   - jersey numbers in `RUSHER/PASSER/RECEIVER` or `OPP ...` columns

3. **Confirm orientation on film.** ODK = the scouted team's side of the ball. Pull frames:
   `python -m filmtools.frames grid "<game folder>" "<scratch dir>" ABC <clip#> <clip#>`
   Pick a big "O" gain and a big "D" gain, and confirm the scouted team's jersey color has the ball on the "O" clip.
   **If the film and the tags disagree, or colors are unclear, ask the coach before going on.**
   Record each game in `_scouting\tagging.txt`:
   `Franklin Pierce = scouted | Orting in red; film check: O = FRA-39`

4. **Build the report:**
   `python -m filmtools report "F:\CHSFootball\Opponents\<Team>"`. Read every warning. The report includes:
   - **Run / pass likelihood** (defensive call sheet): by down, by down & distance, by formation group,
     formation x down, **play type x down** (games with play calls tagged), and red zone (inside the 20 and
     inside the 10), each with counts and a confidence label. Coaches use the formation x down and play type x
     down matrices most; always check they're populated.
     Formation groups are in `filmtools/tendencies.py` `FORMATION_GROUPS`. Add keywords when a new
     tagger's names land in the wrong group, then check the "Formation groups:" note under the table.
   - Offense/defense/special teams tendencies, play lists, clip links.
   - `python -m filmtools.tendencies "<team folder>"` prints the headline tendencies and writes `tendencies.csv`.

5. **Opponent offensive playbook (formations + scout cards). Always include it.** It's embedded in the report
   automatically (section "Offensive playbook"). Also run `python -m filmtools.playbook "<team folder>"`
   for the standalone `<Team>\Offensive Playbook\` page the scout-team coach can print. Every report has
   **all three phases (offense, defense, special teams), the formations and the playbook**; the coach expects
   the full package every week. Open a few cards and check:
   - every formation they used has a template in `filmtools/playbook.py` `FORMATIONS` (otherwise
     the card says "drawn as Doubles Open"; add the alignment)
   - the route parsing matches the tag (e.g. "Deep Outs Seams" = deep outs outside, seams inside)
   - formations that have no template or aren't confirmed on film are flagged
   Add alignments to `Offensive Playbook\formations.txt`. End a line with `| note` when it's drawn from the
   name rather than measured; the card shows the note. Keep guesses about one opponent's labels in that
   team's file, not in `playbook.py`.

6. **Coverages/fronts (Hudl doesn't tag them), if asked:** review the defensive snaps with
   `python -m filmtools.frames sheet ...` and record them in `_scouting\film_tags.csv`
   (`game,play,front,shell,coverage,pressure,players,conf,note`). Mark unreadable clips `?` with `conf=low`.

7. **Player call-outs ("dogs" / "dudes"):** use the roster, Hudl jersey tags, staff-confirmed
   `_scouting\positions.txt` (`9 = Will / Mike (rotates)`), or numbers clearly readable on film.
   **Never guess a number.** If you can't read it, name the player by role and list the clips for the staff.

8. **Write `_scouting\gameplan.md`.** Sections:
   - What the data covers
   - (Dudes, if asked)
   - CHS defense vs <Team> offense: lead with the formation and down tells, then red zone, and
     include a Call: line for each
   - CHS offense vs <Team> defense
   - CHS special teams
   Use our call names from `docs/chs-scheme.md` (Raven, Bear, Cover 3 = Green, Seattle = sweep, ...).
   Cite clip labels (`FRA-39`); they become video links. Give the counts behind every percentage.

9. **Verify every number in `gameplan.md`** with a short pandas check against `load_team(...)`,
   fix any that are off, then rebuild the report and check that every clip link resolves.

10. **Hand over.** Name the audience in one line, list where the files are, and give the top tendencies.
    Cover what's weak or unconfirmed and what the staff should check on film. Don't commit unless asked.

## Outputs (in the team folder)

| File | What |
|---|---|
| `_scouting\<Team> Scouting Report.html` | the report: open in a browser, and clip labels play the video |
| `_scouting\gameplan.md` | staff-editable game plan, shown at the top of the report |
| `_scouting\<Team> plays.csv`, `tendencies.csv` | data for Excel |
| `_scouting\tagging.txt`, `positions.txt`, `film_tags.csv`, `notes.md` | staff inputs (all optional) |
| `Offensive Playbook\<Team> Offensive Playbook.html` | scout cards |
