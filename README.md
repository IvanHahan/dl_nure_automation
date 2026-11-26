# dl_nure_automation

Automates grading workflow for [ХНУРЕ ДН](https://dl.nure.ua) (Moodle): download ungraded lab reports, evaluate them with an AI agent against per-lab guidelines, and submit scores (and comments) back to DL.

## How it works

1. **Auth** — CLI uses your browser `MoodleSession` cookie (no password login).
2. **Schedule** — your I@S teacher schedule defines which groups you own. Downloads and evaluation skip other teachers’ groups.
3. **Download / refresh** — pulls Moodle’s **requiregrading** queue for on-schedule groups (never graded **and** Graded–resubmitted). Reuploads get a new file id and replace the local copy.
4. **Evaluate** — an agent (Cursor/Codex skills) dumps each report, checks it against lab guidelines, applies a lateness cap from the schedule, and posts the Moodle grade. Skip only when `needs_grading` is false (resubmits are kept). Lateness uses the **first** submission date, so a reupload does not worsen the cap.
5. **Cleanup** — after a successful Moodle `--score`, the local file and dump are deleted (index updated). Use `/clean-graded` to purge leftovers that are already graded on DL.

Agent entry points: `/evaluate`, `/refresh`, `/clean-graded` (see `.agents/skills/` and `.cursor/commands/`). Per-submission procedure: `nure-lab-evaluate`.

`/evaluate` with **no args** runs the full pipeline: clean-graded → refresh (schedule groups, new + resubmits) → grade every lab that has `guidelines/<subject>/labs/lab-N/guidelines.md` → purge locals after each Moodle score. Pass `lab N`, a group, or an id to narrow; `ask` only lists without grading.

## Moodle session (required)

Copy the session cookie from the browser into `.env`:

1. Open https://dl.nure.ua and sign in.
2. DevTools → **Application** → **Cookies** → `dl.nure.ua`.
3. Copy the value of **`MoodleSession`**.

```bash
cp .env.example .env
# Set MOODLE_SESSION=... in .env
```

Also set `MOODLE_COURSE_IDS` (comma-separated course ids) and optionally `MOODLE_BASE_URL` / `MOODLE_OUTPUT_DIR`. The session expires; refresh the cookie when downloads or grades start failing with auth errors.

**Do not commit `.env`.** Only `.env.example` is in the repo.

## Lab guidelines (required per lab)

Evaluation does **not** invent a grading scale. For each subject/lab you must add:

```text
guidelines/<subject>/labs/lab-N/guidelines.md
```

Example for ТПКС:

| Lab | Path |
|-----|------|
| ЛР1 | `guidelines/tpks/labs/lab-1/guidelines.md` |
| ЛР2 | `guidelines/tpks/labs/lab-2/guidelines.md` |
| ЛР3 | [grading guidelines](guidelines/tpks/labs/lab-3/guidelines.md) |

`guidelines.md` should define the tasks, how to judge diagram vs code, and the numeric scale (e.g. 1/2/3 correct → 60/70/100). Held-on dates are cached under `labs/lab-N/held/` (gitignored).

Without a guidelines file for that lab, the agent must stop — do not freestyle scores.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # paste MoodleSession + course ids
```

Teacher schedule (for group ownership + lateness):

1. Save I@S «Расписание на преподавателей» HTML into `local/schedule/`.
2. `python -m nure_dl schedule-parse` → `local/schedule/parsed.json`.

## Common commands

```bash
# Ungraded downloads (schedule groups only)
python -m nure_dl download --dry-run
python -m nure_dl download
python -m nure_dl download --group КІУКІ-24-3
python -m nure_dl refresh              # force re-download ungraded
python -m nure_dl clean-graded         # delete locals already graded on Moodle

python -m nure_dl submissions
python -m nure_dl grade-status SUBMISSION_ID
python -m nure_dl held-date SUBMISSION_ID
python -m nure_dl grade-cap SUBMISSION_ID --score 100

# Prepare dump / submit score (+ comment when anything is wrong)
python -m nure_dl grade SUBMISSION_ID
python -m nure_dl grade SUBMISSION_ID -s 70 -c "T2: code≠diagram"
# After -s, local file + dump are purged unless --keep-local
```

Agent batch grading:

```text
/evaluate              # full pipeline (default)
/evaluate lab 2 24-3   # one lab + group
/evaluate 24-3
/evaluate ask          # list only
```

## Layout

```text
src/nure_dl/          # CLI package
guidelines/<subject>/ # per-lab evaluation rules
downloads/            # local cache (gitignored)
local/schedule/       # I@S HTML + parsed.json (gitignored)
.agents/skills/       # Codex + shared skills
.cursor/commands/     # Cursor slash commands (symlinked)
```
