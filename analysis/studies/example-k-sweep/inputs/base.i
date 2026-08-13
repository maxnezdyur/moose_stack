# Minimal steady heat-conduction problem used by the example sweep study.
# The analysis toolkit sweeps the conductivity via a command-line override of
# Materials/thermal/prop_values and reads peak_T / avg_T from the CSV output.

[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 10
    ny = 10
  []
[]

[Variables]
  [T]
  []
[]

[Kernels]
  [diff]
    type = MatDiffusion
    variable = T
    diffusivity = k
  []
[]

[Materials]
  [thermal]
    type = GenericConstantMaterial
    prop_names = 'k'
    prop_values = '1.0'
  []
[]

[BCs]
  [left]
    type = DirichletBC
    variable = T
    boundary = left
    value = 300
  []
  [right]
    type = DirichletBC
    variable = T
    boundary = right
    value = 900
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
[]

[Postprocessors]
  [peak_T]
    type = NodalExtremeValue
    variable = T
    value_type = max
  []
  [avg_T]
    type = ElementAverageValue
    variable = T
  []
[]

[Outputs]
  csv = true
[]
