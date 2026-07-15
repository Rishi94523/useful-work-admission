# PoUW CAPTCHA

**Proof-of-Useful-Work CAPTCHA System**

PoUW CAPTCHA replaces traditional puzzle CAPTCHAs with useful browser-side ML
computation. A user contributes a verified segment of inference work, the
server checks that work cheaply, and the completed distributed inference can
feed a human-verified golden dataset.

The product remains centered on compact label-producing models and selective
human auditing. Transformer/LLM execution is an optional stress-test
embodiment, not the default CAPTCHA workload. See
[Product, Paper, and Patent Scope](docs/research/PRODUCT_PAPER_PATENT_SCOPE.md)
for the authoritative distinction. The working Indian filing packet is in
[the provisional self-filing guide](docs/research/INDIA_PROVISIONAL_SELF_FILING.md);
it is an engineering draft, not a filed application or legal opinion.

## Current Implementation

- Browser widget computes assigned shards of a real trained model.
- Backend coordinates distributed inference runs across CAPTCHA sessions.
- Server verifies computation with commitment hashes, secret projection checks,
  and occasional spot audits.
- Human verification can confirm completed labels into the golden dataset.
- The checked-in model is `mnist-tiny`, a dense MNIST classifier.

## Model

The current model lives in `models/mnist-tiny/`:

```text
models/mnist-tiny/
├── manifest.json
└── weights.npz
```

`mnist-tiny` is a dense `784 -> 128 -> 64 -> 10` classifier trained on MNIST.
The manifest pins real SHA-256 checksums for each layer and a model checksum
derived from those layer checksums.

## Runtime Flow

1. Browser calls `POST /api/v1/captcha/init`.
2. Server risk-scores the session and claims the next pipeline segment.
3. Server returns the assigned dense layer shard(s), input activation, labels,
   checksums, and timing expectation.
4. Browser verifies shard checksums and runs the assigned layer segment.
5. Browser submits pre-activation vectors, output commitments, proof hash, and
   timing to `POST /api/v1/captcha/submit`.
6. Server verifies the proof without routinely recomputing the segment.
7. The pipeline stores the verified activation for the next solver, or derives
   the final prediction if the model is complete.
8. Optional human verification contributes to the golden dataset.
9. Server issues a signed CAPTCHA token.

## Project Structure

```text
packages/
├── widget/          # Browser CAPTCHA widget and dense shard executor
└── sdk/             # Vanilla/React/Vue integration helpers
server/
├── app/api/         # FastAPI CAPTCHA, verification, and dashboard endpoints
├── app/core/        # Risk scoring, task assignment, distributed pipeline
├── app/ml/          # Model store and proof verifier
├── app/models/      # SQLAlchemy models
├── app/schemas/     # Pydantic request/response schemas
└── app/services/    # Golden dataset and reputation services
models/
└── mnist-tiny/      # Current trained model and manifest
scripts/            # Training, seeding, retraining, and E2E client scripts
demo/frontend/      # Static demo frontend
docs/               # Architecture and workflow docs
```

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- Redis 7+

PostgreSQL is supported through configuration, but local development defaults
to SQLite.

### Install

```bash
npm install

cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Seed Data

```bash
cd server
.venv\Scripts\python ..\scripts\seed_data.py --count 200
```

### Run Backend

```bash
cd server
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Useful local endpoints:

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Demo: `http://localhost:8000/demo`
- Dashboard: `http://localhost:8000/dashboard`
- Pipeline runs: `http://localhost:8000/api/v1/pipeline/runs`

### Run Widget Dev Server

```bash
npm run dev --workspace=packages/widget
```

### Simulate Solvers

```bash
cd server
.venv\Scripts\python ..\scripts\e2e_client.py --solves 12
```

The E2E client behaves like the browser shard engine: it verifies checksums,
computes assigned dense layer segments, submits pre-activation proofs, and
answers verification prompts.

## API

### Initialize CAPTCHA

```http
POST /api/v1/captcha/init
```

### Submit Computation Proof

```http
POST /api/v1/captcha/submit
```

### Submit Human Verification

```http
POST /api/v1/captcha/verify
```

### Validate Token

```http
GET /api/v1/captcha/validate/{token}
```

## Browser Integration

```html
<script src="/path/to/pouw-captcha.umd.js"></script>
<div id="captcha-container"></div>
<script>
  const captcha = new PoUWCaptcha({
    siteKey: 'pk_demo_1234567890',
    apiUrl: 'http://localhost:8000/api/v1',
    container: '#captcha-container',
    onSuccess: (token) => {
      console.log('CAPTCHA solved:', token);
    },
  });
</script>
```

## Verification Model

The server validates submitted work in three layers:

- Commitment hashes bind each submitted pre-activation vector to the task,
  sample, and model segment.
- Secret projection checks verify dense layer equations at `O(input + output)`
  cost per projection instead of recomputing the client-side `O(input *
  output)` matrix multiply.
- Probabilistic spot audits occasionally recompute the segment to catch
  implementation drift and bound adaptive attacks.

See [docs/CORE_WORKFLOW.md](docs/CORE_WORKFLOW.md) for the full design.

## Tests

```bash
npm test

cd server
.venv\Scripts\pytest
```

## License

MIT
