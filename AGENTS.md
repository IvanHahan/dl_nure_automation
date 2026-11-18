# AGENTS.md

Use the methodology skill for task lifecycle and PR handoff.

## Stack

Python 3.11+, setuptools, HTTPX, Beautiful Soup, and Loguru.

## Commands

- Create the environment with `python3 -m venv .venv`.
- Install the project with `.venv/bin/python -m pip install -e .`.
- Run the CLI with `.venv/bin/python -m nure_dl`.

## Repo layout

- `src/nure_dl/` contains the CLI and Moodle workflows.
- `guidelines/` contains grading criteria.
- `downloads/` and `local/` hold local student submissions and schedule data.

## Jira

Not used. Track tasks in `docs/tracker.md`.

## Branching

- Integration branch: `main`
- Release branch: `main`
