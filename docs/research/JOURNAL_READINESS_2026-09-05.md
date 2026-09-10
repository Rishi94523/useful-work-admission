# Journal readiness and research direction — 5 September 2026

**Central research question**

> Can anonymous browsers contribute useful inference work that is verified cheaply, within a bounded access delay, even when some contributors submit malicious results or disappear?

This question guides the protocol and evaluation. Qwen and human-feedback retraining are optional extensions under the current scope.

## Latest update: distributing stock-shaped Vina tasks across users, 10 September

The [completed task-decomposition investigation](VINA_TASK_DECOMPOSITION_2026-09-10.md) establishes that a browser need not complete an entire ligand docking job. All 32 separately executed native tasks in the FA10 E32 control, including raw minima and traces, reproduced the same-build monolithic final result exactly. Preserve the normal retained-minima behavior and original merge/refinement; combining independently normalized best scores is not equivalent.

The 312 aggregate configurations support this scientific decomposition, but do not establish a validated short-visit admission system. On the FA10 source crystal, 143 medium runs reached 0.455 Å versus normal E32 at 0.466 Å with derivative-evaluation budgets within 0.31%. Independent-conformer score-selected RMSDs after 32 normal runs were 8.770/0.471/15.184 Å across FA10/HS90A/TRYB1. Ranking remains weak on some targets. These are small reused panels, not independent population-level validation.

Real Chrome 64k tasks took 0.758–1.011 s warm, versus 12.918–17.440 s for normal FA10 tasks. Molecular search occupied 98.6–99.5% of warm task-call time, but cold map initialization took 4.842 s and allocated WASM heap was about 550 MiB. A one-run audit provided no substantial cost advantage; pooling scientific coverage across users does not confer a per-user multi-run audit guarantee. See [measured tables](VINA_TASK_MEASUREMENTS_2026-09-10.md) and the [security/work-credit model](VINA_TASK_SECURITY_MODEL_2026-09-10.md).

Durable output ingestion, ordered aggregation, later verification and atomic multi-ligand leases are implemented. Thirty-two simulated single-run visitors with real bounded molecular outputs merged exactly; they were not 32 humans or a production deployment. Completed units cannot earn duplicate credit within the trusted identity domain. Keep this decomposition as the scientific reference; validate a scientifically useful independent-input campaign and then measure optimized cold/browser/admission economics. Distributed docking and spot-checking alone are established ideas, so a distinct security contribution and external replication remain necessary. Human feedback and Cloudflare remain deferred; both original research questions are preserved.

## Previous update: adaptive admission and multi-target docking, 9 September

The [adaptive investigation](ADAPTIVE_DOCKING_FINDINGS_2026-09-08.md) implements the missing conventional outer controller: server-side risk, work tiers, abandonment penalties, retry/range limits, issuance budgets and cooldown. Real Chrome/Node/SQLite trials show honest visitors remaining low, valid spam escalating and then cooling down, and partial-work/retry failures increasing cost or terminating admission. It does not solve generic bot detection or Sybil resistance.

Shared XS scoring tables repair much of the preparation overhead: optimized warm low-tier client median0.355 s; medium6.400 s; high20.984 s, with97–99% molecular-kernel time. Full local high-tier client/server ratio is16.39× atq8, but medium narrowly misses the20% server-cost gate and cold Chrome initialization is10.245 s. These are historical16-ligand FA10 browser measurements, not demonstrated latency across the new scientific panel or devices.

Stronger whole-run sampling is implemented and measured. For230 correct records among256, q27 reduces theoretical pass probability to4.694%, versus41.920% atq8. Median replay plus local IPC rises from1.278 s to4.095 s. The stronger sweep's browser runs were roughly twice as slow as the earlier tier measurements; cross-experiment ratios are explicitly sensitivity calculations. No nearly constant verifier cost or generic attacker computational lower bound is established.

Scientific quality remains the blocking result. The original and post-hoc MMFF-converged cohorts cover **4,173 unique bounded/refinement records**, three prepared targets, independently generated conformers and matched stock comparisons. The corrected4×64k setting reaches≤2 Å onFA10/HS90A, but its AUC is≥0.65 only onFA10. Other corrected settings fail the2/3 independent-redocking gate. No tested configuration satisfies both declared scientific gates. Strong stock failures on some identical independent inputs indicate a preparation/scoring/search problem broader than the audit protocol; they do not turn the bounded workload into validated science.

Keep whole-run sampling as a useful experimental baseline. **Do not submit the present system as a demonstrated journal-ready useful-work CAPTCHA, or return to full Groth16 simply because the science gates fail.** The next defensible milestone is a target-specific, independently validated scientific campaign followed by the complete browser/admission benchmark on exactly those inputs. A paper also needs a substantive contribution beyond prior volunteer-computing spot-checking/reputation, stronger cheap-correct-output and heterogeneous-cost adversarial analysis, durable scientific ingestion and repair, real devices/network/deadline/concurrency evidence, and an independent replication. The [verification analysis](DOCKING_VERIFICATION_ANALYSIS_2026-09-08.md) separates correct records, historical one-use work credit and scientific truth.

