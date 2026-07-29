# Hand-computed corpus cases

Each `cases/*.toml` is a micro verdict table whose expected report values were
computed by hand and written down before the code ran. The runner
(`tests/test_corpus_cases.py`) builds the archive, runs the ordinary
`build_report` path, and compares each dotted-path assertion exactly.

Format:

```toml
title = "what this case pins"
rulings = ["LMN-RNK-001"]          # spec rulings this case exercises

[[rows]]                            # model, item, verdicts-per-draw
model = "A"
item = "i1"
verdicts = [1, 0]

[expected]                          # dotted paths into the report envelope
"rulings.pair.0.sign_stability.ruling" = "SIGN-UNSTABLE"
```

Floats must be written exactly as limen serializes them (round-half-even to
6 places), so a wrong hand computation fails loudly rather than approximately.
