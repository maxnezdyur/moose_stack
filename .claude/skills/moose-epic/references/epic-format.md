# epic.md format

The epic plan is one markdown file, `<worktree-root>/specs/epic.md`. It is one or two pages. It
decides the cuts and the joins of a chain of pull requests. It holds no file-level unit, no test
list and no work-plan JSON: those belong to the blueprint of each slice
(`specs/blueprint.md`, format in `../../moose-blueprint/references/blueprint-format.md`).
`example-epic.md` beside this file is a complete example. Write yours in the same shape.

## Front matter

```yaml
---
epic: <worktree name, kebab-case>
title: <what the chain delivers, as a heading>
repo: moose
issue: <N> | pending
created: YYYY-MM-DD
---
```

- `epic` is the worktree name. It is also the name of the branch in the `moose` checkout.
- No line of this file starts with `feature:`. The board takes a `specs/*.md` file with such a
  line as a slice blueprint when `blueprint.md` is absent.
- `repo` is `moose`. The first version of the stack script supports one repository per epic.
- `issue` is the epic issue on `idaholab/moose`. Confirm it with
  `gh issue view <N> --repo idaholab/moose --json title,state` before you write it. Write
  `pending` when the user has no issue yet. `/moose-ship` refuses `pending`.

## Sections, in this order, with these exact `##` headings

| heading | content |
|---|---|
| `## Goal` | One paragraph: what the chain delivers to a MOOSE user, and why it needs more than one pull request. |
| `## Shared physics` | The equations and the symbols that more than one slice uses, written once. A slice blueprint points here and adds only its own part. |
| `## Slices` | One table, one row per slice, in merge order. The columns are below. |
| `## Seams` | One table, one row per interface that one slice leaves for a later slice. The columns are below. Write `None.` when the slices share no interface. |
| `## Cross-slice decisions` | One bullet per decision that touches more than one slice: `- YYYY-MM-DD: chose A over B because C`. A decision inside one slice belongs to its blueprint. |
| `## Related features` | One bullet per independent feature of the same theme: the slug, and one sentence that says why it is not a slice. Write `None.` when there is none. |
| `## Out of scope` | Non-goals of the whole epic, one bullet each. |
| `## Amendments` | Append-only dated log. Never delete or edit a line. |

### The `## Slices` table

```
| id | title | needs | a user can | tests prove it |
|---|---|---|---|---|
| s1 | <title> | - | <one sentence> | <test names or one sentence> |
| s2 | <title> | s1: <what it uses> | <one sentence> | <test names or one sentence> |
```

- `id` is `s<n>`. The slice ref is `epic/<epic>/<id>`, and so is the head branch of its pull request.
  A slice is sealed when that ref exists:
  `git -C <worktree-root>/moose for-each-ref --format='%(refname:short)' 'refs/heads/epic/<epic>/s*'`
  lists the sealed slices.
- A sealed slice keeps its id for ever. The stack script gives a new slice the highest id used
  plus 1, so the table must agree with it: number the unsealed rows consecutively in row order,
  starting at the highest sealed id plus 1 (`s1` when no slice is sealed).
- Number the unsealed rows again each time you add, drop or reorder an unsealed row. Then
  correct each id in `## Seams`, and the `slice:` key of `specs/blueprint.md` when the id of its
  row changed.
- The row order is the merge order.
- `needs` names the row directly above and the code that this slice uses from it. The first row
  has `-`.
- `a user can` says what a MOOSE user can do when this slice merges alone.
- `tests prove it` names the regression tests that show it.
- Do not write a state, a commit, or a pull request number in this table. The stack script and
  the board derive them from git and GitHub.

### The `## Seams` table

```
| seam | contract | owner | used by |
|---|---|---|---|
| <short name> | <one sentence: what the later slice can rely on> | s1 | s2 |
```

Write the contract as one sentence. Do not write a class signature: the code at the slice ref
is the signature, and a signature in this file goes stale in review.

## The cut tests

Apply each test to each row before you write the file.

1. **Stands alone.** The row says what a user can do when the slice merges alone. A row that
   cannot say it is a wrong cut: merge it into a neighbour or cut again.
2. **Proved.** The row names the tests that prove that sentence.
3. **Needs the row above.** Each row after the first uses code from the row directly above. A
   candidate that needs nothing from the row above is not a slice. Move it to
   `## Related features`; it is an ordinary feature with its own worktree.
4. **Seam is exercised.** A slice adds a seam only if the tests of that same slice exercise it,
   with a test-app object if no user object uses it yet. If not, move the seam to the slice that
   first uses it. Code that only a later slice uses fails the coverage check on its own pull
   request.
5. **One line.** Two rows that need the same row but not each other are a fan-out. The first
   version supports a straight line only. Put them in an order, or make one of them a related
   feature that starts when its base merges.
6. **One repository.** A slice that changes `blackbear` or `isopod` stops the plan. The first
   version does not support it.

## Amending the plan

Change, add, drop or reorder a row only when its slice is not sealed, and number the unsealed
rows again as the `## Slices` rules say. For each change, append one line to `## Amendments`:
the date, what changed, and why. A sealed slice is never dropped or reordered in this version,
and a split of a sealed slice is not supported: tell the user.

## Checks before you stop

Read the file back and confirm each item.

- The front matter has the five keys. `epic` equals the worktree name.
- No line starts with `feature:`.
- The eight `##` headings are present, in order, and none holds a placeholder.
- Each row has an id that no other row has. The unsealed rows are numbered consecutively in
  row order from the highest sealed id plus 1.
- Each row passes the six cut tests.
- Each seam names an owner row and a user row, and the owner is above the user.
- The table holds no state, no commit, and no pull request number.