The ledger prevents repeated redemption within its trusted canonical registration domain; equivalence across encodings/engine versions and global chemical identity are not automatically solved. Human feedback, retraining and Cloudflare deployment remain deferred. Both original research questions below/above are unchanged.

## Previous update: whole-run Vina auditing, 8 September

The [completed independent-run investigation](WHOLE_RUN_DOCKING_2026-09-08.md) replaces the rigid-bank recommendation below. Actual flexible Vina runs, post-commit complete-run replay, trace binding and one-use precomputed scientific credits are implemented. All 46 honest audit transcripts passed. Warm client molecular fractions are 94.1–99.2%, but the four requirements are not satisfied together: bounded WASM redocking remains at least 3.52 Å versus stock Vina 0.48 Å; the 256-run warm molecular ratio of 14.7× falls to 2.08× including ligand setup on both sides; first initialization is 11.04 seconds with a large memory footprint.

The investigation also demonstrates a partial-cache retry attack and adds a global three-challenge cap per scientific range. This limits repeated chances across identities but creates work-pool exhaustion and recovery costs. Historical precomputation is accepted as one-use scientific credit, not misclassified as fresh CPU work. Keep whole-run auditing as a research baseline; test stronger scientifically justified units and reusable preparation before claiming journal readiness. No novel security contribution or deployed admission system is established. Human feedback and Cloudflare remain deferred. Both research questions are preserved below/above.

## Previous update: useful-work enforcement without full Groth16, 8 September

> Can we make attacker cost scale with the amount of assigned USEFUL docking work while keeping server verification much cheaper and keeping cryptographic/non-useful client overhead a minority of total work?

The [completed lightweight docking investigation](LIGHTWEIGHT_DOCKING_FINDINGS_2026-09-08.md) now drives the decision. Disjoint leases and 1/4/16-ligand audits are implemented. At 16 × 16,384 poses, Chrome takes 1.04–1.10 seconds with 88–94% molecular-kernel time and 9–12 ms warm checking, excluding network/database costs. However, the coarse bank fails the scientific gate (pilot AUC 0.352 versus uncapped Vina 0.664; redocking 9.05 Å versus 0.44 Å). Cached-science recommitment and hidden-optimum attacks pass. Prefer scalar audits plus independent jobs as the experimental baseline; do not deploy the current bank or return to full Groth16 by default. Effective molecular search, a defensible work/record relationship and novel security contribution are still unresolved. The original inference question is preserved above.

## Previous update: bounded scientific search and difficulty ladder, 7 September

**Read the [bounded-search investigation](BOUNDED_SEARCH_DIFFICULTY_LADDER_2026-09-07.md) first.** Actual original-circuit proofs now cover 2/8/16/32/64 candidates, with 128/256 circuits compiled and resource projections clearly separated. Raw trajectory audits fail a generic effort-enforcement counterexample. A real Vina-grid numerical pilot and exact proof of a restricted published protein-design problem are implemented. The latter proves 16/64 candidates in Chrome at 0.625/1.422 seconds, but central search remains cheaper than proof verification.

Historical recommendation (superseded by the 8 September update): keep docking as a scientific comparison and prioritize certified discrete molecular search. Scientific validity, correctness of the assigned computation, and fresh attacker effort are separate claims. Neither Groth16 nor an optimization certificate alone establishes the last one. The next gates are a defensible effort/amortization model, stronger scientific campaigns, complete economics and production/device evaluation. No new admission mechanism is ready for use; human feedback and Cloudflare remain deferred. The original question above is unchanged.

## Previous update: docking and Groth16 tested, 7 September

**Read the [measured docking/Groth16 feasibility report](DOCKING_GROTH16_FEASIBILITY_2026-09-07.md) first.** Completed 63 native and 13 browser docking searches, cached rescoring and explicit effort-cheating experiments. Score-only checking accepts low-effort substitutions and tiny shifts of cached poses. Actual Node/browser Groth16 proofs bind a reduced integer contact search, but this is not Vina and verification costs more than that tiny search centrally. No secure admission replacement or new scientific discovery is established.

The next gate is a scientifically validated bounded search relation with favorable complete proof/admission economics. Human feedback and Cloudflare remain deferred. The original question above is preserved exactly. The [pilot evidence](../evaluation/docking_pilot_2026-09-06/README.md) includes reproducible inputs, generated poses, public proofs, timing boundaries and failed checks.

## Previous update: broader useful-computation investigation, 6 September

**Read the [useful-computation pivot audit](USEFUL_COMPUTATION_PIVOT_AUDIT_2026-09-06.md) first.** The narrow VGG margin prompted a broader review of succinct proofs, scientific computing, docking, quantum verification, security witnesses and optimization. The next feasibility priority is small, externally demanded proof-generation jobs; bounded security-witness search is a second route, and docking with independent rescoring is the preferred biology candidate. Search-based tasks may require a separate voluntary background mode because useful success is not guaranteed within each access deadline.

