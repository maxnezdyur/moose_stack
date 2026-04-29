---
name: moose-unit-test-standards
description: MOOSE gtest unit test standards for moose, blackbear, and isopod. Auto-loads when authoring or editing files under unit/ or files matching *Test.{C,h}. Covers fixtures (MooseObjectUnitTest, MFEMObjectUnitTest), the build system, the _throw_on_error pattern, MooseUnitUtils helpers, factory-based object construction, common pitfalls, and the unit-vs-regression decision.
user-invocable: false
---

# MOOSE Unit Test Standards

Reference for authoring gtest-based unit tests in `moose/unit/`, `moose/modules/<m>/unit/`, `blackbear/unit/`, and `isopod/unit/`. Apply whenever editing a `*Test.C`/`*Test.h` file under any `unit/` directory.

For *regression* tests (`tests` HIT specs + `.i` inputs + gold), see **moose-test-standards**. For running anything, see **moose-run-tests**.

## Layout

```
<repo>/unit/
  Makefile         # builds <name>-unit-opt
  run_tests        # 30-line shell wrapper around the binary
  src/             # *.C — one file per logical unit
    main.C
    base/<Name>UnitApp.C
    LinearInterpolationTest.C, MooseUtilsTest.C, ParsedFunctionTest.C, ...
  include/         # *.h — only when a fixture class is needed
    base/<Name>UnitApp.h
    ParsedFunctionTest.h, RankTwoTensorTest.h, ...
  files/           # CSV/JSON data fixtures
```

Module unit tests follow the same shape under `moose/modules/<m>/unit/` and produce `<m>-unit-opt`. `blackbear/unit/` and `isopod/unit/` exist but currently ship only stub `SampleTest.C` files.

### Naming

- One source file per class/area: `<ThingUnderTest>Test.C`. e.g. `LinearInterpolationTest.C`, `MathUtilsTest.C`.
- Fixture class lives in matching `.h` (e.g. `ParsedFunctionTest.h` declares `class ParsedFunctionTest : public MooseObjectUnitTest`).
- `TEST(<ThingUnderTest>Test, <action>)` — first arg is conventionally the same `<ThingUnderTest>Test` string.

## Build system

`moose/unit/Makefile` differs from a regular MOOSE app Makefile in three ways:

- Adds `-DMOOSE_UNIT_TEST` to `ADDITIONAL_CPPFLAGS`.
- Adds `gtest` to `ADDITIONAL_INCLUDES` and links against `framework/contrib/gtest/libgtest.la`.
- `APPLICATION_NAME` ends in `-unit` (binary becomes `moose-unit-opt`, not `moose-opt`).
- `app_BASE_DIR :=` is intentionally blank.

Module `unit/Makefile` enables specific modules then includes `modules.mk`:

```make
HEAT_TRANSFER := yes
include $(MOOSE_DIR)/modules/modules.mk
APPLICATION_NAME := heat_transfer-unit
```

Meta-app Makefiles (`blackbear/unit/Makefile`) flag-flip every module they depend on.

### Building & running

    cd moose/unit && make -j8                       # builds moose-unit-opt
    ./run_tests                                     # invokes ./moose-unit-$METHOD
    ./moose-unit-opt --gtest_filter=MooseUtils.*    # direct gtest call
    METHOD=dbg ./run_tests                          # use dbg binary

`unit/run_tests` is a 30-line shell wrapper that just `exec`s the binary. There is **no** `tests` HIT spec file in `unit/` — gtest discovers tests at runtime.

## `main.C` — every unit binary has one

```cpp
GTEST_API_ int main(int argc, char ** argv)
{
  testing::InitGoogleTest(&argc, argv);   // must precede MooseInit
  MooseInit init(argc, argv);
  registerApp(MooseUnitApp);
  Moose::_throw_on_error = true;          // makes mooseError catchable
  Moose::_throw_on_warning = true;
  return RUN_ALL_TESTS();
}
```

The two flag flips are load-bearing: they turn `mooseError` and `mooseWarning` into exceptions (`MooseRuntimeError`) so `EXPECT_THROW`/`EXPECT_MOOSEERROR_MSG_CONTAINS` work. Without them, `mooseError` would `abort()` the process.

