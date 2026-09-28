"""One-off: write the amendment-14 verification-leverage results into the
manuscript and supplement. Numbers are read from the recorded result files.
Run once after the availability grid completes; refuses to run twice."""
import json
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]; P = Path(os.environ.get('PAPER_DIR', ROOT / 'docs/paper'))
LEV = json.loads((ROOT / 'local-research/inference-leverage-2026-09-28/results.json').read_text(encoding='utf-8'))
SUM = json.loads((ROOT / 'local-research/inference-leverage-2026-09-28/summary.json').read_text(encoding='utf-8'))
NAMES = {'mnist-mlp': 'MNIST MLP', 'mnist-cnn': 'MNIST CNN', 'cifar-cnn': 'CIFAR CNN', 'vgg11-bn': 'VGG11-BN', 'mnist-wide-mlp': 'Wide MNIST MLP'}
m = (P / 'MANUSCRIPT.md').read_text(encoding='utf-8'); s = (P / 'SUPPLEMENTARY.md').read_text(encoding='utf-8')
assert '### 3.6 Verification time and leverage' not in m, 'Already applied'


def rep(t, a, b):
    assert t.count(a) == 1, (a[:70], t.count(a)); return t.replace(a, b)


fmt = lambda x: ('%.3f' % x) if x < 1 else ('%.2f' % x)
rows = '\n'.join('| %s | %.1f%% | %s | %s | %.2f | %.2f | %s | %s |' % (
    NAMES[r['model']], 100 * r['quantized_accuracy'], fmt(r['central_ms']), fmt(r['verify_eff_ms']),
    r['leverage_no_audit'], r['leverage_8pct'], ('%.1f KB' % (r['trace_bytes'] / 1e3)), ('%.2f MB' % (r['weight_bytes'] / 1e6)))
    for r in LEV)
lmin = min(r['leverage_8pct'] for r in LEV); lmax = max(r['leverage_8pct'] for r in LEV)
vmin = min(r['verify_eff_ms'] for r in LEV); vmax = max(r['verify_eff_ms'] for r in LEV)
wide = next(r for r in LEV if r['model'] == 'mnist-wide-mlp')
assert SUM.get('L4') is True and SUM.get('L4_runs') == 1800, 'L4 must be scored on the complete grid before writing its result'

# Introduction: a sixth question and two workloads.
m = rep(m, 'economics of admission. We test it through five questions, each answered by a',
        'economics of admission. We test it on two workload classes through six questions, each answered by a')
m = rep(m, '''The protocol was amended thirteen times,''', '''The protocol was amended fifteen times,''')
m = rep(m, '''An outside trust signal helps only under stated issuer assumptions (Section 5.5).
''', '''An outside trust signal helps only under stated issuer assumptions (Section 5.5).
6. **Does cheaper verification escape the trade-off?** Not in the workloads we measured. Five image classifiers for data labelling, verified algebraically instead of by replay, verify in %s–%s ms and keep every device class served under attack, but verifying costs the server about as much as computing the answer itself: leverage %.2f–%.2f. Docking reaches leverage 4 to 10 only by paying for replay (Section 5.6).
''' % (fmt(vmin), fmt(vmax), lmin, lmax))

# Framework definitions.
m = rep(m, '''## 4 Methodology''', '''### 3.6 Verification time and leverage

Three quantities characterise a useful-work gate. The verification time V is
the verifier's CPU time per admission, including audits; with W verifier cores
the gate can check at most W / V admissions per second, the capacity R of
Section 5.5. The leverage L is the time the server would need to compute the
same useful output itself, with its best native implementation, divided by V:
useful work obtained per unit of verifier work. The delivery D is the bytes a
client downloads and uploads per admission. Proof of work has V of about a
microsecond and no useful output. A docking bundle has V = 1.52 s for four
units of work, L = 4, and L = 1/p in the trusted tier, where only a fraction p
of units is replayed. Section 5.6 measures V, L and D for a second workload
class whose results are checked algebraically rather than by replay.

## 4 Methodology''')

m = rep(m, '''| Attestation benefit | Mock issuer, token checks and one-use nullifiers | Assumed quota and token supply; no deployed issuer or blind-signature integration |''',
'''| Attestation benefit | Mock issuer, token checks and one-use nullifiers | Assumed quota and token supply; no deployed issuer or blind-signature integration |
| Inference leverage | Actual exact-integer verification and native inference timings on one host | Five small models, single-input admissions, one CPU; not GPU or batched serving |''')

