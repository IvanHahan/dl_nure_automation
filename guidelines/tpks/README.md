# ТПКС — Технології проектування комп'ютерних систем

Evaluation guidelines for this subject. Each lab is a folder:

```
labs/lab-N/
  guidelines.md     # how to judge + grading scale
  held/<group>.json # local cache only (gitignored) — from held-date
```

| Folder | Lab |
|--------|-----|
| `labs/lab-1/` | Лабораторна робота 1 |
| `labs/lab-2/` | Лабораторна робота 2 — поведінкові/структурні SV-моделі |
| [labs/lab-3/](labs/lab-3/guidelines.md) | Лабораторна робота 3 — автомати Мура та Мілі |

Schedule: put the I@S HTML in `local/schedule/`, then `python -m nure_dl schedule-parse` → `local/schedule/parsed.json`.
Held-on: `python -m nure_dl held-date` (Lab N = N-th `ТПКС Лб` for the group). Reuse `held/*.json` if present.
