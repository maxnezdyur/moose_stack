[Mesh]
  type = GeneratedMesh
  dim = 3
[]
[Problem]
  kernel_coverage_check = false
[]
[Variables]
  [u]
  []
[]
[AuxVariables]
  [phi]
  []
[]
[Functions]
  [phi_fn]
    type = ParsedFunction
    expression = '100 + t'
  []
[]
[AuxKernels]
  [phi]
    type = FunctionAux
    variable = phi
    function = phi_fn
    execute_on = 'initial timestep_begin'
  []
[]
[UserObjects]
  [uel]
    type = AbaqusUserElement
    variables = u
    external_fields = phi
    plugin = probe_uel
    num_state_vars = 0
    constant_properties = '0'
  []
[]
[Executioner]
  type = Transient
  solve_type = NEWTON
  num_steps = 3
  dt = 1
[]
