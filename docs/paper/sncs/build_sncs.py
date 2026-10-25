"""Generate the SN Computer Science submission from the Markdown sources.

docs/paper/MANUSCRIPT.md, RELATED_WORK.md, SUPPLEMENTARY.md and references.bib
are the source of truth; this script applies the journal version's edits and
typesets them with the Springer Nature template (sn-jnl, numbered references):
a structured abstract, a three-findings introduction, amendment bookkeeping
moved out of the Results prose into a supplementary mapping table, acronyms
defined at first use, completed reference fields and a "Statements and
Declarations" section. Single-blind review, so authors are shown. Every edit
must match its source exactly once, so a changed source stops the build.

Output in docs/paper/sncs/: manuscript-sncs.tex, supplementary-sncs.tex,
references-sncs.bib and, with latexmk installed, their PDFs.
Build with: python docs/paper/sncs/build_sncs.py
"""
import re
import subprocess
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]; sys.path.insert(0, str(ROOT))
import scripts.build_manuscript as bm
PAPER = ROOT / 'docs/paper'
TITLE = 'The Price of Utility: Verification Leverage in Useful-Work Browser Admission'

ABSTRACT = [
    ('Purpose', "Proof-of-work challenges protect websites by making visitors spend computation that is then discarded. "
                "We ask what it costs to make that computation useful."),
    ('Methods', "Under a protocol whose predictions were committed before each experiment, we measured two kinds of work: "
                "short molecular-docking tasks for a drug-screening campaign, checked by secretly replaying one task per "
                "bundle, and image classifiers for data labelling, checked algebraically. The evidence combines a matched "
                "docking campaign, phone execution, adaptive attacks, admission simulations and a real-time replay test."),
    ('Results', "Splitting docking into admission-sized tasks preserved screening results on the tested panels, and phones "
                "reproduced the tested units exactly. Once three easily overlooked scheduler flaws were fixed, every tested "
                "cheating strategy cost about as much as honest work, even with free identities, and replay caught every "
                "tested shortcut through the search. Each check is a full replay, so in simulations under attack replay "
                "capacity decided who was admitted and budget phones were turned away first, while the same queue checking "
                "proof of work kept every device class at least 90% served. The classifiers were checked in milliseconds and "
                "stayed available, but checking them cost the server nearly as much as computing the answers."),
    ('Conclusion', "In both workloads we measured, work worth delegating was expensive to verify, and work cheap to verify "
                   "bought little."),
]
KEYWORDS = ['Proof of work', 'Useful work', 'Admission control', 'Denial of service', 'Verifiable computation', 'Molecular docking']

AUTHORS = r'''\author*[1]{\fnm{Rishi} \sur{D V}}\email{rishidv2005@gmail.com}
\author[1]{\fnm{Ram Ganesh} \sur{Vemula}}\email{ramganeshvemula@gmail.com}
\author[1]{\fnm{Rithik Madhav} \sur{V}}\email{rithik7680@gmail.com}
\author[1]{\fnm{Sanjay} \sur{D M}}\email{sanjaydm23072005@gmail.com}
\author[2]{\fnm{Jayashree} \sur{R}\,\orcidlink{0000-0002-9509-0066}}\email{jayashree@pes.edu}
\affil*[1]{\orgname{PES University}, \orgaddress{\city{Bengaluru}, \state{Karnataka}, \country{India}}}
\affil[2]{\orgdiv{Department of Computer Science and Engineering (AI \& ML)}, \orgname{PES University}, \orgaddress{\city{Bengaluru}, \state{Karnataka}, \country{India}}}'''
SUPP_AUTHORS = 'Rishi D V, Ram Ganesh Vemula, Rithik Madhav V, Sanjay D M and Jayashree R'

