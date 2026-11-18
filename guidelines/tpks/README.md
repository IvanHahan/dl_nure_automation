# ТПКС — Технології проектування комп'ютерних систем

Evaluation guidelines for this subject. Each lab is a folder:

```
labs/lab-N/
  guidelines.md     # how to judge + grading scale
  held/<group>.json # when that group's N-th ТПКС lab session was held
```

| Folder | Lab |
|--------|-----|
| `labs/lab-1/` | Лабораторна робота 1 |
| `labs/lab-2/` | Лабораторна робота 2 (add when ready) |
| `labs/lab-3/` | Лабораторна робота 3 (add when ready) |

Schedule: put the I@S HTML in `local/schedule/`, then `python -m nure_dl schedule-parse` → `local/schedule/parsed.json`.
Held-on: `python -m nure_dl held-date` (Lab N = N-th `ТПКС Лб` for the group). Reuse `held/*.json` if present.
