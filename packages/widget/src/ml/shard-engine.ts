/**
 * Federated Inference Shard Engine
 *
 * Executes model shards (partial layer-wise computation) for CAPTCHA verification.
 * Replaces simulated proof-of-work with actual ML inference computation.
 */

import { Config } from '../core/config';
import type {
  ModelShard,
  ShardTask,
  InferenceProof,
  Prediction,
} from '../types';
import { hashData } from '../utils/crypto';

function decodeBase64Bytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Result from executing a model shard
 */
export interface ShardExecutionResult {
  /** Pre-activation outputs for each executed layer (proof material) */
  layerOutputs: (Float32Array | Float64Array)[];
  /** Final prediction; only present when the segment includes the last layer */
  prediction?: Prediction;
  /** Whether this segment completes the model */
  isFinalSegment: boolean;
  /** Proof of computation */
  proof: InferenceProof;
  /** Execution timing */
  timing: {
    totalMs: number;
    layerMs: number[];
  };
}

/**
 * Simple neural network layer implementation for shard execution
 * Uses pure JavaScript for maximum compatibility
 */
class NeuralLayer {
  public readonly name: string;
  public readonly type: string;
  public readonly weights: Float32Array;
  public readonly biases: Float32Array;
  public readonly inputShape: number[];
  public readonly outputShape: number[];
  public readonly activation: string;
  public readonly kernel?: number[];
  public readonly quantized: boolean;
  public readonly seq?: number;
  public readonly dModel?: number;
  public readonly patchify?: { grid: number[]; patch: number[] };
  public readonly scales: Float32Array;
  public readonly inputOps: NonNullable<ModelShard['layers'][0]['inputOps']>;
  public readonly nHeads?: number;
  public readonly nKvHeads?: number;
  public readonly headDim?: number;
  public readonly ropeTheta?: number;
  public readonly ffnDim?: number;
  private readonly int8Weights?: Int8Array;
  public readonly postOps: NonNullable<ModelShard['layers'][0]['postOps']>;

  constructor(config: ModelShard['layers'][0]) {
    this.name = config.name;
    this.type = config.type;
    this.weights = new Float32Array(config.weights);
    this.biases = new Float32Array(config.biases);
    this.inputShape = config.inputShape;
    this.outputShape = config.outputShape;
    this.activation = config.activation;
    this.kernel = config.kernel;
    this.quantized = config.quantized ?? false;
    this.seq = config.seq;
    this.dModel = config.dModel;
    this.patchify = config.patchify;
    this.scales = new Float32Array(config.scales ?? []);
    this.inputOps = config.inputOps ?? [];
    this.nHeads = config.nHeads;
    this.nKvHeads = config.nKvHeads;
    this.headDim = config.headDim;
    this.ropeTheta = config.ropeTheta;
    this.ffnDim = config.ffnDim;
    if (config.weightsB64) {
      const bytes = decodeBase64Bytes(config.weightsB64);
      this.int8Weights = new Int8Array(
        bytes.buffer,
        bytes.byteOffset,
        bytes.byteLength
      );
    }
    // Legacy payloads carry only an activation name; treat it as a one-op chain
    this.postOps =
      config.postOps && config.postOps.length > 0
        ? config.postOps
        : config.activation && config.activation !== 'linear'
          ? [{ op: config.activation }]
          : [];
  }

  /**
   * Execute the layer's affine computation (z = LÂ·x + b), returning the RAW
   * pre-activation output. Every provable layer type is affine â€” dense
   * (matmul) or conv2d (convolution) â€” which is exactly what lets the server
   * verify z with secret projection checks instead of recomputing it. The
   * post-ops are applied separately (and re-applied server-side) before
   * feeding the next layer.
   */
  forward(input: ArrayLike<number>, padLen = 0): Float32Array | Float64Array {
    const startTime = performance.now();
    let output: Float32Array | Float64Array;

    switch (this.type) {
      case 'conv2d':
        output = this.conv2dForward(input);
        break;
      case 'dense':
      case 'fully_connected':
        output = this.denseForward(input);
        break;
      case 'token_dense':
        output = this.tokenDenseForward(input);
        break;
      case 'attention':
        output = this.attentionForward(input);
        break;
      case 'gqa_attention':
        output = this.gqaAttentionForward(input, padLen);
        break;
      case 'swiglu_mlp':
        output = this.swigluForward(input);
        break;
      case 'candidate_logits':
        output = this.candidateLogitsForward(input);
        break;
      default:
        throw new Error(`Unsupported layer type: ${this.type}`);
    }

    const endTime = performance.now();
    this.lastExecutionTime = endTime - startTime;

    return output;
  }

  private lastExecutionTime = 0;

  getExecutionTime(): number {
    return this.lastExecutionTime;
  }

