# Agent instructions & standards

Standards for any agent working in this repo on Cedarcrest (CHS) football film and scouting.
The user is the CHS FB/TE coach. Scouting reports are for the whole staff and every position group.

## Data

- Root: `F:\CHSFootball\`
  - `CHS playbook\{O,D,ST}\*.pdf`: our playbook (diagrams). Summary and terminology: [docs/chs-scheme.md](docs/chs-scheme.md).
  - `Opponents\<Team>\<game folder>\`: one clip per play (`Wide - Clip NNN.mp4`) plus a Hudl breakdown `.xlsx`.
    The original Hudl `.zip` downloads may sit next to the folders; ignore them.
  - `Opponents\<Team>\_scouting\`: report output plus staff-editable `gameplan.md`, `notes.md` and `tagging.txt`.
- Breakdown row `PLAY #` N = `Clip N`. Check that the row and clip counts match. Some exports are
  numbered 2..N+1 (or 3.., 4..) for clips 1..N; the loader shifts them back and warns you, so spot-check a clip.
- Team names in breakdowns may be initials ("OHS" = Orting High School); the loader matches them.

## Tagging rule (ODK)

- **The ODK field is the side of the ball the opponent being scouted is on.** O = opponent on offense,
  D = opponent on defense, K = kicking game.
- Game folder names usually include at least one team's jersey color (e.g. `Sammamish (black) vs ...`,
  `Foster High (Black)`). Use it to tell the teams apart on film.
- **If the side of the ball or the jersey colors aren't clear, ask the user before building a breakdown or report.**
- Before trusting a game, spot-check one or two "O" clips on film (pull frames with ffmpeg) to confirm
  the scouted team has the ball. If the film and the rule disagree, **stop and ask the user**. Don't
  silently pick one. The film is the tiebreaker the user has confirmed before.
- Record each decision in `_scouting\tagging.txt` (`<folder text> = scouted | opponent | note`) so the
  report shows how every game was read.

## Each week stands alone

- **Start every week fresh.** Treat that week's opponent folder as a new set of film and breakdowns,
  even if a game, opponent or file looks like one from an earlier week.
- Don't carry forward earlier weeks' analysis, reports, game plans, tagging decisions or file
  comparisons unless the user specifically says to. Look at each week's film in isolation.
- What does carry over: this file, the tool, and our playbook (docs/chs-scheme.md).

## Building the weekly report

The full step-by-step is the project skill `.claude/skills/weekly-scouting-report/SKILL.md`
(`/weekly-scouting-report` in Claude Code). Summary:

1. `python -m filmtools report "F:\CHSFootball\Opponents\<Team>"`. Read every warning.
2. Review the data: what each game actually tags (play calls, formations, jerseys), and how taggers'
   vocabularies differ. Say so in the report; don't merge vocabularies by guessing.
3. Write `_scouting\gameplan.md`, with CHS defense, CHS offense and CHS special teams sections:
   - Use our playbook's call names (docs/chs-scheme.md). Use the opponent-specific ST plan if the
     playbook has one; otherwise say which plan is the baseline.
   - Back every recommendation with a number and clip labels (e.g. `FOS-18`). Labels become video links.
   - Separate what the data shows from what film or staff still need to confirm.
4. **Verify every number in `gameplan.md` against the data before handing it over**, then rebuild
   the report and check that the links resolve.
5. When asked for the opponent's playbook: `python -m filmtools.playbook "<team folder>"`. Check that the
   route parsing on the cards makes sense, and flag formations that aren't confirmed on film.
6. Player call-outs ("dogs"/"dudes"): never guess jersey numbers. Use the roster, Hudl jersey tags,
   staff-confirmed `positions.txt`, or numbers clearly readable on film. Otherwise list the play-makers
   by role and clip for the staff to identify.

## Interpretation standards

- Success: 40% of the distance on 1st down, 60% on 2nd, 100% on 3rd/4th. Explosive: run 10+, pass 15+.
- Penalty and timeout rows count as calls but are left out of yardage and success.
- Who kicked is worked out from possession (return TDs, defensive TDs, recovered onsides and
  re-kicks after penalties included). Hudl's kick tags don't say reliably.
- Our offense: Y = FB/TE in a sidecar next to the QB; S and B are receivers. Run concepts: Seattle =
  true sweep, Jacksonville = toss, Chicago = counter, Tennessee = trap, Indy = inside zone,
  Dallas = outside stretch with a cutback read.

## Working norms

- Don't commit or push unless the user asks.
- Re-read this file at the start of each weekly report.
