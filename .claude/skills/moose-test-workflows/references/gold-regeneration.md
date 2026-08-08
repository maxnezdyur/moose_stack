# Gold regeneration end-to-end

Reached from the routing table in **moose-test-workflows** SKILL.md on a structural `DIFF` whose
new behavior you have confirmed correct, or on `FAIL` with reason `MISSING GOLD FILE`.

There is **no automation** (no `--copy-gold` / `--update-golds`). Manual `cp` workflow:

    # 1. Run the failing test, verbose, single slot
    cd <scope>           # moose/test, moose/modules/<m>/, blackbear, isopod
    ./run_tests --re=<test_name> -v --no-color -j 1

    # 2. Inspect the diff. Decide whether the new behavior is correct.
    #    (For exodiff, reproduce standalone to drill in — command in references/failure-diagnosis.md.)

    # 3. Copy fresh outputs into gold/
    cd test/tests/<area>/<feature>      # the spec dir
    mkdir -p gold
    cp <feature>_out.e gold/<feature>_out.e
    # For multiapp: copy every file listed in the spec's exodiff = '...'
    # For Outputs/file_base=foo parametrized tests: gold is gold/foo.e (no _out)

    # 4. Confirm
    cd <scope>
    ./run_tests --re=<test_name> -v --no-color -j 1

    # 5. Commit gold separately with explanation
    git add <path>/gold/
    git commit -m "Regenerate <area>/<feature> gold for <change>"

For `RunException`/`RunApp` (output-pattern) tests, there's NO gold. Edit `expect_err`/`expect_out`/`absent_out` in the spec instead.
