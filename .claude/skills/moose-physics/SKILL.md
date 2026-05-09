---
name: moose-physics
description: Design the physics for a MOOSE study from a freeform problem description. Grills the user round after round (batched 1–4 questions per round, no assumptions) until every physics axis is locked, then writes `physics-spec.md` in cwd that `moose-input-writer` consumes. Primed by `PHYSICS-MAP.md` (curated index of 768+ MOOSE tutorials, theory pages, examples) and `INPUT-MAP.md` (input syntax catalog, for vocabulary alignment). Auto-triggers on phrasings like "I want to study X", "model Y under Z", "simulate ...", or invoke directly via `/moose-physics <description>`. Designs physics + modules + regimes; leaves MOOSE-specific type choices (mortar vs node-face contact, AD vs non-AD, etc.) to the writer.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
  - Skill
---

# /moose-physics

Convert a freeform physics description into a concrete `physics-spec.md` that `moose-input-writer` consumes. Grills the user until every physics axis is locked; **does not assume**, does not auto-spawn the writer, does not search the codebase.

The skill is *physics-deep* and *MOOSE-shallow*: it locks active modules, coupling regimes, material behavior, boundary conditions in physical terms, and loading. It does NOT pick types within those modules — `mortar` vs `node-face` contact, `ADDirichletBC` vs `DirichletBC`, exact strain measure class — those belong to `moose-input-writer`.

## Usage

```
/moose-physics <freeform physics description>
```

Examples:
- `/moose-physics fuel pin under thermal cycling with fission gas swelling`
- `/moose-physics two compliant cylinders in frictional contact, then heated`
- `/moose-physics steady creep of a turbine blade under centrifugal load`

If `$ARGUMENTS` is empty, prompt the user via `AskUserQuestion` for the description.

## Steps

### 1. Bootstrap

1. Read `$ARGUMENTS`. If empty, ask via `AskUserQuestion`: "What physics do you want to model?".
2. Detect the target app from cwd:
   - cwd under `moose/` → `moose` (framework / module)
   - cwd under `blackbear/` → `blackbear`
   - cwd under `isopod/` → `isopod`
   - anywhere else → `isopod` (widest superset)

   Capture this as the **Target app** for the spec.
3. Stat `./physics-spec.md`.
   - **Exists** → **resume mode**: read the file, parse which axes (see §3) are missing or vague, jump straight to grilling those.
   - **Does not exist** → **fresh mode**: continue with priming.

### 2. Priming (fresh mode only)

Two-stage priming:

**Stage A — physics map (primary source).** Read `.claude/contexts/moose-physics/PHYSICS-MAP.md`. This is a curated index of 768+ MOOSE tutorials, theory pages, worked examples, PDFs, module landing pages, and framework conceptual pages, organized into 19 physics-domain sections (Solid mechanics, Heat transfer, Contact, Fluid–Navier-Stokes, Fluid–porous flow, Phase field, Chemistry, Multiphysics, Optimization, Stochastic, etc.).

Based on the user's freeform description:

1. Identify which sections of `PHYSICS-MAP.md` are relevant. (E.g. "thermomechanical contact w/ finite strain" → Solid mechanics + Heat transfer + Contact + Multiphysics — combined module.)
2. Within those sections, scan the one-line descriptions and pick the specific rows whose topics genuinely match what the user is describing. Prefer:
   - `Theory` rows when you need to understand a physics concept (e.g. small vs finite strain kinematics)
   - `Tutorial` rows when you need a walk-through (e.g. how a thermomechanical contact problem is structured end-to-end)
   - `Example` rows when you need a canonical worked pattern
   - `Index` rows when scoping which module covers which capability
3. `Read` only the matched rows — typically 5–15 pages, not entire sections. The map is *too large* to load wholesale (153 KB) and most rows won't be relevant.

For PDF rows, use the `pages` parameter on `Read` to grab the relevant section rather than loading the whole document.

**Stage B — input vocabulary alignment.** Read `.claude/contexts/moose-input/INPUT-MAP.md` and the "When to use this (vs alternatives)" sections of input-catalog guides whose topics overlap with the user's physics (e.g. `heat-transfer.md`, `solid-mechanics.md`, `contact.md`). This stage is **only** for translating physics → MOOSE block vocabulary ("what's a `[Modules/TensorMechanics]` block? what's the difference between `[Contact]` and `[Constraints]`?"). Skip the type-level catalogs — that's writer territory.

Both stages serve **understanding the physics-to-MOOSE-concept mapping**, not type selection. The aim is to be conversant enough to grill the user accurately on physics decisions.

### 3. Grill until convergence — no assumptions

Round after round of `AskUserQuestion` (each round batches 1–4 questions; phrase recommended option first when one applies). **Do not invent answers.** Continue rounds until every axis below is locked:

**Required physics axes:**

