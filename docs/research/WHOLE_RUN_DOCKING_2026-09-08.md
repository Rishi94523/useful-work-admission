# Independently auditable bounded Vina runs

Investigation in progress, 8 September 2026. This checkpoint records the implementation; the completed decision and measurements will replace this status after the browser, replay and attack sweeps finish.

The scientific unit is an independently seeded Vina 1.2.7 Monte Carlo/BFGS search with flexible ligand torsions, fixed PDBQT/maps, one thread, an explicit evaluation budget and a result. Maps use the same no-refine Vina grid objective as the earlier controls. Unlike the old rigid bank, orientations, translations and torsions are optimized.

The WASM engine is built locally with pinned Emscripten 4.0.15 and shared by browser clients and Node replay. Native builds are controls, not interchangeable replay backends: the initial cross-platform smoke outputs differed. Four pre-trace browser/Node WASM outputs matched exactly; the full trace-bound replay sweep remains pending.

Vina checks `max_evals` between Monte Carlo iterations. An iteration can invoke up to two local optimizations, each bounded by the implementation's BFGS steps and ten line-search trials. Actual evaluation counts are recorded. A budget is neither an exact evaluation count nor a hardware-independent time promise.

Final-output-only checking has a shortcut: some higher-budget runs return exactly the same best pose/score as a lower-budget run. The protocol therefore also commits the natural sequence of optimized candidate energies and their evaluation counts. A challenged unit is replayed in full and its output plus trace compared exactly. This is a complete-unit replay check, not sampling individual transitions or proving every operation with a SNARK.

The existing transactional scheduler remains in use. The whole-run adapter binds inputs, engine, region, budget, seed derivation and range. It rejects overlap even across budget changes, preventing deliberate reuse of the same seed's shorter search prefix as a new independently priced assignment. Completed units are not reissued. Expired uncompleted leases remain reassignable.

The intended economic property is conditional **one-use coverage credit for previously uncompleted scientific units**. Precomputation may produce legitimate new-to-the-campaign output; it does not prove fresh post-issuance CPU effort. Shared caches, faster algorithms, abandonment and fixed-output plateaus must be analyzed separately. Scientific outputs are provisional until the chosen scientific validation policy runs; access acceptance is not a global-optimum certificate.

Primary scientific references: [Vina methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC10683950/), [official reproducibility/search FAQ](https://autodock-vina.readthedocs.io/en/latest/faq.html), [pinned upstream source](https://github.com/ccsb-scripps/AutoDock-Vina/tree/3c65c0b3e6c2c1d183f6a175ecb65e3c5ba91645). The earlier [lightweight report](LIGHTWEIGHT_DOCKING_FINDINGS_2026-09-08.md) contains closely related volunteer-computing prior art; this iteration makes no novelty claim yet.
