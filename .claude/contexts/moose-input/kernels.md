# Authoring inputs: Kernels (residual contributions)

Reach for this guide when you need to add a residual-contributing object to a `.i` file by **picking from the catalog** of registered MOOSE kernels — volumetric, face, point, nodal, scalar, interface. If the residual lives on a Dirichlet/Neumann boundary, see [bcs.md](./bcs.md). If you only need a derived field for output (no residual), see [postprocess.md](./postprocess.md) or the AuxKernels catalog below. If the kernel you need does not exist yet (i.e. you're writing C++), see `../moose/kernel-authoring.md`.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`). AD twins (`ADFoo`) live in the same header as the templated class — same required params, same patterns.

## When to use this (vs alternatives)

Decide on **which top-level block** first, then pick the entry from the catalog. Default to `AD*` named classes for new inputs.

1. Standard FE volumetric residual (most common): **`[Kernels]`** — `ADDiffusion`, `ADTimeDerivative`, `ADBodyForce`.
2. Field that is *only* for output / postprocessing (no residual contribution): **`[AuxKernels]`** — `ParsedAux`, `FunctionAux`, `MaterialRealAux`.
3. Cell-centered FV variable (`type = MooseVariableFVReal` in `[Variables]`): **`[FVKernels]`** — always AD; `FVDiffusion`, `FVAdvection`, `FVTimeKernel`.
4. Linear-system FV (`MooseLinearVariableFVReal`, no Newton): **`[LinearFVKernels]`** — `LinearFVDiffusion`, `LinearFVAdvection`, `LinearFVSource`.
5. DG interior-facet term coupled to an FE variable: **`[DGKernels]`** — `ADDGDiffusion` (pair with a DG-aware BC).
6. Hybridized DG: **`[HDGKernels]`** — `DiffusionLHDGKernel`, `DiffusionIPHDGKernel`. Almost always need a `[GlobalParams]` block to share the variable trio.
7. Per-node residual (no integration), e.g. nodal ODE, penalty Dirichlet: **`[NodalKernels]`** — `TimeDerivativeNodalKernel`, `ConstantRate`, `PenaltyDirichletNodalKernel`.
8. Point source/sink at a physical location: **`[DiracKernels]`** — `ConstantPointSource`, `FunctionDiracSource`, `FunctorDiracKernel`.
9. ODE row driven by a **scalar** variable (no spatial integration): **`[ScalarKernels]`** — `ODETimeDerivative`, `ParsedODEKernel`.
10. Term coupling a primary variable to a `neighbor_var` across a sideset: **`[InterfaceKernels]`** — `InterfaceDiffusion`, `InterfaceReaction`.

For solid-mechanics or heat-conduction kernels (`StressDivergenceTensors`, `HeatConduction`, etc.), see the module recipes [solid-mechanics.md](./solid-mechanics.md) and [heat-transfer.md](./heat-transfer.md) — they're listed there with the surrounding strain/stress/material wiring that makes them useful.

## Catalog

### `[Kernels]` — FE volumetric residuals

#### Diffusion-like

##### `Diffusion` / `ADDiffusion`
- Source: `framework/include/kernels/Diffusion.h:18` / `framework/include/kernels/ADDiffusion.h:14`
- Example: `test/tests/kernels/simple_diffusion/simple_diffusion.i:14`; AD: `test/tests/kernels/ad_simple_diffusion/ad_simple_diffusion.i:14`
- Plain Laplacian `(grad u, grad psi)` — the canonical first kernel.
- Required: `variable`.
- Useful: `block`, `boundary`, `use_displaced_mesh`.

##### `MatDiffusion` / `ADMatDiffusion`
- Source: `framework/include/kernels/MatDiffusion.h:24`
- Example: `test/tests/kernels/2d_diffusion/matdiffusion.i:14`; AD: `test/tests/kernels/ad_mat_diffusion/ad_2d_steady_state.i:23`
- Diffusion with isotropic diffusivity from a material property.
- Required: `variable`. Useful: `diffusivity` (defaults to `"D"`), `v` (alternative concentration).

##### `AnisotropicDiffusion`
- Source: `framework/include/kernels/AnisotropicDiffusion.h:20`
- Example: `test/tests/kernels/anisotropic_diffusion/aniso_diffusion.i:23`
- Laplacian premultiplied by a fixed 2nd-order tensor `K` (9-entry vector input).
- Required: `variable`, `tensor_coeff`.

##### `FunctionDiffusion`
- Source: `framework/include/kernels/FunctionDiffusion.h:17`
- Example: `test/tests/kernels/function_diffusion/function_diffusion.i:14`
- Diffusion with a scalar coefficient supplied as a `Function`.
- Required: `variable`. Useful: `function` (defaults to 1).

##### `ConservativeAdvection` / `ADConservativeAdvection`
- Source: `framework/include/kernels/ConservativeAdvection.h:20`
- Example: `test/tests/kernels/conservative_advection/no_upwinding_1D.i:38`
- Conservative form `div(v u)` with optional full upwinding.
- Required: `variable` plus exactly one velocity source — `velocity_variable` OR `velocity_material` OR `velocity_as_variable_gradient`.
- Useful: `upwinding_type` (`none|full`), `advected_quantity`.

#### Time derivatives

##### `TimeDerivative` / `ADTimeDerivative`
- Source: `framework/include/kernels/TimeDerivative.h:14` / `framework/include/kernels/ADTimeDerivative.h:14`
- Example: `test/tests/kernels/coupled_time_derivative/coupled_time_derivative_test.i:22`; AD: `test/tests/kernels/ad_transient_diffusion/ad_transient_diffusion.i:19`
- Standard `(psi, du/dt)`.
- Required: `variable`. Useful: `lumping`.

##### `CoupledTimeDerivative` / `ADCoupledTimeDerivative`
- Source: `framework/include/kernels/CoupledTimeDerivative.h:17`
- Example: `test/tests/kernels/coupled_time_derivative/coupled_time_derivative_test.i:31`
- `(psi, dv/dt)` driven by a coupled var `v` (kernel acts on a *different* variable).
- Required: `variable`, `v`.

##### `MassMatrix`
- Source: `framework/include/kernels/MassMatrix.h:17`
- Example: `test/tests/tag/fe-mass-matrix.i:25`
- Forms an FE mass matrix into a *tagged* matrix — no residual contribution. Pair with `extra_tag_matrices` in `[Problem]`.
- Required: `variable`, `matrix_tags` or `extra_matrix_tags`. Useful: `density` (default 1).

#### Reactions / sources

##### `Reaction` / `ADReaction`
- Source: `framework/include/kernels/Reaction.h:18`
- Example: `test/tests/kernels/reaction/exact.i:18`
- Linear consuming reaction `(psi, lambda u)`.
- Required: `variable`. Useful: `rate` (default 1, controllable). Prefer this over the deprecated `CoefReaction`.

##### `BodyForce` / `ADBodyForce`
- Source: `framework/include/kernels/BodyForce.h:25`
- Example: `test/tests/kernels/2d_diffusion/bodyforce.i:31`; with a function: `test/tests/kernels/body_force/forcing_function_test.i:30`
- Volumetric source `-c * f * psi` with optional `Function` and `Postprocessor` multipliers.
- Required: `variable`. Useful: `value` (default 1, controllable), `function`, `postprocessor`.

##### `CoupledForce` / `ADCoupledForce`
- Source: `framework/include/kernels/CoupledForce.h:19`
- Example: `test/tests/kernels/ad_coupled_force/fe_test.i:22`
- Volumetric source proportional to a coupled variable: `-coef * v * psi`.
- Required: `variable`, `v`. Useful: `coef` (default 1).

##### `MatReaction` / `ADMatReaction`
- Source: `framework/include/kernels/MatReaction.h:21`
- Example: `modules/phase_field/test/tests/ad_coupled_gradient_dot/diffusion_rate.i` (search `type = ADMatReaction`)
- `-L * v * psi`, `L` from a material property.
- Required: `variable`, `reaction_rate`. Useful: `v` (defaults to nonlinear var), `args`.

#### Scalar coupling

##### `ScalarLagrangeMultiplier`
- Source: `framework/include/kernels/ScalarLagrangeMultiplier.h:32`
- Example: `test/tests/kernels/scalar_constraint/scalar_constraint_kernel.i:69`
- Lagrange-multiplier residual coupling a field variable to a scalar variable for integral constraints. Pair with `AverageValueConstraint` in `[ScalarKernels]`.
- Required: `variable`, `lambda` (coupled scalar).

### `[AuxKernels]` — derived fields for output

#### Field arithmetic

##### `ParsedAux`
- Source: `framework/include/auxkernels/ParsedAux.h:18`
- Example: `test/tests/auxkernels/parsed_aux/parsed_aux_test.i:78`
- Sets the variable to a parsed math expression of coupled vars / mat props / functors.
- Required: `variable`, `expression`. Useful: `coupled_variables`, `material_properties`, `ad_material_properties`, `functor_names`, `use_xyzt`.

##### `ConstantAux`
- Source: `framework/include/auxkernels/ConstantAux.h:17`
- Example: `test/tests/auxkernels/vector_magnitude/vector_magnitude.i:58`
- Constant scalar value across the domain.
- Required: `variable`. Useful: `value` (default 0, controllable).

##### `FunctionAux`
- Source: `framework/include/auxkernels/FunctionAux.h:19`
- Example: `test/tests/transfers/multiapp_userobject_transfer/3d_1d_sub.i:35`
- Samples a `Function` to populate an aux variable.
- Required: `variable`, `function`.

##### `FunctorAux`
- Source: `framework/include/auxkernels/FunctorAux.h:18`
- Example: `test/tests/variables/linearfv/diffusion-1d-aux.i:41`
- Evaluates any functor (variable, function, functor mat prop) and writes to the aux variable.
- Required: `variable`, `functor`. Useful: `factor` (default 1).

##### `SpatialUserObjectAux`
- Source: `framework/include/auxkernels/SpatialUserObjectAux.h:19`
- Example: `test/tests/userobjects/layered_average/layered_average_1d_displaced.i:44`
- Samples a SpatialUserObject (e.g. `LayeredAverage`) at the centroid/node.
- Required: `variable`, `user_object`.

#### Material / flux outputs

##### `MaterialRealAux` / `ADMaterialRealAux` / `FunctorMaterialRealAux` / `ADFunctorMaterialRealAux`
- Source: `framework/include/auxkernels/MaterialRealAux.h:19`
- Example: `test/tests/vectorpostprocessors/line_material_sampler/line_material_real_sampler.i:53`
- Volume-averaged value of a scalar material property to a variable.
- Required: `variable`, `property`. Useful: `factor`, `offset`, `selected_qp`.

##### `DiffusionFluxAux`
- Source: `framework/include/auxkernels/DiffusionFluxAux.h:18`
- Example: `test/tests/auxkernels/diffusion_flux/diffusion_flux.i:41`
- One component of `J = -D grad u`.
- Required: `variable`, `component` (`x|y|z|normal`), `diffusion_variable`, `diffusivity`. Useful: `boundary` (required if `component = normal`).

##### `RankTwoAux` / `ADRankTwoAux`
- Source: `modules/solid_mechanics/include/auxkernels/RankTwoAux.h:22`
- Example: `modules/solid_mechanics/test/tests/visco/visco_small_strain.i:49`
- One component `(i,j)` of a `RankTwoTensor` material property (stress, strain). Most users get this auto-added by `[Physics/SolidMechanics]` `generate_output` — see [solid-mechanics.md](./solid-mechanics.md).
- Required: `variable`, `rank_two_tensor`, `index_i` (0-2), `index_j` (0-2).

#### Diagnostic / mesh

##### `ElementLengthAux`
- Source: `framework/include/auxkernels/ElementLengthAux.h:18`
- Example: `test/tests/auxkernels/element_length/element_length.i:20`
- Element `hmin` or `hmax` per element (CFL etc.).
- Required: `variable`, `method` (`min|max`).

##### `VolumeAux`
- Source: `framework/include/auxkernels/VolumeAux.h:17`
- Example: `test/tests/auxkernels/volume_aux/element.i:17`
- Element volume.
- Required: `variable`.

### `[FVKernels]` — finite-volume residuals (always AD)

##### `FVDiffusion`
- Source: `framework/include/fvkernels/FVDiffusion.h:25`
- Example: `test/tests/fvkernels/fv_simple_diffusion/dirichlet.i:26`
- FV diffusion `int_A k grad u . n dA`; `coeff` is a functor.
- Required: `variable`, `coeff`. Useful: `coeff_interp_method` (`average|harmonic`, default harmonic).

##### `FVAnisotropicDiffusion`
- Source: `framework/include/fvkernels/FVAnisotropicDiffusion.h:19`
- Example: `test/tests/fvkernels/fv_anisotropic_diffusion/fv_anisotropic_diffusion.i:62`
- FV diffusion with a diagonal-tensor coefficient supplied as a vector functor.
- Required: `variable`, `coeff` (vector functor).

##### `FVAdvection`
- Source: `framework/include/fvkernels/FVAdvection.h:14`
- Example: `test/tests/fvkernels/fv_constant_scalar_advection/2D_constant_scalar_advection.i:30`
- FV advection with a *constant* velocity vector.
- Required: `variable`, `velocity` (RealVectorValue). Useful: `advected_interp_method` (`upwind|average|sou|min_mod|vanLeer|quick|venkatakrishnan|skewness-corrected`).

##### `FVMatAdvection`
- Source: `framework/include/fvkernels/FVMatAdvection.h:14`
- Example: `test/tests/fvkernels/mms/mat-advection-diffusion.i:27`
- FV advection with a *functor* velocity (e.g. material-property field).
- Required: `variable`, `vel`. Useful: `advected_quantity`, `advected_interp_method`.

##### `FVTimeKernel`
- Source: `framework/include/fvkernels/FVTimeKernel.h:14`
- Example: `test/tests/fvkernels/fv_constant_scalar_advection/2D_constant_scalar_advection.i:35`
- `du/dt` for an FV variable.
- Required: `variable`.

##### `FVBodyForce`
- Source: `framework/include/fvkernels/FVBodyForce.h:21`
- Example: `test/tests/fvkernels/mms/mat-advection-diffusion.i:37`
- FV volumetric source `-c * f`.
- Required: `variable`. Useful: `value`, `function`, `postprocessor`.

##### `FVReaction`
- Source: `framework/include/fvkernels/FVReaction.h:14`
- Example: `test/tests/fvkernels/fv_coupled_var/coupled.i:50`
- Linear consuming reaction `rate * u` per cell.
- Required: `variable`. Useful: `rate` (default 1).

##### `FVCoupledForce`
- Source: `framework/include/fvkernels/FVCoupledForce.h:17`
- Example: `test/tests/fvkernels/fv_coupled_var/coupled.i:60`
- `-coef * v` source where `v` is any functor.
- Required: `variable`, `v`. Useful: `coef` (default 1).

### `[DGKernels]` — discontinuous-Galerkin interior facets

##### `DGDiffusion` / `ADDGDiffusion`
- Source: `framework/include/dgkernels/DGDiffusion.h:24` / `framework/include/dgkernels/ADDGDiffusion.h:24`
- Example: `test/tests/dgkernels/2d_diffusion_dg/2d_diffusion_dg_test.i:101`; AD: `test/tests/dgkernels/ad_dg_diffusion/2d_diffusion_ad_dg_test.i:58`
- Interior penalty / SIPG diffusion edge term using `epsilon` and `sigma`.
- Required: `variable`, `sigma`, `epsilon`. Useful: `diff` (default 1).

##### `DGConvection` / `ADDGAdvection`
- Source: `framework/include/dgkernels/DGConvection.h:14` / `framework/include/dgkernels/ADDGAdvection.h:18`
- Example: `test/tests/dgkernels/1d_advection_dg/1d_advection_dg.i:41`; AD: `test/tests/dgkernels/ad_dg_convection/ad_dg_convection.i:23`
- DG advection with a constant velocity (non-AD) or functor / material-property velocity (AD).
- Required: `variable`, `velocity`. Useful (AD): `advected_quantity`.

### `[NodalKernels]` — per-node residuals

##### `TimeDerivativeNodalKernel`
- Source: `framework/include/nodalkernels/TimeDerivativeNodalKernel.h:17`
- Example: `test/tests/nodalkernels/constant_rate/constant_rate.i:28`
- `du/dt` evaluated at all nodes — for nodal ODEs.
- Required: `variable`.

##### `ConstantRate`
- Source: `framework/include/nodalkernels/ConstantRate.h:17`
- Example: `test/tests/nodalkernels/constant_rate/constant_rate.i:32`
- Adds a constant `rate` to a nodal ODE residual.
- Required: `variable`, `rate`.

##### `PenaltyDirichletNodalKernel`
- Source: `framework/include/nodalkernels/PenaltyDirichletNodalKernel.h:14`
- Example: `test/tests/nodalkernels/penalty_dirichlet/nodal_penalty_dirichlet.i:48`
- Soft Dirichlet via penalty `p (u - v)`. Prefer over `PenaltyDirichletBC` when you also need block restriction.
- Required: `variable`, `penalty`. Useful: `value` (default 0, controllable), `boundary`.

##### `LowerBoundNodalKernel` / `UpperBoundNodalKernel`
- Source: `framework/include/nodalkernels/LowerBoundNodalKernel.h:17` / `framework/include/nodalkernels/UpperBoundNodalKernel.h:17`
- Example: `test/tests/nodalkernels/constraint_enforcement/lower-bound.i:44`
- NCP-style bound enforcement on coupled `v` via Lagrange multiplier `variable`. Often paired with `CoupledForceNodalKernel`.
- Required: `variable`, `v`. Useful: `lower_bound` / `upper_bound` (default 0), `exclude_boundaries`.

### `[DiracKernels]` — point sources

##### `ConstantPointSource`
- Source: `framework/include/dirackernels/ConstantPointSource.h:18`
- Example: `test/tests/dirackernels/constant_point_source/1d_point_source.i:37`
- Constant residual at a single point.
- Required: `variable`, `value`, `point`.

##### `FunctionDiracSource`
- Source: `framework/include/dirackernels/FunctionDiracSource.h:17`
- Example: `test/tests/dirackernels/function_dirac_source/function_dirac_source.i:31`
- Point source magnitude from a `Function` of (t,x,y,z).
- Required: `variable`, `function`, `point`.

##### `FunctorDiracKernel`
- Source: `framework/include/dirackernels/FunctorDiracKernel.h:17`
- Example: `test/tests/dirackernels/functor_dirac_kernel/functor_dirac_kernel.i:63`
- AD point source whose magnitude is any functor.
- Required: `variable`, `functor`, `point`.

##### `ReporterPointSource`
- Source: `framework/include/dirackernels/ReporterPointSource.h:21`
- Example: `test/tests/dirackernels/reporter_point_source/2d_vpp.i`
- Variable-valued point sources whose locations and values come from a `Reporter` (e.g. VectorPostprocessor).
- Required: `variable`, `value_name`. Useful: `x_coord_name`, `y_coord_name`, `z_coord_name`, `weight_name`.

### `[ScalarKernels]` — scalar-variable ODE rows

##### `ODETimeDerivative` / `ADScalarTimeDerivative`
- Source: `framework/include/scalarkernels/ODETimeDerivative.h:14` / `framework/include/scalarkernels/ADScalarTimeDerivative.h:14`
- Example: `test/tests/kernels/ode/ode_sys_impl_test.i:68`; AD: `test/tests/scalar_kernels/ad_scalar_time_derivative/ad_scalar_time_derivative.i:17`
- `du/dt` for a SCALAR variable.
- Required: `variable`.

##### `ParsedODEKernel`
- Source: `framework/include/scalarkernels/ParsedODEKernel.h:18`
- Example: `test/tests/kernels/ode/parsedode_pp_test.i:26`
- Parsed-expression scalar ODE residual.
- Required: `variable`, `expression`. Useful: `coupled_variables`, `postprocessors`, `constant_names`/`constant_expressions`.

##### `AverageValueConstraint`
- Source: `framework/include/scalarkernels/AverageValueConstraint.h:31`
- Example: `test/tests/kernels/scalar_constraint/scalar_constraint_kernel.i:77`
- LM residual that enforces `int phi = value`. Pair with `ScalarLagrangeMultiplier` in `[Kernels]`.
- Required: `variable` (scalar LM), `pp_name`, `value`.

### `[InterfaceKernels]` — sideset coupling between two subdomains

##### `InterfaceDiffusion`
- Source: `framework/include/interfacekernels/InterfaceDiffusion.h:17`
- Example: `test/tests/interfacekernels/1d_interface/coupled_value_coupled_flux.i:56`
- Enforces flux balance `D_a grad u_a . n = D_b grad u_b . n` at an interface between two subdomains.
- Required: `variable`, `neighbor_var`, `boundary`. Useful: `D` (default `D`), `D_neighbor` (default `D_neighbor`).

##### `InterfaceReaction`
- Source: `framework/include/interfacekernels/InterfaceReaction.h:18`
- Example: `test/tests/interfacekernels/1d_interface/reaction_1D_steady.i:88`
- First-order reaction at interface: `R = kf*u - kb*v`.
- Required: `variable`, `neighbor_var`, `boundary`, `kf`, `kb`.

##### `PenaltyInterfaceDiffusion` (and AD / Vector variants)
- Source: `framework/include/interfacekernels/PenaltyInterfaceDiffusion.h:18`
- Example: `test/tests/interfacekernels/resid_jac_together/jump.i:60`
- Penalty-based continuity + flux equivalence across an interface; can subtract a material-defined jump.
- Required: `variable`, `neighbor_var`, `boundary`, `penalty`. Useful: `jump_prop_name`.

### `[HDGKernels]` — hybridized DG

HDG kernels rely on `[GlobalParams]` to share the variable trio (primal + face + optional gradient). Read the validParams of the matching `*AssemblyHelper.h` for the full required-param list before authoring.

##### `DiffusionLHDGKernel`
- Source: `framework/include/hdgkernels/DiffusionLHDGKernel.h:18`
- Example: `test/tests/hdgkernels/ldg-diffusion/diffusion.i:31`
- Hybridized local DG diffusion (introduces gradient + face-trace variables).
- Required: `variable`, `gradient_variable` (vector L2), `face_variable` (SIDE_HIERARCHIC), `diffusivity` (typically wired via `[GlobalParams]`). Useful: `source` (functor, default 0).

##### `DiffusionIPHDGKernel` / `AdvectionIPHDGKernel`
- Source: `framework/include/hdgkernels/DiffusionIPHDGKernel.h:19` / `framework/include/hdgkernels/AdvectionIPHDGKernel.h:19`
- Example: `test/tests/hdgkernels/ip-advection-diffusion/simple_ip_hdg_diffusion.i:28`; advection: `test/tests/hdgkernels/ip-advection-diffusion/simple_ip_hdg_advection.i:26`
- Hybridized interior-penalty DG (no gradient variable; just `variable` + `face_variable`).
- Required: `variable`, `face_variable`, `diffusivity` or `velocity`+`coeff`, `alpha` (penalty, IPHDG diffusion).

For hybridized Navier-Stokes, see `modules/navier_stokes/include/hdgkernels/NavierStokesLHDGKernel.h`.

### `[LinearFVKernels]` — pre-assembled linear-system FV

##### `LinearFVDiffusion`
- Source: `framework/include/linearfvkernels/LinearFVDiffusion.h:20`
- Example: `test/tests/linearfvkernels/diffusion/diffusion-1d.i:31`
- FV diffusion assembled directly into a linear system; the variable type must be `MooseLinearVariableFVReal`.
- Required: `variable`. Useful: `diffusion_coeff` (functor, default 1), `coeff_interp_method`, `use_nonorthogonal_correction` (default true).

##### `LinearFVAdvection`
- Source: `framework/include/linearfvkernels/LinearFVAdvection.h:20`
- Example: `test/tests/linearfvkernels/advection/advection-1d.i:43`
- Linear-FV advection with a constant velocity vector.
- Required: `variable`, `velocity`, `advected_interp_method_name`.

##### `LinearFVReaction`
- Source: `framework/include/linearfvkernels/LinearFVReaction.h:18`
- Example: `test/tests/linearfvkernels/reaction/reaction-1d.i:22`
- Reaction `c u` for linear-system FV.
- Required: `variable`. Useful: `coeff` (functor, default 1).

##### `LinearFVTimeDerivative`
- Source: `framework/include/linearfvkernels/LinearFVTimeDerivative.h:19`
- Example: `test/tests/time_integrators/implicit-euler/ie-linearfv.i:46`
- `du/dt` for linear-system FV variables.
- Required: `variable`. Useful: `factor` (functor, default 1).

##### `LinearFVSource`
- Source: `framework/include/linearfvkernels/LinearFVSource.h:18`
- Example: `test/tests/linearfvkernels/diffusion/diffusion-1d.i:36`
- Solution-independent source `-rho * f` (RHS only).
- Required: `variable`. Useful: `source_density` (default 1), `scaling_factor` (default 1).

## Cross-cutting concerns

### AD vs non-AD
- Default to `AD*` for new inputs. Off-diagonal Jacobians are automatic; no manual coupling list. Non-AD twins exist for legacy parity, performance tuning, or cases where the AD chain is broken upstream.
- `[FVKernels]` and `[HDGKernels]` are *always* AD — there is no non-AD twin. `[LinearFVKernels]` are non-AD by construction (they assemble matrix + RHS directly without Newton).
- AD twins (`ADReaction`, `ADBodyForce`, `ADMatReaction`, ...) are typedefs from the same templated header — same params, same patterns.

### Coupling
- Coupled variables go in via `addCoupledVar`-type params (`v`, `coupled_variables`, `temperature`, `displacements`, `args`). The variable being coupled must be declared in `[Variables]` or `[AuxVariables]` — see [variables.md](./variables.md).
- Non-AD kernels with coupled variables silently produce a wrong off-diagonal Jacobian unless you list the dependency in `args` (or `coupled_variables` for derivative materials). Newton convergence will degrade. Use AD to avoid this.
- Scalar-variable coupling requires `[ScalarKernels]` — see `ScalarLagrangeMultiplier` + `AverageValueConstraint`.

### Material properties
- Most kernel parameters that look like names (`diffusivity`, `density`, `coeff`, `D`) are `MaterialPropertyName`s. The matching property must be declared in a `[Materials]` entry — see [materials.md](./materials.md).
- AD kernels consume `getADMaterialProperty`; if the producing `[Materials]` entry uses non-AD `declareProperty`, the chain is broken. Use `AD*` materials with `AD*` kernels.
- Functors (e.g. `coeff` in `FVDiffusion`, `velocity` in `FVMatAdvection`) accept variable names, function names, *and* functor mat-prop names interchangeably.

### Block / boundary restriction
- `block = subdomain_name` restricts the kernel to a subdomain. `boundary = sideset_name` restricts boundary-side and interface-side kernels. Both accept lists.
- For `[InterfaceKernels]`, `boundary` *must* be a sideset that lies between the subdomain owning `variable` and the subdomain owning `neighbor_var`. Reversing the two will mostly compile but produce the wrong residual sign.
- `displacements` is *not* `block` — `displacements` in solid-mechanics kernels turns on small-strain displacement coupling, not mesh restriction.

### Time integration
- Use `TimeDerivative` / `ADTimeDerivative` (or `*TimeKernel`/`*TimeDerivativeNodalKernel` for FV/Nodal) — never hand-code `(_u - _u_old)` math; the time integrator (BDF2, Crank-Nicolson) won't be consulted.
- `MassMatrix` and `FVMassMatrix` add to a tagged matrix only; they need `extra_tag_matrices` declared on `[Problem]` to do anything useful.

### Physics shorthand vs hand-rolled
- For solid mechanics, heat conduction, Navier-Stokes, contact: most users invoke `[Physics/SolidMechanics/QuasiStatic/...]`, `[Physics/HeatConduction/FiniteElement]`, `[Contact/...]` — see [solid-mechanics.md](./solid-mechanics.md), [heat-transfer.md](./heat-transfer.md), [contact.md](./contact.md). The Physics block expands to the equivalent `[Variables]` + `[Kernels]` + `[BCs]` + `[Materials]` automatically. Hand-rolled `[Kernels]` blocks remain valid and are required when you need fine-grained control.

## Minimal scaffold

Steady FE diffusion-reaction with one body-force source — the canonical first input:

```hit
[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 10
    ny = 10
  []
[]

[Variables]
  [u]
  []
[]

[Kernels]
  [diff]
    type = ADDiffusion
    variable = u
  []
  [rxn]
    type = ADReaction
    variable = u
    rate = 1.0
  []
  [bf]
    type = ADBodyForce
    variable = u
    function = forcing_fn
  []
[]

[Functions]
  [forcing_fn]
    type = ParsedFunction
    expression = 'sin(pi*x)*sin(pi*y)'
  []
[]

[BCs]
  [all]
    type = ADDirichletBC
    variable = u
    boundary = 'left right top bottom'
    value = 0
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_hypre_type'
  petsc_options_value = 'hypre boomeramg'
[]

[Outputs]
  exodus = true
[]
```

For a transient FV variant, swap `[Variables/u]` to `type = MooseVariableFVReal`, replace `[Kernels]` with `[FVKernels]` (containing `FVTimeKernel` + `FVDiffusion` + `FVBodyForce`), `[BCs]` with `[FVBCs]`, and `[Executioner] type = Transient`.
