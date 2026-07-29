# Security

Report vulnerabilities via GitHub private vulnerability reporting on
`KurathSec/limen` (Security tab → "Report a vulnerability").

Notes on limen's own surface:

- `limen report` / `limen gate` / `limen synth` open no sockets and execute no
  foreign code; they read files you name and write files where you say.
- `limen regrade` imports a Spaghetti-Architect checkout you point it at and —
  for the refactor task — **executes model-generated code** through that
  checkout's own grading path (Python `exec`, plus compile-and-run
  subprocesses). Treat the checkout and its archives as code you are choosing
  to run; use the same isolation you would use to run the benchmark itself.