Near-constant verification with respect to computation size is established cryptography, not a missing primitive. Proof generation, data handling, fresh demand and malicious request cost remain decisive. At the time of that audit no alternative had been locally benchmarked; the 7 September pilot above supersedes that status. No new contribution is established. The [source ledger](USEFUL_COMPUTATION_SOURCES_2026-09-06.json) records evidence quality and limits. Preserve the exact question above while evaluating a broader workload scope. The human stage and Cloudflare deployment remain deferred.

## Inference evidence and readiness gates

The [direction and cost-boundary report](JOURNAL_DIRECTION_AND_FRONTIER.md) preserves the completed inference experiments. It supersedes earlier requirements that made human recruitment and retraining mandatory for the main paper. Those studies and the shared Cloudflare site are deferred until contribution selection, following the latest user instruction. The exact question above remains recorded as the original framing.

The candidate paper concerns when useful browser work pays for verification under malicious submissions, departures and access deadlines; its main workload is being reconsidered. A new matrix primitive is not a prerequisite, but an original finding or improved mechanism is still required. See the provisional [outline](PAPER_OUTLINE.md) and expanded [prior-art ledger](NOVELTY_LEDGER.md).

| New evidence | Result and limit |
| --- | --- |
| Replacement workload | Published ResNet20/VGG11-BN accuracy reproduced. Exact integer VGG reaches 83.10% on all 2,000 CIFAR-10.1 v6 images; calibration used 256 training images. Public labelled data proves neither new demand nor fresh effort. |
| Prepared checking | A 4096-square synthetic dense layer: 0.0866 ms check versus 5.3649 ms exact central, with 174.60 ms setup. This is a kernel experiment. |
| Complete VGG path | 128 distinct-image paired study: selected verification mean 3.913 ms, practical native INT8 mean 4.949 ms. At 8% full audits the expected measured path is 6.190 ms; setup, HTTP/state and transfers are extra. Robust total savings remain unproved. |
| Real browser | Chrome executes exact VGG in 313.1–326.9 ms on one repeated input; all three traces match Python. Weights are 9.76 MB, full trace 610,344 bytes, selected trace 344,064 bytes. Phone/network evidence is absent. |
| Actual protocol probes | 64 honest full/hybrid traces accepted and 64 sparse forgeries rejected. Loopback HTTP: 16 honest accepted, 8 forged rejected, 8 malformed rejected, one credit in a 16-way duplicate race, late response rejected and 8 departures expired. Separate research endpoint, not production DB integration. |
| Bounded admission | Server-owned plans, byte/reservation caps, one-start/one-credit, deadlines, attempt cap and overrun closure; 180 corrected arrival scenarios compare early versus result-arrival reservation. Ready reservation improves the measured simulation tradeoff but can reject clients after computation. These are baselines, not established novelty. |

**Correction:** the earlier five-model timing table was MNIST; the failed fresh-batch experiment was synthetic. They did not establish that CIFAR verification is fundamentally unable to be cheaper. The new experiments confirm your fixed-weight intuition while exposing the full-cost qualifications.

Current submission gates: observable-protocol/adaptive analysis; a substantive contribution against prior art; repeated strong-baseline economics across workloads/hardware; live lease/token integration and PostgreSQL/Redis concurrency/failover; physical browser/network measurements; real workload demand; independent rerun and manuscript/declarations. Human audits/retraining are needed only if the paper claims their benefits.

The later shared site will use persistent pseudonymous IDs with authentication/recovery, resumable assignments and no per-person repeats, with Pages/R2/D1 intended. It is not deployed; invitation removal and dashboard changes remain deferred with the human stage. Sending ten invitations is not a paper-readiness step.

Raw results and commands: [frontier experiment record](../evaluation/journal_frontier_2026-09-05/README.md).

## Earlier implementation update (historical scope and measurements)

The local research pipeline is now implemented and tested, but **the project is still not ready for journal submission**. Arithmetic aliasing is repaired; a full security proof, a demonstrated new mechanism, competitive economics and the human/retraining studies remain open. The numbered assessment below preserves the original findings and rationale; its old timings and code descriptions are a pre-repair snapshot.

