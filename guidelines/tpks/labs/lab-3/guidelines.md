# Lab 3 — evaluation guidelines

Subject: **Технології проектування комп'ютерних систем** (ТПКС).

Лабораторна робота 3: **Розробка автоматів Мура та Мілі** (Moore and Mealy machines).

## Task 1 — finite-state machine

The submission must include a state diagram and two implementations of the machine shown in the diagram, one in Verilog and one in SystemVerilog.

Mark Task 1 **CORRECT** only if all three artifacts are present and both implementations match the diagram. Check the initial state, transition conditions, and output behavior, including whether outputs depend on the state alone (Moore) or on the state and inputs (Mealy). Record any missing artifact or specific mismatch.

## Task 2 — SystemVerilog interface and test program

Mark Task 2 **CORRECT** only if all of the following hold:

- The SystemVerilog interface is implemented correctly and connects the right inputs and outputs to the machine from Task 1.
- The test program uses that interface to drive and observe the machine.
- The program calls `randomize()` to generate the test inputs it drives through the interface.

Record any missing component, incorrect signal connection, or missing use of the interface or randomization.

## Grading

| Correct tasks | Task score |
|---------------|-----------:|
| Task 1 and Task 2 | 100 |
| Task 1 only | 70 |
| Task 1 incomplete or incorrect | 0 |

Apply the subject-wide lateness cap using `python -m nure_dl grade-cap` and submit the lower of the task score and the cap. Leave a Moodle submission comment identifying any missing or incorrect work.
