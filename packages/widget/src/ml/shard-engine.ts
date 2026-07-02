/**
 * Federated Inference Shard Engine
 *
 * Executes model shards (partial layer-wise computation) for CAPTCHA verification.
 * Replaces simulated proof-of-work with actual ML inference computation.
 */

import type {
  ModelShard,
  ShardTask,
  InferenceProof,
  Prediction,
} from '../types';
import { Config } from '../core/config';
import { hashData } from '../utils/crypto';

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
  public readonly postOps: NonNullable<
    ModelShard['layers'][0]['postOps']
  >;

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
  forward(input: ArrayLike<number>): Float32Array | Float64Array {
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
      return input instanceof Float32Array
        ? input
        : Float32Array.from(input as ArrayLike<number>);
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
            out[i] = Math.min(Math.floor((current[i] * mult + half) / divisor), maxVal);
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
            out[i] = current[i] + (layerInput[i] as number);
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
              const idx = (c * height + oy * pool + py) * width + ox * pool + px;
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
    let weightBytes: Uint8Array;
    let biasBytes: Uint8Array;
    if (layer.quantized) {
      // int8 weights + little-endian int32 biases
      weightBytes = new Uint8Array(new Int8Array(layer.weights).buffer);
      biasBytes = new Uint8Array(new Int32Array(layer.biases).buffer);
    } else {
      weightBytes = new Uint8Array(new Float32Array(layer.weights).buffer);
      biasBytes =
        layer.type === 'attention'
          ? new Uint8Array(0)
          : new Uint8Array(new Float32Array(layer.biases).buffer);
    }
    const bytes = new Uint8Array(weightBytes.byteLength + biasBytes.byteLength);
    bytes.set(weightBytes, 0);
    bytes.set(biasBytes, weightBytes.byteLength);
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
      const pre = layer.forward(current);
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
      prediction
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

  private normalizeConfidences(output: Float32Array | Float64Array): Float32Array | Float64Array {
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
      minVal >= 0 &&
      maxVal <= 1 &&
      Math.abs(sum - 1) < 1e-3;

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
    prediction?: Prediction
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

    const proofData = [
      taskId,
      sampleId,
      segmentStart.toString(),
      preActivations.length.toString(),
      ...outputHashes,
      predictionHash,
    ].join(':');

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
  private async hashTensor(tensor: Float32Array | Float64Array): Promise<string> {
    const canonical = Array.from(tensor, (value) => value.toFixed(4)).join(',');
    return await hashData(canonical);
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