1. **Active physics modules** — heat conduction / mechanics / contact / fluid / chemistry / electromagnetics / radiation / phase-field / …
2. **Coupling regime per module pair** — one-way (e.g. T → mechanics only) / two-way (e.g. T ↔ mechanics) / staggered / monolithic
3. **Deformation kinematics** (if mechanics active) — small strain / finite strain / explicit strain measure if user has a preference
4. **Material behavior per subdomain** — elastic / hyperelastic / plastic / viscoelastic / creep / thermo-elastic / etc.; isotropic / anisotropic; any state variables (damage, plastic strain, etc.)
5. **Domain & geometry**
   - Dimension (2D / 3D / axisymmetric)
   - Geometry description (analytic shape, CAD-like description, or "import this file")
   - Subdomains (names + roles, e.g. "fuel = pellet interior, clad = annular shell")
   - Sidesets (names + roles, e.g. "top = loaded face, bottom = symmetry, outer = convective")
6. **Boundary conditions per sideset, in physical terms** — "fixed displacement," "applied flux 1e6 W/m²," "convective with h = 50, T_inf = 300," "free surface," "tied to neighbor."
7. **Initial conditions per variable** — uniform value, function of position, prior solution checkpoint, etc.
8. **Loading / time evolution** — steady / transient; if transient: time horizon, ramp shape, any cycling pattern.
9. **Outputs of interest** — fields to visualize, scalar postprocessors (integrals / averages / maxes), time-histories, frequency.

**Convergence criterion:** every axis above has an explicit, unambiguous answer. If the user gives a vague answer ("some kind of heat transfer"), keep grilling until it's specific. Never substitute a default.

If, during grilling, the user says "I don't know — pick something sensible," that is a *legitimate* answer for items in the **Left to writer** zone (mortar vs node-face, AD vs non-AD, time integrator, solver options). Capture those in the "Left to writer" section of the spec rather than grilling further. But for *physics* axes (1–9 above), keep grilling — the user does know the physics or shouldn't be running the study.

### 4. Resume mode

If `physics-spec.md` already exists, read it and treat each section as either complete (every axis answered concretely) or incomplete. Grill only the incomplete sections. Never overwrite a complete section without asking the user explicitly. Final write merges new content into the existing file rather than replacing it.

### 5. Write `physics-spec.md`

Use this schema. Every section gets a concrete answer; never `TODO`. Skip a section only if it doesn't apply (e.g. no `## Initial conditions` for a steady problem with default zero initial state).

```markdown
# <problem name>

## Problem
<2–4 sentence physics narrative — what is being modeled and why>

## Target app
`moose` | `moose/modules/<m>` | `blackbear` | `isopod`

## Domain
- Dimension: 2D | 3D | axisymmetric
- Geometry: <description>
- Subdomains: <name: role>, …
- Sidesets: <name: role>, …

## Active physics
- Heat conduction: yes | no
- Mechanics: yes | no — <small | finite> strain
- Contact: yes | no — <friction | frictionless>; <tied | sliding>
- Fluid: yes | no — <regime>
- <other modules as relevant>

## Coupling regime
- <module1> ↔ <module2>: one-way | two-way | staggered | monolithic
- …

## Material behavior
- <subdomain1>: <constitutive description>
- …

## Boundary conditions (physical)
- <sideset1>: <physical description>
- …

## Initial conditions
- <variable>: <initial state>
- …

## Loading / time evolution
- Regime: steady | transient
- <if transient> Time horizon: <t0> → <t_final>
- <if transient> Ramp / cycle shape: <description>

## Outputs of interest
- Fields: <list>
- Postprocessors: <list>
- Time-histories: <list>
- Frequency: <every step | interval>

## Left to writer (MOOSE-specific decisions deferred)
- Contact algorithm (mortar | node-face | penalty) — writer picks based on robustness needs
- AD vs non-AD — writer picks
- Time integrator and solver options (NEWTON | PJFNK; tolerances) — writer picks
- Exact strain measure class (`ADComputeFiniteStrain` vs `ComputeFiniteStrain` vs total Lagrangian) — writer picks
- <other writer-territory items the user explicitly deferred>
```

### 6. Hand-off

After writing the spec, print exactly:

```
Spec written: <absolute path to physics-spec.md>
Target app: <app>
Next: invoke /moose-input-writer with this spec.
```

Do not auto-invoke the writer skill. The two-step gate is intentional: the user reviews the spec before authoring the input.

## Hard rules

- **No assumptions on physics axes.** If the user is vague about a physics axis (1–9), grill harder. Defaults are forbidden in physics territory.
- **Only physics belongs in the spec.** Type-level MOOSE choices (which `BC` class, which solver) go under "Left to writer," never assumed inline.
- **No codebase scouting.** Do not grep `*/test/tests/**/*.i` or other source code, do not spawn investigators. `PHYSICS-MAP.md` and the input catalog are curated indexes — read only the rows they point to. Never tree-walk beyond what the maps explicitly reference.
- **Resume, don't overwrite.** If `physics-spec.md` exists, fill gaps rather than restarting.
- **No auto-write hand-off.** Print the next step; don't auto-invoke the writer skill.

## Out of scope (v1)

- Searching for similar existing `.i` examples (no scout step). `PHYSICS-MAP.md` already indexes the canonical examples; pick from there if needed.
- Auto-spawning `moose-input-writer`.
- Validation that the chosen physics is actually implementable in the target app — the writer's `--check-input` loop catches that downstream.
