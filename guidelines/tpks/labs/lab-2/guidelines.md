# Lab 2 — evaluation guidelines

Subject: **Технології проектування комп'ютерних систем** (ТПКС).

Лабораторна робота 2: **Розробка поведінкових та структурних SV-моделей**.

## Tasks

Identify from the student report (wording/variant numbers vary):

1. **Counter** — behavioral SystemVerilog model of the variant’s counter (+ testbench).
2. **Register** — behavioral model of the variant’s register / shift register (+ testbench).
3. **Generate** — structural model built with the `generate` operator (+ testbench), per the variant figure.

There is a **dedicated scheme/diagram for each task** (three circuit diagrams in the assignment/variant). Do not use waveforms as those diagrams.

## Correctness (same idea as Lab 1)

Per task:

1. Find the **scheme diagram for that circuit** (counter / register / generate structure) — not a waveform or `$monitor` dump.
2. Read from the diagram **how it must work** (bit width, control signals, modes, reset/set/load/shift polarity, connectivity of generated instances, etc.).
3. Find the **code snippet** that implements that circuit.
4. If the diagram is missing → **INCORRECT** (`missing diagram`).
5. If the code is missing → **INCORRECT** (`missing code`).
6. If both present: implementation must match the diagram → **CORRECT**, else **INCORRECT** (`code≠diagram: …`).

Ignore waveforms, kernel dumps, and EDA Playground links as proof.

## Grading

Same scale as Lab 1:

min grade 60, max 100

- if only 1 is done correctly - 60 grade
- 2 - 70
- 3 - 100

Count only tasks marked **CORRECT**. If zero tasks are correct, submit **0** on DL (work reviewed) unless the instructor specifies another value.

After the task score, clamp with lateness via `python -m nure_dl grade-cap` (≤2 weeks → max 100; 2–6 weeks → max 90; later → max 80). Submit `final_score`.

## Moodle comment

If anything is INCORRECT or missing → **must** leave a Moodle submission comment (with the grade).

Do not leave a comment only when everything is correct and there are no complaints.