  /**
   * Valid (no padding), stride-1 2D convolution in channel-major (C, H, W)
   * layout, matching the server's wire format exactly:
   * weights[((oc*inCh + ic)*kh + u)*kw + v], tensors flattened (C, H, W).
   */
  private conv2dForward(input: ArrayLike<number>): Float32Array | Float64Array {
    const [inChannels, inHeight, inWidth] = this.inputShape;
    const [outChannels, outHeight, outWidth] = this.outputShape;
    const kh = this.kernel?.[0] ?? inHeight - outHeight + 1;
    const kw = this.kernel?.[1] ?? inWidth - outWidth + 1;

    // Quantized layers produce exact integers that can exceed float32's
    // 2^24 integer range â€” store in Float64Array so nothing rounds.
    const output = this.quantized
      ? new Float64Array(outChannels * outHeight * outWidth)
      : new Float32Array(outChannels * outHeight * outWidth);

    for (let oc = 0; oc < outChannels; oc++) {
      for (let oy = 0; oy < outHeight; oy++) {
        for (let ox = 0; ox < outWidth; ox++) {
          let sum = this.biases[oc];
          for (let ic = 0; ic < inChannels; ic++) {
            for (let u = 0; u < kh; u++) {
              const inRow = (ic * inHeight + oy + u) * inWidth + ox;
              const wRow = ((oc * inChannels + ic) * kh + u) * kw;
              for (let v = 0; v < kw; v++) {
                sum += input[inRow + v] * this.weights[wRow + v];
              }
            }
          }
          output[(oc * outHeight + oy) * outWidth + ox] = sum;
        }
      }
    }

    return output;
  }

  /**
   * Dense/Fully Connected forward pass
   */
  private denseForward(input: ArrayLike<number>): Float32Array | Float64Array {
    const inputSize = this.inputShape[this.inputShape.length - 1];
    const outputSize = this.outputShape[this.outputShape.length - 1];
    const output = this.quantized
      ? new Float64Array(outputSize)
      : new Float32Array(outputSize);

    for (let o = 0; o < outputSize; o++) {
      let sum = this.biases[o];
      for (let i = 0; i < inputSize; i++) {
        sum += input[i] * this.weights[o * inputSize + i];
      }
      output[o] = sum;
    }

    return output;
  }

  /**
   * Per-token dense layer (transformer patch/token embedding): shared
   * weights, per-token bias. Optionally extracts patches from a flat image.
   */
  private tokenDenseForward(input: ArrayLike<number>): Float32Array {
    const [seq, inSize] = this.inputShape;
    const outSize = this.outputShape[this.outputShape.length - 1];
    const tokens = this.extractTokens(input, seq, inSize);
    const output = new Float32Array(seq * outSize);

    for (let t = 0; t < seq; t++) {
      for (let o = 0; o < outSize; o++) {
        let sum = this.biases[t * outSize + o];
        for (let i = 0; i < inSize; i++) {
          sum += tokens[t * inSize + i] * this.weights[o * inSize + i];
        }
        output[t * outSize + o] = sum;
      }
    }
    return output;
  }

  private extractTokens(
    input: ArrayLike<number>,
    seq: number,
    inSize: number
  ): Float32Array {
    if (!this.patchify) {
      return input instanceof Float32Array ? input : Float32Array.from(input);
    }
    const [gy, gx] = this.patchify.grid;
    const [py, px] = this.patchify.patch;
    const width = gx * px;
    const tokens = new Float32Array(seq * inSize);
    for (let ty = 0; ty < gy; ty++) {
      for (let tx = 0; tx < gx; tx++) {
        const t = ty * gx + tx;
        for (let yy = 0; yy < py; yy++) {
          for (let xx = 0; xx < px; xx++) {
            tokens[t * inSize + yy * px + xx] =
              input[(ty * py + yy) * width + tx * px + xx];
          }
        }
      }
    }
    return tokens;
  }

