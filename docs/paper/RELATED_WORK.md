# Related work — draft, 25 September 2026

Draft section for the *Cybersecurity* manuscript. Every entry in
`references.bib` was checked against a primary or publisher record on
25 September 2026; fields that could not be confirmed were left out rather than
guessed. Numbers quoted from our own work come from `STATUS.md`.

The section is organised around the seven bodies of work a reviewer will hold
this paper against. Each subsection ends with what we take from that work and
what we do not claim. The closing claims ledger lists what remains ours.

---

## 2 Related work

### 2.1 Client puzzles and proof-of-work admission

Charging a requester computation before granting a shared resource goes back to
Dwork and Naor's pricing functions [DworkNaor92] and Back's Hashcash [Back02].
Juels and Brainard applied client puzzles to connection depletion
[JuelsBrainard99], already dividing a puzzle into independent subpuzzles, and
Aura et al. combined puzzles with stateless authentication [Aura00], as our
ticket prototype does. Stebila et al. strengthened the definition of puzzle
difficulty so that solving n puzzles is provably n times as hard as solving one
[Stebila11], which is the property our effort count, a number of distinct
subpuzzle solutions, relies on. The property of puzzles we contrast with most is
older and simpler: a hash puzzle verifies in microseconds, so verification never
limits the defender.

Two lines of criticism carry over directly. Laurie and Clayton argued that no
single price deters spammers without burdening legitimate senders, because the
two groups' computing resources differ too widely [LaurieClayton04]. Abadi et
al. traced the same disparity to hardware and proposed memory-bound functions
so that low-end and high-end machines pay similar costs [Abadi05]. Our device
measurements show the disparity is sharper in browsers: native hashing runs
about 36 times faster per core than the budget phone's JavaScript, and that
ratio, not the price rule, decides which newcomers lose under attack. Liu and
Camp answered Laurie and Clayton by weighting the work requirement with a
reputation function [LiuCamp06]; our trust tier, earned by three audited
bundles, and our attested lane are instances of that idea.

Proof of work has become a deployed browser defence. Friendly Captcha splits the
work into many small puzzles to reduce solve-time variance [FriendlyCaptcha],
ALTCHA and mCaptcha offer self-hosted variants, the latter framed as a rate
limiter rather than a human test [mCaptcha24], and Anubis, released in 2025,
places a SHA-256 challenge in front of sites to slow AI crawlers [Anubis];
operators report that crawlers adapted within months. NGCaptcha [Ding25]
couples a hash puzzle with a visual task designed to resist vision models, and
reasoning gates replace hashing with puzzles that are costly for AI agents to
reason through yet cheap to check [Kumar25]; neither produces useful output.
Among image and behavioural CAPTCHAs, Searles et al. measured 1,400 users
solving deployed CAPTCHAs [Searles23], and Motoyama et al. showed that human
solving services price CAPTCHAs at a small fraction of a cent [Motoyama10]. We
take from this work the baseline (a subpuzzle hash puzzle is the strongest
wasteful comparator) and the device-disparity problem. We do not claim a new
puzzle. On phones, a 64-subpuzzle puzzle proved as predictable as a docking
unit (Section 5.5), so we claim no latency advantage over this baseline.

### 2.2 Useful work in place of wasted work at the gate

reCAPTCHA made the human effort spent at an admission gate useful by pairing an
unknown word, whose transcription digitised books, with a control word of known
answer that decided admission [vonAhn08]. Our design mirrors that split at the
level of computation: the admission decision rests on a replayed unit, and the
remaining units are accepted into the scientific pool unverified. The
difference is that reCAPTCHA needed human consensus to trust the unknown word,
whereas a docking unit can be replayed bit for bit.

Computational useful work at the gate has been proposed with far less evidence.
The Coinhive proof-of-work CAPTCHA mined Monero for the site owner; measurement
studies documented how the same scripts were used without consent
[Eskandari18, Konoth18, Rueth18], a history that makes consent and
transparency first-order design requirements for any system that spends a
visitor's CPU. The closest prior proposal to ours is Chadam and Topa's
password-cracking CAPTCHA [ChadamTopa23]: the visitor brute-forces a range of
candidate passwords against a stored hash, and progress is trusted when at
least 51% of a small group of visitors agree. It is a four-page
work-in-progress design without implementation measurements, adversarial
evaluation or device results, and its majority rule is exactly the redundancy
that Sybil identities defeat [Douceur02]. Klarman et al.'s Webcoin rewards
crowdsourced web indexing rather than hashing and states plainly the problem we
quantify: unlike a nonce, useful output cannot be validated in nanoseconds, so
only a fraction of it is verified [Klarman18].

What we add is not the idea but the measured system: a real scientific workload
(AutoDock Vina [Trott10, Eberhardt21] units of 256,000 evaluations), verified
by deterministic replay rather than by majority, shown to reproduce monolithic
screening results at matched compute on five targets, attacked under a
predeclared protocol, and timed on four phones.

### 2.3 Proofs of useful work in consensus

