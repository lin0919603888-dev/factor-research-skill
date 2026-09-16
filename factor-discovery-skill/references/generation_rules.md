# Factor Generation Rules

## Evolution strategies

### Initial

- Use only when the current research requirement cannot be represented by an
  existing parent mechanism.
- Record the research goal and the reason for introducing a new signal.
- Do not produce many unrelated initial factors from one experiment.

### Mutation

- Select one parent that is directly relevant to the research direction.
- Apply one recorded deterministic operation.
- Require a research reason, not merely a random formula change.

### Crossover

- Select two parents whose mechanisms are complementary or test the same
  hypothesis from different states.
- Normalize signals when their scales differ.
- Record both parents and the combination weights.

### Refinement

- Preserve the parent mechanism.
- Change robustness or stability only, such as rolling normalization or
  smoothing.
- Record why the refinement is expected to improve or clarify the parent.

## Required provenance

Every candidate YAML must record:

- `metadata.source`
- `metadata.generation`
- `metadata.lineage.parents`
- operation and reason when applicable
- evaluation results after the program has produced them

## Prohibited behavior

- Unrecorded random formula changes.
- Saving unevaluated candidates as accepted factors.
- Overwriting an existing library YAML.
- Assuming fields outside the supplied minute-bar format.
- Creating a large batch of unsourced factors to search for a lucky result.

