# MOOSE Physics Map

Index of MOOSE physics tutorials, theory pages, examples, and conceptual references — for use by the `/moose-physics` skill (and any future physics-design or input-design skill).

This file points to docs **outside** `.claude/`. Each row gives a meta-repo-relative path, a doc type, and a one-line description. Load only the rows whose descriptions match the user's physics — do not load entire sections wholesale unless the prompt is broad.

## Companions

- `.claude/contexts/moose-input/INPUT-MAP.md` — picks **which MOOSE object** to use in `.i` files (input syntax catalog).
- `.claude/contexts/moose/AUTHORING-MAP.md` — picks **which C++ pattern** to use when writing new MOOSE objects.

This file (`PHYSICS-MAP.md`) picks **which physics references** to consult when designing the physics layer of a MOOSE study.

## Conventions

- **Path**: meta-repo-relative, starting with `moose/`, `blackbear/`, or `isopod/`. Resolve by prepending `/Users/maxnezdyur/projects/moose_stack/`.
- **Type**:
  - `Theory` — math/physics derivation pages
  - `Tutorial` — pedagogical walkthroughs
  - `Example` — worked input files with companion docs
  - `PDF` — `.pdf` references (use the `pages:` parameter when reading)
  - `Index` — module landing pages
  - `System` — framework-level conceptual pages
- **Description**: one line; what the page covers, from a physicist's perspective.

## How to use

1. Read the user's physics description.
2. Identify candidate sections below (Solid mechanics? Heat transfer? Contact? Multiphysics combined?).
3. Within those sections, scan descriptions and Read only the specific rows whose topics match.
4. Cite the path back to the user when explaining a design choice.


## Solid mechanics

| Path | Type | Description |
|---|---|---|
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/1d_elastic_waves.md | Theory | Frequency-domain analysis: modal eigenvalue problem and frequency response functions (FRF) on a cantilever beam. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/beam_vandv.md | Example | Beam V&V cases: small-strain Timoshenko vs Euler bending, large-deformation cantilevers, dynamic responses with analytical comparisons. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/C0TimoshenkoBeam.md | Theory | C0 Timoshenko beam element (2 nodes, 6 DOFs); updated Lagrangian, Euler-angle rotation increments, shear+bending deformation. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/common/seealsoADStressDivergenceKernels.md | System | Cross-reference snippet listing AD stress-divergence kernel variants for XYZ, RZ, RSPHERICAL coordinate systems. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/common/supplementalADAxisymmetricRZStrain.md | Theory | AD axisymmetric RZ strain calculator: cylindrical coordinates, z-axis symmetry, paired with ADStressDivergenceRZTensors. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/common/supplementalADStressDivergenceKernels.md | Theory | Weak form of stress divergence for AD kernels; emphasizes use_displaced_mesh consistency and AD material requirement. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/common/supplementalAxisymmetricRZStrain.md | Theory | Non-AD axisymmetric RZ strain calculator: cylindrical coordinates, z-axis symmetry, paired with StressDivergenceRZTensors. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/common/supplementalRadialReturnStressUpdate.md | Theory | Radial-return algorithm: trial elastic stress, von Mises yield surface check, Newton iteration on effective inelastic strain. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/common/supplementalStressDivergenceKernels.md | Theory | Non-AD stress divergence kernel weak form, JFNK-vs-NEWTON Jacobian options, use_finite_deform_jacobian flag. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/Convergence.md | Theory | Setting nonlinear residual tolerances and plasticity-specific tolerances (yield function, plastic strain, internal parameters). |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/CriticalTimeStepMath.md | Theory | Critical time-step formulas for explicit dynamics (3D isotropic, beam, truss): wave-speed-based stability limits. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/Dynamics.md | Theory | Structural dynamics: Newmark/HHT time integration, Rayleigh damping, and the M-C-K equation of motion for forcing/wave problems. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/examples_index.md | Index | Index of solid mechanics tutorials and worked examples (introduction tutorial, IGA c-frame). |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/examples/cframe_iga.md | Example | Isogeometric Analysis (IGA) c-frame example: u-spline mesh from Cubit, RATIONAL_BERNSTEIN element family, max principal stress. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/FractureIntegrals.md | Theory | J-integral, interaction integrals, KI/KII/KIII stress intensity factors and T-stress for cracks via domain-integral method. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/generalized_plane_strain.md | Theory | Generalized plane strain with extra out-of-plane scalar DOF for non-vanishing constant axial strain on 2D domain. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/Homogenization.md | Theory | Imposing cell-average stress or strain (P or F) constraints on periodic unit cells via Lagrangian kernels for effective property extraction. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/index.md | Index | Solid Mechanics module landing page; lists capabilities (elasticity, plasticity, creep, damage, Cosserat) and combined-physics integrations. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/LagrangianKernelTheory.md | Theory | Theory for new total Lagrangian (PK1) and updated Lagrangian (Cauchy) stress-divergence kernels; reference vs current configurations. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/LAROMANCE.md | Theory | Reduced-order creep model (LAROMANCE) for stainless steels using radial return with VPSC-trained ROM of dislocation densities. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/NewMaterialSystem.md | Theory | Material classes (ComputeLagrangianStrain, Cauchy/PK1 stress base) for total/updated Lagrangian kernels, plus existing-material wrapper. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/plug_n_play.md | System | Plug-n-play architecture: strain + elasticity tensor + stress materials (plus eigenstrain/extra-stress options) decompose any mechanics model. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/ShellElements.md | Theory | 4-node Dvorkin-Bathe shell element with 5 DOFs/node for thin/thick plates; plane stress condition and shear-locking correction. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/Stabilization.md | Theory | F-bar and B-bar stabilization for Lagrangian kernels to avoid volumetric locking under near-incompressibility/plasticity/hyperelasticity. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/Strains.md | Theory | Strain measure formulations: small total, small incremental, finite incremental; choosing between path-independent vs incremental theories. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/StressDivergence.md | Theory | Strong/weak form of momentum balance; consistency rules between strain formulation, stress, and use_displaced_mesh. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/Stresses.md | Theory | Stress calculators for elastic, plastic, creep stresses; UserObject-based plasticity vs StressUpdate radial-return materials. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/systems.md | Index | Auto-generated complete system/syntax index for SolidMechanicsApp; entry point to all registered objects. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/TensorClasses.md | System | RankTwoTensor/RankFourTensor (and Symmetric/Mandel variants): input-file fill methods, indexing, operators used throughout the module. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer01a.md | Tutorial | Step1 Q&A: choosing consistent units (Pa, m, s) and the MOOSE `${units ...}` conversion shorthand. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer01b.md | Tutorial | Step1 Q&A: zero-load problem trivially converges; how to compile and run `solid_mechanics-opt`. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer02a.md | Tutorial | Step2 Q&A: switching to FINITE strain and ComputeFiniteStrainElasticStress when deformations grow large. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer02b.md | Tutorial | Step2 Q&A: dimensional analysis showing equal-scaling of Young's modulus and pressure leaves displacements unchanged. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer02c.md | Tutorial | Step2 Q&A: converting input to automatic differentiation (use_automatic_differentiation, ADDirichletBC, AD materials). |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer03a.md | Tutorial | Step3 Q&A: outputting vonmises_stress via generate_output and material_output_order for smoother fields. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer03b.md | Tutorial | Step3 Q&A: predicting bimetallic-strip bending under thermal expansion mismatch. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer03c.md | Tutorial | Step3 Q&A: how constraining x on the whole bottom of a thermally expanding strip induces concentrated stress. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer03d.md | Tutorial | Step3 Q&A: pinning translational+rotational modes with two ExtraNodesetGenerator nodes instead of fixing a full edge. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer04a.md | Tutorial | Step4 Q&A: cantilevers overlap without contact - motivates contact module setup in next tutorial. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/answer04b.md | Tutorial | Step4 Q&A: extracting cantilever tip deflection with NodalExtremeValue postprocessor and CSV output. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/index.md | Tutorial | Top-level intro-to-solid-mechanics tutorial index linking steps 1-4: minimal mechanics, BCs, subdomains, multi-mesh. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/step01.md | Tutorial | Bare-bones small-strain mechanics input: GeneratedMeshGenerator, QuasiStatic Physics action, isotropic elasticity, units. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/step02.md | Tutorial | Add DirichletBC fixities and Pressure boundary action with time-dependent ParsedFunction load. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/step03.md | Tutorial | Two subdomains via SubdomainBoundingBoxGenerator with per-block elasticity tensors; NEWTON solver + SMP/LU. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/step03a.md | Tutorial | Thermal-expansion eigenstrain on a bimetallic strip using ComputeThermalExpansionEigenstrain and automatic_eigenstrain_names. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/step04.md | Tutorial | Two side-by-side cantilevers via MeshCollectionGenerator with finite-strain formulation and pressure loading. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/step04a.md | Tutorial | Volumetric locking demonstration: QUAD4 vs QUAD8, volumetric_locking_correction, mesh refinement effects. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/tutorials/introduction/supplemental02.md | Tutorial | Auto-generated `!syntax list /BCs` reference of available solid-mechanics boundary condition objects. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/VisualizingTensors.md | System | Outputting stress, strain, elasticity tensor components to AuxVariables via RankTwoAux/RankFourAux for visualization and postprocessing. |
| moose/modules/solid_mechanics/doc/content/modules/solid_mechanics/VolumetricLocking.md | Theory | B-bar correction for fully integrated linear elements near incompressibility; deviatoric/volumetric strain split. |
| moose/modules/solid_mechanics/doc/theory/capped_weak_plane.pdf | PDF | CSIRO theory manual for capped weak-plane plasticity: layered/jointed-rock yield surfaces with tensile/compressive caps. |
| moose/modules/solid_mechanics/doc/theory/cosserat.pdf | PDF | CSIRO theory manual for Cosserat (micropolar) mechanics: couple stresses, micro-rotations, and 2D/3D layered formulation. |
| moose/modules/solid_mechanics/doc/theory/tensile.pdf | PDF | CSIRO theory manual for tensile (Rankine) plasticity: yield when max principal stress exceeds tensile strength. |

## Heat transfer

| Path | Type | Description |
|---|---|---|
| moose/modules/heat_transfer/doc/content/index.md | Index | Top-level redirect to the heat_transfer module landing page. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/index.md | Index | Module overview: heat conduction PDE, Robin/Neumann/convective/radiative BCs, and opaque gray-diffuse net-radiation theory. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/nafems_t3_verif.md | Theory | NAFEMS T3 verification benchmark: 1D transient conduction in a bar (1D/2D/3D mesh), code-to-standard validation. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer01a.md | Tutorial | Answer 1a: identify where physical units appear in the Step 1 input (mesh size, conductivity, time step). |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer01b.md | Tutorial | Answer 1b: predict the trivial zero-residual outcome of Step 1 with no BCs and zero initial condition. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer02a.md | Tutorial | Answer 2a: explain that Step 2 reduces to Laplace's equation, giving a linear-in-x steady temperature distribution. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer02b.md | Tutorial | Answer 2b: scaling thermal conductivity has no effect when only the conduction term is present in steady state. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer03a.md | Tutorial | Answer 3a: predict transient temperature evolution with the time-derivative term and ramped right-side BC. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer03b.md | Tutorial | Answer 3b: lowering density or specific heat reduces transient lag and recovers the steady linear solution. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/answer03c.md | Tutorial | Answer 3c: volumetric heating biases temperature upward with the largest rise at the domain center. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/index.md | Tutorial | Landing page for the introductory heat-conduction tutorial series, sequencing steps from minimal input through volumetric heating. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/supplemental02a.md | Tutorial | Supplemental 2a: auto-generated catalog of available `[Functions]` blocks for use in time-dependent BCs. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/supplemental02b.md | Tutorial | Supplemental 2b: auto-generated catalog of available `[BCs]` types applicable to the heat conduction module. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/therm_step01.md | Tutorial | Step 1: minimal input file for a heat-conduction problem on a generated rectangular mesh, no BCs or sources. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/therm_step02.md | Tutorial | Step 2: prescribe Dirichlet temperature BCs on left/right sides to drive a steady linear conduction profile. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/therm_step02a.md | Tutorial | Step 2a: add a LineValueSampler to extract temperature along a line and write CSV output for post-processing. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/therm_step03.md | Tutorial | Step 3: extend the steady conduction problem with the rho*c*dT/dt time-derivative kernel for transient response. |
| moose/modules/heat_transfer/doc/content/modules/heat_transfer/tutorials/introduction/therm_step03a.md | Tutorial | Step 3a: add a volumetric heat source qdot (e.g. fission, resistive, exothermic) via a body-force kernel. |

## Contact

| Path | Type | Description |
|---|---|---|
| moose/modules/contact/doc/content/index.md | Index | Top-level redirect/landing page for the contact module documentation. |
| moose/modules/contact/doc/content/modules/contact/BerkovichIndenterNodeFace.md | Example | 3D Berkovich indenter into crystal-plasticity bcc base material; tangential_penalty frictional node-face contact. |
| moose/modules/contact/doc/content/modules/contact/contact_examples.md | Index | List of contact tutorials and indenter examples (introduction, 2D mortar, 2D node-face, 3D Berkovich). |
| moose/modules/contact/doc/content/modules/contact/index.md | Index | Contact module overview: KKT contact theory (g<=0, t_N>=0, t_N*g=0), node/face vs mortar enforcement. |
| moose/modules/contact/doc/content/modules/contact/MortarPerformance.md | Theory | Performance comparison of frictionless mortar vs nodal contact: NCP functions (min, FB, RANFS), iteration counts. |
| moose/modules/contact/doc/content/modules/contact/tutorials/index.md | Index | Landing page listing contact tutorials and example problems. |
| moose/modules/contact/doc/content/modules/contact/tutorials/introduction/answer02a.md | Tutorial | Answer key: sample mortar Lagrange multiplier (normal_lm) along contact subdomain via NodalValueSampler. |
| moose/modules/contact/doc/content/modules/contact/tutorials/introduction/index.md | Tutorial | Intro to contact tutorial: prerequisites (solid mechanics intro), step1 first contact, step2 mortar contact. |
| moose/modules/contact/doc/content/modules/contact/tutorials/introduction/step01.md | Tutorial | Step 1: add penalty/kinematic/mortar frictionless contact via [Contact] action between two cantilevers. |
| moose/modules/contact/doc/content/modules/contact/tutorials/introduction/step02.md | Tutorial | Step 2: migrate node-on-face to mortar contact with Lagrange multipliers on lower-dimensional subdomains. |
| moose/modules/contact/doc/content/modules/contact/TwoDimensionalSphericalIndenterMortar.md | Example | 2D RZ spherical indenter into inelastic material: frictionless mortar contact via NormalNodalLM/NormalMortarMechanicalContact. |
| moose/modules/contact/doc/content/modules/contact/TwoDimensionalSphericalIndenterNodeFace.md | Example | 2D RZ spherical indenter with frictional node-face contact: penalty/kinematic/tangential_penalty + ContactSlipDamper. |