`mooseAssert` is **not** affected by these flags — it's debug-only and aborts. You cannot test an `mooseAssert`-protected path with `EXPECT_THROW`.

## Fixtures — two of them, no others

### `MooseObjectUnitTest`

`moose/framework/include/base/MooseObjectUnitTest.h`. Inherits `::testing::Test`. Constructor builds a real `GeneratedMesh` (3D 2x2x2), an `FEProblem` named `"problem"`, gauss quadrature, and wires the problem into the app's `ActionWarehouse`. Exposes `_app`, `_factory`, `_mesh`, `_fe_problem`.

Use when the SUT is a `MooseObject` you need to construct via the factory.

```cpp
class ParsedFunctionTest : public MooseObjectUnitTest
{
public:
  ParsedFunctionTest() : MooseObjectUnitTest("MooseUnitApp") {}
};
```

Pass the registered MOOSE app name to the base ctor (`"MooseUnitApp"`, `"FluidPropertiesApp"`, `"HeatTransferApp"`, ...).

### `MFEMObjectUnitTest`

`moose/unit/include/MFEMObjectUnitTest.h`. Same shape but builds an `MFEMMesh` + `MFEMProblem` from a real `.mesh` file. Gated `#ifdef MOOSE_MFEM_ENABLED`.

Both fixtures expose `addObject<T>(type, name, params)` which calls `_fe_problem->addObject<T>` and returns the singleton.

There is **no `GtestApp` class**. The convention is `<Name>UnitApp` + one of these two fixtures.

## gtest patterns used

| Form | When |
|---|---|
| `TEST(suite, name)` | Pure utility class, no MOOSE state |
| `TEST_F(Fixture, name)` | Need mesh/FEProblem/factory |
| `EXPECT_THROW(stmt, MooseException)` | Negative path, exception type fixed |
| `EXPECT_THROW(stmt, MooseRuntimeError)` | mooseError path (works because of `_throw_on_error`) |
| `EXPECT_MOOSEERROR_MSG_CONTAINS(stmt, "substr")` | mooseError + substring check (preferred) |
| `EXPECT_DOUBLE_EQ(a, b)` / `EXPECT_NEAR(a, b, tol)` | Floating point |
| `EXPECT_EQ` / `ASSERT_EQ` | Integer / discrete |

`TYPED_TEST` is **not** in use anywhere in the tree. AD vs non-AD type variation uses manual overloads (Real / ADReal versions of the same test) instead.

## `MooseUnitUtils.h` helpers

`moose/framework/include/utils/MooseUnitUtils.h` ships:

- `Moose::UnitUtils::assertThrows<Ex>(action, "substring")` — function form. Used in `InputParametersTest.C`.
- Macros: `EXPECT_THROW_MSG`, `ASSERT_THROW_MSG`, `EXPECT_THROW_MSG_CONTAINS`, `ASSERT_THROW_MSG_CONTAINS`, `EXPECT_MOOSEERROR_MSG`, `ASSERT_MOOSEERROR_MSG`, `EXPECT_MOOSEERROR_MSG_CONTAINS`, `ASSERT_MOOSEERROR_MSG_CONTAINS`. The `MOOSEERROR_*` variants auto-wrap with `Moose::ScopedThrowOnError` so they work even when not running through `main.C`.
- `Moose::UnitUtils::TempFile` — RAII temp file for tests touching disk.

Prefer `EXPECT_MOOSEERROR_MSG_CONTAINS(stmt, "substr")` over the older try/catch + `ASSERT_NE(msg.find(...), npos)` pattern.

## Constructing a MOOSE object — the canonical pattern

```cpp
InputParameters params = _factory.getValidParams("ParsedFunction");
params.set<FEProblem *>("_fe_problem")          = _fe_problem.get();
params.set<FEProblemBase *>("_fe_problem_base") = _fe_problem.get();
params.set<std::string>("expression") = "x + 1.5*y + 2*z + t/4";
_fe_problem->addFunction("ParsedFunction", "test0", params);
auto & f = _fe_problem->getFunction("test0");
```

