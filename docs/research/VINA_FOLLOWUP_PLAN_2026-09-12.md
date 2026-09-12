# Frozen follow-up protocol, before new ranking outcomes

Reference architecture: d25cca4. No changes to Vina search, the scientific
scheduler, original finalizer, or whole-run audit.

## Ranking

Candidates fixed now: DUD-E FA10, TRYB1 and ESR1. FA10 anchors the positive pilot;
TRYB1 is the adverse pilot; ESR1 adds a different receptor family. Retain failures.
Select 32 actives and 64 decoys per target using deterministic SHA256 ordering
of canonical isomeric SMILES with a fixed salt. Exclude molecules in previous
panels. Use the first 2000 valid, unique eligible entries per source library;
eligibility: one connected component, 12–55 heavy atoms, supported elements,
finite supplied3D coordinates. This is a bounded subset, not the full DUD-E set.
Save selection before docking. Preparation failures are retained, not replaced.

Use supplied DUD-E ligand conformations and protonation, Meeko PDBQT preparation,
the existing receptor preparation recipe and a crystal-centered30A box. This
removes the earlier ETKDG/MMFF conformer-generation step; all compared methods use
exactly the same new prepared inputs. Consequently this is a new campaign, not
a clean causal test of that old preparation pipeline.

Stock gate: official Vina E8, seed104729, one CPU, nine modes. Require complete
96-compound results, AUC>=0.75, stratified-bootstrap95% lower AUC>0.60, and
EF10%>=1.5. Do not retune failed targets or silently replace them.

For gate-passing targets, compare normal E8 against independent256k runs matched
to its actual evaluation count, using parent seeds104729,130363,155921. Keep raw
minima and original finalization. Report per-target, per-seed AUC, EF10%, paired
compound-bootstrap differences and evaluation ratios. AUC noninferiority margin:
-0.05; a lower95% bound must exceed it before claiming preservation. With this
sample size an inconclusive result is possible and must remain inconclusive.

Repeat the original fixed TRYB1 4+4 comparison over those three seeds as a
separate diagnostic, retaining the old prepared inputs. Do not promote a failed
stock-gate campaign into the primary validation analysis.

## Admission

Compare deferred random audit; unpredictable immediate mandatory audit on a
fraction of visits; deterministic periodic audit with an adaptive attacker;
delayed provisional access with no protected action before a selected verdict;
and N=2/4 bundles with q=1/2. Model fresh identities, persistent identities,
audited-correct farming followed by cheating, and selective abandonment. Report
work per successful admission, success rate, verifier work, and exposure before
detection. Parameterize identity acquisition cost; never assume it is positive.

## Devices

Explicit-start six-run64k browser page. Same optimized WASM and Node reference.
Measure asset/module/init time, warm runs, main-thread frame gaps, visibility
changes, allocated heap, errors and exact raw-pool/trace equality. Save claimed
device/OS and user agent. Test this host plus the user's physical iPhone15 when
available. Headless desktop controls are not additional physical devices; Safari
heap allocation is not peak resident memory. No simulated phone claims.
