---
name: moose-code-standards
description: MOOSE coding standards (C++ and Python). Auto-loads when writing or editing C++/Python source in moose, blackbear, or isopod. Preloaded into the moose-implementer, moose-code-reviewer, and moose-unit-test-writer agents.
user-invocable: true
---

# MOOSE Code Standards

One canonical source, maintained upstream and shared by all three repos — read it directly rather than working from remembered standards:

**`moose/framework/doc/content/sqa/framework_scs.md`** (relative to the meta-repo root)

If the file is missing (submodule not checked out), report that and stop — do not substitute remembered standards.

## ASCII only

Every byte you write — C++, Python, `tests` specs, `.i` inputs — must be 7-bit ASCII. CIVET rejects non-ASCII, and it sneaks in invisibly via AI prose and paste: smart quotes, em/en dashes, NBSP, unicode math (`×`, `°`, Greek letters). Use `'`/`"`, `--`, plain spaces, and spelled-out or LaTeX-in-comments math instead. Scan before reporting done: `grep -nP '[^\x00-\x7F]' <file>` must return nothing.