Proof-of-useful-work research asks when the work securing a blockchain can
also be useful. Permacoin repurposes mining for archival storage
[Miller14]; Ball et al. defined proofs of useful work for problems such as
orthogonal vectors and later revised their definition after observing that the
original admits a naive construction [Ball17, Ball18]; Ofelimos realises a
provably secure longest-chain protocol whose puzzle is a doubly parallel local
search [Fitzi22]; Komargodski and Weinstein obtain proofs of useful work for
arbitrary matrix multiplication with 1 + o(1) overhead under hardness
assumptions [Komargodski25]. Dotan and Tochner show that wasteless mining
constrains which problems can be used at all [DotanTochner20].

These works need what our setting does not: problems chosen or derived without
a trusted party, hardness guarantees for adversarially chosen instances, and
public verification. An admission gate has a trusted server that assigns the
task and holds the verification key, so useful work can come from an ordinary
scientific queue. Pass shows that, at equilibrium pricing, useful work does not
lower the cost of attacking a proof-of-useful-work chain [Pass26]; our setting
reaches a related conclusion by measurement, since usefulness never discounts
the attacker's price of admission. What the consensus setting teaches instead is the cost of
verification. Luu et al.'s verifier's dilemma shows that when checking a
computation is expensive, rational verifiers skip it [Luu15]. Our verifier
cannot skip replay without admitting fabricated output, so the dilemma becomes
a capacity limit: every fake submission costs a full replay, and spare replay
capacity, which costs the defender real CPU, bounds who can be admitted under
attack.

### 2.4 Result verification in volunteer computing

Volunteer computing has verified untrusted results for over two decades. BOINC
uses replication with adaptive policies based on host history [Anderson20];
Sarmenta introduced spot-checking and credibility-based fault tolerance
[Sarmenta02]; Golle and Mironov planted secret "ringers" whose images reveal
lazy workers [GolleMironov01]; and Kondo et al. measured how often desktop-grid
results are actually wrong [Kondo07]. Browser volunteer computing followed with
Pando [LavoieHendren19] and JSDoop [Morell19], and Webina runs AutoDock Vina
itself in the browser through WebAssembly [Kochnev20]. Docking itself has run on
volunteer machines before, in Docking@Home on BOINC [Estrada10], among
long-lived, credited volunteers rather than anonymous visitors. Outside
volunteer computing, Tan et al. audit an untrusted web server by re-executing
its requests and cut the cost of naive replay by deduplication [Tan17]; our
verifier replays one sampled unit per bundle and faces the same trade-off
between audit coverage and re-execution cost.

Our audit is a spot check in Sarmenta's sense, and we do not claim the audit
mechanism as new. The setting differs in who the adversary is. Volunteers are
long-lived identities who accumulate credit and can be blacklisted; an
admission gate faces anonymous newcomers whose identities are free, so every
fix we measured had to hold with identity cost at zero, and did (attacker
discount factor at parity or above after reseeding, removal of the audit
reveal and a three-bundle trust threshold). Replay is only decisive if execution is
deterministic across platforms. WebAssembly specifies deterministic floating
point except for NaN payloads [Haas17]; we observed all 68 phone units bitwise
identical to native execution across iOS and Android, and confined the only
cross-toolchain divergence to last-bit C runtime differences amplified by Monte
Carlo search.

One threat appears to be specific to useful work that is merged: an attacker
who never needs to be admitted can still corrupt the aggregate. Falsified
energies in 5% of units displaced honest minima from the finaliser's retained
set and lowered screening ROC-AUC by up to 0.034; rescoring every submitted
minimum before merging (+91 ms per ligand state) removed the effect. We have
not found this attack class treated in the volunteer-computing literature,
which verifies results individually rather than through the aggregation step,
but we state this as the result of our search, not as a novelty guarantee.

### 2.5 Pricing admission under denial-of-service attack

Several designs let clients bid for scarce service. Wang and Reiter's puzzle
auctions let clients choose puzzle difficulty and serve the highest bids first
[WangReiter03]; speak-up has clients pay in bandwidth [Walfish06]; Portcullis
allocates connection-setup capacity by per-computation fairness [Parno07]; and
Chakraborty et al. price jobs from an estimate of the honest workload so that
the defender's cost grows more slowly than the attacker's [Chakraborty22]. The
deployed descendant closest to our mechanism is Tor's onion-service defence
(proposal 327, shipped in Tor 0.4.8 in 2023), in which clients attach
Equi-X proofs of self-chosen effort, requests wait in an effort-ordered queue,
and the service publishes a suggested effort that rises with backlog and decays
when idle [TorProp327, TorPoW23]. Our effort-priority newcomer queue
(amendment 9) adopts that design and makes no claim to it.

What differs is what the queue protects. In these systems admitted service is
the scarce resource and puzzle verification is free; in ours the scarce
resource is replay of the submission itself. That changes the threshold: honest
newcomers stay served while the attacker's hash rate is below
(R − λ) × device hash rate × patience, with R the verifier's replay rate and λ
the honest arrival rate. This held in 46 of 48 testable cells, it shows that
the defender buys protection with replay CPU, and it exposes the device
disparity of Section 2.1: budget phones cross their threshold at one attacker
core with up to four verifier workers. The measurement is a simulation over
the real queue code with puzzle costs accounted from measured rates, not a
deployment.

