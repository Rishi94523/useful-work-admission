# Completed preselected ranking campaign

The campaign completed all 288 official stock-Vina jobs without preparation or
docking failures. Only ESR1 passed the predeclared strong baseline. On ESR1,
distributed 256k units preserved average ranking within the declared five-point
AUC margin at similar compute. **This is one qualifying target, not a completed
multi-target validation.** The architecture is unchanged.

| Target | Stock E8 AUC | Bootstrap 95% interval | EF10% | Declared gate |
|---|---:|---:|---:|---|
| FA10 | 0.628 | 0.507–0.745 | 1.5 | Fail |
| TRYB1 | 0.636 | 0.514–0.752 | 2.7 | Fail |
| ESR1 | 0.826 | 0.733–0.906 | 2.7 | Pass |

Each target has 32 actives and 64 decoys, selected before scores using the frozen
manifest. The gate required AUC>=.75, lower95%>.60 and EF10%>=1.5, with complete
inputs/results. Failed targets remain in the evidence; they were not silently
replaced or promoted into the primary comparison. These are bounded DUD-E
subsets, not full-library or prospective screening experiments.

## ESR1 matched comparison

Each row covers the same 96 molecules. Normal E8 and independent 256k units use
the same instrumented native build and the original Vina finalizer. The stock
gate above uses the official binary, so its exact scores differ from this
same-build reference.

| Parent seed | Normal AUC | Medium AUC | Medium / normal evaluations | Medium / normal search time |
|---|---:|---:|---:|---:|
| 104729 | 0.8354 | 0.8066 | 1.0147 | 1.0098 |
| 130363 | 0.8145 | 0.8149 | 1.0141 | 1.0160 |
| 155921 | 0.8120 | 0.8076 | 1.0130 | 1.0126 |

All six EF10% values are 2.7. The mean seed-specific AUC difference is **-0.0109**,
with paired compound-bootstrap95% interval **[-0.0288, +0.0049]**. Its lower bound
exceeds the frozen -0.05 margin, establishing the planned average-seed
noninferiority result for this panel. It does not establish zero loss.

The first seed's difference interval is [-0.0610,-0.0039], so noninferiority is
not established for every individual seed. Resampling keeps the three results
for each compound together; seeds are not counted as extra independent compounds.
Intervals condition on only three seeds, and target selection on the same
stock-scored cohort limits generalization. Concurrent timings support similar
compute in this experiment, not an isolated throughput claim.

## Original TRYB1 diagnostic

The old four-active/four-decoy inputs were preserved to separate seed variation
from the new supplied-conformer preparation pipeline.

| Parent seed | Normal AUC | Medium AUC | Difference |
|---|---:|---:|---:|
| 104729 | 0.6250 | 0.4375 | -0.1875 |
| 130363 | 0.3750 | 0.3750 | 0 |
| 155921 | 0.5625 | 0.3750 | -0.1875 |

The mean difference is -0.125, with a wide paired interval [-0.375,+0.0833]. The
drop recurs in two seeds; calling it one unlucky random seed is unsupported.
However, the underlying normal ranking is weak and the panel tiny. Neither a
general decomposition failure nor a target-specific causal explanation is
established. The new larger TRYB1 stock failure reinforces the need to validate
the reference workload before attributing differences to distribution.

## Consequences for the next experiments

Preserve the current decomposition, scheduler, finalizer and whole-run audit.
ESR1 is positive evidence for medium-run screening; FA10/TRYB1 are failures of
this strong reference gate. We still need at least another independently
preselected, stock-qualified target before claiming multi-target preservation.
Any expanded target cohort or changed preparation must be declared as a new
experiment, retain these failures, and avoid tuning on the same ranking labels.

The 256k physical-phone test is the current priority. Its new page measures
fresh-worker startup, then two batches within the same worker; desktop control
has passed 6/6 exact raw-output comparisons. The subsequently received iPhone result also passed6/6 matches, with
5.149s initialization and1.009�1.035s calls; see the startup/background report. No further 64k device test was performed.

Low-risk admission remains governed by the completed policy analysis: sparse
auditing is conditional on trusted eligibility and bounded exposure, while risky
bundles use mandatory random replay. A one-run fresh identity is not secured by
5% sampling alone. Trusted-tier integration, audit backpressure and late output
quarantine remain distinct from scientific ranking and device-speed evidence.

Reproduce with `python scripts/analyze_vina_followup.py`. Completed raw rows are
preserved as lossless `.jsonl.gz` archives with hashes in
`docs/evaluation/vina_followup_2026-09-12/ranking_archive_manifest.json`.
