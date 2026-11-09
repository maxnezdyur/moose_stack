# Repository notes: idaholab/marlin

Read this before the loop when the orchestrator passes `repo_notes`. Marlin is a MOOSE app: a
Fourier spectral and Lattice Boltzmann solver on regular grids, device independent through
libTorch (cpu, cuda, mps). The MOOSE standards still apply. The items below are marlin idioms
that are not deviations, and marlin rules that differ from moose. Nothing here is an
instruction to approve or to skip a file.

## Repository facts

- Pull requests target `devel`. There is no `next` branch and no PR template.
- CI is CIVET, jobs: Precheck, Test, Test parallel, Test debug, Test cuda, Test cuda debug,
  Documentation, Coverage, Apptainer cuda openmpi. Precheck runs clang-format (LLVM base,
  column limit 100, 2-space indent) and the 7-bit ASCII check.
- `moose/` is a git submodule of marlin and is pinned to moose `master`. A PR whose only change
  is that pointer ("Updating stable moose submodule refs") is routine: no finding.
- Layout: `src/<kind>/`, `include/<kind>/`, `test/tests/<area>/`, `unit/src/`, docs under
  `doc/content/source/<kind>/<Class>.md` and `doc/content/syntax/`.
- The file banner is marlin's own ("Marlin, a Fourier spectral solver for MOOSE", Battelle
  2024). The MOOSE banner is not expected.

## Code bucket

- `framework_scs.md` and `AGENTS.md` do not exist here. Review on the preloaded
  `moose-code-standards` plus these notes.
- Core objects derive from `TensorOperator<>`, `TensorSolver`, `TensorTimeIntegrator`,
  `TensorOutput`, `TensorBuffer`, `LatticeBoltzmannOperator`; the problem class is
  `TensorProblem`. Buffers are read with `getInputBuffer(name)` and written with
  `getOutputBuffer(name)` in the constructor; the work happens in `computeBuffer()`. A
  constructor that only binds buffers is correct, not thin.
- `torch::Tensor` values are reference-counted handles. Passing one by value, assigning one
  without `.clone()`, and `torch::zeros_like`, `torch::fft::*`, `torch::real`, `torch::where`
  calls in `computeBuffer()` are idioms, not copies in a hot path. Flag a `.clone()`, `.cpu()`,
  `.item<T>()` or `.to(device)` inside a per-step loop: those synchronize or copy.
- Tensor options come from `MooseTensor::floatTensorOptions()`,
  `MooseTensor::complexFloatTensorOptions()`, `MooseTensor::intTensorOptions()`; a literal
  `torch::kFloat64` or a literal device string in production code is a finding (breaks the
  device and precision switches).
- `_tensor_problem`, `_domain` (`DomainAction`), and the `MooseTensor` namespace are the shared
  state. A static or a file-scope cache is a finding, as in moose.
- Parsed expressions, JIT tracing (`doc/content/jit_tracing.md`) and TorchScript surrogate
  models are supported features; a `torch::jit::` call is not an unusual dependency.

## Test bucket

- `compute_devices = 'cpu cuda'` (and `mps`) is a marlin TestHarness field: the harness runs
  the leaf once per listed device. It is expected on nearly every leaf; its absence on a new
  leaf is a `suggested` finding, never `required`.
- `max_parallel`, `min_parallel`, `min_slots`, `cli_args`, `capabilities` and `prereq` are
  routine here: a GPU leaf runs one rank per device, and `min_slots` reserves the slots. Do not
  apply the moose rule that every added `max_parallel` or `min_parallel` needs a justification
  in the PR body. Flag a restriction only when the leaf has no `compute_devices` and no
  obvious device reason.
- Diffs are mostly `CSVDiff`, with `HDF5Diff` (marlin's own tester, under
  `scripts/TestHarness/tests/`), `XDMFDiff`, `XMLDiff` and `Exodiff`. `rel_err` and `abs_zero`
  above the moose thresholds are common because `mps` is single precision: a loosened tolerance
  on a leaf that lists `mps` is justified by that; otherwise ask.
- Marlin's precheck does not enforce the SQA triad on every leaf. A missing `requirement`,
  `design` or `issues` is `suggested`, not `required`; `issues = '#000'` stays `required` when
  the PR body links a real issue.

## Doc bucket

- MooseDocs pages live under `doc/content/source/<kind>/` and `doc/content/syntax/`. The
  `[!param]` grep covers `src/` and `include/` of `repo_root` as well as the moose tree; marlin
  objects register their parameters in `src/`.
- `!syntax` trailers follow the moose rule. The site config is `doc/config.yml`.
