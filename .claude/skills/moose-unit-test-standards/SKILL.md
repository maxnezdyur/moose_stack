---
name: moose-unit-test-standards
description: MOOSE gtest unit test standards for moose, blackbear, and isopod. Auto-loads when authoring or editing files under unit/ or files matching *Test.{C,h}. Covers the two fixtures (MooseObjectUnitTest, MFEMObjectUnitTest), factory-based object construction, the _throw_on_error pattern, MooseUnitUtils helpers, the build and run recipe, and the unit-vs-regression decision.
user-invocable: false
---

# MOOSE Unit Test Standards

Standards for gtest unit tests in `moose/unit/`, `moose/modules/<m>/unit/`, `blackbear/unit/`,
and `isopod/unit/`. Regression tests (`tests` HIT specs, `.i` inputs, gold files) follow
`moose-test-standards`; `moose-run-tests` covers only the TestHarness `./run_tests` and does not
apply to unit binaries.

## Layout and naming

- One source file per class or area: `<repo>/unit/src/<ThingUnderTest>Test.C`.
- A fixture class lives in the matching header `<repo>/unit/include/<ThingUnderTest>Test.h`;
  a header exists only when a fixture is needed.
- `TEST(<ThingUnderTest>Test, <action>)`: the suite name matches the file base, so
  `--gtest_filter=<ThingUnderTest>Test.*` selects the file.
- CSV and JSON data fixtures go in `<repo>/unit/files/`.
- Module unit trees have the same shape under `moose/modules/<m>/unit/` and build
  `<m>-unit-opt`. `blackbear/unit/` and `isopod/unit/` currently hold only a stub `SampleTest.C`.
- A test in `<m>/unit/` can only include types from modules its `unit/Makefile` enables; check
  the flags before adding a cross-module dependency.

## Build and run

    bash <meta-root>/scripts/conda-run.sh -C <repo>/unit -- make -j 2
    bash <meta-root>/scripts/conda-run.sh -C <repo>/unit -- ./run_tests --gtest_filter=<Suite>.*
    bash <meta-root>/scripts/conda-run.sh -C <repo>/unit -- ./run_tests            # everything
    METHOD=dbg ... ./run_tests                                                     # dbg binary

On INL HPC hostnames run the same commands bare. `unit/run_tests` is a shell wrapper that
`exec`s `./<app>-unit-$METHOD` with its arguments; it is not the TestHarness, there is no `tests`
HIT spec under `unit/`, and gtest discovers tests at runtime. Build internals are in
`moose/unit/Makefile` and `moose/modules/heat_transfer/unit/Makefile`.

## Error handling in tests

`unit/src/main.C` sets `Moose::_throw_on_error` and `Moose::_throw_on_warning` after
`InitGoogleTest`, which turns `mooseError` and `mooseWarning` into `MooseRuntimeError` exceptions
instead of `abort()`. That is what makes `EXPECT_THROW` and the `MOOSEERROR` macros work.
`mooseAssert` is not affected: it is debug-only and aborts, so an assert-guarded path is tested
with `EXPECT_DEATH` (rare in MOOSE) or not at all.

| Form | When |
|---|---|
| `EXPECT_THROW(stmt, MooseException)` | Negative path where the exception type is fixed |
| `EXPECT_THROW(stmt, MooseRuntimeError)` | A `mooseError` path |
| `EXPECT_MOOSEERROR_MSG_CONTAINS(stmt, "substr")` | A `mooseError` path with a message check (preferred) |

`moose/framework/include/utils/MooseUnitUtils.h` provides `Moose::UnitUtils::assertThrows<Ex>(action,
"substring")`, the macros `EXPECT_THROW_MSG`, `EXPECT_THROW_MSG_CONTAINS`, `EXPECT_MOOSEERROR_MSG`,
`EXPECT_MOOSEERROR_MSG_CONTAINS` (each with an `ASSERT_` twin), and `Moose::UnitUtils::TempFile`
(RAII temp file). The `MOOSEERROR_*` macros wrap the statement in `Moose::ScopedThrowOnError`,
so they also work in code that does not run through `main.C`. Prefer them over try/catch plus
`ASSERT_NE(msg.find(...), npos)`.