  /**
   * Single-head self-attention. Returns the concatenation [Q|K|V|S|O|Z] the
   * server verifies with affine projections + Freivalds product checks
   * (softmax is replayed server-side). Wire weights are [Wq|Wk|Wv|Wo], each
   * (out, in) row-major.
   */
  private attentionForward(input: ArrayLike<number>): Float32Array {
    const seq = this.seq ?? this.inputShape[0];
    const d = this.dModel ?? this.inputShape[1];
    const dd = d * d;

    const matmulW = (wOffset: number): Float32Array => {
      const out = new Float32Array(seq * d);
      for (let t = 0; t < seq; t++) {
        for (let o = 0; o < d; o++) {
          let sum = 0;
          for (let i = 0; i < d; i++) {
            sum += input[t * d + i] * this.weights[wOffset + o * d + i];
          }
          out[t * d + o] = sum;
        }
      }
      return out;
    };

    const q = matmulW(0);
    const k = matmulW(dd);
    const v = matmulW(2 * dd);

    const s = new Float32Array(seq * seq);
    for (let a = 0; a < seq; a++) {
      for (let b = 0; b < seq; b++) {
        let sum = 0;
        for (let i = 0; i < d; i++) {
          sum += q[a * d + i] * k[b * d + i];
        }
        s[a * seq + b] = sum;
      }
    }

    // rowwise softmax
    const p = new Float64Array(seq * seq);
    for (let a = 0; a < seq; a++) {
      let max = -Infinity;
      for (let b = 0; b < seq; b++) max = Math.max(max, s[a * seq + b]);
      let total = 0;
      for (let b = 0; b < seq; b++) {
        p[a * seq + b] = Math.exp(s[a * seq + b] - max);
        total += p[a * seq + b];
      }
      for (let b = 0; b < seq; b++) p[a * seq + b] /= total;
    }

    const o = new Float32Array(seq * d);
    for (let a = 0; a < seq; a++) {
      for (let i = 0; i < d; i++) {
        let sum = 0;
        for (let b = 0; b < seq; b++) {
          sum += p[a * seq + b] * v[b * d + i];
        }
        o[a * d + i] = sum;
      }
    }

    const z = new Float32Array(seq * d);
    for (let t = 0; t < seq; t++) {
      for (let oIdx = 0; oIdx < d; oIdx++) {
        let sum = 0;
        for (let i = 0; i < d; i++) {
          sum += o[t * d + i] * this.weights[3 * dd + oIdx * d + i];
        }
        z[t * d + oIdx] = sum;
      }
    }

    const concat = new Float32Array(5 * seq * d + seq * seq);
    concat.set(q, 0);
    concat.set(k, seq * d);
    concat.set(v, 2 * seq * d);
    concat.set(s, 3 * seq * d);
    concat.set(o, 3 * seq * d + seq * seq);
    concat.set(z, 4 * seq * d + seq * seq);
    return concat;
  }

  private requireTransformerConfig(): Int8Array {
    if (!this.int8Weights || this.scales.length === 0) {
      throw new Error(`${this.type} requires weightsB64 and scales`);
    }
    return this.int8Weights;
  }

  private dequantizeRows(
    weights: Int8Array,
    weightOffset: number,
    scaleOffset: number,
    rows: number,
    columns: number
  ): Float32Array {
    const matrix = new Float32Array(rows * columns);
    for (let row = 0; row < rows; row++) {
      const scale = this.scales[scaleOffset + row];
      const source = weightOffset + row * columns;
      const target = row * columns;
      for (let column = 0; column < columns; column++) {
        matrix[target + column] = weights[source + column] * scale;
      }
    }
    return matrix;
  }

  private matmulRows(
    input: ArrayLike<number>,
    matrix: Float32Array,
    inputRows: number,
    inputColumns: number,
    outputColumns: number,
    biases?: ArrayLike<number>
  ): Float32Array {
    const output = new Float32Array(inputRows * outputColumns);
    for (let row = 0; row < inputRows; row++) {
      const inputOffset = row * inputColumns;
      for (let out = 0; out < outputColumns; out++) {
        let sum = biases?.[out] ?? 0;
        const matrixOffset = out * inputColumns;
        for (let column = 0; column < inputColumns; column++) {
          sum += input[inputOffset + column] * matrix[matrixOffset + column];
        }
        output[row * outputColumns + out] = sum;
      }
    }
    return output;
  }

  private applyInputOps(input: ArrayLike<number>): Float64Array {
    let current = Float64Array.from(input);
    for (const op of this.inputOps) {
      switch (op.op) {
        case 'last_token': {
          const seq = op.seq ?? 1;
          const dim = op.dim ?? Math.floor(current.length / seq);
          current = current.slice((seq - 1) * dim, seq * dim);
          break;
        }
        case 'rmsnorm': {
          const seq = op.seq ?? 1;
          const dim = Math.floor(current.length / seq);
          const weight = op.weight;
          if (!weight || weight.length !== dim) {
            throw new Error('rmsnorm input-op has an invalid weight vector');
          }
          const eps = op.eps ?? 1e-6;
          const normalized = new Float64Array(current.length);
          for (let row = 0; row < seq; row++) {
            const offset = row * dim;
            let squareSum = 0;
            for (let column = 0; column < dim; column++) {
              const value = current[offset + column];
              squareSum += value * value;
            }
            const inverseRms = 1 / Math.sqrt(squareSum / dim + eps);
            for (let column = 0; column < dim; column++) {
              normalized[offset + column] =
                current[offset + column] * inverseRms * weight[column];
            }
          }
          current = normalized;
          break;
        }
        default:
          throw new Error(`Unsupported input-op: ${op.op}`);
      }
    }
    return current;
  }

