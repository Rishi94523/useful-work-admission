# Evaluation Artifacts

Run the local evaluator from the repository root:

```bash
cd server
venv\Scripts\python ..\scripts\evaluate_pouw.py --samples 50
```

The script emits:

- `docs/evaluation/latest.json`
- `docs/evaluation/latest.md`

These artifacts are intended for paper, grant, and patent-supporting evidence.
They evaluate the current `mnist-tiny` dense model, distributed segment
correctness, tamper rejection, audit rejection, and verification asymmetry.
