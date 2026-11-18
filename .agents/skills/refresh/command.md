Refresh the local ungraded queue: re-download every submission that is still ungraded on Moodle (overwrite existing local files and re-index).

Usage: `/refresh $ARGUMENTS`

Invoking this command is confirmation to hit Moodle and overwrite matching locals.

This does **not** delete graded locals — use `/clean-graded` for that (often run before `/refresh`).

Only groups on the teacher's parsed schedule are included (other teachers' Moodle sections are skipped). Needs `local/schedule/parsed.json` (`schedule-parse`). Pass `all-groups` to bypass.

## Resolve scope from $ARGUMENTS

| Pattern | Meaning |
|---------|---------|
| empty | All courses from `.env` / settings (schedule groups only). |
| `<group>` | Only labs whose group name contains this substring (still must be on schedule). |
| `all-groups` / `--all-groups` | Also download groups not on the schedule. |
| `dry-run` / `--dry-run` | List destinations without downloading. |

## Run

```bash
.venv/bin/python -m nure_dl refresh [ --group GROUP ] [ --all-groups ] [ --dry-run ]
```

Equivalent to `download --force` for currently ungraded files only.

Report how many files were refreshed and the downloads root. Then optionally `python -m nure_dl submissions` for the updated index.
