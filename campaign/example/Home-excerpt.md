# Home.md, the lines a campaign adds

The one-line summary gains a count:

```
_33 features, 1 campaign, 16 workspaces, 9 open PRs. ..._
```

`## Needs you` gains a row like any other card:

```
| card | next move | why |
|---|---|---|
| [[ptr-depth-sensitivity]] | `~/projects/moose_stack/factory/factory start ptr-depth-sensitivity` | D017 awaits your tick; D016 is ticked and will run on the next start |
```

Under the six posture sections, `## Campaigns` replaces `## Studies`:

```
## Campaigns (1)

| campaign | status | runs | budget | last finding | next |
|---|---|---|---|---|---|
| [[ptr-depth-sensitivity]] | active, needs you | 5: 3 supported, 1 refuted, 1 failed | 14.1 / 60 core-h, day 7 of 14 | F3. At 2.0 mm the 1 Hz shift is 0.004 rad, below the noise floor | tick D017 |
```

`Board.html` shows the same card in the needs-you column: the question, the budget line, the
three verdict counts, the last finding heading, the two proposals with their boxes, and the
figure thumbnail from `Gallery/ptr-depth-sensitivity/shift-vs-depth.png`.