DECLARATIONS = r'''\section*{Statements and Declarations}

\bmhead{Competing interests} The authors declare no competing interests.

\bmhead{Funding} No funding was received for conducting this study.

\bmhead{Ethics approval} Not applicable. All phone timing tests were run by the authors on phones they own; the test page stored the device model and operating system as entered, the browser user agent and performance measurements, and no names, contact details or location data.

\bmhead{Consent to participate and for publication} Not applicable.

\bmhead{Data availability} The result ledgers behind every reported number and the submission revision are archived at \url{https://doi.org/10.5281/zenodo.23005913}.

\bmhead{Code availability} Code, protocol amendments, run manifests, analysis scripts and the figure and manuscript builders are available at \url{https://github.com/Rishi94523/useful-work-admission} under the MIT licence; AutoDock Vina and other upstream components are fetched and patched at build time and keep their own licences.

\bmhead{Author contributions} Conceptualization, methodology, software, validation, formal analysis, data curation, visualization and writing of the original draft: Rishi D V. Investigation (device experiments): Rishi D V, Ram Ganesh Vemula, Sanjay D M and Rithik Madhav V. Writing, review and editing: Ram Ganesh Vemula, Sanjay D M, Rithik Madhav V and Jayashree R. Supervision: Jayashree R. All authors read and approved the final manuscript.

\bmhead{Use of AI tools} The authors used two AI coding assistants, Anthropic Claude (Claude Code) and OpenAI Codex (2026 versions), in three ways. First, to write and debug the experiment software: the docking benchmark runners, the admission and verification prototypes, the analysis scripts, and the figure and manuscript build scripts. Second, to search for references and check their details; the authors verified each reference against its source. Third, to draft and revise text in every section of this article and its supplementary material. The authors directed the study, reviewed and edited all generated code and text, checked every reported number against the recorded data, and take full responsibility for the content of this article.

\bmhead{Supplementary information} Online Resource 1: supplementary methods, phone timing studies, availability prediction checks, further admission-economics configurations, the proof-of-work gate baseline, inference-leverage methods, follow-up validation, the screened-newcomer comparison, layer-width methods, protocol chronology and the mapping of results to protocol amendments.
'''

FINDINGS = '''This is a characterisation study of admission security, scientific output
and verification economics. Its contributions are three empirical findings:

1. **Final-result agreement can hide incomplete useful work.** Pool-only commitments let quarter- and half-finished searches pass in 20 and 45 of 99 cases. Trace commitments rejected the tested truncations and all 297 adaptive-shortcut submissions (Section 5.3). A matching trace requiring essentially the honest computation remains an assumption, not a proved lower bound (Section 3.5). Separately, five qualified 96-compound panels and 2,073 paired jobs establish screening preservation under the tested decomposition (Section 5.1); rescoring prevents fabricated energies from reordering candidates but cannot recover omitted search (Section 5.4).
2. **Free identities expose discounts that per-submission checks miss.** Reused assignment seeds, early audit disclosure and premature trust grants enabled large discounts. The measured fixes brought bundle-tier estimates near honest-work parity and trusted-tier costs above honest costs under the evaluated strategies (Section 5.3). Measured device rates yield a conditional capacity estimate of about 5.4 replay cores per attacker core to protect budget phones; in the tested proof-of-work control, each device class achieved at least 90% five-seed mean service across every tested configuration (Sections 5.5 and 6). Outside trust signals help only under stated assumptions.
3. **Cheap algebraic checks can lose their advantage against optimized inference.** Five classifiers, batching and a fused native verifier test whether low verification cost also makes delegation economical. Neither batching nor native verification achieved leverage four against the fastest measured server option. Synthetic layer-width experiments improved leverage relative to a CPU at substantial download cost, but did not retain that advantage when the GPU baseline was included (Section 5.6).

The contribution is an empirical account of when correct-looking outputs fail
to enforce useful work, how retry and trust paths affect its price, and why
apparently cheap checks buy little against optimized inference. Docking's
honest-submission leverage follows from the chosen replay fraction; the
measurements establish the tested security and availability consequences and
the hardware-relative economics of verification.

Each experiment's predictions and thresholds were predeclared before that
experiment ran; the study as a whole was not preregistered, later experiments
were chosen in light of earlier results, and failed predictions are reported.
Section 4 describes the protocol and measurement boundaries, and the supplement
maps each result to its protocol amendment.
'''

