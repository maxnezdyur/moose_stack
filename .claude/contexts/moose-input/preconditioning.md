# Authoring inputs: Preconditioning

Reach for this guide when you need to add a `[Preconditioning]` block to a `.i` file by **picking from the catalog** of registered preconditioner classes. The `[Preconditioning]` block builds (or wires up) the matrix that PETSc then preconditions; the `[Executioner]` chooses the nonlinear solve type and global PETSc options. If you only need to tweak `solve_type`, KSP, or PC and your problem is single-physics, you can skip this block entirely — see "When to use this" below. For PETSc options syntax shared with `[Executioner]`, see [executioner.md](./executioner.md).

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the `[Preconditioning]` sub-block>`).

## When to use this (vs alternatives)

Decide **whether** you need a `[Preconditioning]` block, then **which type**:

1. Single-variable / single-physics, default Newton or PJFNK: **omit the block**. With `solve_type = NEWTON` MOOSE assembles a hand-coded Jacobian and uses libMesh's default ILU/LU; with `solve_type = PJFNK` MOOSE uses a matrix-free Jacobian with the standard preconditioning matrix. Set `petsc_options_iname/value` directly in `[Executioner]`.
2. Tightly-coupled multi-physics where off-diagonal blocks of the Jacobian matter (most common): use **`SMP`** with `full = true`. Pair with `solve_type = NEWTON` and an algebraic-multigrid PC (`hypre/boomeramg`) or LU.
3. Block-structured solver where each variable (or group of variables) gets its own KSP/PC, possibly with Schur-complement reduction (Stokes, Navier-Stokes, mixed FE): use **`FSP`** with nested split sub-blocks naming `vars` and `splitting_type`.
4. Verifying that your hand-coded Jacobian is correct, or bringing up a new physics module: use **`FDP`** (color finite-difference). Slow; not for production. Pair with `solve_type = NEWTON`.
5. Operator-split / segregated solve where physics are advanced one block at a time using libMesh `Preconditioner` objects per variable: use **`PBP`**. Niche; mostly historical.
6. Mortar Lagrange-multiplier (e.g. dual-LM contact) where the LM rows make the Jacobian indefinite: use **`VCP`** to statically condense the LMs.
7. Statically-condensed FE (HDG) plus field split on the trace system: use **`SCFSP`** (`StaticCondensationFieldSplitPreconditioner`) — same syntax as `FSP`.

`[Preconditioning]` only takes effect when the problem has at least one nonlinear system; for `LinearFV` problems use `[Executioner]` PETSc options directly.

## Catalog

##### `SMP` (SingleMatrixPreconditioner)
- Source: `framework/include/preconditioners/SingleMatrixPreconditioner.h:17`
- Example: `test/tests/preconditioners/smp/smp_single_test.i:30` (sub-block `[./SMP]` at `:31`); full-coupling variant: `test/tests/preconditioners/auto_smp/ad_coupled_convection.i:61` (`[Preconditioning/smp]`)
- Default for tightly-coupled multi-physics. Builds one global Jacobian whose sparsity pattern is controlled by a coupling matrix.
- Required: `type = SMP`. Either `full = true` (recommended) **or** matched `off_diag_row` / `off_diag_column` lists naming the variables whose off-diagonal blocks should be assembled.
- Useful: `coupled_groups` (alternative to `off_diag_*`: every pair within a comma-separated group is coupled both ways), `solve_type` (set here OR in `[Executioner]` — typically `NEWTON` or `PJFNK`), `pc_side` (`left|right|symmetric|default`), `petsc_options_iname` / `petsc_options_value`, `trust_my_coupling` (suppresses MOOSE's automatic full-coupling override that AD global-indexing triggers).

##### `FSP` (FieldSplitPreconditioner)
- Source: `framework/include/preconditioners/FieldSplitPreconditioner.h:88` (template at `:48`)
- Example: `test/tests/preconditioners/fsp/fsp_test.i:85` (sub-block `[./FSP]` at `:88`)
- Maps onto PETSc's `PCFieldSplit`. Each named split solves on a subset of variables; splits are combined `additive | multiplicative | symmetric_multiplicative | schur`.
- Required: `type = FSP`, `topsplit = <name>` (must match a sub-block name), and at least one `[<topsplit_name>]` sub-block under `[Preconditioning/<FSP_name>]` whose `splitting = '<leaf1> <leaf2> ...'` lists more sub-blocks. Each leaf sub-block sets `vars = '<var1> <var2> ...'`.
- Useful: `full = true` (default for `FSP`; assembles the off-diagonal blocks the split solver needs), per-split `petsc_options_iname` / `petsc_options_value` (no `-` prefix needed; MOOSE prepends the DM/split prefix), `splitting_type = schur` plus `schur_type` (`diag|upper|lower|full`) and `schur_pre` (`self|selfp|a11`), `unsides`/`sides`/`blocks` for boundary/block-restricted splits.
- See "FSP sub-block syntax" below.

##### `FDP` (FiniteDifferencePreconditioner)
- Source: `framework/include/preconditioners/FiniteDifferencePreconditioner.h:18`
- Example: `test/tests/preconditioners/fdp/fdp_test.i:15` (sub-block `[./FDP]` at `:16`)
- Numerical Jacobian via finite differences (with graph coloring by default). Use only for **testing/verification** of hand-coded Jacobians; serial or very-small parallel runs only.
- Required: `type = FDP`.
- Useful: `finite_difference_type = coloring|standard` (default `coloring`; `standard` forces `full = true`), `implicit_geometric_coupling` (add Jacobian entries for DoFs coupled via geometric search — needed for contact/mortar checks), `full`, `off_diag_row`/`off_diag_column`. Always pair with `solve_type = NEWTON` (or `JFNK` if you want to compare against the matrix-free assembly).

##### `PBP` (PhysicsBasedPreconditioner)
- Source: `framework/include/preconditioners/PhysicsBasedPreconditioner.h:28`
- Example: `test/tests/preconditioners/pbp/pbp_test.i:25` (sub-block `[./PBP]` at `:26`)
- Composite preconditioner: solves variable-block sub-systems sequentially with libMesh `Preconditioner`s. Almost always paired with `solve_type = JFNK`. Niche; prefer `FSP` for new inputs.
- Required: `type = PBP`, `solve_order = '<var1> <var2> ...'` (order in which each variable's block is solved; a variable may appear more than once to build cycles), `preconditioner = '<P1> <P2> ...'` (one libMesh PC name per entry in `solve_order` — e.g. `LU`, `AMG`, `JACOBI`).
- Useful: `off_diag_row` / `off_diag_column`, `petsc_options` (set on the block — see precedence below).

##### `VCP` (VariableCondensationPreconditioner)
- Source: `framework/include/preconditioners/VariableCondensationPreconditioner.h:33`
- Example: `test/tests/preconditioners/vcp/vcp_test.i:97` (sub-block `[vcp]` at `:98`)
- Statically condenses out a "condensed" variable (typically a dual-mortar Lagrange multiplier) before handing the reduced system to a standard PC. Solves the indefinite-saddle-point convergence problem you hit when the LM rows have zero diagonal.
- Required: `type = VCP`, `lm_variable = '<lm_var>'`, `primary_variable = '<primal_var>'`, `preconditioner = AMG|LU|JACOBI|...` (libMesh PC type for the condensed system).
- Useful: `full = true` (almost always — VCP needs the off-diagonal `D` block), `is_lm_coupling_diagonal = true` (cheap diagonal-`D` inversion; only valid when the LM/primary coupling is element-diagonal, e.g. dual mortar), `adaptive_condensation` (skip rows where the LM has no support).

##### `SCFSP` (StaticCondensationFieldSplitPreconditioner)
- Source: `framework/include/preconditioners/StaticCondensationFieldSplitPreconditioner.h:18`
- Example: `test/tests/preconditioners/fsp/scfsp_test.i:73` (sub-block `[FSP]` at `:74`)
- `FSP` layered on top of `MooseStaticCondensationPreconditioner`. Use when you have HDG / interior-eliminated DoFs and still want a field-split on the remaining trace system.
- Required: same as `FSP` (`topsplit`, splits with `vars`).
- Useful: same as `FSP`. Inherits all `FSP` options; the static-condensation step is automatic when the variables support it.

##### `StaticCondensation`
- Source: `framework/include/preconditioners/MooseStaticCondensationPreconditioner.h` (registered as `StaticCondensation` in `MooseStaticCondensationPreconditioner.C:19`)
- Pure static-condensation preconditioner without field split. Used when you need to solve only the condensed (e.g. HDG trace) system with one PC. If you also want to split that system, use `SCFSP` instead.

### `FSP` sub-block syntax

`FSP` is the only preconditioner that uses **nested sub-blocks** under `[Preconditioning/<FSP_name>]`. Each sub-block is a `Split` (`framework/include/splits/Split.h:25`):

```hit
[Preconditioning]
  [FSP]
    type = FSP
    topsplit = 'uv'           # name of the entry sub-block
    [uv]
      splitting = 'u v'        # names of the leaf sub-blocks
      splitting_type = additive   # additive|multiplicative|symmetric_multiplicative|schur
    []
    [u]
      vars = 'u'               # which variables this leaf solves
      petsc_options_iname = '-pc_type -ksp_type'
      petsc_options_value = 'hypre  preonly'
    []
    [v]
      vars = 'v'
      petsc_options_iname = '-pc_type -ksp_type'
      petsc_options_value = 'lu     preonly'
    []
  []
