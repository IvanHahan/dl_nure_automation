Evaluate and grade ХНУРЕ DL lab submissions for a chosen scope, then write scores (and comments when needed) to Moodle.

Usage: `/evaluate $ARGUMENTS`

This command is the **driver**; `nure-lab-evaluate` is the **SSOT** for per-submission steps (grade-status → held-date → dump → guidelines → score → grade-cap → Moodle). Load and follow that skill for every id you grade.

## Resolve scope from $ARGUMENTS

Treat tokens case-insensitively. Ukrainian aliases (`лр`, `лабораторна`) count as `lab`.

| Pattern | Meaning |
|---------|---------|
| empty | List indexed labs/groups briefly and ask what to evaluate (do not grade yet). |
| `sf-…` / `local-…` | That single submission id. |
| `lab N` / `лр N` / `лрN` | Lab **N** for **all** groups that have indexed submissions. |
| `lab N <group>` | Lab **N** for groups whose name contains `<group>` (e.g. `24-3`, `КІУКІ-24-3`). |
| `<group>` alone | **All** labs for that group substring. |
| `lab N all` | Same as `lab N` (all groups). |
| `tpks …` | Subject override (default **tpks**). |
| `regrade` / `--regrade` | Also process submissions already graded on Moodle (normally skip). |

Examples:

- `/evaluate lab 2 24-3`
- `/evaluate лр1 КІУКІ-24-1`
- `/evaluate lab 2`
- `/evaluate 24-3`
- `/evaluate local-24-3-2-x-2-24-3-docx`
- `/evaluate lab 1 24-3 regrade`

If both lab and group are missing and it is not a submission id, ask — do not invent a scope.

## Build the work list

1. Ensure the index exists:

```bash
.venv/bin/python -m nure_dl submissions
```

2. Filter to the resolved scope (match `lab_title` for lab number; substring-match `group`). Prefer machine-readable filter:

```bash
.venv/bin/python -m nure_dl submissions --json
```

3. Drop every submission whose **group is not on the teacher schedule** (`local/schedule/parsed.json`). Same rule as `download` / `refresh`. Note them as `skipped not on schedule`. **Never ask the user for a held-on date** for those groups — ignore and move on.

4. If the remaining list is empty: say so. Optionally run download for an on-schedule group, then re-list — do not invent ids.

```bash
.venv/bin/python -m nure_dl download --group GROUP_SUBSTRING
```

5. Deduplicate: one file per student when both `.docx` and `.pdf` exist for the same person/lab — prefer `.docx`, else the newest/largest; note skips in the summary.

6. Print the planned list (id, student, group, lab) and proceed (invoking `/evaluate` is confirmation to grade that scope).

## Evaluate each submission

For each id, follow **`nure-lab-evaluate`** end-to-end:

1. `grade-status` — skip if graded unless `regrade`.
2. Schedule / `held-date` — if the group is off-schedule or held-date is missing → **skip** (`skipped not on schedule`); do not ask the user.
3. Dump / prepare via `grade SUBMISSION_ID`.
4. Load `guidelines/<subject>/labs/lab-N/guidelines.md` — stop if missing.
5. Judge tasks → task score → `grade-cap` → submit Moodle `--score` (+ `-c` when anything incorrect).

Do not stop the whole batch on one failure or one off-schedule group: record the skip/error, continue, report at the end.

Large batches: process sequentially (Moodle + dumps); you may parallelize read-only `grade-status` checks first to shrink the list.

## Final report

```
Scope: subject=… lab=… group=… (or all) regrade=yes|no
Planned: N | Skipped graded: K | Skipped not on schedule: S | Evaluated: M | Failed: F

id | student | group | lab | task_score | final | DL | note
…  | …       | …     | …   | …          | …     | …  | …

Failures:
- id — reason
```

Keep notes short (`skipped graded`, `skipped not on schedule`, `missing guidelines`, `missing diagram`, …).
