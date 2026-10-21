# Local review -- moosify-uel

## Code
- (no code files in this branch)

## Tests
- modules/combined/examples/thermomechanics/moosify_uel.i:1-11 -- [required] Remove this header block. Input files carry no header comments; the face mapping and the placeholder-UMAT note belong in the `detail` or `requirement` of the spec (`modules/combined/examples/thermomechanics/tests`).
  ```suggestion
  ```
- modules/combined/examples/thermomechanics/moosify_uel.i:128-129 -- [required] Remove these two physics comments. The source formula and shut-off time are rationale, which goes in the spec or the class docs, not in the input.
  ```suggestion
  ```
- modules/combined/examples/thermomechanics/tests:28 -- [required] `abs_zero = 1e-12` tightens the FileTester default of 1e-10, but nothing in the spec explains why. Add a comment next to this parameter that states the reason for the tighter tolerance, or drop the override if the default passes.

## Docs
- (no doc files in this branch)

## AD
- (lens not triggered)

## Reuse
- (lens not triggered)

## Completeness
- (lens not triggered)

