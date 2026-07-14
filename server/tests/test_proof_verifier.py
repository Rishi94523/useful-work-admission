"""
Tests for the proof-of-computation verifier.

Simulates an honest browser client (float32 layer math, like the JS shard
engine) and several classes of cheaters, and checks the verifier's verdicts.
"""

import numpy as np
import pytest

from app.ml.model_store import apply_post_ops, get_model_store
from app.ml.proof_verifier import (
    ProofVerifier,
    canonical_vector_hash,
    compute_proof_hash,
)


@pytest.fixture(scope="module")
def model():
    return get_model_store().get_default()


@pytest.fixture(scope="module")
def cnn_model():
    spec = get_model_store().get("mnist-cnn")
    if spec is None:
        pytest.skip("mnist-cnn not trained (run scripts/train_mnist_cnn_numpy.py)")
    return spec


@pytest.fixture(scope="module")
def quantized_model():
    spec = get_model_store().get("mnist-tiny-q8")
    if spec is None:
        pytest.skip("mnist-tiny-q8 not built (run scripts/quantize_model.py)")
    return spec


@pytest.fixture(scope="module")
def attention_model():
    spec = get_model_store().get("mnist-attn")
    if spec is None:
        pytest.skip("mnist-attn not trained (run scripts/train_mnist_attn_numpy.py)")
    return spec


@pytest.fixture()
def verifier():
    # audit_rate=0 so tests exercise the projection path deterministically
    return ProofVerifier(audit_rate=0.0)


def client_compute(model, x, start, end):
    """
    Simulate the browser client: float32 storage (Float32Array) for float
    layers, exact float64-held integers for quantized layers, post-ops
    applied between layers. Layer-type agnostic — the same path covers
    dense, conv2d, token_dense and attention segments.
    """
    h = np.asarray(x, dtype=np.float32)
    pre_activations = []
    for idx in range(start, end):
        layer = model.layers[idx]
        z = layer.forward(h.astype(np.float64))
        if not getattr(layer, "exact", False):
            z = z.astype(np.float32)
        pre_activations.append([float(v) for v in z])
        h = model.apply_layer_post_ops(
            z.astype(np.float64), idx, layer_input=h
        ).astype(np.float32)
    return pre_activations


def build_proof(model, x, start, end, task_id="task-1", sample_id="sample-1",
                prediction_hash="", verification_nonce=""):
    pre_activations = client_compute(model, x, start, end)
    output_hashes = [canonical_vector_hash(z) for z in pre_activations]
    proof_hash = compute_proof_hash(
        task_id,
        sample_id,
        start,
        len(pre_activations),
        output_hashes,
        prediction_hash,
        verification_nonce,
    )
    return pre_activations, output_hashes, proof_hash


def random_input(seed=3):
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 1, 784).astype(np.float32).tolist()


