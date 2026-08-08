# CIVET-only failures and interactive debugging

Reached from the routing table in **moose-test-workflows** SKILL.md when a test is green locally
and red on CIVET, when you need the archived CI forensics, or when you need a debugger.
CIVET basics (server-side recipes, `group = 'hpc'`): **moose-run-tests**.

## CIVET-only failures (passes locally, fails CI)

| Likely cause | Reproduce locally |
|---|---|
| Heavy split | `./run_tests --heavy --re=<name>` |
| Distributed mesh | `./run_tests --distributed-mesh --re=<name>` |
| Parallel scaling | `./run_tests --re=<name> -p 2` (or higher) |
| Machine arch (`machine=x86_64` vs `arm64`) | Can't fully — but check `capabilities` line in spec |
| Heavy valgrind | `./run_tests --valgrind-heavy --re=<name>` |
| Conda env drift (PETSc/MFEM/libtorch versions) | `./<app>-opt --show-capabilities` to compare |
| HPC pipeline (`group = 'hpc'`) | `./run_tests -g hpc --re=<name>` |

The forensic artifact CIVET archives is `.previous_test_results.json` — pull it down to inspect `testharness.args` (the exact CI invocation), `environment`/`apptainer` (the host and container that produced the run — settles the env-drift and arch rows above), and per-test command, exit code, caveats, output paths, timings, `max_memory`, PerfGraph JSON.

## Interactive debugging (gdb/lldb)

Not officially documented. Convention:

    ./run_tests --re=<test_name> --dry-run        # get the exact command the harness would run

    cd <spec_dir>
    gdb --args <path/to/app>-dbg -i <input.i> <other args>
    lldb -- <path/to/app>-dbg -i <input.i> <other args>    # macOS

For MPI failures: launch with `mpiexec`, attach with `gdb -p <pid>`. `METHOD=dbg` (or `--dbg`) gets you full symbols and live `mooseAssert`.
