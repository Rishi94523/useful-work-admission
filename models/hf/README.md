# Raw Hugging Face LLMs (for distributed-inference PoC)

These are **raw upstream checkpoints**, fetched by `scripts/fetch_hf_llm.py`
and **gitignored** (weights are large; re-fetch instead of committing). They
are *not yet wired* into the pipeline — the conversion/quantization step
(`scripts/import_hf_llm.py`, TODO by Fable 5) turns them into the plug-and-play
`models/<name>/manifest.json` + `weights.npz` format the shard engine serves.

This file is the wiring spec: everything the converter needs to know.

## What's here

| local dir | repo | params | layers | d_model | heads (Q/KV) | head_dim | vocab | attn bias |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `qwen2.5-0.5b-instruct` | Qwen/Qwen2.5-0.5B-Instruct | 0.5B | 24 | 896 | 14 / 2 | 64 | 151936 | **yes (q,k,v)** |
| `smollm2-360m-instruct` | HuggingFaceTB/SmolLM2-360M-Instruct | 360M | 32 | 960 | 15 / 5 | 64 | 49152 | no |

Both: `bfloat16`, SwiGLU MLP (`hidden_act=silu`), RMSNorm, RoPE, GQA,
**tied embeddings** (`tie_word_embeddings=true` → no `lm_head.weight`; the
output projection is `embed_tokens.weight` transposed). Recommend **Qwen2.5**
as the primary PoC target (instruct-tuned, strong for its size); SmolLM2 is
the smaller/faster fallback.

## Tensor layout (safetensors keys)

Non-layer: `model.embed_tokens.weight` [vocab, d], `model.norm.weight` [d].

Per block `model.layers.{i}.`:
- `input_layernorm.weight` [d]                        — RMSNorm (pre-attn)
- `self_attn.q_proj.weight` [d, d] (+`.bias` [d] on Qwen)
- `self_attn.k_proj.weight` [kv, d] (+`.bias` [kv] on Qwen)   kv = n_kv*head_dim
- `self_attn.v_proj.weight` [kv, d] (+`.bias` [kv] on Qwen)
- `self_attn.o_proj.weight` [d, d]
- `post_attention_layernorm.weight` [d]               — RMSNorm (pre-MLP)
- `mlp.gate_proj.weight` [ffn, d]
- `mlp.up_proj.weight`   [ffn, d]
- `mlp.down_proj.weight` [d, ffn]

HF stores linear weights as `[out, in]` — same `(out,in)` convention the shard
engine already uses (`weights[o*inSize+i]`), so the existing dense/int8 wire
flattening applies directly.

## How each op maps to the existing verification primitives

Everything below is **already supported** or is a **server-replayed post-op**
in the same pattern as softmax/relu/maxpool — no new verification math:

- **q/k/v/o/gate/up/down projections** → affine layers. Freivalds
  `r·z = (Wᵀr)·x + r·b` already covers them (bias is optional; Qwen uses it).
  Quantize to int8 → **exact mod-p** verification (see `quantize_model.py`).
- **Attention core (S=QKᵀ, softmax, O=PV)** → the `AttentionLayer` protocol
  already built (`model_store.AttentionLayer`, verified via matrix-product
  Freivalds + server-side softmax). Needs GQA generalization: KV heads are
  repeated to match Q heads (n_rep = n_q/n_kv), causal mask on S.
- **RMSNorm** → new post-op, O(n): `x * w / sqrt(mean(x²)+eps)`. Cheap,
  deterministic, server-replayable. `eps`: Qwen 1e-6, SmolLM2 1e-5.
- **RoPE** → new post-op applied to Q,K before S: a fixed rotation by
  precomputed cos/sin (deterministic per position). `rope_theta`: Qwen 1e6,
  SmolLM2 1e5. Server replays it.
- **SwiGLU** → the elegant case: `down_proj( silu(gate_proj·x) ⊙ (up_proj·x) )`.
  `gate` and `up` are both affine-in-x (verify each), then the elementwise
  product `⊙` of two *already-verified* vectors is an O(n) server-replayed
  post-op; `down_proj` is one more affine check.
- **Residuals** → `residual_input` post-op (already built for mnist-attn).
- **Final logits** → tied: reuse `embed_tokens` as the output matmul (affine).
  For a labeling PoC read only the logits of the candidate answer tokens.

## Suggested block → segment decomposition

One transformer block ≈ these provable units (each a pipeline segment):
`q_proj | k_proj | v_proj` (or fused) → attention core → `o_proj` →
`gate_proj | up_proj` → `down_proj`. ~5–6 verified segments/block; ~24 blocks
(Qwen) or ~32 (SmolLM2) per token. Frame the PoC as a **single forward pass
for classification/labeling** (no autoregressive loop): prompt → read
candidate-token logits → done.

## Provenance

Each dir has `PROVENANCE.json` (repo id, arch, file list, size, fetch time).
Re-fetch anytime: `python scripts/fetch_hf_llm.py --all`.