Tests that flip global state (`Registry`, `AppFactory`, `CapabilityRegistry`,
`Moose::_throw_on_error`, `Moose::_throw_on_warning`) restore it, or use
`Moose::ScopedThrowOnError`; that state outlives the test.

## Fixtures

There are two fixtures and no `GtestApp` class; the convention is `<Name>UnitApp` plus one of:

- `MooseObjectUnitTest` (`moose/framework/include/base/MooseObjectUnitTest.h`): builds a 3D
  2x2x2 `GeneratedMesh`, an `FEProblem` named `"problem"`, Gauss quadrature, and wires the
  problem into the app's `ActionWarehouse`. Exposes `_app`, `_factory`, `_mesh`, `_fe_problem`.
  Use it when the SUT is a `MooseObject` constructed through the factory.
- `MFEMObjectUnitTest` (`moose/unit/include/MFEMObjectUnitTest.h`): same shape, builds an
  `MFEMMesh` and `MFEMProblem` from a real `.mesh` file; gated by `#ifdef MOOSE_MFEM_ENABLED`.

Both expose `addObject<T>(type, name, params)`, which calls `_fe_problem->addObject<T>` and returns
the single created object.

```cpp
class ParsedFunctionTest : public MooseObjectUnitTest
{
public:
  ParsedFunctionTest() : MooseObjectUnitTest("MooseUnitApp") {}
};
```

The base constructor takes the registered app name (`"MooseUnitApp"`, `"HeatTransferApp"`,
`"FluidPropertiesApp"`, ...); a typo fails at runtime, not at compile time.

`TYPED_TEST` is not used in the tree. AD and non-AD variants are separate overloads of the same
test body (`Real` and `ADReal`).

## Constructing a MOOSE object

```cpp
InputParameters params = _factory.getValidParams("ParsedFunction");
params.set<FEProblem *>("_fe_problem")          = _fe_problem.get();
params.set<FEProblemBase *>("_fe_problem_base") = _fe_problem.get();
params.set<std::string>("expression") = "x + 1.5*y + 2*z + t/4";
_fe_problem->addFunction("ParsedFunction", "test0", params);
auto & f = _fe_problem->getFunction("test0");
```

The shape is `getValidParams(type)`, set params, `_fe_problem->add<X>(type, name, params)`, then
`get<X>(name)`; the same holds for `addUserObject`/`getUserObject<T>` and, for kernels,
`addObject<T>`. The private `_fe_problem` and `_fe_problem_base` params are required: classes read
them from `InputParameters`, and omitting them null-derefs at runtime instead of erroring. The
warehouse owns every object, so a test does not `new` a `MooseObject` directly.

## Reference unit tests

Read one of the same kind before authoring.

| Pattern | Reference |
|---|---|
| Pure utility class, no fixture | `moose/unit/src/LinearInterpolationTest.C` |
| Fixture exercising a MOOSE object via the factory | `moose/unit/include/ParsedFunctionTest.h` + `moose/unit/src/ParsedFunctionTest.C` |
| `SetUp()` + tensor data | `moose/unit/include/RankTwoTensorTest.h` + `moose/unit/src/RankTwoTensorTest.C` |
| Module fluid-property / AD chain rule | `moose/modules/fluid_properties/unit/include/ADFluidPropsTest.h` + `.../unit/src/ADFluidPropsTest.C` |
| Negative path with `EXPECT_THROW` | `moose/unit/src/MatrixToolsTest.C` |
| MFEM kernel type-mapping | `moose/unit/src/MFEMKernelTest.C` |
| Substring error-message assertion | `moose/unit/src/InputParametersTest.C` |
| Module `unit/Makefile` | `moose/modules/heat_transfer/unit/Makefile` |

## Unit vs regression

Unit-test whatever runs in milliseconds without an executioner: pure utility classes (math,
interpolation, parsing), AD chain-rule correctness on a material property or UserObject,
`validParams` edge cases, a specific `mooseError` message, and factory wiring (does `<Type>`
register, does `getValidParams` work). Write a regression test only once a residual has to be
assembled: time integration, multiphysics coupling, convergence behavior, MPI or threading
correctness on a real solve, a kernel, BC, or material whose behavior depends on quadrature,
neighboring elements, or boundary integration, or a check of the integrated solution against a
CSV or Exodus gold file.
