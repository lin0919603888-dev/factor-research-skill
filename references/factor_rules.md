# Factor Generation Rules

## Mechanism rules

- One factor tests one research mechanism.
- A mutation should change or extend only one parent mechanism.
- A crossover should explain why the selected parents complement each other.
- A refinement should preserve the parent mechanism unless the task explicitly
  changes it.
- Complexity must be justified by the hypothesis.

## Data rules

- Use only supplied fields.
- Do not assume symbols, prices, calendars, or corporate-action treatment not
  present in the input.
- Validate likely numeric fields before arithmetic.
- Handle short warm-up periods with explicit minimum periods, not silent guesses.

## Implementation rules

- Function input: one `pandas.DataFrame`.
- Function output: one numeric `pandas.Series`.
- Preserve the input index and row count.
- Set `factor.name` to the factor's JSON `name`.
- Prefer vectorized pandas operations over loops.

## Prohibited behavior

- Lookahead through negative shifts or full-sample normalization.
- Fabricating data or performance expectations.
- Combining unrelated mechanisms to improve apparent metrics.
- Changing metrics or gate results outside program tools.