## Multiphysics — combined module

| Path | Type | Description |
|---|---|---|
| moose/modules/combined/doc/content/index.md | Index | Top-level redirect to combined module index page |
| moose/modules/combined/doc/content/modules/combined/examples/current_heating_of_wire.md | Example | Coupled electromagnetics + heat transfer: Joule heating of copper wire at fusing current via magnetic vector potential A-formulation |
| moose/modules/combined/doc/content/modules/combined/examples/stm_laserwelding_dimred.md | Example | Laser-weld melt pool (Navier-Stokes, ALE) with stochastic-tools dimensionality reduction (POD) for full-field surrogate over process params |
| moose/modules/combined/doc/content/modules/combined/examples/stm_thermomechanics.md | Example | Stochastic-tools multiphysics: 3D hollow cylinder thermomechanics with uncertain props, Monte Carlo + polynomial chaos surrogates, sensitivity analysis |
| moose/modules/combined/doc/content/modules/combined/index.md | Index | Combined module overview: links physics modules together for coupled testing/demonstration; embeds tutorials index |
| moose/modules/combined/doc/content/modules/combined/tutorials/index.md | Index | Coupled physics tutorials list: thermo-mechanical intro, stochastic-tools multiphysics, laser welding ROM, EM+heat wire, SIMP topology optimization |
| moose/modules/combined/doc/content/modules/combined/tutorials/introduction/index.md | Index | Intro to coupled thermo-mechanical modeling: three parts (basic coupling, thermal/mechanical contact, multi-body contact) |
| moose/modules/combined/doc/content/modules/combined/tutorials/introduction/step01.md | Tutorial | Thermal mortar contact step 1: adds T variable + Lagrange multiplier heat-flux on mortar subdomain, GapConductanceConstraint |
| moose/modules/combined/doc/content/modules/combined/tutorials/introduction/step02.md | Tutorial | Thermal contact via node-on-face approach (alternate to mortar) for two-block coupled thermo-mechanical contact |
| moose/modules/combined/doc/content/modules/combined/tutorials/introduction/thermomech_answer01.md | Tutorial | Answer: explains where thermo-mechanical coupling enters (eigenstrain temperature parameter, displaced-mesh thermal kernels) |
| moose/modules/combined/doc/content/modules/combined/tutorials/introduction/thermomech_step01.md | Tutorial | Basic thermal/mechanical coupling on a single block: T variable + auto disp_x/disp_y via QuasiStatic action, thermal eigenstrain |
| moose/modules/combined/examples/geochem-porous_flow/forge/rates.md | Theory | Mineral kinetic reaction rate formula and Palandri/Kharaka rate-constant table for the FORGE geochem-porous-flow coupled example |

## Fluid — Navier-Stokes

| Path | Type | Description |
|---|---|---|
| moose/modules/navier_stokes/doc/content/design/linear_fv_cht.md | Theory | Conjugate heat transfer design for the linear FV system via SIMPLE executioner with CHT BCs and interface functors. |
| moose/modules/navier_stokes/doc/content/index.md | Index | Top-level redirect to the Navier-Stokes module landing page. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/cgfe.md | Theory | Continuous Galerkin FE Navier-Stokes (incompressible + compressible) with SUPG/PSPG stabilization and INS RZ notes. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/hcgdgfe.md | Theory | Hybrid CG (pressure) / DG (velocity) FE NS scheme; LBB-stable equal-order, lid-driven cavity walkthrough. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/index.md | Index | NS module landing page summarizing INS/WCNS/CNS/PINS/HDG/CGFE/FV solver variants and capabilities. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/inschorin.md | Theory | Chorin predictor-corrector segregated method for incompressible NS (predict, pressure Poisson, correct). |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/insfv.md | Theory | Incompressible NS finite volume on colocated grid with Rhie-Chow; lid-driven and channel flow examples. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/inshdg.md | Theory | Hybridized DG NS: interior-penalty (advection-dominated) and LDG (diffusion-dominated, superconvergent velocity). |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/laser_welding.md | Example | 3D laser-welding INS+energy on displaced mesh with rotating Gaussian heat flux, SUPG/PSPG, radiative BC. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/linear_wcnsfv.md | Theory | Weakly-compressible NS with linear FV discretization and segregated SIMPLE/PIMPLE solve algorithms. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/pinsfv.md | Theory | Porous media incompressible NS finite volume in superficial velocity with Darcy/Forchheimer friction. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/rans_theory.md | Theory | Turbulence modeling theory: Reynolds averaging, RANS closures (mixing length, k-epsilon) for the NS module. |
| moose/modules/navier_stokes/doc/content/modules/navier_stokes/wcnsfv.md | Theory | Weakly-compressible FV NS extending INSFV with functor density; lid-driven heated cavity and heated channel. |
| moose/modules/navier_stokes/doc/intro/modules/navier_stokes/intro/index.md | Tutorial | NS Workshop introductory slide deck overviewing fluid types, flow regimes, and module capabilities. |

## Fluid — porous flow

| Path | Type | Description |
|---|---|---|
| moose/modules/porous_flow/doc/content/index.md | Index | Top-level entry that redirects to the porous_flow module index page |
| moose/modules/porous_flow/doc/content/modules/porous_flow/1Dradial.md | Example | 1D radial CO2 injection well intercomparison (Pruess problem 3) with similarity solution |
| moose/modules/porous_flow/doc/content/modules/porous_flow/additional_objects.md | Index | Catalog of Actions, AuxKernels, postprocessors, and other helper objects in PorousFlow |
| moose/modules/porous_flow/doc/content/modules/porous_flow/ates.md | Example | Aquifer Thermal Energy Storage: hot/cold water cycling in subsurface aquifers (Sheldon 2021) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/boundaries.md | Theory | Boundary conditions: PorousFlowSink family and PorousFlowOutflowBC for free boundaries |
| moose/modules/porous_flow/doc/content/modules/porous_flow/brineco2.md | Theory | High-precision brine-CO2 EOS with mutual solubility for geological CO2 storage in saline aquifers |
| moose/modules/porous_flow/doc/content/modules/porous_flow/capillary_pressure.md | Theory | Capillary pressure theory and PorousFlow conventions (Young-Laplace, P_c = P_nw - P_w) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/co2_intercomparison.md | Example | Index of CO2 storage in saline aquifer benchmark/intercomparison problems (Pruess) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/coal_mining.md | Example | Underground longwall coal-mining simulation with goaf collapse, fluid flow, geomechanics |
| moose/modules/porous_flow/doc/content/modules/porous_flow/compositional_flash.md | Theory | Rachford-Rice compositional flash to partition fluid components among phases for persistent variables |
| moose/modules/porous_flow/doc/content/modules/porous_flow/contents.md | Index | A-to-Z auto-generated index of all PorousFlow documentation pages |
| moose/modules/porous_flow/doc/content/modules/porous_flow/convergence.md | Theory | Setting nl_abs_tol/snes_atol appropriately for fluid, heat, and mechanics PorousFlow problems |
| moose/modules/porous_flow/doc/content/modules/porous_flow/dictator.md | Theory | PorousFlowDictator UserObject that holds nonlinear-variable, phase, and component metadata |
| moose/modules/porous_flow/doc/content/modules/porous_flow/diffusivity.md | Theory | Diffusion coefficient and tortuosity material models for dispersive flux kernel |
| moose/modules/porous_flow/doc/content/modules/porous_flow/flow_models.md | Index | Catalog of available flow models: single/multiphase, water-steam, water-NCG, brine-CO2 |
| moose/modules/porous_flow/doc/content/modules/porous_flow/flow_through_fractured_media.md | Example | Index: fractured-medium flow strategies (mesh-incorporated vs MultiApp-decoupled) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/fluidflower.md | Example | FluidFlower international CO2-storage benchmark in Hele-Shaw apparatus (Bergen) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/fluids.md | Theory | Using FluidProperties module UserObjects to supply density, viscosity, enthalpy in PorousFlow |
| moose/modules/porous_flow/doc/content/modules/porous_flow/getting_started_with_pf.md | Tutorial | Building the PorousFlow executable and first steps using the module |
| moose/modules/porous_flow/doc/content/modules/porous_flow/governing_equations.md | Theory | Full TH(M)C governing equations: mass conservation per species, Darcy flux, heat, mechanics, chemistry |
| moose/modules/porous_flow/doc/content/modules/porous_flow/groundwater_models.md | Example | Groundwater modeling with hydraulic-head/porepressure conversions, vadose zone, recharge |
| moose/modules/porous_flow/doc/content/modules/porous_flow/heterogeneous_models.md | Example | Heterogeneous rock-property models (SPE10) with permeability/porosity from external data |
| moose/modules/porous_flow/doc/content/modules/porous_flow/hysteresis.md | Theory | Hysteretic capillary pressure and rel-perm following TOUGH; turning-point curves of orders 0-3 |
| moose/modules/porous_flow/doc/content/modules/porous_flow/index.md | Index | PorousFlow module landing page: multiphase/multicomponent THMC fluid+heat flow in porous media |
| moose/modules/porous_flow/doc/content/modules/porous_flow/kt_worked.md | Theory | Worked 1D heat-advection example illustrating Kuzmin-Turek algorithm step by step |
| moose/modules/porous_flow/doc/content/modules/porous_flow/kt.md | Theory | Using Kuzmin-Turek TVD flux-limited stabilization in PorousFlow inputs |
| moose/modules/porous_flow/doc/content/modules/porous_flow/lagrangian_eulerian.md | Theory | Lagrangian vs Eulerian coordinate frames and continuity equation derivation for deforming skeleton |
| moose/modules/porous_flow/doc/content/modules/porous_flow/lava_lamp.md | Example | Density-driven convective mixing of CO2 dissolving into brine (single- and two-phase) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/mass_lumping.md | Theory | Mass-lumping discretization of time derivatives for fluid and heat conservation |
| moose/modules/porous_flow/doc/content/modules/porous_flow/material_laws.md | Index | Index of constitutive material laws: capillary pressure, rel perm, perm, porosity, diffusivity, hysteresis |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_diffusion.md | Example | Mixed-dimension diffusion in fracture-matrix system using MultiApp transfers |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_equations.md | Theory | Mathematical/physical formulation of mixed-dimension fracture-matrix heat and mass equations |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_introduction.md | Example | MultiApp fracture-flow approach intro: lower-D fracture mesh decoupled from matrix mesh |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_PorousFlow_2D.md | Example | MultiApp PorousFlow simulation of single matrix system with fracture in 2D |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_PorousFlow_3D.md | Example | MultiApp PorousFlow simulation of 3D fracture network embedded in matrix |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_primer.md | Example | MultiApp primer with non-fractured diffusion to quantify MultiApp coupling errors |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiapp_fracture_flow_transfers.md | Theory | Description of MultiApp Reporter/InterpolationTransfer types used in fracture-flow models |
| moose/modules/porous_flow/doc/content/modules/porous_flow/multiphase.md | Theory | Two-phase flow formulations: PP and PS variable choices with hysteretic variants |
| moose/modules/porous_flow/doc/content/modules/porous_flow/natural_convection.md | Example | Elder problem: natural convection in 2D porous tank heated from below |
| moose/modules/porous_flow/doc/content/modules/porous_flow/nomenclature.md | Theory | Symbol/units/description table for all variables used in PorousFlow documentation |
| moose/modules/porous_flow/doc/content/modules/porous_flow/nomultiapp_flow_through_fractured_media.md | Example | Mesh-incorporated explicit fractures using lower-dimensional elements with full Jacobian |
| moose/modules/porous_flow/doc/content/modules/porous_flow/nonlinear_convergence_problems.md | Theory | Diagnosing and fixing nonlinear convergence failures in PorousFlow (EOS, BCs, stabilization) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/numerical_diffusion.md | Theory | Sources of artificial numerical diffusion and comparison of stabilization schemes |
| moose/modules/porous_flow/doc/content/modules/porous_flow/permeability.md | Theory | Permeability tensor models: constant, spatially varying from AuxVariable, porosity-dependent |
| moose/modules/porous_flow/doc/content/modules/porous_flow/persistent_variables.md | Theory | Choice of primary variables for miscible multiphase flows where phases appear/disappear |
| moose/modules/porous_flow/doc/content/modules/porous_flow/porosity.md | Theory | Porosity formulations: constant, linear, function of porepressure/strain/temperature/chemistry |
| moose/modules/porous_flow/doc/content/modules/porous_flow/porous_flow_examples.md | Index | Master list of PorousFlow tutorials and example problems |
| moose/modules/porous_flow/doc/content/modules/porous_flow/relative_permeability.md | Theory | Relative permeability formulations as functions of effective phase saturation |
| moose/modules/porous_flow/doc/content/modules/porous_flow/restart.md | Example | Restart/recover: hydrostatic gravity equilibration then gas injection on the same reservoir |
| moose/modules/porous_flow/doc/content/modules/porous_flow/singlephase.md | Theory | Single-phase flow Materials: fully saturated, partially saturated, hysteretic capillary pressure |
| moose/modules/porous_flow/doc/content/modules/porous_flow/sinks.md | Theory | Point and line source/sink DiracKernels (constant, polyline, borehole) for fluid and heat |
| moose/modules/porous_flow/doc/content/modules/porous_flow/solute_tracer_transport.md | Example | 1D and 2D solute tracer advection-diffusion-dispersion through saturated porous media |
| moose/modules/porous_flow/doc/content/modules/porous_flow/solvers.md | Theory | Recommended PETSc preconditioners and Krylov solvers for PorousFlow simulations |
| moose/modules/porous_flow/doc/content/modules/porous_flow/stabilization.md | Theory | Numerical stabilization overview (mass lumping, full upwinding, KT, numerical diffusion) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/systems.md | Index | Auto-generated complete syntax documentation for PorousFlowApp |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests.md | Index | Index of QA regression tests with analytical or benchmark verification |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/actions/actions_tests.md | Index | Actions tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/aux_kernels/aux_kernels_tests.md | Index | AuxKernels tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/avdonin/1d_avdonin.md | Theory | Avdonin/Ross 1D analytical heat+mass transport from cold-water injection into warm reservoir |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/avdonin/1d_radial_avdonin.md | Theory | Avdonin/Ross 1D radial analytical heat+mass transport from cold-water injection well |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/basic_advection/basic_advection_tests.md | Index | Basic advection tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/buckley_leverett/buckley_leverett_tests.md | Theory | Buckley-Leverett single-phase saturation-front advection benchmark |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/capillary_pressure/capillary_pressure_tests.md | Theory | Tests of Brooks-Corey, van Genuchten and other capillary-pressure curves with log-extension |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/chemistry/chemistry_tests.md | Index | Chemistry tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/density/density_tests.md | Index | Density tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/desorption/desorption_tests.md | Index | Desorption tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/dirackernels/dirackernels_tests.md | Theory | Geometric tests of point/line sinks: nodal placement, polyline boreholes, fluid+heat withdrawal |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/dispersion/dispersion_tests.md | Theory | Classical 1D diffusion profile and hydrodynamic dispersion verification |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/energy_conservation/energy_conservation_tests.md | Index | Energy conservation tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/fluids/fluids_tests.md | Index | Fluids tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/fluidstate/fluidstate_tests.md | Theory | Multi-phase multi-component radial Theis-style injection with similarity solution |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/flux_limited_TVD_advection/flux_limited_TVD_advection_tests.md | Index | Flux-limited TVD advection tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/flux_limited_TVD_pflow/flux_limited_TVD_pflow_tests.md | Index | Flux-limited TVD PorousFlow tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/functions/functions_tests.md | Index | Functions tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/gravity/gravity_tests.md | Theory | 1D gravitational head equilibrium tests against P(x)=P0-rho*g*x analytic solution |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/heat_advection/heat_advection_tests.md | Theory | 1D heat advection in saturated bar with fixed pressure ends |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/heat_conduction/heat_conduction_tests.md | Theory | Pure heat-conduction tests with PorousFlow energy equation simplifications |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/heterogeneous_materials/heterogeneous_materials_tests.md | Index | Heterogeneous-materials tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/infiltration_and_drainage/infiltration_and_drainage_tests.md | Theory | Constant-rainfall recharge into 1D unsaturated column with 2-phase analytic infiltration |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/jacobian/jacobian_tests.md | Theory | Jacobian verification: analytical full Jacobian wrt PorousFlow nonlinear variables |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/mass_conservation/mass_conservation_tests.md | Theory | Verification of fluid-mass postprocessor and mass balance for single/multi-phase systems |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/newton_cooling/newton_cooling_tests.md | Theory | Newton cooling and 1D bar fluid+heat response benchmarks against analytical solutions |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/non_thermal_equilibrium/non_thermal_equilibrium_tests.md | Index | Non-thermal-equilibrium (rock-fluid) tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/numerical_diffusion/numerical_diffusion_tests.md | Index | Numerical diffusion tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/plastic_heating/plastic_heating_tests.md | Theory | Plastic heat-energy generation kernel: c*(1-phi)*sigma:eps_plastic verified |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/poro_elasticity/poro_elasticity_tests.md | Theory | Poroelasticity tests: saturated single-phase fluid coupled to small-strain elasticity |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/poroperm/poroperm_tests.md | Index | Porosity/permeability evolution tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/pressure_pulse/pressure_pulse_tests.md | Theory | 1D Darcy pressure-pulse evolution test against analytical exponential-density solution |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/radioactive_decay/radioactive_decay_tests.md | Index | Radioactive decay tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/relperm/relperm_tests.md | Theory | Tests of Brooks-Corey, Corey, FLAC, and other relative-permeability formulations |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/rogers_stallybrass_clements/rogers_stallybrass_clements_tests.md | Index | Rogers-Stallybrass-Clements unsaturated test page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/sinks/sinks_tests.md | Theory | Sink/source BC tests for full-upwinded fluid and heat boundary fluxes |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/thermal_conductivity/thermal_conductivity_tests.md | Index | Thermal conductivity tests page (placeholder/TODO) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tests/thm_rehbinder/thm_rehbinder_tests.md | Theory | Rehbinder cylindrical THM analytical benchmark (heated/pressurized cavity, steady state) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/thm_example.md | Example | Cold CO2 injection into elastic reservoir - 2-phase THM (LaForce semi-analytical) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/thmc_example.md | Example | Cold CO2 injection with reactive geochemistry - 2-phase THMC kinetic dissolution |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tidal.md | Example | Earth-tide, barometric, and oceanic tidal effects on porepressure for hydrogeological inversion |
| moose/modules/porous_flow/doc/content/modules/porous_flow/time_derivative.md | Theory | Numerical implementation of time derivatives with mass lumping in mechanically-coupled deforming meshes |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_00.md | Tutorial | PorousFlow tutorial table of contents (pages 01-13) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_01.md | Tutorial | Tutorial 01: single-fluid Darcy flow with poroelastic and thermal coupling terms |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_02.md | Tutorial | Tutorial 02: numerical issues - Newton solve, Jacobian, lumping, stabilization choices |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_03.md | Tutorial | Tutorial 03: adding heat advection and conduction to the fluid-flow model |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_04.md | Tutorial | Tutorial 04: adding solid mechanics with effective stress and thermal expansion (THM) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_05.md | Tutorial | Tutorial 05: replacing simple fluid with realistic Water97 IAPWS equation of state |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_06.md | Tutorial | Tutorial 06: adding a multi-component tracer using PorousFlowFullySaturated action |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_07.md | Tutorial | Tutorial 07: chemically reactive precipitating tracer with porosity and permeability evolution |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_08.md | Tutorial | Tutorial 08: PorousFlowSink boundary conditions and unsaturated flow with rel perm |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_09.md | Tutorial | Tutorial 09: overview of PorousFlow architecture - kernels, materials, properties, naming |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_10.md | Tutorial | Tutorial 10: building unsaturated-flow input from raw Kernels and Materials without Actions |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_11.md | Tutorial | Tutorial 11: full two-phase THM borehole CO2 injection model from scratch |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_12.md | Tutorial | Tutorial 12: boundary sinks/sources and polyline (borehole/river) sources placeholder page |
| moose/modules/porous_flow/doc/content/modules/porous_flow/tutorial_13.md | Tutorial | Tutorial 13: more elaborate aqueous chemistry (dolomite-style precipitation/dissolution) |
| moose/modules/porous_flow/doc/content/modules/porous_flow/upwinding.md | Theory | Full upwinding for nonlinear advection; default scheme to avoid withdrawing fluid from empty nodes |
| moose/modules/porous_flow/doc/content/modules/porous_flow/water_vapor.md | Theory | Water-steam single-component two-phase EOS using porepressure-enthalpy persistent variables |
| moose/modules/porous_flow/doc/content/modules/porous_flow/waterncg.md | Theory | Miscible water + non-condensable gas EOS using Henry's law for NCG mass fraction |
| moose/modules/porous_flow/doc/theory/theory.pdf | PDF | Compiled PorousFlow theory manual: physics equations, EOS, mechanics, chemistry, BC, line sinks |
| moose/modules/porous_flow/joss_paper.md | Theory | JOSS submission paper metadata for PorousFlow (THMC multiphysics Darcy code) |
| moose/modules/porous_flow/README.md | Index | Module README pointing to online PorousFlow docs and getting-started resources |

