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
  layerOutputs: Float32Array[];
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
    // Legacy payloads carry only an activation name; treat it as a one-op chain
    this.postOps =
      config.postOps && config.postOps.length > 0
        ? config.postOps
        : config.activation && config.activation !== 'linear'
          ? [{ op: config.activation }]
          : [];
  }

  /**
   * Execute the layer's affine computation (z = L·x + b), returning the RAW
   * pre-activation output. Every provable layer type is affine — dense
   * (matmul) or conv2d (convolution) — which is exactly what lets the server
   * verify z with secret projection checks instead of recomputing it. The
   * post-ops are applied separately (and re-applied server-side) before
   * feeding the next layer.
   */
  forward(input: Float32Array): Float32Array {
    const startTime = performance.now();
    let output: Float32Array;

    switch (this.type) {
      case 'conv2d':
        output = this.conv2dForward(input);
        break;
      case 'dense':
      case 'fully_connected':
        output = this.denseForward(input);
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
  private conv2dForward(input: Float32Array): Float32Array {
    const [inChannels, inHeight, inWidth] = this.inputShape;
    const [outChannels, outHeight, outWidth] = this.outputShape;
    const kh = this.kernel?.[0] ?? inHeight - outHeight + 1;
    const kw = this.kernel?.[1] ?? inWidth - outWidth + 1;

    const output = new Float32Array(outChannels * outHeight * outWidth);

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
  private denseForward(input: Float32Array): Float32Array {
    const inputSize = this.inputShape[this.inputShape.length - 1];
    const outputSize = this.outputShape[this.outputShape.length - 1];
    const output = new Float32Array(outputSize);

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
   * Apply the layer's post-op chain (activation, pooling, flatten) to its
   * pre-activation output. Cheap O(n) ops, mirrored exactly server-side.
   */
  applyPostOps(data: Float32Array): Float32Array {
    let current = data;
    for (const op of this.postOps) {
      switch (op.op) {
        case 'relu':
          current = current.map((x) => Math.max(0, x));
          break;
        case 'softmax':
          current = this.softmax(current);
          break;
        case 'sigmoid':
          current = current.map((x) => 1 / (1 + Math.exp(-x)));
          break;
        case 'tanh':
          current = current.map((x) => Math.tanh(x));
          break;
        case 'maxpool2d':
          current = this.maxPool2d(current, op.shape ?? [], op.pool ?? 2);
          break;
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
    data: Float32Array,
    shape: number[],
    pool: number
  ): Float32Array {
    const [channels, height, width] = shape;
    const outHeight = Math.floor(height / pool);
    const outWidth = Math.floor(width / pool);
    const output = new Float32Array(channels * outHeight * outWidth);

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
  private softmax(data: Float32Array): Float32Array {
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
    const weights = new Float32Array(layer.weights);
    const biases = new Float32Array(layer.biases);
    const bytes = new Uint8Array(weights.byteLength + biases.byteLength);
    bytes.set(new Uint8Array(weights.buffer), 0);
    bytes.set(new Uint8Array(biases.buffer), weights.byteLength);
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
    const preActivations: Float32Array[] = [];
    const layerTimes: number[] = [];
    let current = input;

    for (let i = 0; i < this.layers.length; i++) {
      const layer = this.layers[i];
      this.config.debug(
        `Executing layer ${i + 1}/${this.layers.length}: ${layer.name}`
      );

      const layerStartTime = performance.now();
      const pre = layer.forward(current);
      current = layer.applyPostOps(pre);
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
    output: Float32Array,
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

  private normalizeConfidences(output: Float32Array): Float32Array {
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
    preActivations: Float32Array[],
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
  private async hashTensor(tensor: Float32Array): Promise<string> {
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
