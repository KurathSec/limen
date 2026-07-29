# Contributing

## Setup

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" -c constraints/ci.txt
pytest
```

Python >= 3.12. The package has zero runtime dependencies and must stay that
way. A new runtime dependency is a design discussion.

## The bar a change must clear

- `ruff check src tests tools calibration` and `mypy` (strict) green.
- `pytest` green, including the three mechanical gates:
  - **calibration drift**: committed tables regenerate committed rulings
    byte-for-byte;
  - **spec coverage**: every numbered ruling cited, every citation resolves;
  - **layering**: only the adapter imports the foreign checkout, lazily.
- New measurement behaviour needs a numbered spec ruling
  (`src/limen/spec/rulings/*.toml`) and a test citing it. Add a hand-computed
  corpus case (`tests/corpus/cases/`) where practical.

## Changing what a number means

Don't. Supersede it instead. A ruling's text is immutable once released.
Mark it `superseded`, add its successor, bump the rulings-spec version in
`index.toml` (MAJOR if a recorded value changes), regenerate goldens via
`python tools/update_calibration.py --write --confirm-spec-bump`, and state
both versions in CHANGELOG.md. `tools/update_calibration.py` refuses every
shortcut around this on purpose.

## Refreshing the calibration corpus

Needs a local Spaghetti-Architect checkout (never touched, never needed in CI):

```sh
python calibration/spaghetti/build_tables.py --repo /path/to/checkout
python tools/update_calibration.py --write
```

The refactor task executes model-generated code while grading; run it only
where you would run the benchmark itself.

## Generated docs

`docs/spec/rulings.md` and `docs/spec/sensitivity.md` are generated
(`tools/render_rulings.py`, `tools/render_sensitivity.py`). CI diffs them.
Edit the sources, not the output.
