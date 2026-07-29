"""Adapters: table builders that need a foreign checkout, kept behind a seam.

Only :mod:`limen.adapters.spaghetti` may import the Spaghetti-Architect
checkout's modules, and only lazily inside functions — enforced by ruff TID253
and tests/test_layering.py. Nothing here runs at ``import limen`` time.

This seam is also where the PF-11/B2-07 gap-survival limbs (``repaudit``) would
live if built: the dossiers record that those two cells are one instrument with
two report sections, and this package keeps that door open rather than
spawning a sibling.
"""