  /** Qwen-style grouped-query attention; mirrors scripts/e2e_client.py. */
  private gqaAttentionForward(
    input: ArrayLike<number>,
    padLen: number
  ): Float32Array {
    const weights = this.requireTransformerConfig();
    const seq = this.seq ?? this.inputShape[0];
    const d = this.dModel ?? this.inputShape[1];
    const nHeads = this.nHeads ?? 0;
    const nKvHeads = this.nKvHeads ?? 0;
    const headDim = this.headDim ?? 0;
    if (!nHeads || !nKvHeads || !headDim || nHeads % nKvHeads !== 0) {
      throw new Error('Invalid grouped-query attention dimensions');
    }
    const qDim = nHeads * headDim;
    const kvDim = nKvHeads * headDim;
    let weightOffset = 0;
    let scaleOffset = 0;
    const wq = this.dequantizeRows(weights, weightOffset, scaleOffset, qDim, d);
    weightOffset += qDim * d;
    scaleOffset += qDim;
    const wk = this.dequantizeRows(
      weights,
      weightOffset,
      scaleOffset,
      kvDim,
      d
    );
    weightOffset += kvDim * d;
    scaleOffset += kvDim;
    const wv = this.dequantizeRows(
      weights,
      weightOffset,
      scaleOffset,
      kvDim,
      d
    );
    weightOffset += kvDim * d;
    scaleOffset += kvDim;
    const wo = this.dequantizeRows(weights, weightOffset, scaleOffset, d, qDim);

    const normalized = this.applyInputOps(input);
    const qBase = this.matmulRows(
      normalized,
      wq,
      seq,
      d,
      qDim,
      this.biases.subarray(0, qDim)
    );
    const kBase = this.matmulRows(
      normalized,
      wk,
      seq,
      d,
      kvDim,
      this.biases.subarray(qDim, qDim + kvDim)
    );
    const v = this.matmulRows(
      normalized,
      wv,
      seq,
      d,
      kvDim,
      this.biases.subarray(qDim + kvDim, qDim + 2 * kvDim)
    );

    const q = new Float64Array(qBase.length);
    const k = new Float64Array(kBase.length);
    const half = headDim / 2;
    const theta = this.ropeTheta ?? 10000;
    for (let token = 0; token < seq; token++) {
      for (let head = 0; head < nHeads; head++) {
        const offset = (token * nHeads + head) * headDim;
        for (let column = 0; column < headDim; column++) {
          const frequencyIndex = column < half ? column : column - half;
          const angle =
            token * Math.pow(theta, -(2 * frequencyIndex) / headDim);
          const rotated =
            column < half
              ? -qBase[offset + column + half]
              : qBase[offset + column - half];
          q[offset + column] =
            qBase[offset + column] * Math.cos(angle) +
            rotated * Math.sin(angle);
        }
      }
      for (let head = 0; head < nKvHeads; head++) {
        const offset = (token * nKvHeads + head) * headDim;
        for (let column = 0; column < headDim; column++) {
          const frequencyIndex = column < half ? column : column - half;
          const angle =
            token * Math.pow(theta, -(2 * frequencyIndex) / headDim);
          const rotated =
            column < half
              ? -kBase[offset + column + half]
              : kBase[offset + column - half];
          k[offset + column] =
            kBase[offset + column] * Math.cos(angle) +
            rotated * Math.sin(angle);
        }
      }
    }

    const scores = new Float32Array(nHeads * seq * seq);
    const probabilities = new Float64Array(scores.length);
    const headsPerKv = nHeads / nKvHeads;
    const scale = Math.sqrt(headDim);
    for (let head = 0; head < nHeads; head++) {
      const kvHead = Math.floor(head / headsPerKv);
      for (let row = 0; row < seq; row++) {
        let rowMax = -Infinity;
        for (let column = 0; column < seq; column++) {
          let score = 0;
          for (let dim = 0; dim < headDim; dim++) {
            score +=
              q[(row * nHeads + head) * headDim + dim] *
              k[(column * nKvHeads + kvHead) * headDim + dim];
          }
          const index = (head * seq + row) * seq + column;
          scores[index] = score;
          const allowed = column <= row && (column >= padLen || row < padLen);
          const scaled = allowed ? scores[index] / scale : -1e30;
          probabilities[index] = scaled;
          rowMax = Math.max(rowMax, scaled);
        }
        let total = 0;
        const rowOffset = (head * seq + row) * seq;
        for (let column = 0; column < seq; column++) {
          const value = Math.exp(probabilities[rowOffset + column] - rowMax);
          probabilities[rowOffset + column] = value;
          total += value;
        }
        for (let column = 0; column < seq; column++) {
          probabilities[rowOffset + column] /= total;
        }
      }
    }

    const attention = new Float32Array(seq * qDim);
    for (let row = 0; row < seq; row++) {
      for (let head = 0; head < nHeads; head++) {
        const kvHead = Math.floor(head / headsPerKv);
        const probabilityOffset = (head * seq + row) * seq;
        for (let dim = 0; dim < headDim; dim++) {
          let sum = 0;
          for (let column = 0; column < seq; column++) {
            sum +=
              probabilities[probabilityOffset + column] *
              v[(column * nKvHeads + kvHead) * headDim + dim];
          }
          attention[row * qDim + head * headDim + dim] = sum;
        }
      }
    }
    const z = this.matmulRows(attention, wo, seq, qDim, d);
    const output = new Float32Array(
      q.length +
        k.length +
        v.length +
        scores.length +
        attention.length +
        z.length
    );
    let offset = 0;
    output.set(q, offset);
    offset += q.length;
    output.set(k, offset);
    offset += k.length;
    output.set(v, offset);
    offset += v.length;
    output.set(scores, offset);
    offset += scores.length;
    output.set(attention, offset);
    offset += attention.length;
    output.set(z, offset);
    return output;
  }

