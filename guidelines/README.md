# Evaluation guidelines

Grouped by subject. The `nure-lab-evaluate` skill picks the subject folder, then the lab folder.

| Folder | Subject |
|--------|---------|
| `tpks/` | Технології проектування комп'ютерних систем |

Layout per lab: `guidelines/<subject>/labs/lab-N/guidelines.md` plus `held/<group>.json` for the session date (from `local/schedule/`, before evaluation).

## Lateness cap (all subjects)

After the task score from lab guidelines, run `python -m nure_dl grade-cap`:

- within 2 weeks after held-on → max **100**
- 2–6 weeks → max **90**
- later → max **80**

Submit `final_score` = min(task score, max_grade). Always submit a numeric grade after review (use **0** if nothing is correct) so Moodle shows Graded.

## Moodle comments (all subjects)

If anything is incorrect or missing → **must** leave a submission comment (together with the grade).

Skip the comment only when the work is fully correct and there are no complaints.
