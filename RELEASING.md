# Releasing

1. Decide both versions: package (`src/limen/_version.py`) and rulings spec
   (`src/limen/spec/rulings/index.toml`). A spec MAJOR means a recorded
   meaning changed. Check that `tools/update_calibration.py --check` is green
   and that any golden change was made deliberately with `--confirm-spec-bump`.
2. Update `CHANGELOG.md`: a `## [X.Y.Z]` section stating **both** versions
   ("package X.Y.Z · rulings spec A.B.C") and the changes.
3. Regenerate the generated docs and commit if they moved:
   `python tools/render_rulings.py && python tools/render_sensitivity.py --replicates 200`.
4. Full local gate: `ruff check src tests tools calibration && mypy && pytest`.
5. Commit, push, wait for CI green on main.
6. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`. The release workflow
   re-runs the gate, checks the tag is on main and matches `__version__`,
   checks the CHANGELOG section exists, builds, asserts the sdist excludes
   `.github/ CLAUDE.md site/ scratch/ calibration/`, smoke-tests the wheel in
   a clean venv (env, spec list, synth -> report -> gate), and publishes to
   PyPI via trusted publishing (environment `pypi`).
7. Check the published wheel: `pip install limen==X.Y.Z && limen env`.
