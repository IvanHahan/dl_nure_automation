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
Folders use the Moodle **course shortname** from DL (not the numeric id):

```text
downloads/
  АПОТ:БАК:КІУКІ(и,у):ТПК:о26_27/   ← shortname ( / → _ )
    КІУКІ-23-1/
      Лабораторна робота 1/
        Student Name/
          file.pdf
  АПОТ:БАК:КІУКІ(у):ТПК:о26_27/
    КІУКІ-24-1/
      …
```

```bash
# Preview
python -m nure_dl --dry-run

# Both courses from .env
python -m nure_dl

# One course or group
python -m nure_dl --course-id 32389
python -m nure_dl --group КІУКІ-23-1
```

Requires a teaching/grading role on the assignment (Submissions table access).
