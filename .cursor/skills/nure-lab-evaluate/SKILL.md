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

## 1. Resolve submission + dump

```bash
.venv/bin/python -m nure_dl grade SUBMISSION_ID
```

Note course/subject, `lab_title`, student, dump path (`text.txt`, `images/`). Code may be in Word tables (included in dump).

## 2. Pick subject, then lab guidelines

Subjects (folder slug → full name):

| Slug | Subject |
|------|---------|
| `tpks` | Технології проектування комп'ютерних систем |

Infer the subject from the course/lab context (ТПКС / ТПК / «Технології проектування…»). If unclear, ask. Do not use another subject's scale.

Then map `lab_title` under that subject:

| Lab title contains | Guidelines file |
|--------------------|-----------------|
| `Лабораторна робота 1` / `ЛР №1` / `ЛР1` | `guidelines/<subject>/labs/lab-1.md` |
| `Лабораторна робота 2` / `ЛР №2` / `ЛР2` | `guidelines/<subject>/labs/lab-2.md` |
| `Лабораторна робота 3` / `ЛР №3` / `ЛР3` | `guidelines/<subject>/labs/lab-3.md` |

Example for ТПКС Lab 1: `guidelines/tpks/labs/lab-1.md`.

`Read` that file **before** judging tasks. If no file exists, stop and say which guideline is missing — do not invent a grading scale.

Shared defaults (unless the lab file overrides them):

- Identify tasks from the document yourself (headings differ by student).
- If the **diagram is missing** for a task → that task is **INCORRECT**.
- If **code is missing** for a task → **INCORRECT**.
- When both exist: verify **code against the scheme/FSM diagram only**.
- Match → **CORRECT**. Mismatch → **INCORRECT** (`code≠diagram: …`).
- **Ignore** waveforms / timing diagrams / console dumps / playground links as sole proof.

## 3. Evaluate

1. `Read` dump `text.txt` and scheme/FSM images (skip waveforms).
2. Per task: apply the loaded guidelines → CORRECT / INCORRECT + one-line reason.
3. Compute **score** from the lab file’s grading section (do not freestyle).

## 4. Grade on DL

Always submit the numeric grade. Comment only when there is something wrong.

**No comment** if every task is CORRECT and there are no complaints (full marks, clean work).

**Post a comment** (`-c`) when any task is INCORRECT or you have a concrete complaint — include score and short per-task notes (Ukrainian is fine).

```bash
# All correct — score only
.venv/bin/python -m nure_dl grade SUBMISSION_ID --save /tmp/result.json -s SCORE

# Issues — score + comment
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
guidelines: guidelines/tpks/labs/lab-N.md
Task 1: CORRECT | INCORRECT — <reason>
Task 2: …
Score: N (from guidelines)
DL: grade=… [comment_id=… only if a comment was posted]
```

Reasons: `missing diagram` · `missing code` · `code≠diagram: <what>` · lab-specific notes from guidelines.