MAPPING = '''

## S11 Results and protocol amendments

Table: Main-text results and the protocol amendments that governed them. The amendments, with their predictions and dates, are in the repository's protocol file.

| Main-text result | Amendments |
| --- | --- |
| Phase operationalisation, economic fixes, integrity, trace commitment, rescoring (Sections 5.3–5.4) | 1–8 |
| Newcomer pricing and full-patience bidding (Section 5.5) | 9, 9b |
| Attested lane (Section 5.5) | 10 |
| Subpuzzle baseline on phones (Section 5.2) | 11 |
| Corrected five-seed availability (Section 5.5) | 12 |
| Proof-of-work gate baseline (Section 5.5) | 13 |
| Classifier leverage and availability; phones and scrypt (Section 5.6) | 14, 14b |
| Batching; native dense verifier (Section 5.6) | 15, 15b |
| Adaptive attacks on trace commitment (Section 5.3) | 16 |
| Real HTTP and replay (Section 5.5) | 17 |
| Unit costs and sleeper identities (Section 5.3) | 18 |
| Repeated inference timings; second host (Section 5.6) | 19, 19b |
| External screening (Section 5.5) | 20 |
| Layer width (Section 5.6) | 21 |
'''

# Amendment numbers out of the Results prose; Supplementary S11 maps results to amendments.
BOOKKEEPING = [
    ('(amendment 11; Table 3)', '(Table 3)'),
    ('''Replay makes docking's verification expensive. To test whether that is a
property of useful work or of replay, we added a workload verified
algebraically: image classification for data labelling.''', '''Docking occupies one point in the space of verification time and leverage
defined in Section 3.6: useful work gives it leverage, but checking it needs an
expensive replay. The second workload tests whether a task with far cheaper
verification escapes that trade-off, which would make the trade-off a property
of replay rather than of useful delegation. It is image classification for
data labelling, verified algebraically.'''),
    ('**Adaptive attacks.** Amendment 16 built three shortcuts through the search', '**Adaptive attacks.** We built three shortcuts through the search'),
    ('**Unit costs and sleepers (amendment 18).**', '**Unit costs and sleepers.**'),
    ('To isolate what replay adds, amendment 13\nreran', 'To isolate what replay adds, we\nreran'),
    ('**Real HTTP and replay (amendment 17).**', '**Real HTTP and replay.**'),
    ('**External screening (amendment 20).**', '**External screening.**'),
    ('Of the eight predictions in the\ntwo amendments, three held', 'Of the eight predictions in these\ntwo experiments, three held'),
    ('the wide perceptron with the native verifier of amendment 15b.', 'the wide perceptron with the optimised native verifier.'),
    ('Three predictions were recorded before the page ran\n(amendment 14b), and all held.', 'Three predictions were recorded before the page ran,\nand all held.'),
    ('only the small amendment-17 follow-up executes', 'only the small real-HTTP follow-up executes'),
]

# Caveats already stated in Table 1 or the Limitations, removed or shortened in the Results.
HEDGES = [
    (' These are 96-compound panels, not full-library\nscreens.', ''),
    (' This tests those truncation strategies, not a\ngeneral computational lower bound.', ''),
    ('''The lowest interval, 0.96 ± 0.09, also permits a modest attacker advantage;
containing 1.0 does not establish equality or a lower bound of 1.0.
Identities are free in these experiments, but results apply to the specified
strategies, attempt model and workload costs, not every possible adversary.''',
     'The lowest interval, 0.96 ± 0.09, still permits a modest attacker advantage.'),
    ('''This found no reuse of those recorded energies;
it does not rule out caching intermediate evaluations or reusable subcomputations.''',
     'This does not rule out caching intermediate evaluations.'),
    ('''This offline experiment measures damage conditional on malicious
outputs entering the aggregate; it does not demonstrate a way to bypass the
admission scheduler. In the scheduler, a bundle rejected by immediate audit
does not enter the scientific pool. Unaudited outputs in accepted bundles
and outputs admitted before deferred audit are distinct exposure paths.''',
     '''This offline experiment measures the damage if malicious outputs enter the
aggregate, not a way past the scheduler.'''),
    (' This does\nnot establish biological validity or rule out false positives in screening.', ''),
    ('''These are not measured
whole-panel poisoning outcomes: corpus score shifts were resampled onto
otherwise unchanged campaign scores (Supplementary Section S1).''', '''These are projections,
not measured whole-panel outcomes (Supplementary Section S1).'''),
    ('''This baseline models the gate only: under
proof of work an attacker who pays the puzzle is admitted and loads the
protected service behind it, which we did not simulate. The comparison
therefore isolates the availability price of replay verification rather than
comparing whole deployments.''', '''This baseline models only the gate: under
proof of work an attacker who pays is admitted and loads the service behind
it, which we did not simulate.'''),
    (''' We model the issuer with a mock; this is not a
deployed Privacy Pass integration.''', ''),
]

