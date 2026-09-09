# Verification analysis and threat boundary

This is a research assessment, not a claim of a new proof system. The implemented mechanism is seeded whole-run replay sampling plus conventional stateful admission and transactional campaign accounting. Molecular results, evidence of assigned computation, and consumption of a work credit are separate objects.

## What the current mechanism establishes

The server binds receptor/maps, ligand/conformer, engine relation, seed, search cap and unit index into an assignment. The client commits to every unit's score, pose and natural search trace before unpredictable sampling. Each selected complete unit is replayed from its specified input and seed. A different score, pose or trace fails the audit. Commitments prevent changing the submitted record after seeing the sample; they do not prove that an unselected record is correct.

For N assigned units, k correctly committed records, and q uniformly sampled distinct indices, conditional on the fixed commitment:

`P(pass | k) = C(k,q) / C(N,q) <= (k/N)^q`.

This bound is about correct records, **not measured CPU time**. Turning it into a work-cost statement requires that producing a correct record has substantial cost. It does not exclude alternative algorithms, faster hardware, preparation amortization, or previously computed outputs. With heterogeneous units, the cheapest k records may cost far less than k/N of total compute. Uniform run sampling must not be described as uniform cost sampling. Our current tier measurements and seeded replay regressions are evidence for particular implementations, not a computational lower bound.

For T allowed challenges against a fixed incomplete cache, a union bound gives at most `min(1,T*p)` chance of any pass; `1-(1-p)^T` additionally assumes independent fresh samples and an unchanged k/N. Adaptive changes of tier, seed coverage, q and cache contents generally invalidate the latter shortcut. The implemented policy experiment follows each actual state transition instead.

The low tier audits 4/16 units; the medium and high tiers audit 8/64 and 8/256. The asymmetry comes principally from increasing independently auditable unit count while retaining q, not from constant-time verification of a longer trajectory. Increasing the per-run cap also increases the server cost of replaying that run. Even at fixed q, parsing commitments, manifests and the present linear leaf list grows with N. Network ingress, finite queues and identity policies remain conventional outer controls.

## A. Core useful-work questions

| Attack | Current treatment | What remains unresolved |
|---|---|---|
| Omit entire runs | Post-commit random replay, actual partial-work clients, conditional hypergeometric bound | An accepted incomplete bundle can still contain malicious unsampled outputs |
| Return any cheap valid pose | Replay checks the assigned score, pose **and trace** | A score-only check would not enforce the search |
| Shorten seeded runs | Truncated natural traces fail complete replay; prior measured final-pose plateaus motivate trace binding | No general bound against computing the same trace by a different algorithm |
| Fabricate traces or hash summaries | A self-consistent commitment is cheap to fabricate; sampled replay authenticates selected records | Unsampled records remain provisional |
| Reuse same-seed prefixes at a higher cap | Scheduler rejects overlapping registered seed ranges even when cap/campaign/ligand display alias changes | Related-seed or state-reconstruction shortcuts need further adversarial work |
| Share a result cache | Previously credited canonical ranges cannot earn another credit | Pooling legitimately uncredited work is allowed; identity churn remains an outer issue |
| Reuse grids/scoring tables | Allowed and measured separately; cache experiment preserves the search relation | Attackers receive the same savings; redundant preparation cannot be counted as enforced useful work |
| Faster native/GPU/optimized solver | Treat as implementation/hardware advantage, not cheating by itself | GPU docking software is not automatically compatible with this exact seeded trace relation |
| Bias scientific output | Provisional storage; later replay/replication and top-k checks | Top-k validation repairs false winners, but cannot discover a concealed better unsampled pose by itself |

Registration is trusted. The current identity includes the engine version and input hashes; operators must not manufacture new scientific credit by relabeling equivalent engines, alternate file encodings or already explored conformers. The present single-database tests establish uniqueness within the registered canonical domain, not global chemical equivalence across independent services. Experimental optimized-engine benchmarks use separate databases and do not mint production credits.

## B. Outer abuse controls

`AdaptiveAdmission` maintains bounded risk scores, recent velocity, success/failure/abandonment history and range-level failures. It increases assigned work, limits outstanding leases, limits challenge attempts per range, and applies cooldown. It does not estimate whether a visitor is human. Trusted session continuity is a stated assumption. A fresh identity can evade identity-specific history; the shared issuance bucket limits aggregate issued challenges but does not stop upstream request floods or guarantee fairness against capacity exhaustion.

The local research harness invokes trusted verification and credit-finalization functions. It is not a public HTTP deployment. Logical high-rate request timing models precomputed or accelerated submissions; serial molecular execution wall time is not a production arrival/deadline experiment. Tests of SQLite transaction behavior do not establish distributed throughput or multi-region consistency. Risk logs and consumed campaign records also need retention/archival policies before sustained deployment.

## One-use historical work credit

The defensible interpretation is: a previously uncredited canonical assignment can consume at most one admission credit in the shared ledger after the prescribed probabilistic audit. Work may predate the request. Previously performed useful work does not become free merely because it is retrieved from cache, but marginal retrieval cost is low. A pool can spread historical computation across members; it cannot multiply ledger credits for the same completed range. This property depends on correct canonicalization and a shared atomic ledger.

A accepted bundle is **probabilistically audited**, not fully validated scientific truth. Completed accounting coverage can therefore include incorrect records after a lucky attack. Later repair is a separate scientific expense and must not issue a second access credit. To consume every output as trusted science would require broader validation, redundancy, or an explicit contamination model. If replication is performed by untrusted contributors, two matching colluders are not independent evidence; trusted replay or a defensible assignment/adversary model is necessary.