## Fluid — thermal hydraulics & subchannel

| Path | Type | Description |
|---|---|---|
| moose/modules/subchannel/doc/content/index.md | Index | Top-level redirect to the SCM module landing page. |
| moose/modules/subchannel/doc/content/modules/subchannel/examples/examples-list.md | Index | SCM examples list (currently: thermo-mechanical coupling demonstration). |
| moose/modules/subchannel/doc/content/modules/subchannel/examples/quad_thermo_mech.md | Example | One-pin/four-square-subchannel SCM coupled to 2D-RZ thermo-mechanical fuel-pin sub-app via MultiApp. |
| moose/modules/subchannel/doc/content/modules/subchannel/general/publication_list.md | Index | List of SCM-related publications (development, demonstrations, validation papers). |
| moose/modules/subchannel/doc/content/modules/subchannel/general/subchannel_theory.md | Theory | Subchannel governing equations: integral mass, axial momentum, lateral momentum, energy on subchannel control volumes with crossflow. |
| moose/modules/subchannel/doc/content/modules/subchannel/general/user_notes.md | Index | User notes on SCM index/numbering conventions for square and hexagonal lattices. |
| moose/modules/subchannel/doc/content/modules/subchannel/general/using_SubChannel.md | Tutorial | Running `subchannel-opt -i ...` and inspecting outputs of SCM input files. |
| moose/modules/subchannel/doc/content/modules/subchannel/index.md | Index | SCM module landing page: single-phase subchannel TH for water/Pb/Na/LBE-cooled square or hexagonal pin bundles. |
| moose/modules/subchannel/doc/content/modules/subchannel/syntax.md | Index | Auto-generated complete syntax index for SubChannelApp. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/areva_fctf.md | Example | AREVA FCTF 61-pin wire-wrapped deformed-duct LMFBR validation case. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/EBR-II.md | Example | EBR-II SHRT-17 protected loss-of-flow validation in liquid-sodium-cooled metallic-fuel core. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/enthalpy.md | Example | Enthalpy-mixing-model verification with turbulent momentum and enthalpy mixing terms. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/friction.md | Example | Friction-model verification: two-channel unequal-hydraulic-diameter problem with analytical equilibrium. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/ornl_19_pin.md | Example | ORNL 19-pin SFR-bundle validation against test-series-2 thermal-hydraulic measurements. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/pnnl_12_pin.md | Example | PNNL 2x6 mixed (free+forced) convection benchmark validation under low-flow conditions. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/pnnl_blockage.md | Example | PNNL 7x7 sleeve-blockage benchmark validation simulating PWR clad ballooning during LOCAs. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/PSBT.md | Example | PSBT 5x5 OECD/NRC/NUPEC steady-state mixing benchmark validation in water. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/thors.md | Example | THORS bundle 3A 19-pin LMFBR partial-blockage validation (central 6-channel blockage). |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/toshiba_37_pin.md | Example | Toshiba 37-pin liquid-sodium buoyancy benchmark validation with chopped-cosine axial power. |
| moose/modules/subchannel/doc/content/modules/subchannel/v&v/v&v-list.md | Index | V&V catalog: friction/enthalpy verification; PSBT, PNNL, AREVA, EBR-II, ORNL, Toshiba, THORS validations. |
| moose/modules/subchannel/doc/tutorial/modules/subchannel/tutorial/index.md | Tutorial | SCM tutorial slide deck outline: MOOSE intro, SCM intro, examples. |
| moose/modules/subchannel/doc/tutorial/modules/subchannel/tutorial/moose_intro.md | Tutorial | Tutorial slides introducing the MOOSE framework. |
| moose/modules/subchannel/doc/tutorial/modules/subchannel/tutorial/subchannel_examples.md | Tutorial | Tutorial slides with square-lattice (PSBT) and hexagonal-lattice (ORNL) example pointers. |
| moose/modules/subchannel/doc/tutorial/modules/subchannel/tutorial/subchannel_intro.md | Tutorial | Tutorial slides introducing SCM motivation (vs CFD/system codes) and methodology. |
| moose/modules/thermal_hydraulics/doc/content/index.md | Index | Top-level redirect to the THM module landing page. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/flow_boundary.md | Theory | Flow-boundary components: connect via `input=channel:in/out` to apply BCs at channel ends. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/flow_channel.md | Index | 1D flow-channel components: ElbowPipe1Phase and FlowChannel1Phase. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/flow_junction.md | Index | 0D flow junctions: gate valve, one-to-one, parallel-channels, pump, shaft-connected compressor/pump/turbine, simple turbine, volume junction. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_2d_mesh.md | Theory | Auto-generated blocks/boundaries (`<cname>:inner/outer`, axial sections) for 2D heat structures. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_2d.md | Theory | 2D heat structures (cylindrical/plate) and their temperature-norm convergence criterion. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_boundary_formulation_dirichlet.md | Theory | Dirichlet BC for heat structure: $T = T_b$ on $\Gamma$. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_boundary_formulation_neumann.md | Theory | Neumann BC for heat structure: $k\nabla T\cdot n = q_b$ (incoming heat flux). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_boundary.md | Index | Heat-structure boundary components: ambient/external-app convection, heat flux, radiation, specified temperature. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_formulation.md | Theory | Heat conduction PDE $\rho c_p \partial_t T - \nabla\cdot(k\nabla T) = q'''$ with weak/Galerkin form. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_heat_source.md | Index | Heat-structure volumetric source components: HeatSourceFromPowerDensity, HeatSourceFromTotalPower. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure_variables.md | Theory | Heat-structure variable: solid temperature `T_solid` [K]. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_structure.md | Index | Heat-structure components: 3D-from-file, 2D cylindrical, and 2D plate heat structures. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_transfer_1phase_formulation.md | Theory | Single-phase wall heat flux contribution: $\partial_t(\rho E A) = \dots + q_\text{wall} P_\text{heat}$. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_transfer_1phase.md | Index | Single-phase heat-transfer components for FlowChannel1Phase. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/heat_transfer.md | Index | Heat-transfer components that add heat sources to flow channels (heat-flux, heat-structure, specified-temperature, external-app variants). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/power.md | Index | Power components: provide auxiliary scalar `<comp>:power`; currently TotalPower. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/component_groups/volume_junction.md | Index | Volume-junction subset of flow junctions (those with finite volume rather than zero-thickness interface). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/deprecations/index.md | Index | List of THM deprecations by date (currently empty). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/examples/brayton_cycle/brayton_cycle.md | Example | Open and closed Brayton cycle: shaft, motor, compressor, turbine, generator with heat source/sink. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/examples/index.md | Index | Examples index linking to Brayton and recuperated Brayton cycle examples. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/examples/recuperated_brayton_cycle/recuperated_brayton_cycle.md | Example | Recuperated open Brayton PCU with PID-controlled motor startup transient and recuperator heat structure. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/getting_started.md | Tutorial | Build instructions for the standalone `thm-opt` executable from `modules/thermal_hydraulics`. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/howto/thm_ad_migration_guide.md | Tutorial | Guide for migrating THM input files to AD-aware materials/objects. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/index.md | Index | THM module landing page; links theory, tutorials, examples, components, controls, closures. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/paraview_basics.md | Tutorial | Basic Paraview usage for visualizing Exodus output produced by THM runs. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/peacock/FlowChannelParametersCalculator.md | Index | Peacock widget that computes flow-area, hydraulic diameter, and wetted perimeter from channel geometry. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/peacock/THMPlugins.md | Index | THM Peacock plugins index (FlowChannelParametersCalculator, unit conversion, FluidPropertiesInterrogator). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/syntax.md | Index | Auto-generated complete syntax index for ThermalHydraulicsApp. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/test_problems/index.md | Example | Catalog of THM verification problems: shock tubes (Sod, Lax, Woodward-Colella), Sedov, water hammer, MMS, natural circulation. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/theory_manual/gas_mix_model/index.md | Theory | Binary gas-mixture flow: VACE plus species continuity with Fickian diffusion and diffusive enthalpy flux. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/theory_manual/index.md | Theory | Theory manual index pointing to VACE (compressible Euler) and gas-mix models. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/theory_manual/vace_model/flow_equations.md | Theory | 1D variable-area Euler mass/momentum/energy equations with friction, gravity, heat source; passive scalar transport. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/theory_manual/vace_model/index.md | Theory | Variable-area compressible Euler (VACE) flow model: 1D single-phase compressible duct flow. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/theory_manual/vace_model/volume_junction.md | Theory | Volume-junction conservation-law derivation: integral form over 0D control volume connecting flow channels. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/thm_tutorial.md | Tutorial | Slide-deck-style THM tutorial (outline of MOOSE/THM concepts and physics). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/basics/execution.md | Tutorial | Running a THM input file with `thm-opt -i ...` and threaded execution flags. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/basics/finish.md | Tutorial | Closing page for the basics tutorial. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/basics/index.md | Tutorial | Basics tutorial index: how to run THM, structure of input file, and inspect output. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/basics/input_file.md | Tutorial | Anatomy of a THM input file (templated content). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/basics/output.md | Tutorial | Inspecting Exodus output from THM runs. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/finish.md | Tutorial | Closing page for the single-phase flow tutorial. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/index.md | Tutorial | Index for the single-phase primary-loop tutorial (helium primary, water secondary, heat exchanger). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/problem_description.md | Tutorial | Problem description: helium primary loop with pump and heat exchanger, water secondary side. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/step01.md | Tutorial | Step 1: single flow channel with mass-flow inlet and pressure outlet boundary conditions. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/step02.md | Tutorial | Step 2: conjugate heat transfer between heated solid block and flow channel. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/step03.md | Tutorial | Step 3: upper loop with volume junctions and convective wall-temperature heat transfer. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/step04.md | Tutorial | Step 4: close the primary loop and add PID-controlled pump for prescribed mass flow rate. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/step05.md | Tutorial | Step 5: secondary side of heat exchanger with time-varying inlet mass flow rate. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/tutorials/single_phase_flow/step06.md | Tutorial | Step 6: defining custom closure sets for friction/heat-transfer correlations. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/user/closures.md | Index | Closures user guide stub (closure relations for friction, wall heat transfer, etc.). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/user/command_line_args.md | Index | Reference table of useful command-line flags (`-i`, `--check-input`, `--n-threads`, etc.). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/user/control_logic.md | Index | Control-logic user guide stub for the THM ControlLogic system. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/user/non_overlapping_coupling.md | Theory | Non-overlapping coupling: BC-to-BC transfer of pressure / mass-flow / temperature between two flow simulations. |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/user/parallel_execution.md | Index | Running THM in parallel (stub). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/user/postprocessing.md | Index | Postprocessing in THM (stub). |
| moose/modules/thermal_hydraulics/doc/content/modules/thermal_hydraulics/utilities.md | Index | THM Peacock plugins: fluid-property interrogator, unit converter, FlowChannelParametersCalculator. |
| moose/modules/thermal_hydraulics/joss_paper/joss_paper.md | Theory | JOSS paper describing THM as a 1D variable-area compressible single-phase flow + 2D/3D heat-conduction module. |
| moose/modules/thermal_hydraulics/README.md | Index | Repo README: THM is a common base for MOOSE-based 1D thermal-hydraulic apps. |

## Fluid — FSI, level set, scalar transport, DG, fluid properties

| Path | Type | Description |
|---|---|---|
| moose/modules/fluid_properties/doc/content/index.md | Index | Top-level redirect to the fluid_properties module landing page |
| moose/modules/fluid_properties/doc/content/modules/fluid_properties/index.md | Index | Fluid properties module: consistent FluidProperties UserObject system supplying EOS data (density, viscosity, etc.) to other physics modules. |
| moose/modules/fluid_properties/doc/content/utils/FluidPropertiesUtils.md | Theory | Utility solvers used by fluid EOS classes: 1D and 2D Newton solvers and Brent's method root-finder (from Numerical Recipes) |
| moose/modules/fsi/doc/content/index.md | Index | Top-level FSI module landing redirect to module index page. |
| moose/modules/fsi/doc/content/modules/fsi/fsi_acoustics.md | Theory | Acoustic FSI formulation: inviscid/irrotational fluid wave equation coupled to elastic structure with displacement/stress continuity at interface. |
| moose/modules/fsi/doc/content/modules/fsi/index.md | Index | FSI module overview; acoustic-fluid + elastic-structure coupling, plug-and-play physics, ALE planned. |
| moose/modules/fsi/doc/content/modules/fsi/systems.md | Index | Auto-generated complete syntax listing for FsiApp objects (kernels, BCs, etc.). |
| moose/modules/level_set/doc/content/index.md | Index | Top-level level_set module landing redirect to module index page. |
| moose/modules/level_set/doc/content/modules/level_set/example_circle.md | Example | Constant-velocity 2D circle advection benchmark with periodic BCs and LevelSetOlssonBubble IC. |
| moose/modules/level_set/doc/content/modules/level_set/example_rotate.md | Example | Rotating-bubble benchmark in [-1,1]^2 with v=(4y,-4x); plain, SUPG, and reinitialization MultiApp variants. |
| moose/modules/level_set/doc/content/modules/level_set/example_vortex.md | Example | Olsson vortex benchmark; bubble advected by reversing vortex field, returns at t=2; plain/SUPG/reinit comparison. |
| moose/modules/level_set/doc/content/modules/level_set/index.md | Index | Level set module overview, examples list, future tasks (reinit, GLS, shock capturing), and complete syntax. |
| moose/modules/level_set/doc/content/modules/level_set/level_set_examples.md | Index | Linked list of the three benchmark examples (circle, rotate, vortex). |
| moose/modules/level_set/doc/content/modules/level_set/theory.md | Theory | Level set front-tracking via multi-D advection of signed-distance field; Galerkin FE, SUPG stabilization, Olsson conservative reinitialization. |
| moose/modules/rdg/doc/content/index.md | Index | Top-level rDG module landing redirect to module index page. |
| moose/modules/rdg/doc/content/modules/rdg/index.md | Theory | rDG(P0P1) cell-centered FVM library for convection-dominated problems: slope reconstruction, limiting, numerical flux, BCs; advection example. |
| moose/modules/scalar_transport/doc/content/index.md | Index | Top-level scalar_transport module landing redirect to module index page. |
| moose/modules/scalar_transport/doc/content/modules/scalar_transport/index.md | Index | Scalar Transport module landing page (stub heading; relies on auto-generated syntax for content). |

## Phase field

| Path | Type | Description |
|---|---|---|
| moose/modules/phase_field/doc/content/index.md | Index | Phase field module landing pointer (forwards to modules/phase_field/index.md). |
| moose/modules/phase_field/doc/content/modules/phase_field/Actions.md | Theory | Custom phase field actions (NonconservedAction, ConservedAction) auto-create variables and kernels for AC/CH equations. |
| moose/modules/phase_field/doc/content/modules/phase_field/Anisotropy.md | Theory | Anisotropic mobility/interfacial energy kernels and materials (CahnHilliardAniso, CHInterfaceAniso, GBAnisotropy, MatAnisoDiffusion). |
| moose/modules/phase_field/doc/content/modules/phase_field/CALPHAD.md | Theory | Using `*.tdb` thermodynamic databases via `free_energy.py`/pycalphad to generate DerivativeParsedMaterial free energy blocks. |
| moose/modules/phase_field/doc/content/modules/phase_field/Derivation_explanations.md | Theory | Mathematical primer: divergence theorem, product rule, fundamental lemma of variations used in deriving CH/AC residuals. |
| moose/modules/phase_field/doc/content/modules/phase_field/Elastic_Driving_Force_Grain_Growth.md | Theory | Couples mechanics into grain growth: per-grain rotated elasticity tensor weighted by switching function adds elastic driving force. |
| moose/modules/phase_field/doc/content/modules/phase_field/FAQ.md | Theory | FAQ on interface width vs mesh spacing, resolution rules of thumb (4-5 elements through interface). |
| moose/modules/phase_field/doc/content/modules/phase_field/FunctionMaterialKernels.md | Theory | Kernels (CahnHilliard, SplitCHParsed, AllenCahn) consume FreeEnergy material objects with auto-differentiated derivatives. |
| moose/modules/phase_field/doc/content/modules/phase_field/FunctionMaterials.md | Theory | FunctionMaterialBase family: ParsedMaterial, DerivativeParsedMaterial, DerivativeSumMaterial, ElasticEnergyMaterial, etc. |
| moose/modules/phase_field/doc/content/modules/phase_field/FunctionMaterials/AutomaticDifferentiation.md | Theory | FParser AutoDiff feature in MOOSE's bundled function parser library; generates symbolic derivatives for free energies. |
| moose/modules/phase_field/doc/content/modules/phase_field/FunctionMaterials/ExpressionBuilder.md | Theory | C++ operator-overloaded EBTerm/EBFunction API for building FParser expressions at compile time inside MOOSE classes. |
| moose/modules/phase_field/doc/content/modules/phase_field/FunctionMaterials/FreeEnergy.md | Theory | Free energy function-material approach; example MathFreeEnergy with derivatives needed for direct vs split CH solves. |
| moose/modules/phase_field/doc/content/modules/phase_field/FunctionMaterials/JITCompilation.md | Theory | FParser JIT compilation generates compiled native code from parsed expressions for speedup. |
| moose/modules/phase_field/doc/content/modules/phase_field/Grain_Boundary_Anisotropy.md | Theory | Moelans 2008 parameterization (L, kappa, gamma, mu) of phase field params from GB energy and mobility for poly grain growth. |
| moose/modules/phase_field/doc/content/modules/phase_field/Grain_Growth_Model.md | Theory | Multi-order-parameter Allen-Cahn grain growth model (Chen-Yang 1994, Moelans 2008); curvature-driven GB migration. |
| moose/modules/phase_field/doc/content/modules/phase_field/ICs/EBSD.md | Theory | Reading experimental EBSD data via EBSDMesh + EBSDReader UserObject + ReconVarIC for polycrystal microstructure ICs. |
| moose/modules/phase_field/doc/content/modules/phase_field/ICs/MPS.md | Theory | Maximal Poisson-Disk Sampling via Trilinos MeshingGenie to generate equiaxed RCP grain centroids for PolycrystalVoronoi. |
| moose/modules/phase_field/doc/content/modules/phase_field/ICs/PolycrystalICs.md | Theory | Polycrystal initial conditions via Voronoi/hex/circle/file with graph-coloring for reduced-OP grain assignment. |
| moose/modules/phase_field/doc/content/modules/phase_field/index.md | Index | Phase field module landing page; links to equations, multiphase models, mechanics coupling, ICs, grain growth. |
| moose/modules/phase_field/doc/content/modules/phase_field/Initial_Conditions.md | Theory | Catalog of phase field IC objects (BoundingBoxIC, RndBoundingBoxIC, etc.) for setting up initial microstructures. |
| moose/modules/phase_field/doc/content/modules/phase_field/Linearized_Interface_Grain_Growth.md | Theory | Change-of-variable (psi = atanh of phi) linearizes tanh interface profile so coarser meshes resolve grain boundaries. |
| moose/modules/phase_field/doc/content/modules/phase_field/Mechanics_Coupling.md | Theory | Two-way coupling of phase field with solid_mechanics: variable elasticity/eigenstrain plus elastic free-energy contribution. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/GrandPotentialMultiphase.md | Theory | Grand-potential-density model (Aagesen 2018) for arbitrary phases/grains/components; chemical potential as primary variable. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/KKS.md | Theory | Kim-Kim-Suzuki two-phase model (kim 1999) with per-phase concentrations decoupling interface energy from interface width. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/KKSAnalytical.md | Theory | Analytical 1D-equilibrium KKS solution (tanh order parameter, switching-function weighted composition) for verification. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/KKSDerivations.md | Theory | Derivations of KKS residuals/Jacobians for split CH kernels and KKS material naming conventions. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/KKSMultiComponentExample.md | Example | KKS extended to n components: extra CH equations and KKSPhaseConcentration/ChemicalPotential constraint kernels per added component. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/SLKKS.md | Theory | Sublattice KKS (Schwen 2021): per-sublattice concentrations with equal chemical potential constraint via SLKKSChemicalPotential. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/WBM.md | Theory | Multiphase WBM model: n phases with n order parameters and Lagrange-multiplier constraint that h_i sums to one. |
| moose/modules/phase_field/doc/content/modules/phase_field/MultiPhase/WBMTwoPhase.md | Theory | WBM two-phase model: single order parameter switches between two phase free energies via DerivativeTwoPhaseMaterial. |
| moose/modules/phase_field/doc/content/modules/phase_field/Nucleation/conservednoise_include.md | Theory | ConservedLangevinNoise kernel doc fragment listing conserved (uniform/normal, masked variants) noise user objects. |
| moose/modules/phase_field/doc/content/modules/phase_field/Nucleation/DiscreteNucleation.md | Theory | Discrete nucleation system (Inserter/Map/Material/Marker/Postprocessor) introducing nuclei via free-energy penalty. |
| moose/modules/phase_field/doc/content/modules/phase_field/Nucleation/LangevinNoise.md | Theory | Stable per-timestep Langevin noise injection into PDEs for fluctuation-driven nucleation; conserved variants supported. |
| moose/modules/phase_field/doc/content/modules/phase_field/Phase_Field_Equations.md | Theory | Foundational Cahn-Hilliard (conserved) and Allen-Cahn (nonconserved) PDE formulations with free energy functional. |
| moose/modules/phase_field/doc/content/modules/phase_field/Phase_Field_Model_Units.md | Theory | Dimensional analysis of phase field equations covering free energy, gradient coefficients, mobility, time-evolution units. |
| moose/modules/phase_field/doc/content/modules/phase_field/Quantitative.md | Theory | Two-phase polynomial free energies (4th, 6th, 8th order) replacing logarithmic thermodynamic form for easier convergence. |
| moose/modules/phase_field/doc/content/modules/phase_field/Solving.md | Theory | Recommended PETSc solver settings for phase field models: NEWTON/PJFNK/JFNK and LU/preconditioning options. |
| moose/modules/phase_field/doc/content/modules/phase_field/systems.md | Index | Auto-generated registered-systems syntax landing for the PhaseFieldApp. |
| moose/modules/phase_field/doc/content/modules/phase_field/Tutorial.md | Tutorial | Spinodal decomposition tutorial overview: Fe-Cr alloy at 500C using Cahn-Hilliard with thermodynamic free energy fit. |
| moose/modules/phase_field/doc/content/modules/phase_field/Tutorial/Step1.md | Tutorial | Step 1: minimal split Cahn-Hilliard input (Mesh, Variables, ICs, BCs, Kernels, Materials, Preconditioning, Executioner). |
| moose/modules/phase_field/doc/content/modules/phase_field/Tutorial/Step2.md | Tutorial | Step 2: speed up the model via adaptive timestepping, restricted derivative_order on parsed materials, debug output. |
| moose/modules/phase_field/doc/content/modules/phase_field/Tutorial/Step3.md | Tutorial | Step 3: add RandomIC at 46.774 mol% Cr, longer 7-day solution time, mesh adaptivity, more postprocessors. |
| moose/modules/phase_field/doc/content/modules/phase_field/Tutorial/Step4.md | Tutorial | Step 4: replace constant mobility with composition-dependent DerivativeParsedMaterial; verify Cr phase fraction. |
| moose/modules/phase_field/doc/content/modules/phase_field/Tutorial/Step5.md | Tutorial | Step 5: scale variables to balance residuals and integrate total energy to verify expected S-curve evolution. |
| moose/modules/phase_field/examples/anisotropic_interfaces/ad_snow.i | Example | AD snowflake-like solidification with anisotropic Allen-Cahn dendrite growth (AD version of snow.i). |
| moose/modules/phase_field/examples/anisotropic_interfaces/echebarria_iso.i | Example | Echebarria isothermal dendritic solidification model with anisotropic interfacial energy. |
| moose/modules/phase_field/examples/anisotropic_interfaces/GrandPotentialPlanarGrowth.i | Example | Grand-potential model planar growth front example with anisotropic interface. |
| moose/modules/phase_field/examples/anisotropic_interfaces/GrandPotentialSolidification.i | Example | Grand-potential solidification example with anisotropic interface coupling temperature and composition. |
| moose/modules/phase_field/examples/anisotropic_interfaces/GrandPotentialTwophaseAnisotropy.i | Example | Two-phase grand-potential model with anisotropic interface to demonstrate decoupled energy/width. |
| moose/modules/phase_field/examples/anisotropic_interfaces/snow.i | Example | Snowflake-like dendritic solidification driven by anisotropic interfacial energy. |
| moose/modules/phase_field/examples/anisotropic_transport/diffusion.i | Example | Anisotropic diffusion equation example (MatAnisoDiffusion) demonstrating tensor-valued diffusivity. |
| moose/modules/phase_field/examples/cahn-hilliard/Math_CH.i | Example | Direct Cahn-Hilliard solve using MathFreeEnergy double-well, evolves single conserved concentration. |
| moose/modules/phase_field/examples/cahn-hilliard/Parsed_CH.i | Example | Direct Cahn-Hilliard with DerivativeParsedMaterial-defined free energy. |
| moose/modules/phase_field/examples/cahn-hilliard/Parsed_SplitCH.i | Example | Split Cahn-Hilliard formulation (concentration + chemical potential) with parsed free energy. |
| moose/modules/phase_field/examples/ebsd_reconstruction/IN100-111grn.i | Example | Reconstructs polycrystal microstructure from IN100 EBSD data using EBSDMesh, EBSDReader, ReconVarIC. |
| moose/modules/phase_field/examples/fourier_noise.i | Example | Fourier-series-based stable noise field for phase field simulations. |
| moose/modules/phase_field/examples/grain_growth/3D_6000_gr.i | Example | Large-scale 3D polycrystal grain growth with ~6000 grains and grain tracker. |
| moose/modules/phase_field/examples/grain_growth/grain_growth_2D_graintracker.i | Example | 2D polycrystal grain growth using GrainTracker for reduced order parameter remapping. |
| moose/modules/phase_field/examples/grain_growth/grain_growth_2D_random.i | Example | 2D polycrystal grain growth with random initial grain orientations. |
| moose/modules/phase_field/examples/grain_growth/grain_growth_2D_voronoi_newadapt.i | Example | 2D Voronoi polycrystal grain growth with new adaptivity scheme. |
| moose/modules/phase_field/examples/grain_growth/grain_growth_2D_voronoi.i | Example | 2D Voronoi polycrystal grain growth standard example. |
| moose/modules/phase_field/examples/grain_growth/grain_growth_3D.i | Example | 3D polycrystal grain growth example. |
| moose/modules/phase_field/examples/grain_growth/grain_growth_linearized_interface.i | Example | Linearized-interface grain growth using transformed psi variables and bounded solve. |
| moose/modules/phase_field/examples/interfacekernels/interface_fluxbc.i | Example | Interface flux BC across subdomains using InterfaceKernels in phase field. |
| moose/modules/phase_field/examples/interfacekernels/interface_gradient.i | Example | Interface gradient continuity coupling between subdomain variables via InterfaceKernels. |
| moose/modules/phase_field/examples/kim-kim-suzuki/kks_example_dirichlet.i | Example | KKS two-phase example with Dirichlet boundary conditions. |
| moose/modules/phase_field/examples/kim-kim-suzuki/kks_example_noflux.i | Example | KKS two-phase example with no-flux boundary conditions. |
| moose/modules/phase_field/examples/kim-kim-suzuki/kks_example_ternary.i | Example | KKS extended to a ternary (three-component) system with extra CH and constraint kernels per component. |
| moose/modules/phase_field/examples/measure_interface_energy/1Dinterface_energy.i | Example | Measures interfacial energy from a 1D equilibrium interface for verification against analytical KKS solution. |
| moose/modules/phase_field/examples/multiphase/DerivativeMultiPhaseMaterial.i | Example | Multiphase model using DerivativeMultiPhaseMaterial with Lagrange-multiplier constraint on phase fractions. |
| moose/modules/phase_field/examples/multiphase/GrandPotential3Phase_AD.i | Example | AD version of three-phase grand-potential model. |
| moose/modules/phase_field/examples/multiphase/GrandPotential3Phase_masscons.i | Example | Three-phase grand-potential model with explicit mass-conservation enforcement variant. |
| moose/modules/phase_field/examples/multiphase/GrandPotential3Phase.i | Example | Three-phase grand-potential model example. |
| moose/modules/phase_field/examples/nucleation/cahn_hilliard.i | Example | Discrete nucleation coupled with Cahn-Hilliard evolution showing nucleus insertion. |
| moose/modules/phase_field/examples/nucleation/refine.i | Example | Discrete nucleation with adaptive mesh refinement around nucleus insertion sites. |
| moose/modules/phase_field/examples/rigidbodymotion/AC_CH_advection_constforce_rect.i | Example | Coupled Allen-Cahn/Cahn-Hilliard with advective rigid body motion under constant force on rectangular grain. |
| moose/modules/phase_field/examples/rigidbodymotion/AC_CH_Multigrain.i | Example | Multigrain rigid body motion with coupled Allen-Cahn/Cahn-Hilliard advection. |
| moose/modules/phase_field/examples/rigidbodymotion/grain_forcedensity_ext.i | Example | External force-density-driven grain rigid-body motion in phase field. |
| moose/modules/phase_field/examples/rigidbodymotion/grain_motion_GT.i | Example | Grain rigid-body motion using GrainTracker to identify and translate features. |
| moose/modules/phase_field/examples/slkks/CrFe_sigma.i | Example | SLKKS sublattice model for Cr-Fe sigma phase using exported CALPHAD free energies. |
| moose/modules/phase_field/examples/slkks/CrFe.i | Example | SLKKS sublattice model for Cr-Fe binary system. |
| moose/modules/phase_field/tutorials/spinodal_decomposition/s1_testmodel.i | Tutorial | Spinodal decomposition tutorial Step 1 input: simple Fe-Cr split Cahn-Hilliard test model. |
| moose/modules/phase_field/tutorials/spinodal_decomposition/s2_fasttest.i | Tutorial | Step 2 input: faster spinodal decomposition with restricted derivative order and adaptive timestepping. |
| moose/modules/phase_field/tutorials/spinodal_decomposition/s3_decomp.i | Tutorial | Step 3 input: spinodal decomposition with random IC at 46.774 mol% Cr and mesh adaptivity. |
| moose/modules/phase_field/tutorials/spinodal_decomposition/s4_mobility.i | Tutorial | Step 4 input: spinodal decomposition with composition-dependent mobility via DerivativeParsedMaterial. |
| moose/modules/phase_field/tutorials/spinodal_decomposition/s5_energycurve.i | Tutorial | Step 5 input: spinodal decomposition with variable scaling and total energy postprocessor for S-curve verification. |

## Chemistry

| Path | Type | Description |
|---|---|---|
| moose/modules/chemical_reactions/doc/content/index.md | Index | Top-level redirect to chemical_reactions module index page. |
| moose/modules/chemical_reactions/doc/content/modules/chemical_reactions/index.md | Theory | Multicomponent aqueous reactive transport in porous media; primary/secondary species, mass action, kinetic minerals, Darcy flow. |
| moose/modules/geochemistry/doc/content/index.md | Index | Top-level redirect to geochemistry module index page. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/contents.md | Index | A-to-Z auto-generated index of all geochemistry doc pages. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/database/db_description.md | Theory | MOOSE JSON thermodynamic database format and python converter usage (gwb, eq36 inputs). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/database/geochemistry_database_reader.md | Theory | Internal database reader: standard temperatures, Debye-Hückel coeffs, basis species, sorbing sites. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/database/gwb_database.md | Theory | GWB database format (jan19) and conversion to MOOSE JSON via database_converter.py. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/database/index.md | Index | Database documentation index: description, GWB conversion, DB reader, basis. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/geochemistry_nomenclature.md | Theory | Nomenclature: species, phases, components, basis, moles/mole fraction, molality conventions. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/index.md | Index | Geochemistry module overview: equilibrium aqueous systems, redox, sorption, kinetics, coupled with PorousFlow. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/systems.md | Index | Auto-generated complete syntax listing for GeochemistryApp input-file objects. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/activity_ratios.md | Example | Computing equilibrium activity ratios (e.g. K+/H+ via muscovite-kaolinite) (Bethke 11). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/adding_feldspar.md | Example | Time-dependent reaction path: progressively adding K-feldspar to water (Bethke 13). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/adding_pyrite.md | Example | Pyrite dissolution with and without fixed O2(g) fugacity (Bethke 14.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/amazon.md | Example | Equilibrium chemical model of Amazon river water (Bethke 6.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/bio_arsenate.md | Example | Arsenate-reducing microbe with lactate; thermodynamically-limited reaction (Bethke 33.1). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/bio_death.md | Example | Microbe mortality via exponential decay implemented as GeochemistryKineticRate. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/bio_sulfate.md | Example | Sulfate-reducing microbe in presence of acetate; thermodynamic-limited Monod kinetics (Bethke 18.5). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/bio_zoning.md | Example | Reactive-transport biogeochemistry: aquifer zoning with sulfate reducers and methanogens (Bethke 33.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/calcite_buffer.md | Example | Dump process: equilibrate, remove undissolved minerals, then add chemicals (Bethke 15.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/changing_fugacity_with_calcite.md | Example | Calcite solubility under progressively changing CO2(g) fugacity buffer (Bethke 14.3). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/changing_pH_iron.md | Example | Pseudo-titration: varying pH from 4 to 12 to study sorption on ferric hydroxide (Bethke 14.3). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/cooling_feldspar.md | Example | Equilibrium evolution as a feldspar-bearing solution is cooled from 300 to 25 C (Bethke 14.1). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/eqm_temp_a.md | Example | Solving for equilibrium temperature or activity (gypsum-anhydrite) (Bethke 11). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/flow_through.md | Example | Flow-through evaporation: removing precipitated minerals after each step (Bethke 24.3). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/flush.md | Example | Flush process: alkali flooding a petroleum reservoir with quartz kinetics (Bethke 30.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/forge.md | Example | FORGE geothermal reactive-transport simulation: cold injection into hot aquifer with 2D PorousFlow. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/geotes_2D.md | Example | 2D reactive-transport GeoTES simulation: PorousFlow + geochemistry via MultiApp operator splitting. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/geotes_weber_tensleep.md | Example | 3D Weber-Tensleep GeoTES reactive-transport simulation with heat exchanger and PorousFlow. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/gypsum.md | Example | Solubility of gypsum (CaSO4.2H2O) as a function of NaCl concentration (Bethke 8.3). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/HCl.md | Example | Simple acidic HCl solution at fixed pH; equilibrium molalities benchmarked against GWB. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/ic_unit_conversions.md | Tutorial | Reference for converting concentration measures (molal, moles_bulk_species, g/kg, mg/kg). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/index.md | Index | Catalog of 350+ tests/examples grouped by topic: equilibrium waters, redox, sorption, kinetics, reactive transport, biogeochemistry. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/kinetic_albite.md | Example | Kinetically-controlled dissolution of albite into an acidic solution (Bethke 16.4). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/kinetic_quartz_arrhenius.md | Example | Quartz deposition in a hydrothermal fracture with Arrhenius rate (Bethke 26.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/kinetic_quartz.md | Example | Kinetically-controlled dissolution of quartz into deionized water at 100 C (Bethke 16.4). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/microbial_redox.md | Example | Energy available for microbial respiration via Nernst Eh of redox half-reactions (Bethke 7.4). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/morro.md | Example | Morro de Ferro groundwater with redox disequilibrium and Eh constraint (Bethke 7.3). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/non_unique.md | Example | Models exhibiting nonunique solutions (Boehmite equilibrium etc.) (Bethke 12). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/pH_pe.md | Example | Computing equilibrium pH from mineral equilibrium (e.g. hematite at given Fe2+ activity) (Bethke 11). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/pickup.md | Example | Mixing fluids of different temperatures (seawater "pickup") (Bethke 22.2). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/reaction_balancing.md | Example | Re-balancing reactions in terms of user-chosen components via basis swaps (Bethke 11). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/red_sea.md | Example | Equilibrium chemical model of Red Sea hydrothermal brine at 60 C (Bethke 6.3). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/seawater.md | Example | Equilibrium chemical model of seawater with atmospheric gas partial pressures (Bethke 6.1). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/sebkhat.md | Example | Saturation indices of halite and anhydrite at Sebkhat El Melah brine (Bethke 8.4). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/selenate.md | Example | Langmuir sorption of selenate in loamy soil (Bethke 9.6). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/tests_and_examples/surface_complexation.md | Example | Surface complexation sorption of Hg, Pb, SO4 onto hydrous ferric oxide at pH 4 and 8 (Bethke 10.4). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/activity_coefficients.md | Theory | Activity coefficient models; Debye-Hückel B-dot for ions plus neutral species/water (Pitzer not yet implemented). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/basis.md | Theory | Choosing the chemical basis (primary species), default basis from database, swap rationale. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/biogeochemistry.md | Theory | Microbe-catalyzed (often redox) reactions; representing microbes as primary or kinetic species. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/compute_efficiencies.md | Theory | Memory and compute scaling for geochemistry simulations; AuxVariable cost, parallel performance. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/equilibrium_eqns.md | Theory | Equations relating molality and mole numbers of basis species, including water, minerals, gases. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/equilibrium_reactions.md | Theory | Primer on equilibrium reactions, free energy, chemical potential, mass-action equilibrium constants. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/equilibrium.md | Theory | Notation and formal equilibrium equations for aqueous, mineral, gas, sorbed species (Aw,Ai,Aj,Ak,Am,Ap,Aq). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/fugacity.md | Theory | Gas fugacity theory; chemical potential of gas mixtures, Spycher-Reed fugacity coefficients. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/gwb_diff.md | Theory | Differences between geochemistry module and Geochemist's Workbench (temperature interpolation, ionic strength, bulk constraints). |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/index.md | Theory | Master theory page: reaction types, database role, basis selection, equilibrium and kinetic reactions. |
| moose/modules/geochemistry/doc/content/modules/geochemistry/theory/swap.md | Theory | Basis swaps: in/out of basis, validity test, recomputing reactions and equilibrium constants. |

## Electromagnetics & ray tracing

| Path | Type | Description |
|---|---|---|
| moose/modules/electromagnetics/doc/content/index.md | Index | Top-level redirect to the electromagnetics module landing page. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/benchmarks/DipoleAntenna.md | Example | Half-wave dipole at 1 GHz in vacuum; vector E-field with VectorEMRobinBC first-order absorbing BC, 5-wavelength domain radius. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/benchmarks/EvanescentWave.md | Example | 2D evanescent wave decay through waveguide discontinuity; vector frequency-domain Helmholtz with volumetric current source J. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/benchmarks/OneDReflection.md | Example | 1D metal-backed dielectric slab reflection coefficient via scalar Helmholtz with position-dependent eps_r and mu_r. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/benchmarks/WaveguideEigenvalue.md | Example | SLEPc eigenvalue Helmholtz `psi_xx + psi_yy + kc^2 psi = 0` for TM fundamental wavenumber on rectangular/circular/coaxial waveguides. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/benchmarks/WaveguideTransmission.md | Example | 2D vacuum waveguide TM11 mode at 20 MHz; frequency-domain `curl curl E - mu0 eps omega^2 E = 0` with separate real/imag scalar fields. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/index.md | Index | Electromagnetics module: time-harmonic and transient Maxwell/Helmholtz wave problems in 1D/2D, complex fields, port BCs, electrostatic contact, eigenvalue solves. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/systems.md | Index | Auto-generated complete listing of ElectromagneticsApp objects via `!syntax complete`. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/verification/electrostatic_contact_three_block.md | Example | Electrostatic contact three-block 1D verification: floating block sandwiched between driven and grounded blocks via ElectrostaticContactCondition. |
| moose/modules/electromagnetics/doc/content/modules/electromagnetics/verification/electrostatic_contact_two_block.md | Example | Electrostatic contact two-block 1D verification: Poisson `div(sigma grad phi)=0` with ElectrostaticContactCondition between SS304 and graphite. |
| moose/modules/ray_tracing/doc/content/index.md | Index | Top-level redirect to the ray_tracing module landing page. |
| moose/modules/ray_tracing/doc/content/modules/ray_tracing/examples/flashlight_source.md | Tutorial | Anisotropic cone "flashlight" point source via ConeRayStudy with angular quadrature, ReflectRayBC/KillRayBC, into a diffusion-reaction PDE. |
| moose/modules/ray_tracing/doc/content/modules/ray_tracing/examples/line_integrals.md | Tutorial | Line integral of FE solution along rays using RepeatableRayStudy + VariableIntegralRayKernel on a simple diffusion problem. |
| moose/modules/ray_tracing/doc/content/modules/ray_tracing/examples/line_sources.md | Tutorial | Constant line source `-Lap u = c delta_L` between two points using RepeatableRayStudy + LineSourceRayKernel (PRE_KERNELS). |
| moose/modules/ray_tracing/doc/content/modules/ray_tracing/index.md | Index | Ray tracing module: traces rays through 2D/3D meshes with adaptivity, contributes to residuals/Jacobians, ray-BC and ray-kernel interactions, parallel-scalable. |

## Reactor meshing

| Path | Type | Description |
|---|---|---|
| moose/modules/reactor/doc/content/index.md | Index | Stub redirect to the reactor module index page. |
| moose/modules/reactor/doc/content/modules/reactor/index.md | Index | Reactor module overview: hex/Cartesian mesh generators for assemblies, cores, pins, control drums, and reporting IDs. |

## Discontinuities — XFEM & peridynamics

| Path | Type | Description |
|---|---|---|
| moose/modules/peridynamics/doc/content/index.md | Index | Top-level redirect to the peridynamics module landing page. |
| moose/modules/peridynamics/doc/content/modules/peridynamics/DeformationGradients.md | Theory | Nonlocal deformation gradients via weighted least squares; bond-level and material-point formulations. |
| moose/modules/peridynamics/doc/content/modules/peridynamics/HorizonStates.md | Theory | Peridynamic horizon (H, delta), order-m states, relative position/displacement/deformation vector states. |
| moose/modules/peridynamics/doc/content/modules/peridynamics/index.md | Index | Peridynamics module overview: BPD/OSPD/NOSPD mechanics, heat conduction, thermo-mechanics, correspondence materials. |
| moose/modules/peridynamics/doc/content/modules/peridynamics/PeridynamicModels.md | Theory | Force density functions for bond-based, ordinary/non-ordinary state-based mechanics; bond-based heat; thermo-mechanics. |
| moose/modules/peridynamics/doc/content/modules/peridynamics/systems.md | Index | Auto-generated complete syntax index for PeridynamicsApp objects. |
| moose/modules/xfem/doc/content/index.md | Index | Top-level redirect to the xfem module landing page. |
| moose/modules/xfem/doc/content/modules/xfem/index.md | Index | XFEM module overview: strong/weak discontinuities, applications (cracks, interfaces), gallery. |
| moose/modules/xfem/doc/content/modules/xfem/theory/embedded_interface.md | Theory | Embedded interfaces via GeometricCutUserObject; healing-and-re-cut algorithm with stateful material caching. |
| moose/modules/xfem/doc/content/modules/xfem/theory/examples/growingEdgeCrack.md | Example | Double cantilever beam center-crack growth in 2D and 3D using MeshCut2DFractureUserObject / CrackMeshCut3DUserObject. |
| moose/modules/xfem/doc/content/modules/xfem/theory/examples/inclinedCrack.md | Example | Inclined center crack in infinite plate; K_I/K_II convergence, J-integral q-function, max hoop-stress growth. |
| moose/modules/xfem/doc/content/modules/xfem/theory/examples/index.md | Index | Example index linking inclined-crack and growing-edge-crack tutorials, plus moving-interface verification. |
| moose/modules/xfem/doc/content/modules/xfem/theory/theory.md | Theory | Phantom-node-based XFEM theory; element fragment algorithm (EFA) for mesh cutting and crack-tip handling. |

## Optimization & inverse problems

| Path | Type | Description |
|---|---|---|
| isopod/doc/content/index.md | Index | Isopod landing page; experimental MOOSE-based inverse optimization app using the optimization module + PETSc TAO. |
| moose/modules/optimization/doc/content/index.md | Index | Top-level redirect to optimization module landing page. |
| moose/modules/optimization/doc/content/modules/optimization/examples/constraintOptimization.md | Index | Constrained optimization examples overview; equality/inequality-constrained problems. |
| moose/modules/optimization/doc/content/modules/optimization/examples/debuggingHelp.md | Tutorial | Debugging guide for TAO-based optimization: gradient-free start, finite-difference gradient checks, executioner verbose output. |
| moose/modules/optimization/doc/content/modules/optimization/examples/forceInv_BodyLoad.md | Example | Force inversion Example 3: parameterize distributed body load with main/forward/adjoint sub-app structure. |
| moose/modules/optimization/doc/content/modules/optimization/examples/forceInv_main.md | Index | Force inversion examples overview; linear PDE-constrained optimization with parameterized loads. |
| moose/modules/optimization/doc/content/modules/optimization/examples/forceInv_NeumannBC.md | Example | Force inversion Example 2: parameterize Neumann BC to match displacement measurements in 2D elasticity. |
| moose/modules/optimization/doc/content/modules/optimization/examples/forceInv_pointLoads.md | Example | Force inversion Example 1: parameterize point heat sources to match measured temperature field; recommended first example. |
| moose/modules/optimization/doc/content/modules/optimization/examples/index.md | Index | Examples landing page; force vs material inversion, design (shape/topology) optimization, recommended starting point. |
| moose/modules/optimization/doc/content/modules/optimization/examples/material_transient.md | Example | Material inversion Example 3: transient inversion of spatially varying thermal conductivity using automatic adjoint executioner. |
| moose/modules/optimization/doc/content/modules/optimization/examples/materialInv_ConstK.md | Example | Material inversion Example 2: optimize constant thermal conductivity with forward/adjoint sub-app coupling. |
| moose/modules/optimization/doc/content/modules/optimization/examples/materialInv_ConvectiveBC.md | Example | Material inversion Example 1: fit convective coefficient (Robin BC) for steady heat conduction. |
| moose/modules/optimization/doc/content/modules/optimization/examples/materialInv_diffusion_reaction.md | Example | Material inversion Example 4: nonlinear diffusion-reaction inversion of spatial reaction rate using TAOBQNLS. |
| moose/modules/optimization/doc/content/modules/optimization/examples/materialInv_main.md | Index | Material inversion examples overview; nonlinear inversion of thermal conductivity / convective coefficients. |
| moose/modules/optimization/doc/content/modules/optimization/examples/shapeOpt_Annulus.md | Example | Constrained shape optimization of annulus radii to minimize max temperature with fixed volume constraint. |
| moose/modules/optimization/doc/content/modules/optimization/examples/top_opt_main.md | Index | Topology optimization examples landing with cards for SIMP-based 2D/3D MBB beams, multiload, multimaterial, thermomechanical. |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/2d_mbb_pde_amr.md | Tutorial | 2D MBB topology optimization with PDE filter plus adaptive mesh refinement via ValueJumpIndicator on nodal density. |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/2d_mbb_pde.md | Tutorial | 2D MBB topology optimization using PDE filter (FunctionDiffusion+Reaction+CoupledForce) and boundary penalty. |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/2d_mbb.md | Tutorial | 2D MBB beam SIMP topology optimization with convolution (RadialAverage) sensitivity filter. |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/3d_mbb.md | Example | 3D MBB beam SIMP topology optimization using PDE filter (TROUT in 3D). |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/multiload.md | Example | Multi-load SIMP topology optimization with multiapp scheme; per-load sensitivities combined globally. |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/multimaterial.md | Example | Ordered SIMP multimaterial topology optimization with DensityUpdateTwoConstraints (volume + cost constraints). |
| moose/modules/optimization/doc/content/modules/optimization/examples/topology_optimization/thermomechanical.md | Example | Coupled thermomechanical SIMP topology optimization via multiapps for thermal compliance plus mechanical compliance. |
| moose/modules/optimization/doc/content/modules/optimization/index.md | Index | Optimization module landing page; links to theory, syntax, and examples; uses PETSc TAO for PDE-constrained optimization. |
| moose/modules/optimization/doc/content/modules/optimization/systems.md | Index | Auto-generated complete syntax listing for OptimizationApp objects. |
| moose/modules/optimization/doc/content/modules/optimization/theory/InvOptTheory.md | Theory | PDE-constrained inverse optimization theory; objective, adjoint method derivation, force/material/Robin BC inversion gradients. |

## Stochastic / UQ / surrogate

| Path | Type | Description |
|---|---|---|
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/batch_mode.md | Theory | SamplerFullSolveMultiApp/SamplerTransientMultiApp normal/batch-reset/batch-restore modes; memory-perf tradeoffs |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/distributed_samples.md | Theory | Sampler getSamples/getLocalSamples/getNextLocalRow modes; replicated vs distributed vs iterative memory scaling |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/enable_pytorch.md | Theory | Build STM with libtorch C++ APIs for neural-net surrogates; smoke-test via libtorch_nn regression tests |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/annulus_shape.md | Example | Annulus shape optimization coupling SciPy minimize with StochasticControl; constrained max-temperature min, mesh + displaced-mesh inputs |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/bayesian_uq_1d_diff.md | Example | Bayesian UQ on 1D transient diffusion; MCMC samplers (IndependentGaussianMH, AffineInvariant); likelihood inference of Dirichlet BCs |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/combined_example_2d_trans_diff.md | Example | Compares NearestPoint, PolynomialRegression, PolynomialChaos surrogates on 2D transient nonlinear diffusion with oscillating source |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/cross_validation.md | Example | K-fold cross validation in SurrogateTrainer; cv_n_trials/cv_splits/cv_surrogate; RMSE for PolynomialRegressionTrainer |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/gaussian_process_surrogate.md | Example | Gaussian process surrogate on 1D heat conduction with 4 uncertain parameters; QoI is average temperature; analytical comparison |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/index.md | Index | Catalog of STM examples across parameter studies, surrogates, Bayesian UQ, Python interface, and DRL control |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/libtorch_drl_control.md | Example | Deep reinforcement learning PPO controller via libtorch; controls heat flux to track temperature setpoint in 2D box |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/monte_carlo.md | Example | Monte Carlo on 1D transient diffusion; SamplerReceiver Controls block; uniform-distributed Dirichlet BCs |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/nonlin_parameter_study.md | Example | Parameter study on 2D nonlinear diffusion-reaction (exp source); custom test kernel; QoI distribution variation with parameter dist |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/parameter_study.md | Example | Parent-driven parameter study for 2D transient heat eq; uncertain T0/q0/gamma/s; Tavg and qleft QoIs via SamplerReceiver |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/pod_rb_surrogate.md | Example | POD reduced-basis surrogate on parametric fixed-source diffusion-reaction (1-group neutronics) with multi-region coefficients |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/poly_chaos_surrogate.md | Example | Polynomial chaos surrogate training; orthogonal-polynomial expansion via Monte Carlo or quadrature samplers |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/poly_regression_surrogate.md | Example | Polynomial regression surrogate on 1D heat conduction (Tmax QoI); uniform vs normal parameter distributions; comparison vs PC |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/sobol.md | Example | Sobol global variance-based sensitivity analysis; SobolSampler + SobolReporter; first/second-order/total-effect indices |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/surrogate_creation.md | Tutorial | Authoring custom SurrogateTrainer/SurrogateModel pair; NearestPointSurrogate walkthrough; .rd file; preTrain/postTrain hooks |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/surrogate_evaluate.md | Tutorial | Evaluating a trained surrogate via .rd file; EvaluateSurrogate object; Monte Carlo sampling for stats and PDFs |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/examples/surrogate_training.md | Tutorial | Training surrogate via Trainers block on 1D heat conduction full-order model; uniform/normal parameter distributions |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/index.md | Index | Stochastic tools module: UQ/sensitivity sampling, surrogate/ML modeling (libtorch), batch sub-app execution, distributed sample matrices, stochastic control. |
| moose/modules/stochastic_tools/doc/content/modules/stochastic_tools/python/StochasticControl.md | Tutorial | Python wrapper assembling STM input, running samples via MPI, returning QoI NumPy arrays for SciPy coupling |

## Properties & miscellaneous

| Path | Type | Description |
|---|---|---|
| moose/modules/functional_expansion_tools/doc/content/index.md | Index | Top-level redirect to the functional_expansion_tools module landing page |
| moose/modules/functional_expansion_tools/doc/content/modules/functional_expansion_tools/examples.md | Example | Catalog of FX example inputs: 2D interface coupling, 1D/2D/3D Cartesian volumetric coupling (CoupledForce vs BodyForce), mesh-agnostic submesh demos |
| moose/modules/functional_expansion_tools/doc/content/modules/functional_expansion_tools/index.md | Index | Functional expansion tools: mesh-agnostic MultiApp coupling via Legendre/Zernike functional series — interface and volumetric reduced-data transfer. |
| moose/modules/misc/doc/content/index.md | Index | Top-level redirect to the misc module landing page |
| moose/modules/misc/doc/content/modules/misc/index.md | Index | Misc module: catch-all collection of miscellaneous objects/utilities; documentation is intentionally minimal (flagged as under construction). |
| moose/modules/solid_properties/doc/content/index.md | Index | Top-level redirect to the solid_properties module landing page |
| moose/modules/solid_properties/doc/content/modules/solid_properties/index.md | Index | Solid properties module: temperature-dependent thermal solid properties (rho, cp, k) for graphite, SiC, SS316, function-defined; plug-and-play UserObject interface. |

## Top-level moose tutorials

| Path | Type | Description |
|---|---|---|
| moose/tutorials/darcy_thermo_mech/doc/content/index.md | Tutorial | Workshop landing page; entry point linking to the MOOSE Workshop on Darcy thermo-mechanical pressure-vessel problem. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/01_basics.md | Tutorial | C++ fundamentals: intrinsic data types, operators, control flow primer for MOOSE app developers. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/02_scope.md | Tutorial | C++ scope, memory management (stack/heap), and function/operator overloading. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/03_types.md | Tutorial | C++ static vs dynamic typing, templates, and Standard Template Library (STL) containers/algorithms. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/04_classes.md | Tutorial | C++ classes and object-oriented programming: encapsulation, inheritance, polymorphism for MOOSE objects. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/cpp/standards.md | Tutorial | MOOSE C++ coding standard, clang-format usage, and code style guidelines. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/index.md | Tutorial | Top-level MOOSE Workshop deck aggregating intro, problem, systems, modules, numerical, and infrastructure includes. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/infrastructure/debugging.md | Tutorial | Debugging MOOSE applications using LLDB/GDB and other debuggers in place of print statements. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/infrastructure/mms.md | Tutorial | Method of Manufactured Solutions (MMS) for code verification of PDE implementations in MOOSE. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/infrastructure/restart.md | Tutorial | Restart and Recovery system: continuing simulations from checkpoints with new or modified inputs. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/infrastructure/testing.md | Tutorial | MOOSE test system, continuous integration practices, and writing regression tests. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/infrastructure/troubleshooting.md | Tutorial | Troubleshooting common input file mistakes and solver non-convergence issues. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/intro/getting_started.md | Tutorial | Getting started: installing MOOSE, text editors, and ParaView visualization software. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/intro/inl_background.md | Tutorial | Background on Idaho National Laboratory and its modeling and simulation mission. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/intro/moose_introduction.md | Tutorial | Introduction to MOOSE: Multi-physics Object Oriented Simulation Environment overview. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/intro/moose_multiphysics.md | Tutorial | Historical overview and motivation for tightly-coupled multiphysics simulation in MOOSE. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/modules/modules.md | Tutorial | Survey of MOOSE physics modules (chemical reactions, contact, heat transfer, solid mechanics, etc.). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/numerical/fem_overview.md | Tutorial | Finite Element Method overview: function approximation, weak forms, and Galerkin discretization. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/numerical/fem_shape.md | Tutorial | FEM shape (basis) functions, element types, and quadrature foundations. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/numerical/fem_solve.md | Tutorial | Numerical implementation: integration on reference elements, residual/Jacobian assembly, and solve. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/numerical/fvm_overview.md | Tutorial | Finite Volume Method overview: conservation form, mixed cell types, and advantages for fluid flow. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/laplace_young.md | Tutorial | Hands-on Laplace-Young surface tension problem with nonlinear coefficient k(u) and Neumann BCs. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/overview.md | Tutorial | Problem statement: pressure vessels coupled by a packed-sphere filter; Darcy flow + heat governing equations. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step01.md | Tutorial | Step 1: solve a steady-state Diffusion problem with no code; introduce [Mesh]/[Variables]/[Kernels]/[BCs]/[Executioner]/[Outputs]. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step02.md | Tutorial | Step 2: write a custom DarcyPressure Kernel inheriting ADDiffusion to solve the Darcy pressure equation. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step03.md | Tutorial | Step 3: introduce a [Materials] block (PackedColumn) supplying permeability and viscosity to the DarcyPressure kernel. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step04.md | Tutorial | Step 4: add a DarcyVelocity AuxKernel computing velocity from the pressure gradient via the AuxiliarySystem. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step05.md | Tutorial | Step 5: solve steady heat conduction using the heat_transfer module's ADHeatConduction kernel and a constant material. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step06.md | Tutorial | Step 6: couple the Darcy pressure and heat equations with a custom DarcyAdvection kernel and temperature-dependent material. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step07.md | Tutorial | Step 7: introduce mesh adaptivity via [Adaptivity], comparing coarse and fine solutions of the coupled problem. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step08.md | Tutorial | Step 8: add Postprocessors and VectorPostprocessors to extract average T, heat flux, and line samples. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step09.md | Tutorial | Step 9: add solid mechanics — elastic and thermal strain with axial expansion using the solid_mechanics module. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step10.md | Tutorial | Step 10: multiscale simulation with a MultiApp; micro-scale RandomCorrosion auxkernel feeds k and porosity to macro-scale. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/step11.md | Tutorial | Step 11: build a custom Action (SetupDarcySimulation) registering shortcut syntax for Darcy thermo-mech problems. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/problem/summary.md | Tutorial | Summary linking back to all eleven Darcy thermo-mechanical workshop steps. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/actions.md | Tutorial | MOOSE [Actions] system: programmatic input parsing and shortcut syntax registration. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/adaptivity.md | Tutorial | Mesh adaptivity (h-refinement) system: Indicators, Markers, and refinement controls. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/auxkernels.md | Tutorial | [AuxKernels] system: explicit field computations on auxiliary variables (nodal/elemental). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/boundaryconditions.md | Tutorial | [BCs] system: Dirichlet, Neumann, integrated, and nodal boundary condition objects. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/constraints.md | Tutorial | [Constraints] system: nodal, mortar, and tied-node constraints between variables. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/controls.md | Tutorial | [Controls] system: runtime modification of MOOSE input parameters during a simulation. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/dampers.md | Tutorial | [Dampers] system: limiting Newton step length to improve nonlinear convergence robustness. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/debug.md | Tutorial | [Debug] system: residual/Jacobian inspection, numerical Jacobian comparison, top residuals. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/dgkernels.md | Tutorial | [DGKernels] system: discontinuous Galerkin volume and interface terms. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/dirackernels.md | Tutorial | [DiracKernels] system: point-source contributions to the residual at user-specified locations. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/distributions.md | Tutorial | [Distributions] system: probability distributions used by stochastic_tools and samplers. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/executioners.md | Tutorial | [Executioner] system: Steady, Transient, eigenvalue solver drivers and time integration controls. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/executors.md | Tutorial | [Executors] experimental system: composable execution graph alternative to executioners. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/functions.md | Tutorial | [Functions] system: parsed/piecewise/expression functions used by BCs, ICs, and kernels. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/fvbcs.md | Tutorial | [FVBCs] system: finite volume boundary conditions (Dirichlet, flux, etc.). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/fviks.md | Tutorial | [FVInterfaceKernels] system: finite volume interface flux contributions between subdomains. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/fvkernels.md | Tutorial | [FVKernels] system: finite volume cell-centered residual contributions. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/geomsearch.md | Tutorial | Geometric search system: nearest-node and penetration searches for contact and constraints. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/index.md | Tutorial | Aggregator page including all MOOSE pluggable system pages (actions, kernels, materials, etc.). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/indicators.md | Tutorial | [Indicators] system: error estimators feeding adaptivity Markers. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/initialconditions.md | Tutorial | [ICs] system: initial conditions for nonlinear and auxiliary variables. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/inputparameters.md | Tutorial | InputParameters: validParams, parameter declaration, defaults, and validation. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/interfacekernels.md | Tutorial | [InterfaceKernels] system: jump/flux conditions between subdomains for FE discretizations. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/kernels.md | Tutorial | [Kernels] system: volumetric residual/Jacobian contributions for FE PDEs. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/linesearches.md | Tutorial | Line search system: PETSc line search options for Newton's method (basic, bt, cp, l2). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/markers.md | Tutorial | [Markers] system: per-element refinement decisions consumed by adaptivity. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/materials.md | Tutorial | [Materials] system: spatially varying property computation at quadrature points. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/mesh.md | Tutorial | [Mesh] system: mesh inputs, partitioning, displaced mesh, and uniform refinement. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/meshgenerators.md | Tutorial | MeshGenerators: programmatic mesh construction by chaining generator objects in [Mesh]. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/mooseobject.md | Tutorial | MooseObject base class: validParams, registration, and the foundation of all MOOSE objects. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/multiapps.md | Tutorial | [MultiApps] system: hierarchical sub-applications for multiscale and multiphysics coupling. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/nodalkernels.md | Tutorial | [NodalKernels] system: nodal residual contributions (e.g. nodal source, time derivative). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/outputs.md | Tutorial | [Outputs] system: Exodus, CSV, Console, Checkpoint, and other output formats. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/parser.md | Tutorial | The hit (hierarchical input text) parser that reads MOOSE input files. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/partitioner.md | Tutorial | Mesh [Partitioner] system: parallel mesh decomposition strategies (default, ParMETIS, etc.). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/positions.md | Tutorial | [Positions] system: ordered lists of 3D coordinates consumable by MultiApps and other objects. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/postprocessors.md | Tutorial | [Postprocessors] system: scalar reductions of fields (averages, integrals, extrema). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/preconditioner.md | Tutorial | [Preconditioning] system: SMP, FSP, FDP, and PJFNK preconditioner setup. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/predictor.md | Tutorial | [Predictor] system: extrapolating initial guesses for transient Newton solves. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/problem.md | Tutorial | [Problem] system: FEProblem and custom problem classes that drive the solve. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/relationshipmanagers.md | Tutorial | RelationshipManagers: parallel ghosting policy for elements/sides used by algebraic and geometric ghosting. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/reporters.md | Tutorial | [Reporters] system: arbitrary-typed data exchange between MOOSE objects (replaces simple PPs/VPPs). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/samplers.md | Tutorial | [Samplers] system: parameter-space sampling for stochastic and parameter studies. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/splits.md | Tutorial | [Splits] system: field-split preconditioners for block problems via PETSc FSP. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/timeintegrators.md | Tutorial | [TimeIntegrators] system: implicit Euler, BDF2, Crank-Nicolson, explicit, and Newmark schemes. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/timesteppers.md | Tutorial | [TimeSteppers] system: constant, IterationAdaptive, Function, and post-error timestep selection. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/transfers.md | Tutorial | [Transfers] system: data exchange between parent and sub-apps in MultiApp hierarchies. |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/userobjects.md | Tutorial | [UserObjects] system: general-purpose computation objects (general/element/nodal/side/internal-side). |
| moose/tutorials/darcy_thermo_mech/doc/content/workshop/systems/vectorpostprocessors.md | Tutorial | [VectorPostprocessors] system: vector-valued aggregations (line samplers, distributions, histories). |
| moose/tutorials/shield_multiphysics/doc/content/index.md | Tutorial | Workshop landing page for the concrete shield multiphysics user workshop (NRIC DOME microreactor). |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/index.md | Tutorial | Top-level shield_multiphysics user workshop deck aggregating all problem and systems pages. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/overview.md | Tutorial | Problem statement: cooling of concrete shielding around a future micro-reactor; thermal mechanics + thermal fluids physics. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step01.md | Tutorial | Step 1: build the 2D shield mesh using [GeneratedMeshGenerator] and other mesh generators. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step02.md | Tutorial | Step 2: implement a CoefDiffusion Kernel for steady heat conduction in the concrete shield. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step03.md | Tutorial | Step 3: realistic boundary conditions — fixed flux from reactor, natural convection to air, convective coupling to water. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step04.md | Tutorial | Step 4: introduce a [Materials] block (HeatConductionMaterial) supplying k, density, and specific heat to the kernels. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step05.md | Tutorial | Step 5: use [AuxVariables] for fluid temperature stand-in and AuxKernels for heat-flux postprocessing via Fourier's law. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step06.md | Tutorial | Step 6: extend to transient heat conduction with HeatConductionTimeDerivative and [Transient] executioner. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step07.md | Tutorial | Step 7: add solid mechanics — elastic + thermal strain with the shield held only at the ground sideset. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step08.md | Tutorial | Step 8: introduce mesh adaptivity (uniform refinement, indicators/markers) for the shield heat-conduction problem. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step09.md | Tutorial | Step 9: postprocess with NumElements, NodalExtremeValue, SideDiffusiveFluxIntegral, and LineValueSampler. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step10.md | Tutorial | Step 10: model natural circulation in the water tank with finite volume mass/momentum/energy conservation (FVKernels). |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step11.md | Tutorial | Step 11: multiscale MultiApp — couple solid heat conduction to fluid flow and embed sub-app sensor models. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step12.md | Tutorial | Step 12: use the [Physics] action shorthand syntax (HeatConduction/FiniteElement, SolidMechanics, fluid flow). |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/step13.md | Tutorial | Step 13: hands-on with restart, recovery, and initialization from Checkpoint outputs. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/problem/summary.md | Tutorial | Summary linking back to all thirteen shield_multiphysics tutorial steps. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/actions.md | Tutorial | [Actions] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/adaptivity.md | Tutorial | Mesh adaptivity overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/auxkernels.md | Tutorial | [AuxKernels] / [AuxVariables] overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/boundaryconditions.md | Tutorial | [BCs] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/constraints.md | Tutorial | [Constraints] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/controls.md | Tutorial | [Controls] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/dampers.md | Tutorial | [Dampers] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/debug.md | Tutorial | [Debug] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/dgkernels.md | Tutorial | [DGKernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/dirackernels.md | Tutorial | [DiracKernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/distributions.md | Tutorial | [Distributions] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/executioners.md | Tutorial | [Executioner] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/executors.md | Tutorial | [Executors] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/functions.md | Tutorial | [Functions] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/fvbcs.md | Tutorial | [FVBCs] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/fviks.md | Tutorial | [FVInterfaceKernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/fvkernels.md | Tutorial | [FVKernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/geomsearch.md | Tutorial | Geometric search system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/index.md | Tutorial | Aggregator page including all pluggable-system pages used in the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/indicators.md | Tutorial | [Indicators] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/initialconditions.md | Tutorial | [ICs] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/input_syntax_primer.md | Tutorial | Primer on MOOSE WASP-based hierarchical input file syntax (square-bracket blocks). |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/inputparameters.md | Tutorial | InputParameters / validParams overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/interfacekernels.md | Tutorial | [InterfaceKernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/kernels.md | Tutorial | [Kernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/linesearches.md | Tutorial | Line search options overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/markers.md | Tutorial | [Markers] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/materials.md | Tutorial | [Materials] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/mesh.md | Tutorial | [Mesh] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/meshgenerators.md | Tutorial | MeshGenerators overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/multiapps.md | Tutorial | [MultiApps] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/nodalkernels.md | Tutorial | [NodalKernels] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/outputs.md | Tutorial | [Outputs] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/parser.md | Tutorial | hit-format parser overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/partitioner.md | Tutorial | Mesh [Partitioner] overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/positions.md | Tutorial | [Positions] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/postprocessors.md | Tutorial | [Postprocessors] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/preconditioner.md | Tutorial | [Preconditioning] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/predictor.md | Tutorial | [Predictor] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/problem.md | Tutorial | [Problem] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/relationshipmanagers.md | Tutorial | RelationshipManagers overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/reporters.md | Tutorial | [Reporters] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/samplers.md | Tutorial | [Samplers] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/splits.md | Tutorial | [Splits] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/timeintegrators.md | Tutorial | [TimeIntegrators] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/timesteppers.md | Tutorial | [TimeSteppers] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/transfers.md | Tutorial | [Transfers] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/userobjects.md | Tutorial | [UserObjects] system overview for the user workshop track. |
| moose/tutorials/shield_multiphysics/doc/content/user_workshop/systems_user/vectorpostprocessors.md | Tutorial | [VectorPostprocessors] system overview for the user workshop track. |
| moose/tutorials/tutorial01_app_development/doc/content/index.md | Tutorial | Application development tutorial landing; redirects to the website's Tutorial 1 (slides not yet available). |
| moose/tutorials/tutorial02_multiapps/doc/content/getting_started/examples_and_tutorials/tutorial02_multiapps/presentation/index.md | Tutorial | Top-level MultiApps tutorial deck aggregating intro and three tutorial steps. |
| moose/tutorials/tutorial02_multiapps/doc/content/getting_started/examples_and_tutorials/tutorial02_multiapps/presentation/intro.md | Tutorial | Intro: MOOSE coupling overview; loosely-coupled, native-app, and wrapped-app coupling. |
| moose/tutorials/tutorial02_multiapps/doc/content/getting_started/examples_and_tutorials/tutorial02_multiapps/presentation/step01_multiapps.md | Tutorial | Step 1: [MultiApps] block syntax — app_type, positions, execute_on, and parent/sub-app hierarchy. |
| moose/tutorials/tutorial02_multiapps/doc/content/getting_started/examples_and_tutorials/tutorial02_multiapps/presentation/step02_transfers.md | Tutorial | Step 2: [Transfers] overview — ShapeEvaluation, NearestNode, Postprocessor, UserObject, and GeneralField transfers. |
| moose/tutorials/tutorial02_multiapps/doc/content/getting_started/examples_and_tutorials/tutorial02_multiapps/presentation/step03_coupling.md | Tutorial | Step 3: combine MultiApps and Transfers for loose vs tight (Picard) multiphysics coupling. |
| moose/tutorials/tutorial02_multiapps/doc/content/index.md | Tutorial | Welcome page for the MultiApps tutorial linking into the presentation deck. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/index.md | Tutorial | Top-level Code Verification tutorial deck aggregating contents and all subsections. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/tutorial03_analytical.md | Tutorial | Verification via comparison with analytic 1-D heat-equation solution: define, simulate, error, convergence. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/tutorial03_contents.md | Tutorial | Tutorial 3 contents/table-of-contents page emphasizing theory-vs-practice. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/tutorial03_convergence.md | Tutorial | Convergence theory: L2-norm error definition, expected FEM rates, mesh and timestep refinement studies. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/tutorial03_heat.md | Tutorial | The heat equation: governing PDE, weak form, and boundary conditions used as the verification problem. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/tutorial03_introduction.md | Tutorial | Introduction to verification (IEEE definition) and ensuring MOOSE solves equations correctly. |
| moose/tutorials/tutorial03_verification/doc/content/getting_started/examples_and_tutorials/tutorial03_verification/presentation/tutorial03_mms.md | Tutorial | Method of Manufactured Solutions for spatial and temporal convergence studies on the 2-D heat equation. |
| moose/tutorials/tutorial03_verification/doc/content/index.md | Tutorial | Welcome page for the Code Verification tutorial linking into the presentation deck. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/index.md | Tutorial | Top-level Tutorial 4 (Meshing Reactor Geometries) deck aggregating contents and all step pages. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_contents.md | Tutorial | Tutorial 4 table-of-contents page. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step01_overview.md | Tutorial | Step 1: Reactor Module overview — pin/assembly/core mesh generators, control drums, peripheral zones. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step02_building.md | Tutorial | Step 2: building the Reactor Module — installing MOOSE and compiling a meshing-capable app. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step03_workflow.md | Tutorial | Step 3: hierarchical meshing workflow — pins to assemblies to core, plus periphery, trimming, extrusion. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step04_terminology.md | Tutorial | Step 4: meshing terminology — FEM, mesh, element, sideset, subdomain definitions. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step05_common_geom.md | Tutorial | Step 5: frequently used hexagonal-based reactor geometries and their base mesh generators (pin cell, assembly, core). |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step06_common_ops.md | Tutorial | Step 6: common mesh operations — HexagonMeshTrimmer, CartesianMeshTrimmer, peripheral and through-center trimming. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step07_extra_element_ids.md | Tutorial | Step 7: reporting IDs — bookkeeping pin/assembly/plane element membership for materials and integrals. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step08_abtr.md | Tutorial | Step 8: ABTR sodium-cooled fast reactor — homogenized hexagonal assemblies patterned into a full core. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step09_hpmr.md | Tutorial | Step 9: heat-pipe-cooled microreactor (HP-MR) — 1/6 core mesh with fuel/moderator/heat-pipe pins and control drums. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step10_rgmb.md | Tutorial | Step 10: Reactor Geometry Mesh Builder (RGMB) overview — simplified mesh generators for regular reactor geometry. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step11_rgmb_het_hom.md | Tutorial | Step 11: RGMB heterogeneous-to-homogeneous conversion for the ABTR fast reactor core. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step12_rgmb_empire.md | Tutorial | Step 12: RGMB 2-D EMPIRE microreactor mesh with ControlDrumMeshGenerator stitching. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step13_advanced_tools.md | Tutorial | Step 13: advanced meshing tools — quadratic elements (TRI6/TRI7, QUAD8/QUAD9) and AdvancedExtruderGenerator. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/examples_and_tutorials/tutorial04_meshing/presentation/tutorial04_step14_advanced_examples.md | Tutorial | Step 14: advanced examples — MSRE 2D lattice and other complex reactor geometries. |
| moose/tutorials/tutorial04_meshing/doc/content/getting_started/index.md | Tutorial | Welcome page for the Reactor-Module meshing tutorial linking into the presentation deck. |
| moose/tutorials/user_short_workshop/doc/content/index.md | Tutorial | Welcome page for the MOOSE User Short Workshop linking into the workshop deck. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/index.md | Tutorial | Top-level User Short Workshop deck aggregating intro and tutorial step pages. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/step1_input_and_meshing.md | Tutorial | Step 1: MOOSE HIT input file syntax and basic [Mesh] block / fuel-pin meshing. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/step2_diffusion.md | Tutorial | Step 2: solve a steady diffusion problem on the pin mesh with Dirichlet BCs on inner and water_solid_interface. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/step3_postprocessing.md | Tutorial | Step 3: [Postprocessors] system — volumetric/surface integrals, extrema, and other scalar reductions. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/step4_materials.md | Tutorial | Step 4: introduce a [Materials] block to compute spatially varying properties consumed by Kernels. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/step5_heat_conduction.md | Tutorial | Step 5: solid heat conduction in a fuel pin with volumetric heat source and clad/fuel material differences. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/step6_coupling.md | Tutorial | Step 6: couple fluid and solid (fuel pin) systems via [MultiApp] and [Transfer] at the water_solid_interface boundary. |
| moose/tutorials/user_short_workshop/doc/content/user_short_workshop/tutorial_steps.md | Tutorial | Listing/index of all six User Short Workshop tutorial steps with cross-links. |

## Cross-cutting & framework

| Path | Type | Description |
|---|---|---|
| moose/framework/doc/content/automatic_differentiation/index.md | System | Automatic differentiation overview: motivation, AD vs PJFNK, exact Jacobians via forward-mode AD for nonlinear convergence |
| moose/framework/doc/content/automatic_differentiation/templated_objects.md | System | Templating MOOSE classes on `is_ad` bool to support both AD and non-AD variables/material properties via GenericMaterialProperty |
| moose/framework/doc/content/finite_volumes/fv_design.md | System | FV system design: cell-centered storage, face flux kernels, ghost cells, AD-only support, divergence-theorem flux assembly |
| moose/framework/doc/content/finite_volumes/index.md | System | Finite volume system index page redirecting to FV design overview |
| moose/framework/doc/content/finite_volumes/linear_fv_design.md | System | Linear FV design for Picard-style velocity-pressure coupling: LinearSystem matrix/RHS assembly, sparse stencils, no AD |
| moose/framework/doc/content/framework/contributing.md | System | Contributing guide: code standards, fork workflow, issue references, PR process for MOOSE contributions |
| moose/framework/doc/content/framework/documenting.md | System | Documentation standards: validParams strings, addClassDescription, markdown pages required for new MooseObjects |
| moose/framework/doc/content/framework/patch_to_code.md | System | PR lifecycle: CIVET CI checks, peer review, amend/force-push for fixes, merge into devel via `next` branch |
| moose/framework/doc/content/framework/reviewing.md | System | PR review guidelines: CCB requirements, conduct, review strategy, scope-based thoroughness, handling refusals |
| moose/framework/doc/content/hit.md | System | HIT input format and `hit` CLI tool: find/validate/format/merge/diff/extract parameters across input files |
| moose/framework/doc/content/kokkos/kokkos_warning.md | System | Stub warning page: detailed Kokkos object docs only available when MOOSE is compiled with Kokkos |
| moose/framework/doc/content/libtorch/libtorch_warning.md | System | Stub warning page: detailed Libtorch object docs only available when MOOSE is compiled with Libtorch |
| moose/framework/doc/content/mfem/mfem_warning.md | System | Stub warning page: detailed MFEM object docs only available when MOOSE is compiled with MFEM |
| moose/framework/doc/content/neml2/neml2_warning.md | System | Stub warning page: detailed NEML2 object/syntax docs only available when MOOSE is compiled with NEML2 |

## Blackbear

| Path | Type | Description |
|---|---|---|
| blackbear/doc/content/assessment/assessment_index.md | Index | Assessment problems index: ASR concrete validation cases for verifying BlackBear's degradation models. |
| blackbear/doc/content/example/index.md | Example | Example problems landing page: points users to assessment problems until BlackBear-specific examples are added. |
| blackbear/doc/content/getting_started/BlackBearInputStructure.md | Tutorial | Input file reference: HIT block syntax, key/value parameters, MOOSE object types (Kernel, Material, BC, ...) used in BlackBear inputs. |
| blackbear/doc/content/getting_started/RunningBlackBear.md | Tutorial | Getting-started guide: cloning BlackBear+MOOSE, building PETSc/libMesh, compiling, running tests, post-processing with ParaView, Peacock GUI. |
| blackbear/doc/content/index.md | Index | BlackBear landing page: structural material degradation simulation code for concrete/steel civil structures, built on MOOSE. |
| blackbear/doc/content/units/index.md | Index | Units guide: standard unit-type tags (length, stress, fracture toughness, ...) and consistent unit systems (SI, CGS, IPS, FPS, MMTS). |