  /** Qwen-style SwiGLU MLP; mirrors scripts/e2e_client.py. */
  private swigluForward(input: ArrayLike<number>): Float32Array {
    const weights = this.requireTransformerConfig();
    const seq = this.seq ?? this.inputShape[0];
    const d = this.dModel ?? this.inputShape[1];
    const ffn = this.ffnDim ?? 0;
    if (!ffn) throw new Error('Invalid SwiGLU dimensions');
    const slab = ffn * d;
    const wg = this.dequantizeRows(weights, 0, 0, ffn, d);
    const wu = this.dequantizeRows(weights, slab, ffn, ffn, d);
    const wd = this.dequantizeRows(weights, 2 * slab, 2 * ffn, d, ffn);
    const normalized = this.applyInputOps(input);
    const gate = this.matmulRows(normalized, wg, seq, d, ffn);
    const up = this.matmulRows(normalized, wu, seq, d, ffn);
    const hidden = new Float64Array(seq * ffn);
    for (let i = 0; i < hidden.length; i++) {
      hidden[i] = (gate[i] / (1 + Math.exp(-gate[i]))) * up[i];
    }
    const down = this.matmulRows(hidden, wd, seq, ffn, d);
    const output = new Float32Array(gate.length + up.length + down.length);
    output.set(gate, 0);
    output.set(up, gate.length);
    output.set(down, gate.length + up.length);
    return output;
  }

  private candidateLogitsForward(input: ArrayLike<number>): Float32Array {
    const transformed = this.applyInputOps(input);
    const d = this.dModel ?? transformed.length;
    const labels = this.outputShape[this.outputShape.length - 1];
    return this.matmulRows(transformed, this.weights, 1, d, labels);
  }