# Content corrections from review (numbers taken from the recorded studies).
EDITS = [
    ('''Our answer is a trade-off. A useful-work gate is characterised by how long
the server needs to check one admission and by its leverage, the useful work
it obtains per unit of checking (Section 3.6). Work worth delegating is
expensive for the server to compute, and without a succinct certificate it is
also expensive to check: from honest submissions, docking buys four to ten
units of work per unit replayed, a ratio fixed by its audit rate, but replay
makes verifier capacity decide who is admitted under attack. Work that can be checked cheaply, here image classification checked
algebraically, keeps every device class served but buys little, because at
this scale the server computes the answer almost as cheaply as it checks it;
neither batching nor an optimised native verifier raised its leverage above
2.2 against the server's fastest option. No workload we measured was both
cheap to check and high in leverage by that measure.''',
     '''Our measurements place two workloads at different points in a
verification-time and leverage trade-off (Section 3.6). Docking's honest yield
of four to ten units per replay follows from its audit rate. Its security and
availability costs require measurement: output-only commitments can accept
incomplete searches, free retry and trust paths create discounts, and replay
capacity limits admission under attack. Algebraic checks make classifier
verification much cheaper than molecular replay, but the fastest measured
server implementations compute the answers almost as cheaply as they check
them. Neither batching nor an optimized native verifier raised classifier
leverage above 2.2 against that baseline at the 8% audit rate we used. No
workload we measured combined cheap verification with high leverage by this
measure.'''),
    ('''Under those
conditions, with energies rescored, contamination slowed the campaign,
requiring up to four times as many admissions per ligand, without measurably
changing its rankings.''',
     '''Under this exchangeable-shift model, the projection predicted little
change in rankings when energies were rescored. The 25% useful-yield bound
implies up to four times as many admissions for the same amount of genuine
work; this is a yield calculation, not a measured campaign slowdown.'''),
    ('''It does not cover attacks that concentrate missing
search on particular compounds,''',
     '''The projection does not cover attacks that concentrate missing
search on particular compounds,'''),
    # One source for the budget phone's first contribution (Supplementary S2), and unit versus admission time.
    ('''later admissions, took 3.9 s, restoring it 1.5 s and the unit 7.4 s.''',
     '''later admissions, took 3.8 s, restoring it 1.5 s and the unit 7.5 s in the
first phone study (Supplementary Section S2). These are times for one unit; a
newcomer's four-unit bundle needs about four unit times of computation,
roughly 30 s on the budget phone, an estimate we did not measure.'''),
    ('We therefore ran a\nsecond page on five phones', 'We therefore ran a\nsecond study on five phones'),
    # Table 4 rows in attack order.
    ('''| A1 substitution of another unit's result | 0/99 | [0.00, 0.04] |
| A3 cached resubmission | 99/99 | by design; one-use credits refuse it |
| A2 quarter work, pool-only commitment | 20/99 | [0.13, 0.30] |
| A2 half work, pool-only commitment | 45/99 | [0.35, 0.56] |
| A2 quarter or half work, pool and trace commitment | 0/198 | [0.00, 0.02] |''',
     '''| A1 substitution of another unit's result | 0/99 | [0.00, 0.04] |
| A2 quarter work, pool-only commitment | 20/99 | [0.13, 0.30] |
| A2 half work, pool-only commitment | 45/99 | [0.35, 0.56] |
| A2 quarter or half work, pool and trace commitment | 0/198 | [0.00, 0.02] |
| A3 cached resubmission | 99/99 | by design; one-use credits refuse it |'''),
    # Which baseline each leverage figure uses.
    ('''full-pipeline leverage against the fastest CPU/GPU baseline (Supplementary
Section S7).''',
     '''full-pipeline leverage against the fastest CPU/GPU baseline (Supplementary
Section S7). These CPU-only figures, like the 3.15 above, exceed 2.2 because
they leave out the GPU; 2.2 is the figure against the server's fastest option.'''),
    ('every perturbation of every trace was rejected', 'all tested perturbations were rejected'),
    # One number for the wide layer, tied to Table 9's whole-model time.
    ('''against optimised native inference, a 2,048-wide layer computes in
about a millisecond, and the verifier's''', '''against optimised native inference, the wide model's largest layer, 2,048 by
2,048, computes in about a millisecond of the model's 1.60 ms, and the verifier's'''),
    # Acronyms that first appear in table cells or captions.
    ('| Real queue SQL with modeled arrivals,', '| Real queue code and Structured Query Language (SQL) ledger with modeled arrivals,'),
    ('| Isolated FIFO queue on one laptop,', '| Isolated first-in, first-out (FIFO) queue on one laptop,'),
    ('Table: Verification leverage of five labelling models. C is',
     'Table: Verification leverage of five labelling models (MLP: multilayer perceptron; CNN: convolutional neural network). C is'),
]
RELATED_EDITS = [('publicly verifiable blind-RSA tokens', 'publicly verifiable tokens based on blind Rivest–Shamir–Adleman (RSA) signatures')]
SUP_EDITS = [
    ('so leverages are compared within a session.',
     "so leverages are compared within a session, except that the native-verifier comparison (amendment 15b) uses the GPU "
     "timings measured in amendment 15's separate session."),
]

