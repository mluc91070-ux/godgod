# experiments/

Reproduction scripts and notebooks for individual experiments live here, one
directory per experiment id, alongside the row stored in the `experiments` table.

Empty in PHASE 1: the experiment engine is PHASE 5, and no experiment has been
run against real data yet. The demo experiment in `data/fixtures/research.json`
is fixture data and is labelled as such.

Each directory should contain enough to re-run the analysis from the recorded
`dataset_version` and `dataset_hash`:

```
experiments/000421-attention-vs-survival/
  README.md      question, method, result, limitations
  run.py         the analysis, deterministic given the dataset
  dataset.json   or a pointer to the export it was built from
```
