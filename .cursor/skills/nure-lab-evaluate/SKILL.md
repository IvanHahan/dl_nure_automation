---
name: nure-lab-evaluate
description: >-
  Evaluates ХНУРЕ lab submissions by id using subject/lab guidelines, then
  grades them on dl.nure.ua (Moodle score + submission comment). Use when the
  user asks to evaluate, grade, mark, or check a lab / ЛР / ТПКС submission
  under downloads/, or to apply guidelines from guidelines/<subject>/labs/.
---

# NURE lab evaluate

General evaluator for any subject/lab. Rules live under `guidelines/<subject>/labs/` —
load the matching file before scoring. Always finish by writing the grade to DL
(`--score` + comment). A dump alone is not a grade.

## 0. Already graded? (before anything else)

**For every submission, check Moodle first.** If already graded, **skip** — do not dump, re-score, or overwrite unless the user explicitly asks to regrade.

```bash
.venv/bin/python -m nure_dl grade-status SUBMISSION_ID
# graded: true  → skip this submission
# graded: false → continue
```

When evaluating a group, run `grade-status` per id and only continue for `graded: false`.

## 1. Schedule + lab held-on date

**Do this before dump/evaluate/grade** (only for ungraded submissions).

1. Ensure the teacher schedule is parsed (strict I@S HTML → JSON):

```bash
.venv/bin/python -m nure_dl schedule-parse
# writes local/schedule/parsed.json (gitignored under local/)
```

   Skip if `local/schedule/parsed.json` already exists unless the HTML was replaced.

2. Resolve when **this** lab was held for the student's group; cache under the lab folder:

```bash
.venv/bin/python -m nure_dl held-date SUBMISSION_ID
# or: .venv/bin/python -m nure_dl held-date --subject tpks --lab 1 --group КІУКІ-24-3
```

- Parsed cells: `{SUBJECT} {Лб|Лк|Зал} {MODE} {GROUPS}` e.g. `ТПКС Лб DL КІУКІ-24-3`.
- Lab **N** = the **N-th** chronological `Лб` session for that group in `parsed.json`.
- Cache (gitignored): `guidelines/<subject>/labs/lab-N/held/<group>.json` — **reuse** if present; do not commit.
- If missing from the schedule → **stop**; do not invent a date.

## 2. Resolve submission + dump

```bash
.venv/bin/python -m nure_dl grade SUBMISSION_ID
```

Note course/subject, `lab_title`, student, dump path (`text.txt`, `images/`). Code may be in Word tables (included in dump).

## 3. Pick subject, then lab guidelines

Subjects (folder slug → full name):

| Slug | Subject |
|------|---------|
| `tpks` | Технології проектування комп'ютерних систем |

Infer the subject from the course/lab context (ТПКС / ТПК / «Технології проектування…»). If unclear, ask. Do not use another subject's scale.

Then map `lab_title` under that subject:

| Lab title contains | Guidelines file |
|--------------------|-----------------|
| `Лабораторна робота 1` / `ЛР №1` / `ЛР1` | `guidelines/<subject>/labs/lab-1/guidelines.md` |
| `Лабораторна робота 2` / `ЛР №2` / `ЛР2` | `guidelines/<subject>/labs/lab-2/guidelines.md` |
| `Лабораторна робота 3` / `ЛР №3` / `ЛР3` | `guidelines/<subject>/labs/lab-3/guidelines.md` |

Example for ТПКС Lab 1: `guidelines/tpks/labs/lab-1/guidelines.md`.

`Read` that file **before** judging tasks. If no file exists, stop and say which guideline is missing — do not invent a grading scale.

Shared defaults (unless the lab file overrides them):

- Identify tasks from the document yourself (headings differ by student).
- If the **diagram is missing** for a task → that task is **INCORRECT**.
- If **code is missing** for a task → **INCORRECT**.
- When both exist: verify **code against the scheme/FSM diagram only**.
- Match → **CORRECT**. Mismatch → **INCORRECT** (`code≠diagram: …`).
- **Ignore** waveforms / timing diagrams / console dumps / playground links as sole proof.

## 4. Evaluate

1. `Read` dump `text.txt` and scheme/FSM images (skip waveforms).
2. Per task: apply the loaded guidelines → CORRECT / INCORRECT + one-line reason.
3. Compute the **task score** from the lab file’s grading section (do not freestyle).

## 4b. Lateness cap (before submitting to DL)

Clamp the task score with the max allowed by how late the work was submitted:

```bash
.venv/bin/python -m nure_dl grade-cap SUBMISSION_ID --score TASK_SCORE
# or dry dates: .venv/bin/python -m nure_dl grade-cap --held YYYY-MM-DD --submitted YYYY-MM-DD
```

Rules (calendar days after held-on):

| Delay | max_grade |
|-------|-----------|
| ≤ 2 weeks (≤ 14 days) | 100 |
| 2–6 weeks (15–42 days) | 90 |
| later (> 42 days) | 80 |

Use `final_score` from the command (`min(task_score, max_grade)`). Do not submit a higher Moodle score.

## 5. Grade on DL

Never overwrite an existing Moodle grade unless the user asked to regrade.

### Comments (mandatory on problems)

**If anything is INCORRECT or missing** (diagram, code, mismatch, …) → you **must** post a Moodle submission comment (`-c`), even when no numeric grade is submitted yet (e.g. waiting for a score below the lab minimum).

Comment content: short per-task notes (Ukrainian is fine). Say if the grade is deferred.

**No comment** only when every task is CORRECT and there are no complaints.

### Score

**Always** submit a numeric Moodle grade (`-s`) after review so the work shows as Graded on DL.

- Normal path: `final_score` from guidelines + lateness cap.
- **0 tasks correct** (or otherwise below the lab minimum): submit **0** unless the instructor gives another value. Still leave the mandatory comment.
- Do not leave a submission “reviewed” with only a comment and no grade.

```bash
# All correct — score only, no comment
.venv/bin/python -m nure_dl grade SUBMISSION_ID --save /tmp/result.json -s SCORE

# Issues — score + comment (required)
.venv/bin/python -m nure_dl grade SUBMISSION_ID \
  --save /tmp/result.json \
  -s SCORE \
  -c "COMMENT"
```

`result.json`:

```json
{
  "summary": "…",
  "score": 70,
  "tasks": [
    {"task": 1, "verdict": "CORRECT", "reason": "…"},
    {"task": 2, "verdict": "INCORRECT", "reason": "missing code"}
  ]
}
```

Confirm CLI prints `moodle_grade: …` (and `moodle_comment_id` only if you commented). Re-check on failure; do not claim graded without `--score` success.

## Report format

```
Student / file: …
submission_id: …
subject: tpks
held_on: YYYY-MM-DD (from guidelines/…/held/….json)
guidelines: guidelines/tpks/labs/lab-N/guidelines.md
Task 1: CORRECT | INCORRECT — <reason>
Task 2: …
Task score: N (from guidelines)
Lateness: held_on=… submitted_on=… days_after=… max_grade=…
Score: final (clamped)
DL: grade=… [comment_id=… only if a comment was posted]
```

Reasons: `missing diagram` · `missing code` · `code≠diagram: <what>` · lab-specific notes from guidelines.
