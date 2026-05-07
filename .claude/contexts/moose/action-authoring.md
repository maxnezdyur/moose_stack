# Authoring: Actions and Physics

The Action system is MOOSE's setup-phase scaffolding: Actions run during input parsing to construct MooseObjects (kernels, BCs, variables, etc.) on behalf of the user. PhysicsBase and ActionComponent are specialized Actions that produce, respectively, an entire physics or a geometric component with its associated objects.

## When to use this (vs alternatives)

Decision tree:
- Want users to type a short input block that expands into N MooseObjects? -> **Action**.
- Want a whole-physics shorthand (variables + kernels + BCs + ICs + outputs)? -> **PhysicsBase**.
- Want a geometric-component abstraction (CylinderComponent, PinComponent, ...)? -> **ActionComponent**.
- Just want to set parameters dynamically per object during runtime? -> see [postprocessor-authoring.md](./postprocessor-authoring.md) / Control system, not Action.
- Want to add exactly one MooseObject of an existing type from a block? -> the framework's `Add<X>Action` (e.g., `AddKernelAction`, `AddBCAction`) likely already covers it via `[Kernels]`, `[BCs]`, etc.; no new action needed.

PhysicsBase vs Action: PhysicsBase provides a fixed scaffolding of `addX()` virtuals (one per object type) and dispatches the standard tasks for you (`act()` is `final`). A plain Action is freer-form: you implement `act()` and dispatch on `_current_task` yourself. Choose PhysicsBase when you are creating a coherent system of variables + kernels + BCs + ICs + outputs; choose Action when your block emits a small, custom set of objects that doesn't fit the physics-shorthand pattern.

ActionComponent vs PhysicsBase: a Component owns the *mesh* and may host multiple Physics; a Physics owns the *equations* (variables, kernels, BCs) on whatever mesh exists. The two are designed to compose: `CylinderComponent` adds a cylinder mesh and forwards block restriction to any Physics referencing it via `ComponentPhysicsInterface`.

## Contract

### **Action** (framework/include/actions/Action.h:34)
Purpose: run once per task to add MooseObjects to the simulation.
- **Required overrides**: `act()` (line 120) — pure virtual; runs once per task this action is registered against.
- **Multiple tasks**: dispatch on `_current_task` (line 172, a `const std::string &` member). Each registered task creates a separate Action instance with `_current_task` set accordingly; `_specific_task_name` (line 159) and `_all_tasks` (line 166) are also available.
- **validParams() additions**: typical params for the input block your action handles (e.g., variable names, boundary lists, displacement components).
- **Key members** (lines 168–184): `_awh` (ActionWarehouse), `_mesh`, `_displaced_mesh`, `_problem` (FEProblemBase), `_app`. `_factory` is inherited from `ParallelParamObject`.
- **Lifecycle**: constructed early; `act()` invoked via `timedAct()` (line 52) once per task in dependency order.

### **MooseObjectAction** (framework/include/actions/MooseObjectAction.h:16)
- Specialization for actions that create exactly one MooseObject from an input block. Holds `_type` (line 43) — the object type string — and `_moose_object_pars` (line 46) — InputParameters for the to-be-created object, accessed via `getObjectParams()`.
- Used by `AddKernelAction`, `AddBCAction`, `AddMaterialAction`, etc. Rarely subclassed by user code; the existing `Add<X>Action`s already cover the standard `[Kernels]`, `[BCs]`, `[Materials]`, etc. blocks.

### **PhysicsBase** (framework/include/physics/PhysicsBase.h:30)
- `act()` is `final` (line 46) — do not override. It dispatches to the addX virtuals based on `_current_task`.
- **Override the addX you need** (lines 292–321, all empty by default, all private — override as `protected` or `public` in derived):
  - Variables/ICs: `addSolverVariables`, `addAuxiliaryVariables`, `addInitialConditions`
  - Kernels: `addFEKernels`, `addFVKernels`, `addNodalKernels`, `addDiracKernels`, `addDGKernels`, `addScalarKernels`, `addInterfaceKernels`, `addFVInterfaceKernels`
  - BCs: `addFEBCs`, `addFVBCs`, `addNodalBCs`, `addPeriodicBCs`
  - Other: `addFunctions`, `addAuxiliaryKernels`, `addMaterials`, `addFunctorMaterials`, `addUserObjects`, `addCorrectors`, `addMultiApps`, `addTransfers`, `addPostprocessors`, `addVectorPostprocessors`, `addReporters`, `addOutputs`, `addPreconditioning`, `addExecutioner`, `addExecutors`