# Results section 5.6.
pre = m.split('## 6 Discussion')[0]; TAB = pre.count('\nTable: ') + 1; FIG = pre.count('begin{figure}') + 1
m = rep(m, '''## 6 Discussion''', '''### 5.6 Does cheaper verification escape the trade-off?

Replay makes docking's verification expensive. To test whether that is a
property of useful work or of replay, we added a workload verified
algebraically: image classification for data labelling. A client runs a
small classifier in exact integer arithmetic and uploads every affine layer's
output; the verifier checks each layer with four secret Freivalds projections
[Freivalds77], as in Slalom [Tramer19], and recomputes only the cheap nonlinear
operations. We measured five models, from a 110-thousand-parameter MNIST
perceptron to VGG11-BN on CIFAR-10.1 and a perceptron with two 2,048-wide
layers, against the server's best native inference (Table @TAB@, Supplementary
Section S6).

Table: Verification leverage of five labelling models. Central is the server's best native inference; verification includes parsing, hashing, range checks, projections, nonlinear operations and an 8% audit rate. Leverage is central time over verification time.

| Model | Accuracy | Central (ms) | Verify (ms) | L, no audit | L, 8% audit | Trace | Weights |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
''' + rows + '''

All three predictions about correctness and ordinary models held: every
perturbation of every trace was rejected, and the four ordinary models reached
leverage %.2f–%.2f at an 8%% audit rate, below the predicted 1.5. For the
smallest models the verifier spends more than it would to compute the answer.
The prediction that the wide perceptron would reach leverage 10 failed: it
reached %.2f without audits and %.2f with them. That prediction came from an
earlier micro-benchmark that compared checking with an exact double-precision
baseline; against optimised native inference, a 2,048-wide layer computes in
about a millisecond, and the verifier's fixed per-layer work of parsing,
hashing and range checking, not the projections themselves, dominates.

Cheap verification does fix availability. Rerunning the admission grid with
each model's verification time in place of the replay kept every device class
at least 90%% served in all %d cells up to sixteen attacker cores, as the
proof-of-work gate did. What it does not provide is leverage. Figure @FIG@ places
every measured workload by verification time and leverage: proof of work at a
microsecond with no useful output, the classifiers at 0.2–6 ms with leverage
near one, and docking at leverage 4 and 10 with 152–1,520 ms of verification.
No workload we measured is both cheap to verify and high in leverage.

```latex
\\begin{figure}[htbp]
\\centering
\\includegraphics[width=0.75\\textwidth]{figures/design_space.pdf}
\\caption{Verifier time per admission against verification leverage for every measured workload. The shaded region, cheap to verify with leverage above four, contains no measured workload.}
\\label{fig:design}
\\end{figure}
```

## 6 Discussion''' % (min(r['leverage_8pct'] for r in LEV if r['model'] != 'mnist-wide-mlp'),
                        max(r['leverage_8pct'] for r in LEV if r['model'] != 'mnist-wide-mlp'),
                        wide['leverage_no_audit'], wide['leverage_8pct'], SUM['L4_cells']))

# Discussion: the trade-off.
m = rep(m, '''**When is useful work worth it?** Only when someone needs the output and the
verifier can afford replay.''', '''**The trade-off.** The two workloads fall at opposite ends of one trade-off.
Docking is expensive for the server to compute, so delegating it buys leverage,
but checking it without a certificate means replaying it, which is what exposes
availability. The classifiers can be checked algebraically in milliseconds,
but work that cheap to check at this scale is also cheap for the server to
compute, so delegating it saves nothing. A useful workload in the empty region
of Figure @FIG@ would need results that are expensive to produce and cheap to
check with a certificate, as a hash preimage is for proof of work. Search
problems with succinct certificates have that shape; docking's search does
not, because its best pose carries no proof that the search was done.

**When is useful work worth it?** Only when someone needs the output and the
verifier can afford replay.''')
m = rep(m, '''**Limitations.** Five phone models, one workload and five 96-compound panels.''',
        '''**Limitations.** Five phone models, two workload classes, five 96-compound panels and five small classifiers measured on one host without GPU or batched serving.''')
m = rep(m, '''Useful computation can stand in for discarded proof of work at a browser gate,
but verification changes the economics of admission.''', '''Useful computation can stand in for discarded proof of work at a browser gate,
but verification changes the economics of admission. Across two workload
classes, the work worth delegating was expensive to verify and the work cheap
to verify was not worth delegating.''')
m = rep(m, '''comparisons (S3), further admission-economics configurations (S4), and the
proof-of-work gate baseline (S5).''', '''comparisons (S3), further admission-economics configurations (S4), the
proof-of-work gate baseline (S5), and the inference-leverage methods (S6).''')

s = s.rstrip('\n') + '''

## S6 Inference-leverage methods

Five classifiers were verified by one generic exact-integer implementation:
per-channel int8 weights, signed 7-bit activations with integer requantization,
batch normalisation fused into convolutions, and four secret projections per
affine layer over the field of size 2^31 − 1, with a native C kernel for the
projections and nonlinear operations. The MNIST perceptron (784-128-64-10),
MNIST convolutional network (two 3x3 convolutions of 8 and 16 channels), CIFAR
convolutional network (three convolutions of 16, 32 and 64 channels) and wide
perceptron (784-2048-2048-10) were trained with Adam and seed 20260928 (5, 5,
20 and 5 epochs); VGG11-BN is the pretrained model used earlier, evaluated on
CIFAR-10.1. Calibration uses the first 256 training images. Timings use one
native thread over 128 distinct test inputs with twelve excluded warm-up runs
and method order randomised per input; central is the faster of FP32 and
native INT8 inference in PyTorch. Every single-entry perturbation of every
layer's trace (offsets +1, −1 and 2^31 − 1) was rejected. Availability used the
amendment-13 grid (fixed 16-bit and 18-bit puzzles and the full-patience
priority queue; 1–8 workers; 0–16 attacker cores; five seeds) with each model's
verification time at an 8% audit rate.
'''
m = m.replace('@TAB@', str(TAB)).replace('@FIG@', str(FIG)); assert '@TAB@' not in m and '@FIG@' not in m
(P / 'MANUSCRIPT.md').write_text(m, encoding='utf-8'); (P / 'SUPPLEMENTARY.md').write_text(s, encoding='utf-8')
print('applied; leverage range %.2f-%.2f, verify %.3f-%.3f ms' % (lmin, lmax, vmin, vmax))