  /**
   * Apply the layer's post-op chain (activation, pooling, flatten,
   * requantize, residual, token pooling) to its pre-activation output.
   * Cheap O(n) ops, mirrored exactly server-side. For attention layers the
   * chain operates on the Z sub-block of the [Q|K|V|S|O|Z] concatenation.
   */
  applyPostOps(
    data: Float32Array | Float64Array,
    layerInput?: ArrayLike<number>
  ): Float32Array | Float64Array {
    let current: Float32Array | Float64Array = data;
    if (this.type === 'attention') {
      const seq = this.seq ?? this.inputShape[0];
      const d = this.dModel ?? this.inputShape[1];
      current = current.slice(4 * seq * d + seq * seq) as
        | Float32Array
        | Float64Array;
    } else if (this.type === 'gqa_attention') {
      const seq = this.seq ?? this.inputShape[0];
      const d = this.dModel ?? this.inputShape[1];
      current = current.slice(current.length - seq * d) as Float32Array;
    } else if (this.type === 'swiglu_mlp') {
      const seq = this.seq ?? this.inputShape[0];
      const d = this.dModel ?? this.inputShape[1];
      current = current.slice(current.length - seq * d) as Float32Array;
    }
    for (const op of this.postOps) {
      switch (op.op) {
        case 'relu':
          current = current.map((x) => Math.max(0, x)) as
            | Float32Array
            | Float64Array;
          break;
        case 'softmax':
          current = this.softmax(current);
          break;
        case 'sigmoid':
          current = current.map((x) => 1 / (1 + Math.exp(-x))) as
            | Float32Array
            | Float64Array;
          break;
        case 'tanh':
          current = current.map((x) => Math.tanh(x)) as
            | Float32Array
            | Float64Array;
          break;
        case 'maxpool2d':
          current = this.maxPool2d(current, op.shape ?? [], op.pool ?? 2);
          break;
        case 'requantize': {
          // Exact integer rescale, bit-identical to the server:
          // a = min(max, floor((z*mult + 2^(shift-1)) / 2^shift))
          const mult = op.mult ?? 1;
          const shift = op.shift ?? 0;
          const maxVal = op.max ?? 255;
          const half = Math.pow(2, shift - 1);
          const divisor = Math.pow(2, shift);
          const out = new Float64Array(current.length);
          for (let i = 0; i < current.length; i++) {
            out[i] = Math.min(
              Math.floor((current[i] * mult + half) / divisor),
              maxVal
            );
          }
          current = out;
          break;
        }
        case 'dequantize': {
          const scale = op.scale ?? 1;
          const out = new Float64Array(current.length);
          for (let i = 0; i < current.length; i++) {
            out[i] = current[i] * scale;
          }
          current = out;
          break;
        }
        case 'residual_input': {
          if (!layerInput) {
            throw new Error('residual_input post-op requires the layer input');
          }
          const out = new Float32Array(current.length);
          for (let i = 0; i < current.length; i++) {
            out[i] = current[i] + layerInput[i];
          }
          current = out;
          break;
        }
        case 'mean_pool_tokens': {
          const seq = op.seq ?? 1;
          const dim = op.dim ?? current.length;
          const out = new Float32Array(dim);
          for (let i = 0; i < dim; i++) {
            let sum = 0;
            for (let t = 0; t < seq; t++) {
              sum += current[t * dim + i];
            }
            out[i] = sum / seq;
          }
          current = out;
          break;
        }
        case 'flatten':
        case 'linear':
          break;
        default:
          throw new Error(`Unsupported post-op: ${op.op}`);
      }
    }
    return current;
  }

  /**
   * Apply activation function (legacy single-op path)
   */
  applyActivation(data: Float32Array): Float32Array {
    switch (this.activation) {
      case 'relu':
        return data.map((x) => Math.max(0, x));
      case 'softmax':
        return this.softmax(data);
      case 'sigmoid':
        return data.map((x) => 1 / (1 + Math.exp(-x)));
      case 'tanh':
        return data.map((x) => Math.tanh(x));
      case 'linear':
      default:
        return data;
    }
  }

  /**
   * Channel-major max pooling (floor cropping, matching the server)
   */
  private maxPool2d(
    data: Float32Array | Float64Array,
    shape: number[],
    pool: number
  ): Float32Array | Float64Array {
    const [channels, height, width] = shape;
    const outHeight = Math.floor(height / pool);
    const outWidth = Math.floor(width / pool);
    const output =
      data instanceof Float64Array
        ? new Float64Array(channels * outHeight * outWidth)
        : new Float32Array(channels * outHeight * outWidth);

    for (let c = 0; c < channels; c++) {
      for (let oy = 0; oy < outHeight; oy++) {
        for (let ox = 0; ox < outWidth; ox++) {
          let maxVal = -Infinity;
          for (let py = 0; py < pool; py++) {
            for (let px = 0; px < pool; px++) {
              const idx =
                (c * height + oy * pool + py) * width + ox * pool + px;
              maxVal = Math.max(maxVal, data[idx]);
            }
          }
          output[(c * outHeight + oy) * outWidth + ox] = maxVal;
        }
      }
    }

    return output;
  }

  /**
   * Softmax activation
   */
  private softmax(data: Float32Array | Float64Array): Float32Array {
    let maxVal = data[0];
    for (let i = 1; i < data.length; i++) {
      if (data[i] > maxVal) maxVal = data[i];
    }
    const expData = new Float32Array(data.length);
    let sumExp = 0;
    for (let i = 0; i < data.length; i++) {
      expData[i] = Math.exp(data[i] - maxVal);
      sumExp += expData[i];
    }
    const result = new Float32Array(data.length);
    for (let i = 0; i < data.length; i++) {
      result[i] = expData[i] / sumExp;
    }
    return result;
  }
}

/**
 * Shard Inference Engine
 *
 * Executes partial model computations to prove actual ML work
 */
export class ShardInferenceEngine {
  private config: Config;
  private layers: NeuralLayer[] = [];

  constructor(config: Config) {
    this.config = config;
  }

  /**
   * Load model shards for execution
   */
  loadShards(shards: ModelShard[]): void {
    this.layers = [];
    for (const shard of shards) {
      for (const layerConfig of shard.layers) {
        this.layers.push(new NeuralLayer(layerConfig));
      }
    }
    this.config.debug(`Loaded ${this.layers.length} layers from shards`);
  }

