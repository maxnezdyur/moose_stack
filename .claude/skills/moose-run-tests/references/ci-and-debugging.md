# CIVET, harness reference, and interactive debugging

Reached from the routing table in `moose-run-tests/SKILL.md` when a test is green locally and
red on CIVET, when the archived CI forensics are needed, when a capability expression, testroot
key, or environment variable needs looking up, or when a debugger is needed.

## CIVET

INL's CI runs at `civet.inl.gov`. There is no in-tree `.civet.yml` or `run_cmd.sh`; the recipes
live on the CIVET server and invoke `./run_tests` with extra arguments (commonly `--hpc=pbs`,
`--max-fails 999999`, `MOOSE_TERM_FORMAT=tpnsc`). Tests opt in to the limited HPC pipeline with
`group = 'hpc'`. CIVET covers the OS, compiler, PETSc, parallel, heavy, and distributed-mesh
permutations a local run does not.

CIVET to MooseDocs integration: `moose/python/MooseDocs/extensions/civet.py`,
`moose/python/mooseutils/civet_results.py`, `moose/python/TestHarness/resultsstore/civetstore.py`.

## CIVET-only failures (passes locally, fails CI)

| Likely cause | Reproduce locally |
|---|---|
| Heavy split | `./run_tests --heavy --re=<name>` |
| Distributed mesh | `./run_tests --distributed-mesh --re=<name>` |
| Parallel scaling | `./run_tests --re=<name> -p 2` (or higher) |
| Machine arch (`machine=x86_64` vs `arm64`) | Not reproducible; check the spec's `capabilities` line |
| Heavy valgrind | `./run_tests --valgrind-heavy --re=<name>` |
| Conda env drift (PETSc, MFEM, libtorch versions) | `./<app>-opt --show-capabilities` and compare |
| HPC pipeline (`group = 'hpc'`) | `./run_tests -g hpc --re=<name>` |

CIVET archives `.previous_test_results.json`. It holds `testharness.args` (the exact CI
invocation), `environment` and `apptainer` (the host and container that produced the run, which
settles the env-drift and arch rows), and per-test command, exit code, caveats, output paths,
timings, `max_memory`, and PerfGraph JSON.

## Capability expressions

Specs gate with `capabilities = '<expression>'`. Operators: `& | !` and the comparisons
`>= < = !=`.

    capabilities = 'petsc>=3.18 & vtk & !installation_type=relocated'
    capabilities = 'method=opt'
    capabilities = 'mfem & platform=linux'

`./<app>-opt --show-capabilities` prints the build's set. The harness adds `hpc`, `machine`,
`platform`, and the `known_capabilities` from `testroot`. Overrides: `--ignore-capability NAME`
(NAME counts as satisfied), `--only-tests-that-require NAME` (only specs whose expression uses
NAME), `--minimal-capabilities` (skip the query entirely).

## testroot keys

`app_name`, `run_tests_args`, `extra_pythonpath`, `known_capabilities`, `allow_warnings`,
`allow_unused`, `allow_override`.

## Environment variables

| Variable | Effect |
|---|---|
| `MOOSE_DIR` | Roots the harness; derived when unset |
| `METHOD` | Default binary suffix |
| `MOOSE_TEST_MAX_TIME` | Overrides the 300 s per-test default |
| `MOOSE_TERM_FORMAT` | Output field codes (default `njcstm`: `n`/`N` name, `j` dots, `c` caveats, `s` status, `p` padded pre-status, `t` time, `m` memory) |
| `MOOSE_TERM_COLS` | Terminal width |
| `MOOSE_MAX_MEMORY_PER_SLOT` | MB cap per slot |
| `MOOSE_MPI_COMMAND` | Replaces `mpiexec` |
| `OMP_NUM_THREADS` | Set per job by `--n-threads` |

There is no `MOOSE_INSTALLATION_TYPE`; `installation_type` is a capability name only.

## Interactive debugging (gdb, lldb)

    ./run_tests --re=<name> --dry-run          # the exact command the harness would run

    cd <spec_dir>
    gdb --args <path/to/app>-dbg -i <input.i> <other args>
    lldb -- <path/to/app>-dbg -i <input.i> <other args>    # macOS

For MPI failures, launch with `mpiexec` and attach with `gdb -p <pid>`. `--dbg` (or `METHOD=dbg`)
gives full symbols and a live `mooseAssert`.