Steps: `getValidParams(type)` from the factory → mutate → `_fe_problem->addX(type, name, params)` → fetch via `getX<T>(name)`.

Same shape for `addUserObject`/`getUserObject<T>`, and for kernels via `addObject<T>`.

**Don't `new MooseObject(...)` directly.** Registration and lifecycle break.

## Reference unit tests — read one before authoring

| Pattern | Reference |
|---|---|
| Pure utility class, no fixture | `moose/unit/src/LinearInterpolationTest.C` |
| Fixture exercising MOOSE object via factory | `moose/unit/include/ParsedFunctionTest.h` + `moose/unit/src/ParsedFunctionTest.C` |
| `SetUp()` + tensor data | `moose/unit/include/RankTwoTensorTest.h` + `moose/unit/src/RankTwoTensorTest.C` |
| Module fluid-property / AD chain rule | `moose/modules/fluid_properties/unit/src/ADFluidPropsTest.{h,C}` |
| Negative path with `EXPECT_THROW` | `moose/unit/src/MatrixToolsTest.C` |
| MFEM kernel type-mapping | `moose/unit/src/MFEMKernelTest.C` |
| Substring error-msg assertion | `moose/unit/src/InputParametersTest.C` |
| Module Makefile pattern | `moose/modules/heat_transfer/unit/Makefile` |

## Pitfalls

1. **`mooseAssert` ≠ throwable.** It aborts even with `_throw_on_error = true`. You can't test it with `EXPECT_THROW`. Either use `EXPECT_DEATH` (rare in MOOSE) or skip the negative-path test.
2. **Forgetting `_fe_problem`/`_fe_problem_base` private params.** Many classes (parsed functions, etc.) read these from `InputParameters`. Forgetting them causes a null-deref at runtime instead of a clean error.
3. **Memory ownership.** Always go through `_fe_problem->addX(...)` or `_factory.create...`. The warehouse owns the object. `new MooseObject(...)` directly breaks lifecycle.
4. **`SetUp()` spelling.** gtest looks for `void SetUp() override;`. `setUp` (camelCase) silently disables the hook. Always include `override`.
5. **Tests that mutate global state.** `Registry`, `AppFactory`, `CapabilityRegistry`, `Moose::_throw_on_error`/`_throw_on_warning` outlive any single test. Tests that flip them must restore (or use `Moose::ScopedThrowOnError`).
6. **Module unit binary scope.** A test in `heat_transfer/unit/` cannot include solid_mechanics types unless the module Makefile enables them. Check the Makefile's module flags before adding cross-module dependencies.
7. **`run_tests` (this dir, gtest wrapper) ≠ `run_tests` (TestHarness Python).** They're different scripts. Unit `run_tests` is a tiny shell file with no spec parsing.
8. **App name typo in fixture ctor.** `MooseObjectUnitTest("MooseUnitApp")` — must match a registered app. A typo gives a runtime error, not a compile error.
9. **`TEST` first arg should match the file base.** Convention: `TEST(LinearInterpolationTest, sample)` lives in `LinearInterpolationTest.C`. Mismatches make `--gtest_filter` confusing.

## Unit vs regression — when to write which

Write a **unit test** when:
- The SUT is a pure utility class (math, interpolation, parsing).
- You want AD chain-rule correctness on a property/UO.
- You want parameter validation / `validParams` edge cases.
- You want a specific `mooseError` message tested.
- You want factory wiring (does `<Type>` register? does `getValidParams` work?).
- The SUT is testable in milliseconds without an executioner.

Write a **regression test** when:
- The SUT only makes sense once a residual is being assembled.
- You need time integration, multi-physics coupling, or convergence behavior.
- You need MPI/threading parallel correctness on a real solve.
- The assertion is "the integrated solution matches a CSV/Exodus gold file."
- You're testing a kernel/BC/material whose behavior depends on quadrature, neighboring elements, or boundary integration.

If the SUT can be tested as a unit, prefer it. Reach for regression only when you genuinely need the residual.