### 2.6 Privacy-preserving attestation as an outside trust signal

Privacy Pass lets a client that solved one challenge redeem unlinkable tokens
later instead of solving more [Davidson18]; its architecture, HTTP scheme and
issuance protocols, including publicly verifiable blind-RSA tokens, are now
RFCs 9576–9578 [RFC9576, RFC9577, RFC9578]. Apple's Private Access Tokens use
this scheme with the device vendor as attester, and Cloudflare's Turnstile
accepts them in place of a challenge [ApplePAT22, Turnstile22]. A draft that
would let issuers cap tokens per client per origin [RateLimitDraft] expired in
2024. Apple states that its attester can rate-limit devices to detect farms
but publishes no limits. On the web outside Apple platforms the equivalent is
missing: Google's Web Environment Integrity proposal was abandoned in 2023
[WEI23], and Play Integrity attests Android apps rather than web pages
[PlayIntegrity]. Scrappy combines direct anonymous attestation with hardware
security devices to give servers unlinkable rate-assurance proofs [Akama24],
the closest research design to the per-device cap our lane assumes. Critics
object to device attestation on openness grounds [Rescorla22].

Our attested lane (amendment 10) is an application of these tokens, not a new
credential. Its measured contribution is the interaction with useful-work
replay: token holders, budget phones included, were served and reached the
three-bundle trust threshold within about a minute against a 16-core attacker
while tokens were costly, where every puzzle-only configuration locked them
out; cheap tokens starved anonymous visitors, because attested replays take
priority. Two limits come from the literature above, not from our simulation.
The per-device cap our model assumes is not a published guarantee of any
deployed issuer, and the budget Android phones the lane is meant to protect
have, at present, no deployed privacy-preserving web attestation at all.

### 2.7 Scientific workload

AutoDock Vina [Trott10] and its 1.2 release [Eberhardt21] are among the most
widely used docking programs, and large-scale docking is a standing demand for
computation. We make no methodological claim about docking. Our scientific
claim is narrow: decomposing an exhaustiveness-32 search into independent
256k-evaluation units and merging them with Vina's own finaliser changed
screening ROC-AUC by at most ±0.017 (paired 95% intervals) on five
96-compound panels at under 0.5% extra evaluations.

---

## Claims ledger

What the literature leaves to us, stated no more strongly than the evidence:

| Candidate contribution | Prior work that bounds it | How we state it |
| --- | --- | --- |
| A browser admission gate whose work is a real scientific computation, verified by deterministic replay, evaluated end to end | reCAPTCHA (human useful work), Coinhive (monetised work), Hashptcha (design only, majority vote), Webina (browser Vina, no admission) | "To our knowledge, the first measured and adversarially evaluated" — keep "to our knowledge" |
| Decomposition preserves screening results at matched compute | Vina's own parallel Monte Carlo | Measured on five small panels; not a docking-method claim |
| Admission economics with free identities: attacker discount factor, reseeding, audit-reveal removal, trust threshold | Spot-checking and credibility [Sarmenta02]; BOINC host history | The mechanisms are known; the measured failure modes and fixes in an anonymous-admission setting are ours |
| Aggregation-integrity attack on merged useful work and its fix | Volunteer computing verifies results individually | "We did not find this attack treated" — not "first" |
| Replay capacity as the defender's binding cost; threshold law and device asymmetry | Tor PoW, puzzle auctions, verifier's dilemma, Laurie–Clayton, Abadi et al. | The queue design is Tor's; the law, its measurement and the useful-work-specific cost are ours |
| Outside trust breaks the trust-bootstrap lockout | Privacy Pass, PAT, Liu–Camp | An application with measured conditions and stated platform limits |
| Bounded useful work has lower latency variance than a puzzle | Friendly Captcha subpuzzles | Measured on five phones: advantage over a single puzzle only; parity with 64 subpuzzles. Not claimed |

## Things this search changed

- STATUS.md said Android's Play Integrity "is not unlinkable". The accurate
  statement is stronger: there is no deployed web attestation for Android
  browsers (Play Integrity serves apps; WEI was abandoned in 2023).
- The per-origin rate-limited token draft that amendment 10 cites as the model
  expired in 2024. The per-device cap must be presented as an assumption about
  the attester, not as a property of deployed tokens.
- The phone variance comparison needs the subpuzzle baseline before the paper
  can claim lower variance than proof of work in general.

## Not yet covered

- Kill-Bots — cite if the related-work section grows a DoS-systems paragraph.
- Primecoin and other useful-work cryptocurrencies — optional background.
- Structured search, 25 September 2026: queries across arXiv, the USENIX
  Security 2025/2026 programmes, NDSS, CCS, CACM and web sources for useful
  computation, docking, folding or scientific work used as a CAPTCHA or
  admission gate. Recent venue work on CAPTCHAs concerns solving visual
  CAPTCHAs with vision-language models or hardening them against AI; recent
  proof-of-useful-work work concerns consensus. No admission gate using
  scientific computation was found beyond [ChadamTopa23]. This supports
  "to our knowledge", not a guarantee.
