# NURE DL helpers

Personal scripts for [ХНУРЕ ДН](https://dl.nure.ua) (Moodle), using your browser `MoodleSession`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Paste MoodleSession from DevTools → Application → Cookies → dl.nure.ua
```

## Download ungraded lab submissions

Courses come from `MOODLE_COURSE_IDS` (default both streams: `32388,32389`).
Folders use the Moodle **course shortname** from DL (not the numeric id).

```bash
python -m nure_dl download --dry-run
python -m nure_dl download
python -m nure_dl download --course-id 32389
python -m nure_dl download --group КІУКІ-23-1
```

Each download is registered in `downloads/submissions.json` with a stable id
(`sf-<moodle-file-id>` when available). Later grading uses that id — no DL search:

```bash
python -m nure_dl submissions
python -m nure_dl submissions sf-3032631
```

## Grade any lab (by submission id)

Lab-agnostic — resolves the cached file and dumps it for evaluation (no Lab-1-specific logic):

```bash
python -m nure_dl grade local-25-1-1-x-25-1-1-docx
# Submit Moodle gradebook score (+ optional submission comment)
python -m nure_dl grade local-25-1-1-x-25-1-1-docx -s 70 -c "T1/T3 OK; T2 missing dataflow"
python -m nure_dl grade local-25-1-1-x-25-1-1-docx --score 70 --comment-file notes.txt
```

Agent evaluation: skill `.cursor/skills/nure-lab-evaluate/` + rules in `guidelines/<subject>/labs/lab-N/`.
Before evaluating: `grade-status` (skip if already graded) → `schedule-parse` → `held-date` → evaluate → `grade-cap` (100/90/80) → `--score`.
`--score` writes the numeric grade on DL; `--comment` only when something is wrong (skip if all tasks are correct).

## Dump a report for reading

```bash
python -m nure_dl dump path/to/report.docx -o /tmp/report-dump
```