[]
```

Per-split parameters (from `Split::validParams`):
- `vars` (`std::vector<NonlinearVariableName>`): variables this split owns. Omit to mean "all variables" (only meaningful for the top split).
- `splitting` (`std::vector<std::string>`): names of nested splits — only on non-leaf splits.
- `splitting_type` (`MooseEnum`): `additive` (default), `multiplicative`, `symmetric_multiplicative`, `schur`.
- `schur_type` (when `splitting_type = schur`): `diag|upper|lower|full` (PETSc `-pc_fieldsplit_schur_fact_type`).
- `schur_pre` (when `splitting_type = schur`): `self|selfp|a11` (PETSc `-pc_fieldsplit_schur_precondition`).
- `petsc_options`, `petsc_options_iname`, `petsc_options_value`: forwarded to PETSc with the split's auto-prefix (don't repeat the prefix yourself).
- `blocks`, `sides`, `unsides`, `unside_by_var_boundary_name`, `unside_by_var_var_name`: subdomain/boundary restriction for the split.

## Cross-cutting concerns

### PETSc options precedence: `[Executioner]` vs `[Preconditioning]` vs `Split`

PETSc reads options from a single global database. MOOSE feeds it from up to three sources, **applied in this order, last wins**:
1. `[Executioner]` `petsc_options*` — applied first; treat as defaults.
2. `[Preconditioning/<name>]` `petsc_options*` — applied next; overrides matching keys from the executioner.
3. `Split` sub-block `petsc_options*` (FSP only) — applied last with the split's prefix; overrides the same key for that split only.

Practical rule: put **global** options (`-snes_*`, `-snes_view`, top-level `-ksp_*`) on `[Executioner]`. Put **PC-class-specific** options (`-pc_type hypre`, `-pc_hypre_type boomeramg`) on `[Preconditioning]` — that way changing the preconditioner type doesn't strand options on the executioner. For FSP, put **per-split** options (`-pc_type lu` for the pressure block) inside the `Split` sub-block; do *not* prefix them — MOOSE adds the DM/split prefix automatically.

### `full = true` (off-diagonal couplings)

`full = true` tells the preconditioner to allocate (and let the assembly populate) every off-diagonal block of the Jacobian. Defaults differ by class: `MoosePreconditioner` base = `false` (so `SMP`, `FDP`, `PBP`, `VCP` default to `full = false` and require explicit `off_diag_row`/`off_diag_column`); `FSP`/`SCFSP` override to `full = true`. With AD kernels and any non-trivial coupling, `full = true` is almost always what you want — the alternative is silently-zero off-diagonal Jacobian entries and degraded Newton convergence. The exception is large numbers of variables where memory cost matters; then enumerate `off_diag_row`/`off_diag_column` (or `coupled_groups` on `SMP`).

### `solve_type` and the `[Preconditioning]` / `[Executioner]` split

`solve_type` is a parameter of both blocks (it's added to `MoosePreconditioner` via `Moose::PetscSupport::getPetscValidParams`). Set it in **either**, but conventionally set it in `[Executioner]`. Allowed values:
- `NEWTON` — assembled Jacobian (use with `SMP`, `FDP`, `VCP`, or no `[Preconditioning]`).
- `PJFNK` — matrix-free Jacobian-vector product, but the *preconditioning* matrix is still assembled (use with `SMP` or `FSP`). This is the libMesh/PETSc default if you omit `[Preconditioning]`.
- `JFNK` — fully matrix-free; no preconditioning matrix is assembled. Pair with `PBP` or with no `[Preconditioning]` block at all.
- `LINEAR` — for problems that are linear (`Steady` or `Transient` with linear kernels); skips the SNES outer loop.
- `FD` — finite-difference assembled (paired with `FDP`); rarely used outside Jacobian verification.

`NEWTON` requires a Jacobian; `PJFNK`/`JFNK` are matrix-free on the residual side. `FSP` works with both `NEWTON` and `PJFNK` because it always assembles a preconditioning matrix.

### `[Preconditioning]` block ordering

You may declare more than one preconditioner sub-block, but **only one is active per nonlinear system**. Use `active = '<name>'` on `[Preconditioning]` to select among them; the alternatives stay in the file as configurations to swap between. Multiple nonlinear systems (`[Problem] nl_sys_names = '...'`) can each have their own `[Preconditioning/<name>]` selected via the per-block `nl_sys` parameter.

### Combining with `automatic_scaling`

`[Executioner] automatic_scaling = true` rescales the Jacobian rows before the PC sees them. It is compatible with all preconditioners listed here. With `FSP` and Schur splits the scaling can interact poorly with `selfp` Schur preconditioning; if Newton stagnates, try `schur_pre = self` or disable auto-scaling for the split.

### Auto-preconditioning shortcut

`[Executioner] auto_preconditioning = true` (default for many physics) inserts an implicit `SMP`-with-`full=true` if you don't write a `[Preconditioning]` block. Set `auto_preconditioning = false` if you want the historical "no preconditioning matrix" behavior — this is what the `auto_smp` test exercises.

## Minimal scaffold

`SMP` with hypre algebraic multigrid (most common multi-physics default):

```hit
[Variables]
  [u][]
  [v][]
