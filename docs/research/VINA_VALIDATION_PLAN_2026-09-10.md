# Frozen architecture: validation and resource investigation

Core reference: commit 3b564dd2496bd21e743591e55efaa3daf1c154ae.
Keep the scheduler, one-use work credits, seed allocation, raw minima pools,
original merge/finalization, and post-commit whole-run auditing unchanged.
Experimental builds may change storage ownership, not molecular arithmetic.

## Scientific gates declared before new measurements

1. Reproduce the official Vina 1iep tutorial using its prepared inputs and
   published 20 Angstrom box. This is a method-reproduction positive control,
   not independent-conformer or virtual-screening validation.
2. Retain DUD-E FA10, HS90A and TRYB1, including all previous failures. Repeat
   stock redocking on the existing source inputs before comparing distributed
   aggregates on exactly those inputs. Report source-conformer and independent
   conformer results separately; never promote the former into an unbiased
   prospective docking claim.
3. Stock top-ranked symmetry-aware RMSD <=2 Angstrom is the redocking gate.
   Failing targets remain visible. Ranking requires separate active/decoy
   validation; a successful crystal control does not validate enrichment.
4. Compare medium-run aggregates with normal searches using measured evaluation
   counts and search wall time. Report both ratios; do not label unmatched
   budgets as matched. Preserve all raw pools and original finalization.

## Browser experiment

Separate allocated linear memory, allocator live bytes, process resident working
set, and peak process working set. Sample an isolated Chrome process tree and
instrument initialization phases. Test removal of temporary copies in a separate
build, checking raw pools and traces against the unchanged build. Smaller boxes
are a scientific parameter, not a transparent optimization. Desktop results do
not establish phone feasibility.

## Low-risk experiment

Explore reputation-gated provisional admission with random deferred full-run
replay as a policy outside the frozen verifier. Quantify unaudited cheating,
identity reset/collusion, detection delay and bounded exposure. Keep provisional
scientific outputs distinct from replay-validated outputs. Delayed punishment
cannot undo access already granted, and reputation is not a Sybil proof.