BIB_FIXES = [
    ("doi = {10.1145/3278532.3278539}", "pages = {70--76}, doi = {10.1145/3278532.3278539}"),
    ("doi = {10.1145/3361525.3361539}", "pages = {96--109}, doi = {10.1145/3361525.3361539}"),
    ("journal = {Bioinformatics}, volume = {36}, number = {16}, year = {2020}",
     "journal = {Bioinformatics}, volume = {36}, number = {16}, pages = {4513--4515}, year = {2020}, doi = {10.1093/bioinformatics/btaa579}"),
    ("note = {Educated Guesswork blog}, year = {n.d.}", "note = {Educated Guesswork blog, 29 August 2023}, year = {2023}"),
    ("@misc{Chakraborty22,", "@inproceedings{Chakraborty22,"),
    ("Maxwell Young}, title = {Bankrupting {DoS} Attackers}, year = {2022},", "Maxwell Young}, title = {Bankrupting {DoS} Attackers},"),
    ("note = {arXiv:2205.08287, revised January 2026; preliminary version at SIROCCO 2025}",
     "booktitle = {Structural Information and Communication Complexity (SIROCCO 2025)}, series = {LNCS}, pages = {211--227}, publisher = {Springer}, year = {2025}, doi = {10.1007/978-3-031-91736-3_13}, note = {Extended version arXiv:2205.08287}"),
]
# sn-mathphys-num prints "???" when a publisher has no place; locations from Crossref
# (Douceur02: LNCS 2429, 2002, same Springer Berlin-Heidelberg period; Freivalds77: North-Holland).
ADDRESS = {'DworkNaor92': 'Berlin, Heidelberg', 'Aura00': 'Berlin, Heidelberg', 'Stebila11': 'Berlin, Heidelberg',
           'Ding25': 'New York, NY, USA', 'Douceur02': 'Berlin, Heidelberg', 'Ball18': 'Cham', 'Fitzi22': 'Cham',
           'GolleMironov01': 'Berlin, Heidelberg', 'Kondo07': 'Berlin, Heidelberg', 'Groth16': 'Berlin, Heidelberg',
           'Chakraborty22': 'Cham', 'Freivalds77': 'Amsterdam'}

