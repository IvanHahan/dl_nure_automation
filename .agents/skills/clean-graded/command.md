Delete local copies of submissions that are already graded on Moodle (files, dumps, index/grades entries).

Usage: `/clean-graded $ARGUMENTS`

Invoking this command is confirmation to delete matching graded locals.

## Resolve scope from $ARGUMENTS

| Pattern | Meaning |
|---------|---------|
| empty | All indexed submissions under `downloads/`. |
| `<group>` | Only groups whose name contains this substring (e.g. `24-3`). |
| `lab N` / `лр N` | Only lab **N**. |
| `lab N <group>` | Lab **N** for that group substring. |
| `dry-run` / `--dry-run` | List what would be removed; do not delete. |

## Run

```bash
.venv/bin/python -m nure_dl clean-graded [ --group GROUP ] [ --lab N ] [ --dry-run ]
```

Report `checked` / `graded` / `removed` / `kept` / `errors` and the removed ids. Do not invent deletions outside this CLI.