  /**
   * Verify a shard's integrity: SHA-256 over the exact float32 wire bytes
   * (weights then biases) must match the checksum pinned in the model
   * manifest. Rejects tampered or substituted weights before any compute.
   */
  async verifyShardChecksum(shard: ModelShard): Promise<boolean> {
    if (!shard.checksum || !shard.layers.length) {
      return true; // no checksum to verify against
    }
    const layer = shard.layers[0];
    let parts: Uint8Array[];
    if (layer.type === 'gqa_attention' || layer.type === 'swiglu_mlp') {
      if (!layer.weightsB64 || !layer.scales) return false;
      parts = [
        decodeBase64Bytes(layer.weightsB64),
        new Uint8Array(new Float32Array(layer.scales).buffer),
      ];
      if (layer.type === 'gqa_attention') {
        parts.push(new Uint8Array(new Float32Array(layer.biases).buffer));
      }
    } else if (layer.quantized) {
      // int8 weights + little-endian int32 biases
      parts = [
        new Uint8Array(new Int8Array(layer.weights).buffer),
        new Uint8Array(new Int32Array(layer.biases).buffer),
      ];
    } else {
      parts = [new Uint8Array(new Float32Array(layer.weights).buffer)];
      if (layer.type !== 'attention' && layer.type !== 'candidate_logits') {
        parts.push(new Uint8Array(new Float32Array(layer.biases).buffer));
      }
    }
    const bytes = new Uint8Array(
      parts.reduce((length, part) => length + part.byteLength, 0)
    );
    let byteOffset = 0;
    for (const part of parts) {
      bytes.set(part, byteOffset);
      byteOffset += part.byteLength;
    }
    const digest = await crypto.subtle.digest('SHA-256', bytes.buffer);
    const hex = Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
    return hex === shard.checksum;
  }

  /**
   * Execute the assigned segment of model layers on the input activation.
   *
   * In the distributed pipeline the input is either the raw sample (segment
   * start 0) or the verified activation handed over from a previous solver.
   * Produces pre-activation outputs per layer plus a commitment proof the
   * server can verify without re-running the computation.
   */
  async executeShards(task: ShardTask): Promise<ShardExecutionResult> {
    const totalStartTime = performance.now();

    // Integrity check before executing anything
    for (const shard of task.shards) {
      const ok = await this.verifyShardChecksum(shard);
      if (!ok) {
        throw new Error(`Shard ${shard.name} failed checksum verification`);
      }
    }

    // Load shards
    this.loadShards(task.shards);

    // Decode input data
    const input = this.decodeInput(task.inputData, task.inputShape);

    const segmentStart = task.segmentStart ?? 0;
    const totalLayers = task.totalLayers ?? this.layers.length;
    const isFinalSegment = segmentStart + this.layers.length >= totalLayers;

    // Execute layers, keeping pre-activations (proof material) and feeding
    // post-activations forward
    const preActivations: (Float32Array | Float64Array)[] = [];
    const layerTimes: number[] = [];
    let current: Float32Array | Float64Array = input;

    for (let i = 0; i < this.layers.length; i++) {
      const layer = this.layers[i];
      this.config.debug(
        `Executing layer ${i + 1}/${this.layers.length}: ${layer.name}`
      );

      const layerStartTime = performance.now();
      const pre = layer.forward(current, task.padLen ?? 0);
      current = layer.applyPostOps(pre, current);
      const layerEndTime = performance.now();

      preActivations.push(pre);
      layerTimes.push(layerEndTime - layerStartTime);

      if (task.onProgress) {
        task.onProgress((i + 1) / this.layers.length);
      }
    }

    // Prediction only exists when this segment completes the model
    let prediction: Prediction | undefined;
    if (isFinalSegment) {
      prediction = this.generatePrediction(current, task.labels || []);
    }

    const proof = await this.generateProof(
      task.taskId,
      task.sampleId,
      segmentStart,
      preActivations,
      prediction,
      task.verificationNonce
    );

    const totalEndTime = performance.now();

    return {
      layerOutputs: preActivations,
      prediction,
      isFinalSegment,
      proof,
      timing: {
        totalMs: totalEndTime - totalStartTime,
        layerMs: layerTimes,
      },
    };
  }

  /**
   * Decode base64 input data to Float32Array
   */
  private decodeInput(data: string, _shape: number[]): Float32Array {
    // Remove data URL prefix if present
    const base64Data = data.replace(/^data:.*;base64,/, '');

    // Decode base64
    const binaryString = atob(base64Data);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    // Convert to float32 (assuming normalized [0, 1] or [-1, 1] values)
    return new Float32Array(bytes.buffer);
  }

