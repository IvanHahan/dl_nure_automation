Evaluate and grade ХНУРЕ DL lab submissions, then write scores (and comments when needed) to Moodle.

Usage: `/evaluate $ARGUMENTS`

This command is the **driver**; `nure-lab-evaluate` is the **SSOT** for per-submission steps (grade-status → held-date → dump → guidelines → score → grade-cap → Moodle). Load and follow that skill for every id you grade.

Invoking `/evaluate` (with or without args) is confirmation to run the resolved pipeline, including Moodle downloads and grades.

## Resolve scope from $ARGUMENTS

Treat tokens case-insensitively. Ukrainian aliases (`лр`, `лабораторна`) count as `lab`.

| Pattern | Meaning |
|---------|---------|
| **empty (default)** | **Full pipeline** — refresh the requiregrading queue for schedule groups, then grade every lab that has guidelines (see below). |
| `sf-…` / `local-…` | That single submission id (no refresh unless the id is missing locally). |
| `lab N` / `лр N` / `лрN` | Refresh, then lab **N** for all on-schedule groups (guidelines required). |
| `lab N <group>` | Refresh that group (optional narrow download), then lab **N** for matching groups. |
| `<group>` alone | Refresh that group, then **all labs with guidelines** for that group. |
| `lab N all` | Same as `lab N`. |
| `tpks …` | Subject override (default **tpks**). |
| `regrade` / `--regrade` | Also process submissions with `needs_grading: false`. |
| `ask` / `--ask` | Only list indexed labs/groups and ask — do **not** download or grade. |

Examples:

- `/evaluate` — full pipeline (default)
- `/evaluate lab 2 24-3`
- `/evaluate лр1 КІУКІ-24-1`
- `/evaluate 24-3`
- `/evaluate ask`

## Default full pipeline (empty args)

Run in order:

1. **Schedule** — ensure `local/schedule/parsed.json` (`schedule-parse` if missing).
2. **Clean** — `python -m nure_dl clean-graded` (drop locals that are fully done on Moodle; keeps resubmits).
3. **Refresh** — `python -m nure_dl refresh` (force re-download Moodle requiregrading for **schedule groups only**: new + Graded–resubmitted).
4. **Labs with guidelines** — discover `guidelines/<subject>/labs/lab-N/guidelines.md`. Only those lab numbers are graded; labs without a file are skipped (`missing guidelines`).
5. **Work list** — from `submissions --json`, keep rows whose group is on the schedule and whose lab number has guidelines. Dedupe docx/pdf (prefer `.docx`).
6. **Grade each id** via `nure-lab-evaluate` (below). Successful `--score` purges the local file + dump.

Print a short plan (labs, group count, submission count) before grading, then proceed without asking.

## Scoped runs (non-empty args)

1. Ensure schedule is parsed.
2. Refresh when the scope is a lab and/or group (same as default, but you may pass `--group` to `refresh` / `download` when a group filter is set). Skip refresh for a single known `sf-` / `local-` id that is already indexed.
3. Build the work list from the index, filtered to the scope, then apply schedule + guidelines filters as above.
4. Grade each remaining id.

## Evaluate each submission

For each id, follow **`nure-lab-evaluate`** end-to-end:

1. `grade-status` — skip only when `needs_grading: false` (unless `regrade`). Resubmits have `needs_grading: true` even if an old grade exists — evaluate them.
2. Schedule / `held-date` — if the group is off-schedule or held-date is missing → **skip** (`skipped not on schedule`); do not ask the user.
3. Dump / prepare via `grade SUBMISSION_ID`.
4. Load `guidelines/<subject>/labs/lab-N/guidelines.md` — skip if missing (`missing guidelines`).
5. Judge tasks → task score → `grade-cap` (first submission date) → Moodle `--score` (+ `-c` when anything incorrect). Successful `--score` auto-purges locals (`local_purged`); do not pass `--keep-local` in normal batches.

Do not stop the whole batch on one failure or one off-schedule group: record the skip/error, continue, report at the end.

Large batches: process sequentially (Moodle + dumps); you may parallelize read-only `grade-status` checks first to shrink the list.

## Final report

```
Scope: subject=… pipeline=full|lab|group|id regrade=yes|no
Refreshed: … | Guidelines labs: 1,2,3
Planned: N | Skipped done: K | Skipped not on schedule: S | Skipped no guidelines: G | Evaluated: M | Failed: F

id | student | group | lab | task_score | final | DL | note
…  | …       | …     | …   | …          | …     | …  | …

Failures:
- id — reason
```

Keep notes short (`skipped done`, `skipped not on schedule`, `missing guidelines`, `missing diagram`, `resubmitted`, …).