## Specialized verification candidates

| Candidate | Applicable relation | Assessment |
|---|---|---|
| Lossless binary trace encoding | Same float64 values and order | Reduces representation cost if measured bytes improve; no new soundness and no claim about reduced molecular replay |
| Public rolling checksum | Linear combination of client-supplied values | A compensating change to two entries preserves the checksum; the included counterexample demonstrates this |
| Post-commit random accumulator | Random projection of a fixed committed vector | Detects disagreement with an independently known vector, but obtaining the correct Vina vector still costs replay or a separate proof |
| RNG checkpoints | Prescribed random stream | Cheap skip-ahead can produce RNG evidence without molecular evaluations; public code removes any secrecy argument |
| Locally audited trajectory blocks | Transition from a supplied state | Without authenticating entry-state ancestry, one forged boundary can splice a shortcut into an otherwise valid suffix |
| Independent seeded blocks | Each start fully determined by the assignment | Defensible; becomes the existing independently auditable unit architecture |
| Freivalds-style batching | Genuine linear matrix relation over a defined field | Does not directly verify nonlinear grid-coordinate generation, BFGS, acceptance decisions or an entire Vina search |
| Sumcheck/GKR | Explicit arithmetic circuit and appropriate input relation | Potential research route, with floating-point rounding, branching, memory and nonlinear operations encoded or separately proven; no Vina performance result yet |
| Aggregation across runs | Binding many independently validated relations | Can reduce transport/proof overhead; aggregation cannot authenticate an unproven underlying relation |

The standalone fingerprint experiment checks fabricated records against archived expected records. That is an output-oracle comparison, **not a newly measured molecular replay**. Its local-splice probability is a conditional construction counterexample, not an implemented Vina splice exploit. If B boundaries have exactly one invalid transition and q are sampled uniformly without replacement, the splice is missed with probability `1-q/B`; merely adding more valid transitions can dilute detection. A useful new construction must show why skipping a substantial fraction of molecular cost corrupts many independently sampled checks rather than just one boundary.

## Prior art and novelty limits

Volunteer computing already uses spot-checking, replication and credibility/reputation to manage malicious workers. These components and their composition should be cited as prior art, not claimed as a new cryptographic primitive. [Sarmenta, sabotage tolerance](https://groups.csail.mit.edu/cag/bayanihan/papers/ccgrid01/ccgrid01.pdf); [Generalized Spot-Checking](https://www.jstage.jst.go.jp/article/transinf/E93.D/12/E93.D_12_3164/_article/-char/en).

Li and Mascagni discuss independent Monte Carlo subtasks, lightweight checkpointing, statistical result screening, and checks based on RNG/intermediate values. Section 4.2 also acknowledges limits and relies partly on the difficulty of reverse engineering the checking scheme. For an openly specified adversarial protocol, our assessment is that RNG consistency or encryption of client-provided state does not itself authenticate molecular calculations. This is our critique, not a theorem established by that paper. [Author PDF, sections 3–4](https://www.cs.fsu.edu/~mascagni/papers/RIJP2003_3.pdf).

Trustworthy Monte Carlo develops algebraic certification for structured Monte Carlo estimators, with examples including permanent estimation, DNF counting and logistic-regression gradients. It is a closer verification reference than generic blockchain docking claims. Its applicability depends on the estimator's algebraic structure; we have not derived an equivalent relation for Vina's adaptive optimizer. [NeurIPS 2022 paper](https://openreview.net/pdf?id=jglXPY6gH-1).

GKR-style protocols can be efficient on appropriately structured circuits, with prover cost depending on circuit size and regularity. That does not make an arbitrary floating-point optimizer cheaply verifiable. Rounding arithmetic requires explicit treatment as well. No constraint count, proof overhead or speedup is asserted here without an implemented Vina relation. [Thaler 2013](https://arxiv.org/abs/1304.3812); [Interactive Proofs for Rounding Arithmetic](https://doi.org/10.1109/ACCESS.2022.3223136).

Vina's pinned source already distinguishes atom-type and atom-pair tables. The experimental shared-table variant is an implementation optimization based on XS-type scoring, not a novel docking method or proof. Full table reuse must preserve scoring weights, scoring family, cutoff, smoothing parameters and invalid-type behavior. AD4 charge-dependent scoring is excluded. [Vina 1.2.7 source](https://github.com/ccsb-scripps/AutoDock-Vina/blob/v1.2.7/src/lib/precalculate.h).

Vina-GPU 2.1 changes and parallelizes search/optimization. Its existence is reason to measure hardware and algorithm advantages; it is not evidence that its outputs pass this experiment's exact trace relation. [Upstream software](https://github.com/DeltaGroupNJUPT/Vina-GPU-2.1).

A July 2026 SSRN preprint addresses economic security of sampled-audit useful work using a stake/dispute setting. Only its abstract was reviewed; it is neither relied upon as a verified theorem nor treated as peer-reviewed evidence. Anonymous admission here has no equivalent stake/slashing assumption. It should be followed up when making novelty claims. [Scale-Invariant Economic Security in Sampled-Audit Proof-of-Useful-Work](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7088821).

The strongest current paper framing is an empirical systems/security study of adaptive work credit, cost asymmetry, scientific quality and failure boundaries. A docking-specific lightweight verification novelty has **not** been demonstrated. Do not return to full Groth16 merely to avoid that conclusion; first establish a workload with useful scientific quality and honest end-to-end economics.
