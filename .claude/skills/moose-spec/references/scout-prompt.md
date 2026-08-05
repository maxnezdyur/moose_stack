# moose-scout per-angle prompt template

Consumed by `/moose-spec` step 3. Fill the bracketed pieces and send each angle as its
own `Agent` call (`subagent_type: "moose-scout"`, `run_in_background: true`), all in one message.

The template has three jobs — every prompt must do all three:

1. Pin down the **operator / equation**, not just keywords. Without this a scout reports
   "diffusion kernel" as a match for Navier–Stokes momentum because the names overlap.
2. List **negative criteria** — what would NOT count — so the scout drops near-cousins instead
   of returning them.
3. Force **per-hit verification**: open each candidate, read the residual line, rate the match.
   Grep hits don't count.

```
Agent({
  subagent_type: "moose-scout",
  run_in_background: true,
  prompt: "Search angle: <one-line angle name, e.g. 'Kernel implementations of anisotropic conduction'>

           ## What the user wants (shared across all angles)

           **Plain-English target:** <one paragraph from the grill — what the feature does>

           **Operator / equation:** <full math, e.g. '∇·(K∇T) with rank-2 K' or
             '∂u/∂t + (u·∇)u = -∇p/ρ + ν∇²u (incompressible momentum)'>

           **Distinguishing properties:** <what makes this *different* from name-cousins —
             e.g. 'K is a rank-2 tensor, not a scalar'; 'momentum equation, not continuity';
             'requires ADReal templating'; 'integrates over a subdomain, not the full mesh'>

           ## What this angle covers

           **Scope:** <one of ~/projects/moose_stack/moose, /blackbear, /isopod, or the worktree>

           **Specifically search for:**
           - <angle-specific class names / synonyms>
           - <angle-specific Tester `type = X` references, if applicable>
           - <angle-specific base class hierarchy>

           Do NOT search outside this angle — a sibling moose-scout is covering <other angle>.

           ## What is NOT a match (negative criteria)

           - <e.g. 'Plain Diffusion / FunctionDiffusion: scalar coefficient, not tensor'>
           - <e.g. 'INSMass: continuity only, not momentum'>
           - <e.g. 'Non-AD-only kernels: we need ADReal templating'>
           - Any class that matches by name keywords but computes a different operator.

           ## Required verification per hit

           For each candidate, you MUST:
           1. Open the file and read the residual / contribution code
              (`computeQpResidual`, `computeValue`, `execute`, etc.).
           2. Quote the actual residual line(s) in your report.
           3. Rate the match:
              - **structural** — same base class AND same operator/equation as 'Operator /
                equation' above
              - **behavioral** — different base class but same operator/equation
              - **naming** — matches keywords but computes a different operator → DROP,
                do not return as a hit
           A grep hit is not a match. A hit you haven't opened and read is not a hit.

           ## Output

           For each match, return:
           - `<file_path>:<line>` of the residual / contribution code
           - The quoted residual line(s)
           - Match strength: **structural** or **behavioral**
           - One sentence on how it relates to the operator/equation above

           If nothing in this angle survives verification, say so explicitly — a clean
           'no match in this angle' is more useful than a list of naming false positives."
})
```