| Work | Current state and evidence |
| --- | --- |
| Exact verifier repairs | Finite/integer/range and intermediate bounds, crypto-derived projections, exact forced/sample audits and faster modular dot products. Both original modulus-offset attacks are rejected; honest forced audits run. |
| Assignment and credit | Unique prepared-input/model reservations, dataset filtering, model-checksum pinning, conditional claims/advancement/release, stale/duplicate rejection and atomic token redemption. Public-data precomputation remains possible. |
| Review dashboard | `/review` supports your Correct / Incorrect workflow, optional corrected classes, independent blinded classification, consent, invitations, pause/resume and exports. Simulated responses are explicitly separated. |
| Ready review material | 100 completed CIFAR-10 predictions in a researcher review batch, plus a separate 100-image blinded batch targeting ten people at 30 images each. No participant invitations have been issued for these batches. |
| Human analysis | Counts independent reviewers, rejects duplicate rows, excludes simulations by default, distinguishes model agreement from independent truth, and exports consensus candidates without automatic promotion. |
| RGB workload | Official checksum-checked CIFAR-10 binary data, disjoint train/validation/audit indices and official held-out test; an opt-in 3072→128→64→10 model and 150 imported audit images. Five epochs on 10,000 training images yielded only **34.13%** test accuracy: a weak workload pilot, not a useful-classifier claim. |
| Real local browsers | Four isolated Chromium contexts: 16/16 honest attempts accepted, 8/8 quantized modulus-offset attacks rejected, no extra duplicate tokens, eight intentional departures. Mobile layout checks are viewport emulation. |
| Batching and scheduling research | 36 batch configurations with a strong exact central baseline; 64 synthetic arrival/churn/policy configurations. Batching is a known baseline, has no live token integration and has no proved wall-clock deadline. |
| Code checks | Fresh pinned Python install and dependency check passed; 101 tests passed (159 warnings). Existing JavaScript environment: 31 tests, type checking and both builds passed; lint has zero errors and 27 warnings. |
| Post-repair evaluation | Five MNIST models × 100 inputs: 500/500 direct-label matches, 1,700 honest forced audits performed, all diagnostic perturbations rejected. Full verification remains slower than direct inference for every model; see the implementation record for complete-cost timings and scope. |

**Key economic result:** for a 2048-by-256 synthetic integer layer and 32 honest rows, the fresh-batch verifier took about **12.28 ms**, versus **1.247 ms** for optimized binary64 central inference that is exact for these bounded integers. Comparing only with slower NumPy int64 multiplication would suggest a misleading advantage. These are local operator measurements with five repetitions; they exclude the complete admission/network pipeline.

**Your human-study proposal:** your reviews are a legitimate expert audit. Ten friends are a feasible exploratory convenience sample, not a representative quantitative study or ten times as many people because each labels multiple images. No fixed requirement for 100 humans has been identified. Choose blinded mode for independent class judgments and Correct / Incorrect for operational checking; keep the two analyses separate. Institution-required review/consent must precede recruitment.

Read [the security specification](SECURITY_SPEC.md), [human-study protocol](HUMAN_STUDY_PROTOCOL.md), [novelty ledger](NOVELTY_LEDGER.md), and [implementation record](../evaluation/journal_implementation_2026-09-05/README.md). The public site has not been deployed. The local pilot database and logs are excluded from Git.

Remaining gates: a genuinely improved mechanism and full leakage/adaptive analysis; production PostgreSQL/Redis concurrency/failover; strict deadline/admission policy and saturation tests; physical devices/networks; a stronger application-relevant classifier/workload; approved real participants; controlled held-out retraining and poisoning experiments; independent artifact rerun and completed manuscript/declarations. The widget IIFE build is also very large (about 65.8 MB before gzip), so cold-start delivery needs further work. Simulation cannot replace these human/device measurements.

## Initial assessment and research plan (pre-repair snapshot)

**Assessment:** Springer Nature's *Cybersecurity* is a plausible venue for this project, but the current prototype is not ready for submission. The principal obstacles are a demonstrated verification flaw, unproven fresh-work guarantees, incomplete security analysis, and missing end-to-end economic and human-labeling evidence. No honest checklist can guarantee acceptance. The recommended contribution is a rigorously evaluated security protocol for useful browser admission work, with one specific new mechanism; a general matrix-verification breakthrough is not a prerequisite.

Qwen remains an optional generality experiment or appendix. The central workload should be compact browser models and the selective independent human-audit loop. This matches the checked-in scope decision and the user's current direction.

**What was actually checked**

Reviewed the paper outline, product scope, evaluation code and reports, Python verifier and model arithmetic, task assignment and pipeline leases, submission validation, human-audit selection, consensus service, retraining script, and browser execution path. Publisher requirements and selected primary prior art were checked online. This is a targeted readiness review, not an exhaustive literature survey or complete penetration test.

Fresh local evidence is in `docs/evaluation/journal_audit_2026-09-05/`:

- `security_probes.json`: reproduced cached-trace reuse and modulus-offset output forgery on both quantized models.
- `evaluation.json` and `evaluation.md`: reran the existing evaluator on 100 MNIST images, seed 42, five small models. This is a local Python simulation, not a real multi-browser deployment.
- `eslint.json`: 76 errors and 31 warnings.
- Python tests: 70 passed, 33 warnings. JavaScript tests: SDK 2, widget 29 passed. Typecheck passed.