  /**
   * Generate prediction from output logits
   */
  private generatePrediction(
    output: Float32Array | Float64Array,
    labels: string[]
  ): Prediction {
    const probabilities = this.normalizeConfidences(output);
    const useClassificationLabels = labels.length === probabilities.length;

    // Find top prediction
    let maxIdx = 0;
    let maxVal = probabilities[0];
    for (let i = 1; i < probabilities.length; i++) {
      if (probabilities[i] > maxVal) {
        maxVal = probabilities[i];
        maxIdx = i;
      }
    }

    // Get top-k predictions
    const topK: { label: string; confidence: number }[] = [];
    const entries: { val: number; idx: number }[] = [];
    for (let i = 0; i < probabilities.length; i++) {
      entries.push({ val: probabilities[i], idx: i });
    }
    entries.sort((a, b) => b.val - a.val);
    const topEntries = entries.slice(0, Math.min(5, probabilities.length));

    for (let i = 0; i < topEntries.length; i++) {
      const { val, idx } = topEntries[i];
      topK.push({
        label: useClassificationLabels ? labels[idx] : `feature_${idx}`,
        confidence: Math.round(val * 1000) / 1000,
      });
    }

    return {
      label: useClassificationLabels ? labels[maxIdx] : `feature_${maxIdx}`,
      confidence: Math.round(maxVal * 1000) / 1000,
      topK,
    };
  }

  private normalizeConfidences(
    output: Float32Array | Float64Array
  ): Float32Array | Float64Array {
    if (output.length === 0) {
      return output;
    }

    let minVal = output[0];
    let maxVal = output[0];
    let sum = 0;

    for (let i = 0; i < output.length; i++) {
      const value = output[i];
      if (value < minVal) minVal = value;
      if (value > maxVal) maxVal = value;
      sum += value;
    }

    const alreadyProbabilities =
      minVal >= 0 && maxVal <= 1 && Math.abs(sum - 1) < 1e-3;

    if (alreadyProbabilities) {
      return output;
    }

    let maxLogit = output[0];
    for (let i = 1; i < output.length; i++) {
      if (output[i] > maxLogit) {
        maxLogit = output[i];
      }
    }

    const probabilities = new Float32Array(output.length);
    let expSum = 0;

    for (let i = 0; i < output.length; i++) {
      probabilities[i] = Math.exp(output[i] - maxLogit);
      expSum += probabilities[i];
    }

    for (let i = 0; i < probabilities.length; i++) {
      probabilities[i] /= expSum;
    }

    return probabilities;
  }

  /**
   * Generate cryptographic proof of inference computation.
   *
   * Commits to each layer's pre-activation output and binds the commitments
   * to this exact task/sample/segment, so the proof can be neither replayed
   * nor detached from the submitted data.
   */
  private async generateProof(
    taskId: string,
    sampleId: string,
    segmentStart: number,
    preActivations: (Float32Array | Float64Array)[],
    prediction?: Prediction,
    verificationNonce?: string
  ): Promise<InferenceProof> {
    const outputHashes: string[] = [];
    for (const output of preActivations) {
      const hash = await this.hashTensor(output);
      outputHashes.push(hash);
    }

    // Canonical prediction hash with fixed-point formatting (matches the
    // server's :.4f formatting exactly)
    let predictionHash = '';
    if (prediction) {
      const topK = prediction.topK
        .map((item) => `${item.label}:${item.confidence.toFixed(4)}`)
        .join(',');
      const payload = [
        prediction.label,
        prediction.confidence.toFixed(4),
        topK,
      ].join('|');
      predictionHash = await hashData(payload);
    }

    const proofParts = [
      taskId,
      sampleId,
      segmentStart.toString(),
      preActivations.length.toString(),
      ...outputHashes,
      predictionHash,
    ];
    if (verificationNonce) proofParts.push(verificationNonce);
    const proofData = proofParts.join(':');

    const proofHash = await hashData(proofData);

    return {
      taskId,
      sampleId,
      segmentStart,
      layerCount: preActivations.length,
      preActivations: preActivations.map((pre) => Array.from(pre)),
      outputHashes,
      predictionHash,
      proofHash,
      timestamp: Date.now(),
    };
  }

  /**
   * Hash a tensor (Float32Array)
   */
  private async hashTensor(
    tensor: Float32Array | Float64Array
  ): Promise<string> {
    const bytes = new ArrayBuffer(tensor.length * 8);
    const view = new DataView(bytes);
    for (let i = 0; i < tensor.length; i++) {
      const value = tensor[i] === 0 ? 0 : tensor[i];
      view.setFloat64(i * 8, value, true);
    }
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this.layers = [];
  }
}

/**
 * Utility to check if shard engine is supported
 */
export function isShardEngineSupported(): boolean {
  return (
    typeof Float32Array !== 'undefined' &&
    typeof atob !== 'undefined' &&
    typeof crypto !== 'undefined' &&
    typeof crypto.subtle !== 'undefined'
  );
}
