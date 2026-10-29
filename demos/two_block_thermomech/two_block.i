# Two-material block, coupled temperature-displacement (main.pdf, "Thermomechanical analysis of a
# two-material block in Abaqus/CAE").
#
# Units: SI (m, s, Pa, W, K). The PDF gives lengths in cm; phi uses x in cm, so x_cm = 100 x here.
# Unknowns: disp_x, disp_y, disp_z, T in one Newton solve. Z is STATEV(1) of the UMAT.
#
# Variants (command-line overrides, see README.md):
#   prp_formulation=penalty   PRP by penalty (MOOSE devel today)
#   prp_formulation=exact     PRP by exact constraint rows (idaholab/moose#34249)
#   Constraints/active=''     no PRP, Right and Front faces free

prp_formulation = exact
prp_penalty = 1e12

# Step 3 text: phi goes to zero at t = 1e5 s. The phi formula says 5e6 s (never reached).
phi_off_time = 1e5

E_A = 200e9
nu_A = 0.30
alpha_A = 1.0e-6
E_B = 400e9
nu_B = 0.15
alpha_B = 5.0e-6

# Viscosity is not in the PDF. Placeholder: Maxwell relaxation time near 1e4 s.
eta0_A = 7.7e14
eta0_B = 1.7e15
cz = 10

[GlobalParams]
  displacements = 'disp_x disp_y disp_z'
[]

[Problem]
  extra_tag_vectors = 'ref'
[]

[Mesh]
  [box]
    type = GeneratedMeshGenerator
    dim = 3
    xmin = -0.09
    xmax = 0.09
    ymin = -0.06
    ymax = 0.06
    zmin = -0.04
    zmax = 0.04
    nx = 18
    ny = 12
    nz = 16
  []
  # GeneratedMesh ids: 0 z-, 1 y-, 2 x+, 3 y+, 4 x-, 5 z+. Names follow Table 1 of the PDF.
  [faces]
    type = RenameBoundaryGenerator
    input = box
    old_boundary = '0 1 2 3 4 5'
    new_boundary = 'Bottom Front Right Back Left Top'
  []
  [block_A]
    type = SubdomainBoundingBoxGenerator
    input = faces
    bottom_left = '-0.1 -0.1 -0.05'
    top_right = '0.1 0.1 0'
    block_id = 1
    block_name = A
  []
  [block_B]
    type = RenameBlockGenerator
    input = block_A
    old_block = 0
    new_block = B
  []
  [interface]
    type = SideSetsBetweenSubdomainsGenerator
    input = block_B
    primary_block = A
    paired_block = B
    new_boundary = Interface
  []
[]

[Functions]
  [phi_fn]
    type = ParsedFunction
    expression = 'if(t <= 1000, 3000 - 2.9 * t, if(t < t_off, 100, 0)) * (1 - (100 * x)^2 / 81)'
    symbol_names = 't_off'
    symbol_values = '${phi_off_time}'
  []
  [q_fn]
    type = ParsedFunction
    expression = 'phi^2'
    symbol_names = 'phi'
    symbol_values = 'phi_fn'
  []
  [p_fn]
    type = ParsedFunction
    expression = 'if(t < 1e5, 1e5, 0)'
  []
  [h_fn]
    type = ParsedFunction
    expression = '200 * sin(pi * t / 1e6)'
  []
  [T_inf_fn]
    type = ParsedFunction
    expression = 'if(t < 1e5, 500, 20)'
  []
  # Time step by phase: fine in Step 1 and at the start of Step 3, coarse in Step 2
  [dt_fn]
    type = PiecewiseConstant
    x = '0 500 1000 1e5'
    y = '10 25 1000 100'
  []
[]

[Variables]
  [T]
    initial_condition = 20
  []
[]

[Physics/SolidMechanics/QuasiStatic]
  [all]
    add_variables = true
    strain = FINITE
    temperature = T
    extra_vector_tags = 'ref'
    generate_output = 'stress_xx stress_yy stress_zz stress_xy stress_xz stress_yz vonmises_stress'
  []
[]

[Kernels]
  [heat_dt]
    type = HeatConductionTimeDerivative
    variable = T
  []
  [heat_conduction]
    type = HeatConduction
    variable = T
  []
  [heat_source]
    type = HeatSource
    variable = T
    block = A
    function = q_fn
  []