class TestHonestClient:
    def test_full_model_segment_passes(self, model, verifier):
        x = random_input()
        pre, hashes, proof_hash = build_proof(model, x, 0, 3)
        report = verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert report.valid, report.reason
        assert report.predicted_label in model.labels
        assert report.probabilities is not None
        assert abs(float(report.probabilities.sum()) - 1.0) < 1e-3

    def test_single_layer_segment_passes(self, model, verifier):
        x = random_input()
        pre, hashes, proof_hash = build_proof(model, x, 0, 1)
        report = verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert report.valid, report.reason
        assert report.predicted_label is None  # not final layer
        assert report.final_activation is not None
        assert len(report.final_activation) == 128

    def test_assignment_nonce_is_required(self, model, verifier):
        x = random_input()
        nonce = "assignment-challenge-a"
        pre, hashes, proof_hash = build_proof(
            model, x, 0, 1, verification_nonce=nonce
        )
        accepted = verifier.verify_segment(
            model,
            0,
            x,
            pre,
            hashes,
            proof_hash,
            "task-1",
            "sample-1",
            verification_nonce=nonce,
        )
        rejected = verifier.verify_segment(
            model,
            0,
            x,
            pre,
            hashes,
            proof_hash,
            "task-1",
            "sample-1",
            verification_nonce="assignment-challenge-b",
        )
        assert accepted.valid, accepted.reason
        assert not rejected.valid
        assert rejected.reason == "proof hash mismatch"

    def test_algebraic_challenge_rotates_between_assignments(self, model, verifier):
        """
        Even if an attacker somehow found an error in one task's hidden
        projection nullspace, recomputing the public commitment for a second
        nonce must not make that error reusable.
        """
        x = random_input(seed=41)
        nonce_a = "assignment-algebra-a"
        nonce_b = "assignment-algebra-b"
        pre, _, _ = build_proof(
            model, x, 0, 1, verification_nonce=nonce_a
        )

        projections_a = verifier._layer_projections(
            model, 0, f"task-1:{nonce_a}"
        )
        check_matrix = np.stack([r for r, _, _ in projections_a])
        candidate = np.random.default_rng(42).standard_normal(check_matrix.shape[1])
        correction = check_matrix.T @ np.linalg.solve(
            check_matrix @ check_matrix.T,
            check_matrix @ candidate,
        )
        nullspace_error = candidate - correction
        nullspace_error *= 100.0 / np.linalg.norm(nullspace_error)
        assert np.max(np.abs(check_matrix @ nullspace_error)) < 1e-8

        tampered = [
            [float(value) for value in np.asarray(pre[0]) + nullspace_error]
        ]
        hashes = [canonical_vector_hash(tampered[0])]
        proof_a = compute_proof_hash(
            "task-1", "sample-1", 0, 1, hashes, "", nonce_a
        )
        accepted_for_a = verifier.verify_segment(
            model,
            0,
            x,
            tampered,
            hashes,
            proof_a,
            "task-1",
            "sample-1",
            verification_nonce=nonce_a,
        )
        assert accepted_for_a.valid, accepted_for_a.reason

        # The nonce is public, so model the attacker recomputing the commitment
        # correctly. The hidden equations, not merely the hash, must change.
        proof_b = compute_proof_hash(
            "task-1", "sample-1", 0, 1, hashes, "", nonce_b
        )
        rejected_for_b = verifier.verify_segment(
            model,
            0,
            x,
            tampered,
            hashes,
            proof_b,
            "task-1",
            "sample-1",
            verification_nonce=nonce_b,
        )
        assert not rejected_for_b.valid
        assert "projection" in rejected_for_b.reason

    def test_mid_pipeline_segment_passes(self, model, verifier):
        """Segment starting from a handed-over activation (distributed case)."""
        x = random_input()
        # First contributor computes layer 0
        pre0, h0, p0 = build_proof(model, x, 0, 1)
        report0 = verifier.verify_segment(model, 0, x, pre0, h0, p0, "task-1", "sample-1")
        assert report0.valid

        # Second contributor continues from the stored activation
        handoff = [float(v) for v in report0.final_activation]
        pre1, h1, p1 = build_proof(model, handoff, 1, 3, task_id="task-2")
        report1 = verifier.verify_segment(
            model, 1, handoff, pre1, h1, p1, "task-2", "sample-1"
        )
        assert report1.valid, report1.reason
        assert report1.predicted_label is not None

    def test_pieced_result_matches_direct_inference(self, model, verifier):
        """Distributed segments must piece together to the same label."""
        x = random_input(seed=11)
        direct = model.predict(np.asarray(x, dtype=np.float64))
        direct_label = model.labels[int(np.argmax(direct))]

        activation = x
        report = None
        for start in range(3):
            pre, hashes, ph = build_proof(
                model, activation, start, start + 1, task_id=f"t-{start}"
            )
            report = verifier.verify_segment(
                model, start, activation, pre, hashes, ph, f"t-{start}", "sample-1"
            )
            assert report.valid, report.reason
            activation = [float(v) for v in report.final_activation]

        assert report.predicted_label == direct_label