- **Optional**: `actOnAdditionalTasks()` (line 49) for custom tasks; `addAdditionalRelationshipManagers()` via overridden `addRelationshipManagers()` (line 279); `checkIntegrity()` (line 257) and `checkIntegrityEarly()` (line 286).
- **Required tasks**: register with `registerPhysicsBaseTasks(app, ClassName)` (line 22) — covers `init_physics`, `copy_vars_physics`, `check_integrity_early_physics`. Add per-addX-task registrations on top.
- **Coupling**: `getCoupledPhysics<T>(name, allow_fail)` and `getCoupledPhysics<T>(allow_fail)` (lines 84–88) to retrieve sibling Physics from the warehouse.
- **Block restriction**: `addBlocks`, `blocks()`, `assignBlocks()`, `hasBlocks()`, `shouldCreateVariable/IC/TimeDerivative()` (lines 56–239) handle merging block restrictions across components.

### **ActionComponent** (framework/include/actioncomponents/ActionComponent.h:26)
- `act()` is `final` (line 33) — like PhysicsBase, it dispatches to virtual addX hooks.
- **Required override**: `addMeshGenerators()` (line 62) for components that own their mesh.
- **Optional**: `addPositionsObject`, `addUserObjects`, `setupComponent`, `addSolverVariables`, `addPhysics`, `addMaterials`, `checkIntegrity`, `actOnAdditionalTasks` (lines 62–80).
- **Registration**: `registerActionComponent(app, ClassName)` (line 20) wraps `registerMooseAction(..., "list_component")`.
- **Composability**: mix in `ComponentPhysicsInterface`, `ComponentBoundaryConditionInterface`, `ComponentInitialConditionInterface`, `ComponentMaterialPropertyInterface`, `ComponentMeshTransformHelper` to wire the component to Physics, BCs, ICs, materials, and mesh transforms — see `CylinderComponent` (framework/include/actioncomponents/CylinderComponent.h:23) for the canonical example.

## Coupling & material properties

Actions don't compute residuals — they construct objects that do. The patterns to know:
- `_problem`: `std::shared_ptr<FEProblemBase>` reference (Action.h:178). Use `_problem->addKernel(type, name, params)`, `_problem->addBoundaryCondition(...)`, `_problem->addAuxKernel(...)`, `_problem->addMaterial(...)`, `_problem->addVariable(...)` to create objects.
- `_factory`: `Factory &` (inherited via `ParallelParamObject`). Use `_factory.getValidParams(type)` to retrieve a fresh InputParameters for the object type, set fields, then pass to `_problem->addX`. `MooseObjectAction` already holds `_moose_object_pars` for this purpose.
- `_awh`: `ActionWarehouse &` (Action.h:169). Use `_awh.getActions<T>()` to find sibling actions of a given type — essential for cross-action coordination (e.g., a Physics looking up its Components).
- `_console`: standard `MooseObject` console stream for warnings/info during setup.
- **Order of operations**: set parameters on a created object's InputParameters BEFORE the `_problem->addKernel(...)` call. After the call, the object is constructed and your local InputParameters copy no longer matters.
- **MooseObjectAction shortcut**: `_moose_object_pars` is the params object the parser populated from the input block; mutate it in `act()` then pass to `_problem->addX(_type, _name, _moose_object_pars)`.

## Registration & build

`registerMooseAction("MooseApp", MyAction, "add_kernel")` (framework/include/base/Registry.h:39) — one registration per task the action handles. The macro generates a static initializer that adds the action to the registry under the given app label.

`registerSyntax("MyAction", "Modules/MyModule/*")` (framework/include/actions/ActionFactory.h:23) — bind input syntax path to the action so `[Modules/MyModule/foo]` instantiates `MyAction`. Wildcards (`*`) match any sub-block name. Variants: `registerSyntaxTask` (per-task), `registerDeprecatedSyntax`.

`registerTask("name", is_required)` and `addTaskDependency("a", "b")` (ActionFactory.h:33, 40) — used in your `App.C::registerAll` to declare custom tasks and order them.

For PhysicsBase: use `registerPhysicsBaseTasks(app, ClassName)` plus an explicit `registerMooseAction(app, ClassName, "add_kernel")` (or whichever addX-task) for each addX you override. For ActionComponent: use `registerActionComponent(app, ClassName)`.

