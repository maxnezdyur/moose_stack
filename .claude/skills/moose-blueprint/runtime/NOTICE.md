# Vendored runtime

`htmlplan.css`, `htmlplan.js`, `pack.mjs` and `../references/blocks.md` come from the `html-plan`
plugin by Thariq Shihipar, in `anthropics/claude-plugins-community` at commit
`f60f0454df3045f724c43c6346ec80bdcc3472b2` (2026-10-05). The plugin declares the MIT licence in its
`plugin.json`; the repository carries the Apache-2.0 licence. `pack.mjs` carries one patch: `doc-math` is added to the `KNOWN` element set and to the exhibit-tag list on the claim-tree lint, and excluded from the prose word counts (search `quote|math`). The other files are unmodified. Our
additions are `pack-blueprint.py` (the `doc-math` step and the pack call) and the `doc-math`
section of `blocks.md`.

To refresh: download the four files from `html-plan/skills/html-plan/` and update the commit here.
