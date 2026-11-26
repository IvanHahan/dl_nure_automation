---
name: evaluate
description: >-
  Full ХНУРЕ DL grading pipeline by default: refresh requiregrading (new +
  resubmits) for schedule groups, grade every lab that has guidelines, purge
  locals after Moodle score. Also supports scoped /evaluate lab N, group, or
  submission id. Use when asked to run /evaluate or to grade/evaluate labs.
disable-model-invocation: true
---

Follow the [command instructions](command.md).

Treat `$ARGUMENTS` in those instructions as the text supplied after this skill name, or empty if no arguments were supplied.

Per-submission procedure (grade-status, held-date, dump, guidelines, Moodle grade) lives in the `nure-lab-evaluate` skill — load and follow it for each id.
