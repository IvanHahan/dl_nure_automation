# Lab 1 — evaluation guidelines

Subject: **Технології проектування комп'ютерних систем** (ТПКС).

Лабораторна робота 1: SystemVerilog models of digital devices (gate-level, dataflow, mixed / FSM).

## Tasks (typical)

Identify from the student report (wording varies):

1. **Gate-level** model (+ testbench) for the combinational scheme (variant figure).
2. **Dataflow** model of the same scheme; TB compares dataflow vs gate-level (SEED rules as in the assignment text).
3. **Mixed** model for the sequential / FSM scheme (variant figure) + TB.

## Correctness

- Per task: scheme/FSM diagram **and** implementation code must both be present.
- Missing diagram for that task → **INCORRECT**.
- Missing code for that task → **INCORRECT**.
- If both present: code must match the diagram (gate types/connectivity or FSM next-state / FF wiring).
- Ignore waveforms, kernel dumps, and EDA Playground links as proof.

## Grading

min grade 60, max 100

- if only 1 is done correctly - 60 grade
- 2 - 70
- 3 - 100

Count only tasks marked **CORRECT**. If zero tasks are correct, do not invent a score below the lab minimum without an explicit instructor decision — ask before submitting to DL.