[]

[Kernels]
  [diff_u]
    type = ADDiffusion
    variable = u
  []
  [coupled_v]
    type = ADCoupledForce
    variable = u
    v = v
  []
  [diff_v]
    type = ADDiffusion
    variable = v
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
    petsc_options_iname = '-pc_type -pc_hypre_type'
    petsc_options_value = 'hypre    boomeramg'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1e-8
[]
```

`FSP` with two additive splits — one variable solved with hypre, the other with LU (typical pattern for verification before introducing a Schur split):

```hit
[Variables]
  [u][]
  [v][]
[]

[Kernels]
  [diff_u]
    type = ADDiffusion
    variable = u
  []
  [coupled_v]
    type = ADCoupledForce
    variable = u
    v = v
  []
  [diff_v]
    type = ADDiffusion
    variable = v
  []
[]

[Preconditioning]
  [FSP]
    type = FSP
    topsplit = 'uv'
    [uv]
      splitting = 'u v'
      splitting_type = additive
    []
    [u]
      vars = 'u'
      petsc_options_iname = '-pc_type -ksp_type'
      petsc_options_value = 'hypre    preonly'
    []
    [v]
      vars = 'v'
      petsc_options_iname = '-pc_type -ksp_type'
      petsc_options_value = 'lu       preonly'
    []
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]
```

For a Schur split (e.g. Stokes velocity-pressure), set `splitting_type = schur` and `schur_type = full` on the `[uv]` split, and add `schur_pre = selfp` (use the pressure-Laplacian-style approximation) — the leaf splits keep their per-variable `petsc_options_*` exactly as above.