# Defined at first use in the prose; names of datasets, models and targets are left as names.
ACRONYMS = [
    (r'CAPTCHAs?', lambda t: t + ' (Completely Automated Public Turing test' + ('s' if t.endswith('s') else '') + ' to tell Computers and Humans Apart)'),
    (r'AI', lambda t: 'artificial intelligence (AI)'), (r'GPU', lambda t: 'graphics processing unit (GPU)'),
    (r'CPU', lambda t: 'central processing unit (CPU)'), (r'SHA-256', lambda t: 'Secure Hash Algorithm 256 (SHA-256)'),
    (r'HTTP', lambda t: 'Hypertext Transfer Protocol (HTTP)'), (r'ROC-AUC', lambda t: 'area under the receiver operating characteristic curve (ROC-AUC)'),
    (r'EF10', lambda t: 'enrichment factor at 10% (EF10)'), (r'MLP', lambda t: 'multilayer perceptron (MLP)'),
    (r'CNN', lambda t: 'convolutional neural network (CNN)'), (r'BFGS', lambda t: 'Broyden–Fletcher–Goldfarb–Shanno (BFGS)'),
    (r'CDN', lambda t: 'content delivery network (CDN)'), (r'SQL', lambda t: 'Structured Query Language (SQL)'),
    (r'FIFO', lambda t: 'first-in, first-out (FIFO)'), (r'RSA', lambda t: 'Rivest–Shamir–Adleman (RSA)'),
    (r'RFCs?', lambda t: 'Requests for Comments (' + t + ')'), (r'NaN', lambda t: 'not-a-number (NaN)'),
    (r'RNGs?', lambda t: 'random number generator' + ('s' if t.endswith('s') else '') + ' (' + t + ')'),
    (r'BOINC', lambda t: 'Berkeley Open Infrastructure for Network Computing (BOINC)'),
    (r'FP32', lambda t: '32-bit floating-point (FP32)'), (r'INT8', lambda t: '8-bit integer (INT8)'), (r'FP16', lambda t: '16-bit floating-point (FP16)'),
]
HEADINGS = [('## 4 Methodology', '## 4 Materials and Methods'), ('## 7 Conclusion', '## 7 Conclusions'),
            ('## 2 Related work', '## 2 Related Work'), ('## 3 System and threat model', '## 3 System and Threat Model')]


def replace_once(src, edits, loose=False):
    """Apply each edit to exactly one occurrence; loose matching ignores line wrapping."""
    for old, new in edits:
        rx = re.compile(r'\s+'.join(re.escape(w) for w in old.split()) if loose else re.escape(old))
        n = len(rx.findall(src)); assert n == 1, (old[:70], n); src = rx.sub(lambda m: new, src)
    return src


def define_acronyms(md):
    """Expand each acronym at its first occurrence in prose (not in tables,
    captions, LaTeX blocks, citation keys or URLs)."""
    lines = md.split('\n'); in_latex = False; prose = []
    for i, line in enumerate(lines):
        if line.startswith('```'): in_latex = not in_latex; continue
        if not in_latex and not line.startswith(('|', 'Table:', '#')): prose.append(i)
    done = []
    for pattern, full in ACRONYMS:
        rx = re.compile(r'(?<![\w\[/.-])' + pattern + r'(?![\w\]-])')
        for i in prose:
            masked = re.sub(r'\[[A-Za-z0-9, ]+\]|https?://\S+', lambda m: '\0' * len(m.group(0)), lines[i])
            m = rx.search(masked)
            if m and lines[i][max(0, m.start() - 1):m.start()] == '(' and lines[i][m.end():m.end() + 1] == ')':
                break   # already defined by an explicit edit, e.g. "... Adleman (RSA)"
            if m:
                lines[i] = lines[i][:m.start()] + full(m.group(0)) + lines[i][m.end():]; done.append(m.group(0)); break
    return '\n'.join(lines), done


def manuscript(md, related):
    start = md.index('This is a characterisation study'); end = md.index('We also report where the approach loses.')
    md = md[:start] + FINDINGS + '\n' + md[end:]
    md = replace_once(md, BOOKKEEPING + HEDGES + EDITS, loose=True)
    results = md.split('## 1 Introduction', 1)[1].split('## 4 Methodology', 1)[0] + md.split('## 5 Results', 1)[1].split('## Abbreviations', 1)[0]
    left = re.findall(r'[^.\n]*amendments? \d[^.\n]*', results); assert not left, left
    main_md = md.split('## 1 Introduction', 1)[1].split('## Abbreviations', 1)[0]
    main_md = '## 1 Introduction' + main_md.replace('<!-- include RELATED_WORK -->', replace_once(related, RELATED_EDITS))
    main_md, defined = define_acronyms(replace_once(main_md, HEADINGS))
    words = sum(len(t.split()) for _, t in ABSTRACT); assert 150 <= words <= 250, words
    abstract = ' '.join(r'\textbf{' + h + r':} ' + bm.text(t) for h, t in ABSTRACT)
    tex = ['% Generated by docs/paper/sncs/build_sncs.py from docs/paper/*.md -- do not edit.',
           r'\documentclass[pdflatex,sn-mathphys-num]{sn-jnl}', r'\input{glyphtounicode}', r'\pdfgentounicode=1',
           r'\usepackage{graphicx,booktabs,tabularx,amsmath,amssymb,xcolor,tikz,url}', r'\graphicspath{{../}}',
           r'\let\orcidlogo\undefined', r'\usepackage{orcidlink}',   # sn-jnl's own \orcid needs a logo file the template omits
           r'\renewcommand{\tabularxcolumn}[1]{>{\raggedright\arraybackslash}p{#1}}', r'\usetikzlibrary{arrows.meta,positioning,fit}',
           r'\raggedbottom', r'\begin{document}', r'\title[The Price of Utility]{' + TITLE + '}', AUTHORS,
           r'\abstract{' + abstract + '}', r'\keywords{' + ', '.join(KEYWORDS) + '}', r'\maketitle', '',
           bm.body(main_md), r'\backmatter', DECLARATIONS, r'\bibliography{references-sncs}', r'\end{document}']
    return '\n'.join(tex) + '\n', words, defined