[]

[AuxVariables]
  [phi]
  []
  [Z]
    order = CONSTANT
    family = MONOMIAL
  []
  [rf_x]
  []
  [rf_y]
  []
  [rf_z]
  []
  [heat_flux_x]
    order = CONSTANT
    family = MONOMIAL
  []
  [heat_flux_y]
    order = CONSTANT
    family = MONOMIAL
  []
  [heat_flux_z]
    order = CONSTANT
    family = MONOMIAL
  []
[]

[AuxKernels]
  [phi]
    type = FunctionAux
    variable = phi
    function = phi_fn
    execute_on = 'initial timestep_begin'
  []
  [Z]
    type = MaterialStdVectorAux
    variable = Z
    property = state_var
    index = 0
  []
  # Nodal reaction forces (Abaqus RF): internal force from the stress divergence kernels
  [rf_x]
    type = TagVectorAux
    variable = rf_x
    v = disp_x
    vector_tag = ref
  []
  [rf_y]
    type = TagVectorAux
    variable = rf_y
    v = disp_y
    vector_tag = ref
  []
  [rf_z]
    type = TagVectorAux
    variable = rf_z
    v = disp_z
    vector_tag = ref
  []
  [heat_flux_x]
    type = DiffusionFluxAux
    variable = heat_flux_x
    diffusion_variable = T
    diffusivity = thermal_conductivity
    component = x
  []
  [heat_flux_y]
    type = DiffusionFluxAux
    variable = heat_flux_y
    diffusion_variable = T
    diffusivity = thermal_conductivity
    component = y
  []
  [heat_flux_z]
    type = DiffusionFluxAux
    variable = heat_flux_z
    diffusion_variable = T
    diffusivity = thermal_conductivity
    component = z
  []
[]

[BCs]
  # Symmetric faces
  [sym_bottom]
    type = DirichletBC
    variable = disp_z
    boundary = Bottom
    value = 0
  []
  [sym_left]
    type = DirichletBC
    variable = disp_x
    boundary = Left
    value = 0
  []
  [sym_back]
    type = DirichletBC
    variable = disp_y
    boundary = Back
    value = 0
  []
  # Top face: compressive pressure p(t) and film condition h(t) (T - T_inf(t))
  [pressure_top]
    type = Pressure
    variable = disp_z
    boundary = Top
    function = p_fn
  []
  [film_top]
    type = ConvectiveFluxFunction
    variable = T
    boundary = Top
    coefficient = h_fn
    T_infinity = T_inf_fn
  []
  # All other faces are adiabatic: natural BC, nothing to add.
[]

# Plane remains plane on Right (x+) and Front (y-). The symmetric faces already stay plane.
[Constraints]
  [prp_right]
    type = EqualValueBoundaryConstraint
    variable = disp_x
    secondary = Right
    formulation = ${prp_formulation}
    penalty = ${prp_penalty}
  []
  [prp_front]
    type = EqualValueBoundaryConstraint
    variable = disp_y
    secondary = Front
    formulation = ${prp_formulation}
    penalty = ${prp_penalty}
  []
[]

[Materials]
  # Mechanics: the same compiled UMAT in both blocks, different PROPS. phi goes in as PREDEF(1).
  [umat_A]
    type = AbaqusUMATStress
    block = A
    plugin = 'umat/two_block_umat'
    constant_properties = '${E_A} ${nu_A} ${alpha_A} ${eta0_A} ${cz}'
    num_state_vars = 1
    temperature = T
    external_fields = phi
    use_one_based_indexing = true
    analysis_step_user_object = steps
  []
  [umat_B]
    type = AbaqusUMATStress
    block = B
    plugin = 'umat/two_block_umat'
    constant_properties = '${E_B} ${nu_B} ${alpha_B} ${eta0_B} ${cz}'
    num_state_vars = 1
    temperature = T
    external_fields = phi
    use_one_based_indexing = true
    analysis_step_user_object = steps
  []
  # Thermal properties (Table 2)
  [thermal_A]
    type = HeatConductionMaterial
    block = A
    thermal_conductivity = 80
    specific_heat = 500
  []
  [thermal_B]
    type = HeatConductionMaterial
    block = B
    thermal_conductivity = 200
    specific_heat = 800
  []
  [density_A]
    type = GenericConstantMaterial
    block = A
    prop_names = density
    prop_values = 8000
  []
  [density_B]
    type = GenericConstantMaterial
    block = B
    prop_names = density
    prop_values = 3000
  []
