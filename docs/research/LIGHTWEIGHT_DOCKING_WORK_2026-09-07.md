# Lightweight enforcement of useful docking work

Investigation in progress, 2026-09-07. Measurements and conclusions are added as checks complete.

> Can we make attacker cost scale with the amount of assigned USEFUL docking work while keeping server verification much cheaper and keeping cryptographic/non-useful client overhead a minority of total work?

## Checkpoint 1: disjoint campaign scheduler

Implemented `research/docking_campaign.py`: transactional SQLite leases for bundles of 1–16 distinct ligands, disjoint scientific ranges, expiry/reassignment, a single post-commit challenge, and atomic completion/credit. Scientific identity includes model, receptor, ligand, conformer bank, region and search parameters. Renaming the campaign does not create new scientific work.

Eight scheduler tests pass, including concurrent allocation and a 16-way completion race. Completed ranges are never deliberately reissued; expired uncompleted ranges can be reassigned. This is a local research scheduler, not authenticated HTTP admission or a distributed production service. The trusted verifier must call completion; a client must never supply the acceptance decision.

No unconditional fresh-work guarantee follows: a reassigned unit may already have been computed, and colluding clients can share inputs, partial scores and results. Receptor maps and conformer preparation are reusable preprocessing and cannot be counted anew per request.

## Planned measured comparison

Compare Vina plus score-only checks, discrete pose-bank scalar audits, richer per-atom block audits, selected block-winner checks, the previously measured Groth16 controls, and bundles of 1/4/16 heterogeneous ligands. Test actual partial computation, score guesses, incorrect-record coverage, replay, deadline and cache shortcuts. Separate useful scoring, record storage, hashing, serialization, checking and data transfer.

The molecular pilot uses 16 actives and 16 presumed decoys from DUD-E FA10 selected before docking outcomes. Fixed-conformer grid screening has an established scientific use case for conformationally expanded libraries, but our specific finite bank still needs quality validation against Vina. [DOCK tutorial](https://dock.compbio.ucsf.edu/DOCK_6/tutorials/ligand_sampling_dock/ligand_sampling_dock.html), [DUD-E FA10](https://dude.docking.org/targets/fa10).

Random checks establish a bound in terms of **incorrect committed records**. Turning that into a bound on skipped computation requires evidence about guessing, exact caches and faster algorithms. The report will keep scientific result validity separate from enforcement of requested work. Spot-checking volunteer results is established prior art; the proposed contribution cannot be simply adding Merkle commitments. [Sarmenta, 2002](https://www.sciencedirect.com/science/article/abs/pii/S0167739X01000772).