class TestCheaters:
    def test_fabricated_outputs_fail(self, model, verifier):
        """Client invents plausible-looking outputs without computing."""
        x = random_input()
        rng = np.random.default_rng(99)
        fake_pre = [[float(v) for v in rng.normal(0, 2, 128)]]
        hashes = [canonical_vector_hash(fake_pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            model, 0, x, fake_pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "projection" in report.reason

    def test_tampered_single_value_fails(self, model, verifier):
        """Honest computation with one perturbed output value."""
        x = random_input()
        pre, _, _ = build_proof(model, x, 0, 1)
        pre[0][37] += 0.5  # tamper
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "projection" in report.reason

    def test_wrong_input_fails(self, model, verifier):
        """Client computed on a different input than assigned (precompute attack)."""
        x_assigned = random_input(seed=1)
        x_other = random_input(seed=2)
        pre, hashes, proof_hash = build_proof(model, x_other, 0, 1)
        report = verifier.verify_segment(
            model, 0, x_assigned, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid

    def test_replayed_proof_fails(self, model, verifier):
        """Proof generated for one task replayed against another."""
        x = random_input()
        pre, hashes, proof_hash = build_proof(model, x, 0, 1, task_id="task-A")
        report = verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-B", "sample-1"
        )
        assert not report.valid
        assert "proof hash" in report.reason

    def test_hash_data_mismatch_fails(self, model, verifier):
        """Submitted vectors don't match the committed hashes."""
        x = random_input()
        pre, hashes, proof_hash = build_proof(model, x, 0, 1)
        pre[0][0] += 1.0  # change data but keep old hashes
        report = verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "commitment" in report.reason

    def test_wrong_size_fails(self, model, verifier):
        x = random_input()
        pre = [[0.0] * 64]  # wrong output size for layer 0
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid

    def test_spot_audit_catches_subtle_drift(self, model):
        """
        Small consistent perturbations below projection noise still get
        caught by the full-recompute audit.
        """
        auditing_verifier = ProofVerifier(audit_rate=1.0)
        x = random_input()
        pre, _, _ = build_proof(model, x, 0, 1)
        # nudge every element just above audit tolerance but below projection
        # noise threshold for a single value
        pre[0] = [v + 0.002 for v in pre[0]]
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = auditing_verifier.verify_segment(
            model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid


class TestConvolutionalModel:
    """
    The same projection identity (r·z = (Lᵀr)·x + r·b) must verify
    convolutional work — the proof system is affine-operator-generic.
    """

    def test_honest_full_cnn_passes(self, cnn_model, verifier):
        x = random_input()
        n = cnn_model.total_layers
        pre, hashes, proof_hash = build_proof(cnn_model, x, 0, n)
        report = verifier.verify_segment(
            cnn_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert report.valid, report.reason
        assert report.predicted_label in cnn_model.labels
        assert abs(float(report.probabilities.sum()) - 1.0) < 1e-3

    def test_pieced_cnn_segments_match_direct_inference(self, cnn_model, verifier):
        """Conv + pool handoffs must piece together to the direct label."""
        x = random_input(seed=21)
        direct = cnn_model.predict(np.asarray(x, dtype=np.float64))
        direct_label = cnn_model.labels[int(np.argmax(direct))]

        activation = x
        report = None
        for start in range(cnn_model.total_layers):
            pre, hashes, ph = build_proof(
                cnn_model, activation, start, start + 1, task_id=f"t-{start}"
            )
            report = verifier.verify_segment(
                cnn_model, start, activation, pre, hashes, ph, f"t-{start}", "sample-1"
            )
            assert report.valid, report.reason
            activation = [float(v) for v in report.final_activation]

        assert report.predicted_label == direct_label

    def test_real_mnist_sample_labels_correctly(self, cnn_model, verifier):
        """A real digit through the verified distributed path."""
        import gzip
        import struct as struct_mod
        from pathlib import Path

        images_path = (
            Path(__file__).resolve().parents[2]
            / "data" / "mnist" / "t10k-images-idx3-ubyte.gz"
        )
        labels_path = images_path.parent / "t10k-labels-idx1-ubyte.gz"
        if not images_path.exists():
            pytest.skip("MNIST test data not downloaded")
        with gzip.open(images_path, "rb") as f:
            f.read(16)
            pixels = np.frombuffer(f.read(784), dtype=np.uint8)
        with gzip.open(labels_path, "rb") as f:
            f.read(8)
            true_label = str(np.frombuffer(f.read(1), dtype=np.uint8)[0])

        x = (pixels.astype(np.float32) / 255.0).tolist()
        n = cnn_model.total_layers
        pre, hashes, proof_hash = build_proof(cnn_model, x, 0, n)
        report = verifier.verify_segment(
            cnn_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert report.valid, report.reason
        assert report.predicted_label == true_label

    def test_tampered_conv_output_fails(self, cnn_model, verifier):
        x = random_input()
        pre, _, _ = build_proof(cnn_model, x, 0, 1)
        pre[0][1234] += 0.5  # tamper one conv output pixel
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            cnn_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "projection" in report.reason

    def test_fabricated_conv_outputs_fail(self, cnn_model, verifier):
        x = random_input()
        rng = np.random.default_rng(123)
        fake_pre = [[float(v) for v in rng.normal(0, 1, cnn_model.layers[0].output_size)]]
        hashes = [canonical_vector_hash(fake_pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            cnn_model, 0, x, fake_pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "projection" in report.reason

    def test_conv_wrong_input_fails(self, cnn_model, verifier):
        x_assigned = random_input(seed=5)
        x_other = random_input(seed=6)
        pre, hashes, proof_hash = build_proof(cnn_model, x_other, 0, 1)
        report = verifier.verify_segment(
            cnn_model, 0, x_assigned, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid

    def test_conv_spot_audit_catches_subtle_drift(self, cnn_model):
        auditing_verifier = ProofVerifier(audit_rate=1.0)
        x = random_input()
        pre, _, _ = build_proof(cnn_model, x, 0, 1)
        pre[0] = [v + 0.002 for v in pre[0]]
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = auditing_verifier.verify_segment(
            cnn_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid


def random_int_input(seed=3):
    rng = np.random.default_rng(seed)
    return [float(v) for v in rng.integers(0, 256, 784)]


class TestQuantizedExactVerification:
    """
    Quantized layers verify with Freivalds over Z_p — EXACT equality, zero
    float tolerance, soundness error 1/p per projection, no audits needed.
    """

    def test_honest_full_model_passes_exactly(self, quantized_model, verifier):
        x = random_int_input()
        n = quantized_model.total_layers
        pre, hashes, proof_hash = build_proof(quantized_model, x, 0, n)
        report = verifier.verify_segment(
            quantized_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert report.valid, report.reason
        assert not report.audited  # exact checks make audits unnecessary
        assert report.predicted_label in quantized_model.labels

    def test_pieced_quantized_matches_direct(self, quantized_model, verifier):
        x = random_int_input(seed=13)
        direct = quantized_model.predict(np.asarray(x, dtype=np.float64))
        direct_label = quantized_model.labels[int(np.argmax(direct))]

        activation = x
        report = None
        for start in range(quantized_model.total_layers):
            pre, hashes, ph = build_proof(
                quantized_model, activation, start, start + 1, task_id=f"t-{start}"
            )
            report = verifier.verify_segment(
                quantized_model, start, activation, pre, hashes, ph,
                f"t-{start}", "sample-1",
            )
            assert report.valid, report.reason
            activation = [float(v) for v in report.final_activation]

        assert report.predicted_label == direct_label

    def test_off_by_one_integer_tamper_caught(self, quantized_model, verifier):
        """A ±1 change in ONE integer output is caught with certainty-level
        probability — there is no tolerance band to hide inside."""
        x = random_int_input()
        pre, _, _ = build_proof(quantized_model, x, 0, 1)
        pre[0][37] += 1.0
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            quantized_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "exact projection" in report.reason

    def test_fractional_tamper_rejected_structurally(self, quantized_model, verifier):
        """Sub-integer drift (the float-model attack surface) is impossible:
        non-integer outputs are rejected outright."""
        x = random_int_input()
        pre, _, _ = build_proof(quantized_model, x, 0, 1)
        pre[0][37] += 0.001
        hashes = [canonical_vector_hash(pre[0])]
        proof_hash = compute_proof_hash("task-1", "sample-1", 0, 1, hashes, "")
        report = verifier.verify_segment(
            quantized_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert not report.valid
        assert "non-integer" in report.reason

    def test_quantized_accuracy_close_to_float(self, quantized_model, model):
        q_acc = quantized_model.metrics.get("test_accuracy")
        f_acc = model.metrics.get("test_accuracy")
        assert q_acc is not None and f_acc is not None
        assert abs(f_acc - q_acc) < 0.005  # <0.5pp quantization loss


class TestAttentionVerification:
    """
    Attention blocks verify via affine checks (Q, K, V, Z) plus Freivalds
    matrix-product checks (S = Q·Kᵀ, O = softmax(S)·V) with the softmax
    replayed server-side — the path that scales to transformer/LLM blocks.
    """

    def test_honest_full_model_passes(self, attention_model, verifier):
        x = random_input()
        n = attention_model.total_layers
        pre, hashes, proof_hash = build_proof(attention_model, x, 0, n)
        report = verifier.verify_segment(
            attention_model, 0, x, pre, hashes, proof_hash, "task-1", "sample-1"
        )
        assert report.valid, report.reason
        assert report.predicted_label in attention_model.labels

    def test_pieced_attention_matches_direct(self, attention_model, verifier):
        x = random_input(seed=31)
        direct = attention_model.predict(np.asarray(x, dtype=np.float64))
        direct_label = attention_model.labels[int(np.argmax(direct))]

        activation = x
        report = None
        for start in range(attention_model.total_layers):
            pre, hashes, ph = build_proof(
                attention_model, activation, start, start + 1, task_id=f"t-{start}"
            )
            report = verifier.verify_segment(
                attention_model, start, activation, pre, hashes, ph,
                f"t-{start}", "sample-1",
            )
            assert report.valid, report.reason
            activation = [float(v) for v in report.final_activation]

        assert report.predicted_label == direct_label

    @pytest.mark.parametrize("block", ["Q", "K", "V", "S", "O", "Z"])
    def test_tampered_attention_block_caught(self, attention_model, verifier, block):
        x = random_input()
        attn_index = next(
            i for i, l in enumerate(attention_model.layers)
            if l.layer_type == "attention"
        )
        handoff = x
        for i in range(attn_index):
            _, h = attention_model.forward_segment(
                np.asarray(handoff, dtype=np.float64), i, i + 1
            )
            handoff = [float(v) for v in h]

        layer = attention_model.layers[attn_index]
        pre, _, _ = build_proof(attention_model, handoff, attn_index, attn_index + 1)
        start_off, _ = layer.offsets()[block]
        pre[0][start_off + 3] += 1.0
        hashes = [canonical_vector_hash(pre[0])]
        ph = compute_proof_hash("task-1", "sample-1", attn_index, 1, hashes, "")
        report = verifier.verify_segment(
            attention_model, attn_index, handoff, pre, hashes, ph,
            "task-1", "sample-1",
        )
        assert not report.valid
        assert "attention" in report.reason

    def test_skipped_softmax_caught(self, attention_model, verifier):
        """A client that outputs O = S·V (forgetting the softmax) fails the
        output product check even though Q, K, V, S are all honest."""
        x = random_input()
        attn_index = next(
            i for i, l in enumerate(attention_model.layers)
            if l.layer_type == "attention"
        )
        handoff = x
        for i in range(attn_index):
            _, h = attention_model.forward_segment(
                np.asarray(handoff, dtype=np.float64), i, i + 1
            )
            handoff = [float(v) for v in h]

        layer = attention_model.layers[attn_index]
        z = layer.forward(np.asarray(handoff, dtype=np.float64))
        parts = layer.extract(z)
        fake_o = parts["S"] @ parts["V"]
        offs = layer.offsets()
        z[offs["O"][0] : offs["O"][1]] = fake_o.reshape(-1)
        z[offs["Z"][0] : offs["Z"][1]] = (
            fake_o @ layer.wo.astype(np.float64)
        ).reshape(-1)
        pre = [[float(v) for v in z.astype(np.float32)]]
        hashes = [canonical_vector_hash(pre[0])]
        ph = compute_proof_hash("task-1", "sample-1", attn_index, 1, hashes, "")
        report = verifier.verify_segment(
            attention_model, attn_index, handoff, pre, hashes, ph,
            "task-1", "sample-1",
        )
        assert not report.valid
        assert "attention output product" in report.reason


@pytest.fixture(scope="module")
def llm_model():
    spec = get_model_store().get("llm-qwen2-sentiment")
    if spec is None:
        pytest.skip("LLM not imported (run scripts/import_hf_llm.py)")
    return spec


class TestLLMVerification:
    """
    Real Qwen2.5-0.5B blocks verify with the same primitives: GQA attention
    (RoPE folded into projections, per-head product checks, server-side
    masked softmax) and SwiGLU MLP (server-replayed silu gate).
    """

    @pytest.fixture(scope="class")
    def llm_input(self, llm_model):
        text = "Fantastic quality and arrived earlier than expected."
        vec, ctx = llm_model.prepare_input(text.encode("utf-8"))
        return vec, {"pad_len": ctx["pad_len"]}

    def _submit(self, model, verifier, layer_index, x, z, context, task="t"):
        pre = [[float(v) for v in np.asarray(z, dtype=np.float32)]]
        hashes = [canonical_vector_hash(pre[0])]
        ph = compute_proof_hash(task, "s", layer_index, 1, hashes, "")
        return verifier.verify_segment(
            model, layer_index, x, pre, hashes, ph, task, "s", context=context
        )

    def test_honest_attention_unit_passes(self, llm_model, verifier, llm_input):
        vec, ctx = llm_input
        layer = llm_model.layers[0]
        z = layer.forward(np.asarray(vec, dtype=np.float64), pad_len=ctx["pad_len"])
        report = self._submit(llm_model, verifier, 0, vec, z, ctx)
        assert report.valid, report.reason

    def test_honest_mlp_unit_passes(self, llm_model, verifier, llm_input):
        vec, ctx = llm_input
        _, act1 = llm_model.forward_segment(
            np.asarray(vec, dtype=np.float64), 0, 1, pad_len=ctx["pad_len"]
        )
        layer = llm_model.layers[1]
        z = layer.forward(act1, pad_len=ctx["pad_len"])
        report = self._submit(
            llm_model, verifier, 1, [float(v) for v in act1], z, ctx
        )
        assert report.valid, report.reason

    @pytest.mark.parametrize("block", ["Q", "K", "V", "S", "O", "Z"])
    def test_tampered_attention_block_caught(
        self, llm_model, verifier, llm_input, block
    ):
        vec, ctx = llm_input
        layer = llm_model.layers[0]
        z = layer.forward(np.asarray(vec, dtype=np.float64), pad_len=ctx["pad_len"])
        z = z.copy()
        z[layer.offsets()[block][0] + 5] += 1.0
        report = self._submit(llm_model, verifier, 0, vec, z, ctx, task="cheat")
        assert not report.valid

    def test_skipped_silu_gate_caught(self, llm_model, verifier, llm_input):
        """D computed from plain G⊙U instead of silu(G)⊙U must fail."""
        from app.ml.llm_layers import SwigluMlpLayer

        vec, ctx = llm_input
        _, act1 = llm_model.forward_segment(
            np.asarray(vec, dtype=np.float64), 0, 1, pad_len=ctx["pad_len"]
        )
        layer: SwigluMlpLayer = llm_model.layers[1]
        z = layer.forward(act1, pad_len=ctx["pad_len"]).copy()
        parts = layer.extract(z)
        fake_d = (parts["G"] * parts["U"]) @ layer.dequant("d").astype(np.float64).T
        offs = layer.offsets()
        z[offs["D"][0] : offs["D"][1]] = fake_d.reshape(-1)
        report = self._submit(
            llm_model, verifier, 1, [float(v) for v in act1], z, ctx, task="cheat"
        )
        assert not report.valid
        assert "swiglu D" in report.reason

    def test_candidate_head_verifies_and_labels(self, llm_model, verifier, llm_input):
        vec, ctx = llm_input
        n = llm_model.total_layers
        _, act = llm_model.forward_segment(
            np.asarray(vec, dtype=np.float64), 0, n - 1, pad_len=ctx["pad_len"]
        )
        layer = llm_model.layers[n - 1]
        z = layer.forward(act)
        report = self._submit(
            llm_model, verifier, n - 1, [float(v) for v in act], z, ctx
        )
        assert report.valid, report.reason
        assert report.predicted_label == "positive"


class TestVerificationCost:
    def test_projection_check_is_cheaper_than_recompute(self, model):
        """
        The point of the design: verification work should be much smaller
        than the client's computation. Compare op counts.
        """
        client_ops = sum(l.compute_ops for l in model.layers)
        verify_ops = sum(
            l.projection_ops * 4  # NUM_PROJECTIONS
            for l in model.layers
        )
        assert verify_ops * 10 < client_ops  # >10x asymmetry even on a tiny model

    def test_conv_asymmetry_scales_with_channels(self, cnn_model):
        """
        For convolution the client pays O(out × k² × in_ch) while a projection
        check costs O(in + out), so the asymmetry grows with kernel² × channels.
        The 1→8-channel input layer is the worst case (little work per output
        element); each deeper/wider layer must improve on it, and a
        production-sized conv layer must show strong asymmetry.
        """

        def layer_ratio(layer):
            return layer.compute_ops / (layer.projection_ops * 4)

        conv1, conv2 = cnn_model.layers[0], cnn_model.layers[1]
        assert layer_ratio(conv2) > layer_ratio(conv1)

        # Production-scale conv layer (32→64 channels, 16x16): the kind of
        # layer mid-size vision models are made of.
        from app.ml.model_store import Conv2DLayer

        rng = np.random.default_rng(0)
        big = Conv2DLayer(
            index=0,
            name="conv_mid",
            activation="relu",
            in_channels=32,
            out_channels=64,
            kernel=(3, 3),
            input_shape=(32, 16, 16),
            weights=rng.normal(0, 0.1, (64, 32, 3, 3)).astype(np.float32),
            biases=np.zeros(64, dtype=np.float32),
            checksum="",
        )
        assert layer_ratio(big) > 40
