# Example campaign

`ptr-depth-sensitivity/` is one campaign directory as the formats describe it, and
`Campaigns/ptr-depth-sensitivity.md` plus `Home-excerpt.md` are what `factory board` would render
from it. Read them side by side.

What is real: the constraints table copies the paper model from
`ptr-update/PTR/release_13x13/provenance/campaign_PLAN_2D_PARAM_GRID.md`, the code shas and the
container hash come from its `ENVIRONMENT.md`, and the solver knobs are the ones the release runs
used. What is invented: the campaign question, `truth_layer.i`, every run, every number in
`qoi.json`, `LEDGER.md` and `FINDINGS.md`. Frozen inputs and `run.log` files are omitted; the
manifests list them.
