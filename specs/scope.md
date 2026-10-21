# Scope: moosify-uel

Starting input: `moose/modules/combined/examples/thermomechanics/moosify_uel.i`, copied from
Daniel Schwen's `moosify_nnl.i` (dschwen/moose `moosify`, a6b13f0335). His Global Strain code,
his `elastic.i` plugin change and the "nnl" names stay out.

The rows formulation for tie constraints (cherry-picked from `nodal-constraint-rows`, 5e1d80b6a7)
is on this branch.

## Replace [Physics/SolidMechanics/GlobalStrain] with rows ties

- PRP faces (Right, Front): one `EqualValueBoundaryConstraint` with `formulation = rows` on the
  normal displacement of each face.
- Symmetric faces (Left, Back, Bottom): Dirichlet 0. These faces are already planar, so they need
  no tie.
- With rows ties, each PRP face stays its own plane. That matches the table in main.pdf. Daniel's
  Global Strain made the two PRP directions one homogeneous cell stretch.

## Finish the outputs

- Reaction forces per face.
- Top-face heat flux.
- Total top heat loss.
- The state variable Z as an aux.

## Placeholder UMAT

Keep `elastic_incremental` until NNL provides the viscoplastic law and how Z evolves.

## Decisions to record

- Does the source shut off at 1e5 s or 5e6 s?
- Does x²/81 assume cm?
- What is the time scale of h(t)?
- Does mechanical dissipation feed back into the heat equation?

Defaults: take main.pdf literally and use cm.

## Dependency

The feature branch stacks on #33820. Its PR waits for #33820 to merge, or goes against `next`
with #33820 named as a dependency.
