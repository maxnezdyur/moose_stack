"""moose-factory: a projected board with one next action per card.

The vault at ``$MOOSE_FACTORY_VAULT`` (default ``~/projects/moose-factory``) is a
build artifact. This package is the only writer of its generated files.

Module order, read top to bottom:

    config    paths, caps, thresholds, the hostname guard
    model     dataclasses, lane ranks, the flag and posture vocabularies, Ctx
    probe     every read of the world; each probe returns (value, ok)
    derive    pure: lane, flags, posture, next action
    render    four-marker fencing, atomic writes, Home.md, Features.base
    snapshot  the probe cache with carry-forward, nag memory, the manifest
    timeline  flock'd NDJSON append against the vault
    gates     four monotonic attributed records per feature
    cli       the verbs

Extensions are single files ``tool/ext_<name>.py``, auto-discovered by name.
See ``factory/README.md`` for the contract.
"""

VERSION = "1.0.0"