[]

[UserObjects]
  # Abaqus *Step boundaries; set_sync_times makes the solver land on each one.
  [steps]
    type = AnalysisStepUserObject
    step_start_times = '0 500 1e5'
    set_sync_times = true
  []
[]

[Postprocessors]
  # Temperature
  [T_max]
    type = NodalExtremeValue
    variable = T
  []
  [T_max_A]
    type = NodalExtremeValue
    variable = T
    block = A
  []
  [T_max_B]
    type = NodalExtremeValue
    variable = T
    block = B
  []
  [T_interface]
    type = SideAverageValue
    variable = T
    boundary = Interface
  []
  [T_top]
    type = SideAverageValue
    variable = T
    boundary = Top
  []
  # Total heat flux through the top face [W]
  [heat_out_top]
    type = SideDiffusiveFluxIntegral
    variable = T
    boundary = Top
    diffusivity = thermal_conductivity
  []
  # Reaction force on each face [N]: sum of the nodal reactions
  [Rz_bottom]
    type = NodalSum
    variable = rf_z
    boundary = Bottom
  []
  [Rx_left]
    type = NodalSum
    variable = rf_x
    boundary = Left
  []
  [Ry_back]
    type = NodalSum
    variable = rf_y
    boundary = Back
  []
  [Rx_right]
    type = NodalSum
    variable = rf_x
    boundary = Right
  []
  [Ry_front]
    type = NodalSum
    variable = rf_y
    boundary = Front
  []
  [Rz_top]
    type = NodalSum
    variable = rf_z
    boundary = Top
  []
  # PRP check: the spread of the normal displacement on each PRP face
  [ux_right_max]
    type = NodalExtremeValue
    variable = disp_x
    boundary = Right
    value_type = max
  []
  [ux_right_min]
    type = NodalExtremeValue
    variable = disp_x
    boundary = Right
    value_type = min
  []
  [prp_right_spread]
    type = ParsedPostprocessor
    expression = 'ux_right_max - ux_right_min'
    pp_names = 'ux_right_max ux_right_min'
  []
  [uy_front_max]
    type = NodalExtremeValue
    variable = disp_y
    boundary = Front
    value_type = max
  []
  [uy_front_min]
    type = NodalExtremeValue
    variable = disp_y
    boundary = Front
    value_type = min
  []
  [prp_front_spread]
    type = ParsedPostprocessor
    expression = 'uy_front_max - uy_front_min'
    pp_names = 'uy_front_max uy_front_min'
  []
  # Interface stresses and the state variable
  [szz_interface]
    type = SideAverageValue
    variable = stress_zz
    boundary = Interface
  []
  [sxx_interface]
    type = SideAverageValue
    variable = stress_xx
    boundary = Interface
  []
  [vonmises_max]
    type = ElementExtremeValue
    variable = vonmises_stress
  []
  [Z_max]
    type = ElementExtremeValue
    variable = Z
  []
  [uz_top]
    type = SideAverageValue
    variable = disp_z
    boundary = Top
  []
[]

[VectorPostprocessors]
  # Through-thickness profile at the block center
  [center_line]
    type = LineValueSampler
    variable = 'T stress_xx stress_zz'
    start_point = '0 0 -0.04'
    end_point = '0 0 0.04'
    num_points = 33
    sort_by = z
    execute_on = final
  []
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = PJFNK
  petsc_options_iname = '-pc_type -pc_factor_mat_solver_type'
  petsc_options_value = 'lu superlu_dist'
  # No automatic scaling: it rescales the tagged vector and so the nodal reactions
  line_search = none
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-8
  l_max_its = 100
  nl_max_its = 25

  start_time = 0
  end_time = 1.05e5
  [TimeStepper]
    type = FunctionDT
    function = dt_fn
    cutback_factor_at_failure = 0.5
  []
[]

[Outputs]
  exodus = true
  csv = true
  print_linear_residuals = false
  perf_graph = true
[]
