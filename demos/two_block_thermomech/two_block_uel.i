# The two-block problem of main.pdf with a coupled temperature-displacement UEL in place of the
# UMAT and the MOOSE heat-conduction kernels: uel/two_block_uel.f90 computes the internal force,
# the heat capacity, the conduction and the heat source of every HEX8, and its full 32 x 32
# element Jacobian. MOOSE adds the mesh, the face loads (pressure and film), the symmetry BCs, the
# exact plane-remains-plane constraints, the step sequence and the outputs.
#
# Same problem and same units as two_block.i. The UEL is small strain; compare with
# two_block.i run with Physics/SolidMechanics/QuasiStatic/all/strain=SMALL incremental=true.

phi_off_time = 1e5

E_A = 200e9
nu_A = 0.30
alpha_A = 1.0e-6
E_B = 400e9
nu_B = 0.15
alpha_B = 5.0e-6

# Same placeholder viscosities as two_block.i
eta0_A = 7.7e14
eta0_B = 1.7e15
cz = 10

[GlobalParams]
  displacements = 'disp_x disp_y disp_z'
[]

[Problem]
  kernel_coverage_check = false
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

[Variables]
  [disp_x]
  []
  [disp_y]
  []
  [disp_z]
  []
  [T]
    initial_condition = 20
  []
[]

[Functions]
  [phi_fn]
    type = ParsedFunction
    expression = 'if(t <= 1000, 3000 - 2.9 * t, if(t <= t_off, 100, 0)) * (1 - (100 * x)^2 / 81)'
    symbol_names = 't_off'
    symbol_values = '${phi_off_time}'
  []
  [p_fn]
    type = ParsedFunction
    expression = 'if(t <= 1e5, 1e5, 0)'
  []
  [h_fn]
    type = ParsedFunction
    expression = '200 * sin(pi * t / 1e6)'
  []
  [T_inf_fn]
    type = ParsedFunction
    expression = 'if(t <= 1e5, 500, 20)'
  []
  [dt_fn]
    type = PiecewiseConstant
    x = '0 500 1000 99000'
    y = '10 25 1000 100'
  []
[]

[AuxVariables]
  # PREDEF field 1 of the UEL, nodal
  [phi]
  []
  [rf_x]
  []
  [rf_y]
  []
  [rf_z]
  []
[]

[AuxKernels]
  [phi]
    type = FunctionAux
    variable = phi
    function = phi_fn
    execute_on = 'initial timestep_begin'
  []
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
[]

[UserObjects]
  # One UEL per block: the blocks differ only in PROPS. PROPS(9) = 1 turns on q = phi^2.
  [uel_A]
    type = AbaqusUserElement
    block = A
    variables = 'disp_x disp_y disp_z T'
    external_fields = phi
    plugin = 'uel/two_block_uel'
    jtype = 1
    num_state_vars = 56
    constant_properties = '${E_A} ${nu_A} ${alpha_A} ${eta0_A} ${cz} 80 8000 500 1'
    extra_vector_tags = 'ref'
  []
  [uel_B]
    type = AbaqusUserElement
    block = B
    variables = 'disp_x disp_y disp_z T'
    external_fields = phi
    plugin = 'uel/two_block_uel'
    jtype = 1
    num_state_vars = 56
    constant_properties = '${E_B} ${nu_B} ${alpha_B} ${eta0_B} ${cz} 200 3000 800 0'
    extra_vector_tags = 'ref'
  []
  [steps]
    type = AnalysisStepUserObject
    step_start_times = '0 500 1e5'
    set_sync_times = true
  []
[]

[BCs]
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
  [pressure_top]
    type = Pressure
    variable = disp_z
    boundary = Top
    function = p_fn
    use_displaced_mesh = false
  []
  [film_top]
    type = ConvectiveFluxFunction
    variable = T
    boundary = Top
    coefficient = h_fn
    T_infinity = T_inf_fn
  []
[]

[Constraints]
  [prp_right]
    type = EqualValueBoundaryConstraint
    variable = disp_x
    secondary = Right
    formulation = exact
  []
  [prp_front]
    type = EqualValueBoundaryConstraint
    variable = disp_y
    secondary = Front
    formulation = exact
  []
[]

[Postprocessors]
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
  [uz_top]
    type = SideAverageValue
    variable = disp_z
    boundary = Top
  []
  [ux_right]
    type = SideAverageValue
    variable = disp_x
    boundary = Right
  []
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
[]

[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]

[Executioner]
  type = Transient
  solve_type = NEWTON
  petsc_options_iname = '-pc_type -pc_factor_mat_solver_type'
  petsc_options_value = 'lu superlu_dist'
  line_search = none
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-8
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