def supplement(sup):
    content = '## ' + replace_once(sup.rstrip('\n') + MAPPING, SUP_EDITS, loose=True).split('\n## ', 1)[1]
    content = re.sub(r'^## S\d+ ', '## ', content, flags=re.M)
    stex = [r'\documentclass[11pt]{article}', r'\usepackage[margin=2.5cm]{geometry}', r'\input{glyphtounicode}', r'\pdfgentounicode=1',
            r'\usepackage{graphicx,booktabs,tabularx,amsmath,amssymb,xcolor,url}', r'\graphicspath{{../}}',
            r'\usepackage[numbers,square,sort&compress]{natbib}', r'\usepackage[hidelinks]{hyperref}',
            r'\renewcommand{\tabularxcolumn}[1]{>{\raggedright\arraybackslash}p{#1}}', r'\newcommand{\botrule}{\bottomrule}',
            r'\providecommand{\bibcommenthead}{}', r'\renewcommand{\thesection}{S\arabic{section}}',
            r'\renewcommand{\thetable}{S\arabic{table}}', r'\renewcommand{\thefigure}{S\arabic{figure}}',
            r'\title{Online Resource 1\\[4pt]\large ' + TITLE + '}', r'\author{' + SUPP_AUTHORS + '}', r'\date{}',
            r'\begin{document}', r'\maketitle', '',
            bm.text('Online Resource 1 for the article above. Section and table numbers prefixed S refer to this file; all others refer to the main text.'),
            '', bm.body(content), r'\bibliographystyle{sn-mathphys-num}', r'\bibliography{references-sncs}', r'\end{document}']
    return '\n'.join(stex) + '\n'


def references(bib):
    bib = replace_once(bib, BIB_FIXES, loose=True)
    for key, place in ADDRESS.items():
        rx = re.compile(r'(@\w+\{' + key + r',)')
        assert len(rx.findall(bib)) == 1, key; bib = rx.sub(lambda m: m.group(1) + '\n  address = {' + place + '},', bib)
    return bib


def main():
    read = lambda name: (PAPER / name).read_text(encoding='utf-8')
    related = re.search(r'^## 2 Related work\n(.*?)(?=^## Claims ledger)', read('RELATED_WORK.md'), re.S | re.M).group(1)
    tex, words, defined = manuscript(read('MANUSCRIPT.md'), related)
    (HERE / 'manuscript-sncs.tex').write_text(tex, encoding='utf-8')
    (HERE / 'supplementary-sncs.tex').write_text(supplement(read('SUPPLEMENTARY.md')), encoding='utf-8')
    (HERE / 'references-sncs.bib').write_text(references(read('references.bib')), encoding='utf-8')
    print('abstract words', words, '| defined at first use:', ', '.join(defined))
    if '--no-pdf' in sys.argv: return
    for name in ('manuscript-sncs', 'supplementary-sncs'):
        r = subprocess.run(['latexmk', '-pdf', '-interaction=nonstopmode', '-halt-on-error', name + '.tex'], cwd=HERE, capture_output=True, text=True)
        log = (HERE / (name + '.log')).read_text(encoding='utf-8', errors='replace')
        undefined = sorted(set(re.findall(r"Citation `([^']+)' .*undefined", log)))
        print(name, 'exit', r.returncode, '| undefined citations:', undefined or 'none', '| overfull:', log.count('Overfull'),
              '| pages:', (re.findall(r'Output written on .*?\((\d+) pages', log) or ['?'])[-1])
        if r.returncode: print(r.stdout[-3000:])


if __name__ == '__main__': main()
