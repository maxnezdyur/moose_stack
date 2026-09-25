"""campaign: the tool for open-ended experimental work.

A campaign is one question, a stop condition, a budget, and an append-only
record of runs and findings. The contract is ``campaign/README.md`` and the
four files under ``campaign/formats/``; this package implements it. Nothing in
it names a user, a home directory or a machine: every such value comes from
``tool/config.py``.
"""

__version__ = "0.1.0"