The first Python run from the existing `tmp` directory encountered SQLite file-access errors: 67 passed, one readiness failure and two fixture errors. A second run from the new audit directory, with the application database set to in-memory SQLite and the fixture database local to that directory, passed all 70. This does not validate concurrent PostgreSQL/Redis production behavior. Builds, live HTTP proof submission, token redemption, physical mobile devices, and human experiments were not run in this review.

During the initial review, application source was not changed. The implementation update above was performed afterwards; the original evidence is retained separately and existing unrelated working-tree edits were preserved.

**1. First submission blocker: exact field equality does not imply exact integer equality**

`server/app/ml/proof_verifier.py:799` accepts integer outputs whose absolute values are below 2^53, then checks their projections modulo p = 2^31 − 1. It applies real/integer post-operations to the original submitted values. No tighter range restriction makes each accepted integer a unique representative of its residue class.

Consequently z and z + p have identical residues and pass every field projection, regardless of the secret projections. Their ReLU, requantization, dequantization or softmax results need not agree.

Fresh reproduction using `scripts/audit_journal_security.py`:

| Model | Honest label | Altered label | Altered proof accepted | Requested full audit actually performed |
| --- | --- | --- | --- | --- |
| mnist-tiny-q8 | 5 | 6 | Yes | No |
| mnist-cnn-q8 | 8 | 9 | Yes | No |

The script computes an honest trace once, adds p to a different class's final logit, recomputes public hashes, and submits to the actual verifier. It uses seeded integer input in the permitted input range. It requires no verifier-secret access. This demonstrates arbitrary-choice label manipulation in the verifier on these examples, not a measured attack success rate on a production deployment. The outer HTTP/token flow was not exercised.

Required repair: establish per-layer integer input and output bounds; enforce an allowed interval of width below p containing all honest outputs, or choose a sufficiently large field/multiple moduli and a rigorously specified signed decoding. Validate that the honest arithmetic never wraps and all intermediate rescaling products remain exactly representable. Apply nonlinearities only after the intended integer semantics have been established. Add positive/negative modulus-offset, boundary, non-finite, fractional, overflow, and last-logit manipulation tests. `force_audit=True` must do what its name promises; exact-mode audits currently skip at `proof_verifier.py:858`.

Fixing this implementation error is mandatory but does not by itself constitute a new research contribution.

**2. Correctness, freshness and label quality are different guarantees**

The local probes also accept the same honest trace under a new task ID and nonce after recomputing its public commitment. This is correct behavior for an output-correctness verifier, but contradicts an unconditional claim that every accepted access request paid fresh inference cost.

`server/app/core/pipeline.py:275` picks least-served samples and allows reuse. Changing the secret verification equation does not change a deterministic model's correct answer for the same input. Rehashing a saved answer is much cheaper than recomputing the network.

Define three separate security experiments:

1. **Execution integrity:** an accepted result equals the prescribed model computation under the specified arithmetic.
2. **Work freshness/access economics:** prior transcripts or cached outputs cannot satisfy new useful-work obligations cheaply under an explicit workload and adversary model.
3. **Semantic quality:** accepted predictions and promoted human labels have measured accuracy and poisoning resistance.

A fourth protocol property is access-token single use and site/session binding. The code already contains token replay handling; do not confuse token replay with cached-computation reuse. Test both independently, including concurrent redemptions and multiple workers.

Possible freshness designs include atomic assignment of previously unserved work items, a sufficiently large private stream of new inputs, or useful challenge-dependent transformations. Each needs a cache/precomputation analysis. Unique assignment needs a policy for leases, abandoned work, collusion, duplicate raw inputs under different IDs, and dataset exhaustion. Adding a nonce to the hash, adding an easily derived affine perturbation, or sampling from a small augmentation family does not establish fresh-work hardness. A bot can also run a faster native/GPU implementation: successful computation is not proof of humanity.

**3. Rewrite the soundness argument around the implemented protocol**

The paper outline still claims approximately 2^-124 soundness and no need for audits. That claim is presently invalid for integer-model integrity because of the deterministic alias attack above.

Even after the arithmetic repair, the randomness model needs work:

- Four checks are derived from eight reused basis vectors. Four distinct equations are not automatically four independent fresh uniform full-space challenges under an adaptive transcript.
- `_secret_seed` truncates an HMAC digest to eight bytes and initializes NumPy `default_rng`. Each such initialization has at most 64 bits of seed entropy. NumPy explicitly says its simulation generators are unsuitable for cryptographic use. Replace this with a documented cryptographic PRF/XOF construction, domain separation, unbiased field sampling, and a security parameter. This observation alone is not a demonstrated seed-recovery attack. [NumPy documentation](https://numpy.org/doc/stable/reference/random/)
- For a fixed basis and nonzero basis residual d, the Vandermonde condition is a degree-at-most-seven polynomial in the sampled alpha. An idealized conditional root bound is at most (7/(p−1))^4 for four distinct samples; if d is zero, every combination accepts. Neither statement alone gives the actual protocol's adaptive security bound.
- Conversely, Vandermonde structure alone does not disprove a p^-4 bound in a different idealized experiment: with independent uniform full-field basis vectors, a basis-independent fixed error, and a rank-four coefficient matrix, the four resulting scalar residuals can be uniform jointly. The manuscript must specify which experiment it proves, rather than substitute either formula without its assumptions.
- The existence of a common nullspace does not show that a remote attacker can discover it. State precisely what the attacker observes: accept/reject, numerical failure reasons, timing, repeated queries, and any compromised worker state. Prove a bound over Q attempts and L layers, including model/key epochs and abort behavior.

Slalom already studies hidden-randomness reuse and its security cost. Reuse by itself is not a new idea or automatic insecurity. The challenge is establishing the precise guarantee for this construction and leakage model. [Slalom, Sections 3.2 and Appendix B](https://arxiv.org/html/1806.03287v2)

**4. Matrix multiplication: the useful complexity distinctions**

Think of checking a spreadsheet: recomputing every cell is costly, but a random weighted checksum can catch an incorrect answer. When the same weight matrix is used repeatedly, part of that checksum can be prepared in advance.

For arbitrary explicit dense n×n matrices, conventional multiplication costs O(n^3); this is not the best known theoretical multiplication bound. A Freivalds check of C = AB evaluates A(Br) = Cr in O(n^2) field operations. k rounds cost O(kn^2). Verification below quadratic for arbitrary explicit untrusted matrices with constant soundness against even a single corrupt entry runs into the input-query requirement: one cannot generally skip almost all of the claimed output. Structured matrices, promised errors, prior preprocessing, or proof/commitment access are different models. Current theory also studies derandomization and sparse-error promises, not simply rediscovering Freivalds. [Bennett et al., RANDOM 2024](https://arxiv.org/abs/2309.16176)

For the project's main case, z = Wx + b with fixed W of shape m×n:

    Precompute s = W^T r and beta = r^T b.
    Online check: r^T z = s^T x + beta.

Per projection, preprocessing is O(mn), online checking is O(m+n), and stored projections occupy O(m+n). For k independent projections, multiply these costs by k. For Q uses, account for setup/Q, refreshes, hashes, communication, nonlinearities, audits and state management. The verifier cost grows with vector dimensions; the source comment that it “stays flat as models grow” is misleading.

This fixed-weight improvement already appears in Slalom. A paper cannot claim it, quantization, or batched Freivalds as new. Succinct/interactive proof systems offer other verifier/prover/communication tradeoffs, but their setup, input commitments, browser prover costs and round trips must be counted. SafetyNets is a relevant established comparison. [Slalom implementation](https://github.com/ftramer/slalom), [SafetyNets](https://papers.nips.cc/paper/7053-safetynets-verifiable-execution-of-deep-neural-networks-on-an-untrusted-cloud.pdf)

**5. Recommended novelty candidates — hypotheses to investigate**

| Candidate | Specific research question | Evidence required | Assessment |
| --- | --- | --- | --- |
| Deadline-aware robust verification across anonymous browser sessions | Can a verifier batch work across visitors while bounding acceptance delay and isolating malicious contributions without unbounded verification amplification? | Formal batch soundness; fresh challenge timing; isolation/retry cost bound; churn and malicious-fraction experiments; cost/latency Pareto curves | Best initial mechanism to investigate; batching itself is established |
| Fresh useful-work admission | Can access credit be tied to genuinely new useful outputs despite caching, repeated assignments, abandoned leases and collusion? | Formal reuse game or clearly delimited economic model; cache-sharing attacker; finite-pool exhaustion; utility under fresh transformations | Closest to the fundamental project claim, but work-hardness is difficult |
| Quality-constrained audit allocation | Can limited independent human effort keep label error below a target under distribution shift and adversarial votes? | Compared with random/uncertainty/disagreement sampling; calibrated quality intervals; equal annotation budgets; poisoning and retraining experiments | Feasible empirical contribution if the policy goes beyond existing heuristics |

Do not attempt all three as equally novel headline contributions. First investigate robust batching plus an explicit, honestly delimited freshness policy. Retain human auditing as the demonstrated utility loop. If batching has no new mechanism beyond known scheduling and failure localization, it is an implementation optimization rather than the novelty claim.

A concrete batching baseline: commit B submitted traces before drawing fresh independent batch coefficients a_i. For each affine layer, check

    sum_i a_i z_i = W (sum_i a_i x_i) + b sum_i a_i.

This costs O(mn + B(m+n)) per round, or O(mn/B + m+n) amortized per example. It removes the need for repeated full-matrix work per example without a long-lived projection basis, but moves costs to batch waiting and failure localization. Nonlinearities must still be checked per example, and all intermediate inputs need authenticated custody. Release tokens only after their required checks finish. This algebra is an established Slalom baseline, not a proposed new theorem. The research opportunity would be a demonstrably better policy/protocol under anonymous churn and malicious batch contamination. Compare fresh checks, preprocessed checks, batching and optimized direct inference on equal hardware.

A smaller optimization in the current exact verifier is to evaluate the eight basis residuals first, then combine those scalars into four checks. It can reduce vector mixing from O(kB0(m+n)) to O(B0(m+n)+kB0), where B0=8. This is algebraic reassociation, not a security repair or independent novelty claim; floating-point behavior would require separate analysis.

**6. Current economics do not establish a benefit**

The fresh 100-image diagnostic run gives:

| Model | Direct full inference mean, ms | Mean one-layer verification call, ms | Sum across the model's verification calls, ms |
| --- | ---: | ---: | ---: |
| mnist-tiny | 0.1679 | 0.5079 | 1.5237 |
| mnist-tiny-q8 | 0.5284 | 1.1459 | 3.4377 |
| mnist-cnn | 0.7580 | 1.0155 | 4.0620 |
| mnist-cnn-q8 | 1.3187 | 4.5844 | 18.3376 |
| mnist-attn | 0.1297 | 0.6949 | 2.0847 |

The last column is derived as layer count × mean verification-call time because the script checks every layer once per input. It excludes network and orchestration and does not represent a separately timed whole-model request. These are single-host diagnostic measurements, not controlled repeated performance claims. Nevertheless, the current code has not established server compute savings even before network costs. Fewer counted arithmetic operations do not override these timings; exact modular dot products use Python integer loops and projection-basis mixing has overhead.

An especially important baseline is **ordinary hash-based browser admission + optimized centralized inference + the same human-audit policy**. If that baseline is cheaper, faster and equally useful, moving inference into browsers needs another measured justification. Measure total cost per distinct usable label, not merely submitted inferences or repeated outputs on the same sample.

**7. Experiments needed for a full research article**

The following are proposed study-design targets, not publisher-mandated sample counts or guaranteed acceptance thresholds.

| Study | Required comparisons and measurements |
| --- | --- |
| Real workload | Keep MNIST as a regression test; add at least one realistic labeling workload and preferably a second different domain. Predefine hidden-label splits, separate retraining and test data, include distribution shift, and use thousands of examples with repeated seeds/confidence intervals. |
| Verification | Arithmetic alias/range attacks, fabricated layers, skipped nonlinearities, tolerance abuse, malformed numbers, input substitution, incorrect versions, adaptive oracle use, cross-task cached outputs and model/key rotation. Prove negligible-error claims; experiments cannot establish 124-bit soundness. |
| Admission security | Native/GPU solver advantage, cache sharing, Sybils, request floods, abandoned claims, token/site replay, concurrent redemption, malicious batch contamination and verification-denial-of-service. Measure attacker cost per successful request and defender cost per rejected request. |
| Actual systems cost | Optimized direct CPU inference; an appropriate GPU/batched-server baseline; standard Freivalds; Slalom-style preprocessed verification; hash admission plus central labeling; proposed mechanism. Count preprocessing/rotation, weight delivery, proofs, hashes, parsing, post-ops, DB/Redis and failures. |
| Browser experience | Physical desktop and low-end mobile hardware; Chrome/Firefox/Safari and Android/iOS as available; cold and warm caches, slow networks, bytes, memory, compute/transfer/queue time, completion and abandonment, p50/p95/p99. Include accessible fallback. |
| Label quality | Same-budget machine-only, random auditing, uncertainty auditing and proposed auditing; gold-label error, calibration, class/shift coverage, adversarial vote fraction and collusion. Repeated deterministic model predictions are not independent semantic votes. |
| Human evidence | Obtain the institution's required ethics review before recruitment. Counterbalance tasks, keep audits independent of the model answer, report participant/task counts justified by power or precision analysis, time, error, completion and accessibility. Simulated voters must be described as simulated. |
| Retraining | Compare no update, machine-only pseudo-label training, randomly audited data, proposed audit data and a clean-label reference at equal annotation budgets. Show held-out accuracy/calibration changes, poisoning behavior, forgetting, version promotion and rollback. |
| Concurrency | Exercise actual PostgreSQL/Redis with parallel claim/advance/redeem operations. Current mocked SQL-lock assertions and SQLite tests do not establish deployment correctness. |

Current evaluation reproduces 100% distributed/direct agreement, 97–100% ground-truth accuracy, and rejection of its tested perturbations. These results do not establish robustness against untested attacks. Even zero failures in 100 independent trials permits roughly a 3% failure probability at a one-sided 95% bound; cryptographic soundness needs proof.

The retraining script is currently specialized to the MNIST dense model and a fixed local database path. A retraining scaffold is not evidence of measured learning benefit. Fingerprint vote deduplication uses an IP/user-agent-derived identity; it is not a guarantee of independent humans or Sybil resistance.

**8. Prior art that the manuscript must distinguish**

- Useful CAPTCHA labor: [von Ahn et al., reCAPTCHA, Science 2008](https://www.cs.cmu.edu/~biglou/reCAPTCHA_Science.pdf). The distinction must address machine-generated work and subsequent independent auditing, not merely useful labels.
- Browser computational admission: [Anubis, official design](https://github.com/TecharoHQ/anubis/blob/main/docs/docs/design/how-anubis-works.mdx). Match the access-control threat model and compare with a reproducible implementation.
- Fixed-weight verification, quantized arithmetic and batching: [Slalom, ICLR 2019](https://arxiv.org/abs/1806.03287). Trust placement differs, but the algebraic primitive is established.
- Proof-based neural inference: [SafetyNets, NeurIPS 2017](https://papers.nips.cc/paper/7053-safetynets-verifiable-execution-of-deep-neural-networks-on-an-untrusted-cloud.pdf). Discuss prover overhead, architecture restrictions and communication.
- Layer-partitioned inference: [DEFER](https://arxiv.org/abs/2201.06769). Distribution alone is established; the anonymous adversarial handoff and admission setting need their own contribution.
- Matrix-verification theory: [Bennett et al., RANDOM 2024](https://arxiv.org/abs/2309.16176). Distinguish deterministic, randomized, structured, preprocessed and proof-assisted settings.
- Useful-work enforcement: [The Usefulness Gap in Proof-of-Useful-Work, 2026 preprint](https://arxiv.org/abs/2606.04819). Its authors study a different blockchain system; its relevant framing is the separation between verifying computation and verifying usefulness. Treat it as a preprint, not an independently confirmed claim about this project.

This list is a starting set. Before claiming novelty, forward/backward citation search the selected mechanism, including malicious batch verification, reusable verification, outsourced computation, client puzzles and audit allocation. Record each paper's assumptions, guarantee, costs and the proposed delta. “Nobody combines these exact components” is weak unless the combination solves a previously unresolved technical problem and the evaluation isolates that improvement.

**9. Submission plan for Cybersecurity**

The journal's scope explicitly includes system security, cryptography, adversarial reasoning, AI security and measurement studies. This supports a security-protocol paper with meaningful attacks and systems evidence; a generic ML labeling application would be a weaker fit. [Aims and scope](https://link.springer.com/journal/42400/aims-and-scope)

Verified requirements: the journal uses double-anonymous review; prepare an anonymized main manuscript/artifact and separate identifying material as requested by its submission system. Research articles request a 150–250-word abstract, 3–10 keywords, editable manuscript files, and declarations covering data/material availability, competing interests, funding, contributions and acknowledgements. Include ethics/consent details where relevant and accurately document substantive AI assistance under publisher policy. [Submission guidelines](https://link.springer.com/journal/42400/submission-guidelines), [Research article instructions](https://link.springer.com/journal/42400/submission-guidelines/research)

The APC recorded in the 5 September review was £1,060 / US$1,485 / €1,190, plus applicable taxes, determined at acceptance; this historical amount was not rechecked in the docking investigation. Confirm institutional support and the then-current amount before submission. [Fees](https://link.springer.com/journal/42400/how-to-publish-with-us)

Use a research title that states the security setting, for example **Verifiable Useful-Work Admission Control for Untrusted Browsers**. If the new batch mechanism is established, name that mechanism in the title. Qwen belongs in the appendix and should have no generated-token-throughput claim.

Suggested manuscript flow: problem and measured motivation; related-work comparison; system/adversary model; protocol and arithmetic specification; security theorems and attacks; implementation; research-question-led evaluation; limitations and human-study considerations; reproducibility. Three concrete contributions are enough: a precisely defined protocol/new mechanism, its security analysis, and a reproducible systems-and-utility evaluation.

**10. Prioritized work and decision gates**

1. **Security specification and repair:** close modulus aliasing, define integer ranges, replace randomness derivation, honor audits, define freshness and token guarantees, add targeted regressions. Finish with a reviewed statement of exactly what is proved and what is empirical.
2. **Novelty and economic pilot:** implement the smallest robust-batching candidate; compare with standard batching and optimized direct inference on a realistic model. Include setup, latency and failures. Continue only if there is a distinct mechanism or an informative, reproducible systems result.
3. **Workload and artifact:** add realistic data/model support, atomic assignment rules, model caching, reproducible attack drivers, locked environments, data provenance and independent rerun instructions.
4. **Full evaluation:** multi-device/browser runs, concurrency/abandonment and attack sweeps, annotation-budget experiments, approved human study and held-out retraining evaluation.
5. **Manuscript and internal review:** remove unsupported claims, map every contribution to a theorem/experiment, prepare anonymized artifacts and declarations, and have someone outside the implementation reproduce key results and challenge the threat model.

As a planning estimate, an experienced small team could budget roughly 10–16 weeks after settling the mechanism and securing dataset/device access; novelty research and human-study approvals can extend this. Do not use the estimate as an acceptance prediction. The immediate next milestone is a secure arithmetic/freshness specification and a small economic pilot, not manuscript polishing.
