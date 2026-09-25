# Manuscript

Target: *Cybersecurity* (SpringerOpen), Research article.

- `MANUSCRIPT.md` is the source of truth; `RELATED_WORK.md` supplies Section 2.
- `references.bib` holds only fields checked against publisher or primary
  records; unconfirmed fields are omitted.
- `manuscript.tex` is generated. Do not edit it by hand.

Build:

```bash
python scripts/make_paper_figures.py
python scripts/build_manuscript.py --pdf
```

The Springer Nature class `sn-jnl.cls` and style `sn-basic.bst` (template
v3.1, December 2024) are not redistributed here. Download the journal article
template package from Springer Nature's LaTeX author support page and copy
those two files into this folder. Figures and build outputs are regenerated,
not committed.