File locations (framework):
- Headers: `framework/include/actions/`, `framework/include/physics/`, `framework/include/actioncomponents/`
- Sources: `framework/src/actions/`, `framework/src/physics/`, `framework/src/actioncomponents/`
- Syntax registration: `framework/src/base/Moose.C`/`MooseSyntax.C` for framework, or `modules/<X>/src/base/<X>App.C` (e.g., `modules/contact/src/base/ContactApp.C:43`) for module-level actions.

## Minimal scaffold

A small Action that adds one Kernel and one BC for a `[FooConvDiff]` input block. Header + .C, ~40 lines each. The action is registered on two tasks (`add_kernel`, `add_bc`) and dispatches on `_current_task`.

```cpp
// FooConvDiffAction.h
#pragma once
#include "Action.h"

class FooConvDiffAction : public Action
{
public:
  static InputParameters validParams();
  FooConvDiffAction(const InputParameters & params);
  virtual void act() override;
};
```

```cpp
// FooConvDiffAction.C
#include "FooConvDiffAction.h"
#include "FEProblemBase.h"
#include "Factory.h"

registerMooseAction("MyApp", FooConvDiffAction, "add_kernel");
registerMooseAction("MyApp", FooConvDiffAction, "add_bc");

InputParameters
FooConvDiffAction::validParams()
{
  InputParameters params = Action::validParams();
  params.addRequiredParam<VariableName>("variable", "the field");
  params.addRequiredParam<RealVectorValue>("velocity", "advection vel");
  params.addRequiredParam<BoundaryName>("inlet", "inlet boundary");
  return params;
}

FooConvDiffAction::FooConvDiffAction(const InputParameters & params) : Action(params) {}

void
FooConvDiffAction::act()
{
  if (_current_task == "add_kernel")
  {
    auto kp = _factory.getValidParams("ConservativeAdvection");
    kp.set<NonlinearVariableName>("variable") = getParam<VariableName>("variable");
    kp.set<RealVectorValue>("velocity") = getParam<RealVectorValue>("velocity");
    _problem->addKernel("ConservativeAdvection", name() + "_adv", kp);
  }
  else if (_current_task == "add_bc")
  {
    auto bp = _factory.getValidParams("DirichletBC");
    bp.set<NonlinearVariableName>("variable") = getParam<VariableName>("variable");
    bp.set<std::vector<BoundaryName>>("boundary") = {getParam<BoundaryName>("inlet")};
    bp.set<Real>("value") = 1.0;
    _problem->addBoundaryCondition("DirichletBC", name() + "_inlet", bp);
  }
}
```

In `MyApp.C::registerAll`: `registerSyntax("FooConvDiffAction", "FooConvDiff/*");`

## Common pitfalls

1. **Forgetting a `registerMooseAction` for every dispatched task.** If `act()` checks `_current_task == "add_bc"` but you only registered the action against `"add_kernel"`, that branch is dead code — the action is never instantiated for the BC task.
2. **Mutating params AFTER the create call.** `_problem->addKernel(_type, _name, _moose_object_pars)` copies/finalizes the object; subsequent `_moose_object_pars.set<X>(...)` has no effect on the live object.
3. **Using `getParam<X>("foo")` for a param you didn't declare in `validParams`.** Hard error at runtime; declare every param you read.
4. **PhysicsBase `addX()` virtuals are private.** They look "missing" because they default to no-op. Override the specific one you need; if you accidentally name yours `addKernels` (no FE/FV prefix), it silently won't be called.
5. **Overriding `act()` on PhysicsBase or ActionComponent.** Both declare `act()` as `final`. Use `actOnAdditionalTasks()` plus `registerMooseAction(..., "your_extra_task")` instead.
6. **ActionComponent mesh conflicts.** Two components that both create mesh on overlapping subdomain ids/boundary names will collide. Use unique block/boundary names per component or coordinate via `ComponentMeshTransformHelper`.
7. **`_pars.set<X>` modifies the action's own params, not the object you're creating.** Use `_factory.getValidParams(type)` (or `_moose_object_pars` in MooseObjectAction) for the object's params.
8. **Task ordering.** Adding objects in the wrong task (e.g., `add_kernel` requiring a variable that's added in a later task) will fail because the variable doesn't exist yet. Use `addTaskDependency` or pick the right task; consult `framework/src/base/MooseSyntax.C` for the canonical task order.

