/**
 * Tests for Shard Inference Engine
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { Config } from '../src/core/config';
import {
  ShardInferenceEngine,
  isShardEngineSupported,
} from '../src/ml/shard-engine';
import type { ShardTask, ModelShard, NeuralLayerConfig } from '../src/types';

function encodeFloat32(values: number[]): string {
  const bytes = new Uint8Array(new Float32Array(values).buffer);
  return btoa(String.fromCharCode(...bytes));
}

function encodeInt8(values: number[]): string {
  const bytes = new Uint8Array(new Int8Array(values).buffer);
  return btoa(String.fromCharCode(...bytes));
}

describe('ShardInferenceEngine', () => {
  let engine: ShardInferenceEngine;
  let mockConfig: Config;

  beforeEach(() => {
    mockConfig = new Config({
      siteKey: 'test-key',
      apiUrl: 'http://localhost:8000/api/v1',
      container: document.createElement('div'),
      debug: false,
    });
    engine = new ShardInferenceEngine(mockConfig);
  });

  describe('isShardEngineSupported', () => {
    it('should return true when required APIs are available', () => {
      expect(isShardEngineSupported()).toBe(true);
    });
  });

  describe('executeShards', () => {
    it('should execute a simple dense layer shard', async () => {
      const layerConfig: NeuralLayerConfig = {
        name: 'dense_1',
        type: 'dense',
        weights: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        biases: [0.1, 0.1],
        inputShape: [1, 4],
        outputShape: [1, 2],
        activation: 'relu',
      };

      const shard: ModelShard = {
        index: 0,
        name: 'shard_0',
        layerType: 'dense',
        inputShape: [1, 4],
        outputShape: [1, 2],
        layers: [layerConfig],
      };

      const task: ShardTask = {
        taskId: 'test-task-1',
        sampleId: 'sample-1',
        modelName: 'test-model',
        modelVersion: '1.0',
        shards: [shard],
        inputData: btoa(
          String.fromCharCode(
            ...new Uint8Array(new Float32Array([1, 2, 3, 4]).buffer)
          )
        ),
        inputShape: [1, 4],
        expectedLayers: 1,
        difficulty: 'easy',
        expectedTimeMs: 100,
        groundTruthKey: 'gt-key',
        labels: ['zero', 'one', 'two', 'three'],
      };

      const result = await engine.executeShards(task);

      expect(result).toHaveProperty('layerOutputs');
      expect(result).toHaveProperty('prediction');
      expect(result).toHaveProperty('proof');
      expect(result).toHaveProperty('timing');
      expect(result.layerOutputs).toHaveLength(1);
      expect(result.prediction).toHaveProperty('label');
      expect(result.proof).toHaveProperty('proofHash');
    });

    it('should handle multiple layers', async () => {
      const layers: NeuralLayerConfig[] = [
        {
          name: 'dense_1',
          type: 'dense',
          weights: new Array(784 * 128).fill(0.01),
          biases: new Array(128).fill(0.1),
          inputShape: [1, 784],
          outputShape: [1, 128],
          activation: 'relu',
        },
        {
          name: 'dense_2',
          type: 'dense',
          weights: new Array(128 * 10).fill(0.01),
          biases: new Array(10).fill(0.1),
          inputShape: [1, 128],
          outputShape: [1, 10],
          activation: 'softmax',
        },
      ];

      const shard: ModelShard = {
        index: 0,
        name: 'full_model',
        layerType: 'dense',
        inputShape: [1, 784],
        outputShape: [1, 10],
        layers,
      };

      const task: ShardTask = {
        taskId: 'test-task-2',
        sampleId: 'sample-2',
        modelName: 'mnist-tiny',
        modelVersion: '1.0',
        shards: [shard],
        inputData: btoa(
          String.fromCharCode(
            ...new Uint8Array(new Float32Array(784).fill(0.5).buffer)
          )
        ),
        inputShape: [1, 784],
        expectedLayers: 2,
        difficulty: 'medium',
        expectedTimeMs: 500,
        groundTruthKey: 'gt-key-2',
        labels: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
      };

      const result = await engine.executeShards(task);

      expect(result.layerOutputs).toHaveLength(2);
      expect(result.prediction!.topK).toHaveLength(5);
    });

    it('should call progress callback', async () => {
      const progressCallback = vi.fn();

      const layer: NeuralLayerConfig = {
        name: 'dense_1',
        type: 'dense',
        weights: [0.1, 0.2, 0.3, 0.4],
        biases: [0.1, 0.1],
        inputShape: [1, 2],
        outputShape: [1, 2],
        activation: 'relu',
      };

      const shard: ModelShard = {
        index: 0,
        name: 'shard_0',
        layerType: 'dense',
        inputShape: [1, 2],
        outputShape: [1, 2],
        layers: [layer],
      };

      const task: ShardTask = {
        taskId: 'test-task-3',
        sampleId: 'sample-3',
        modelName: 'test',
        modelVersion: '1.0',
        shards: [shard],
        inputData: btoa(
          String.fromCharCode(
            ...new Uint8Array(new Float32Array([1, 2]).buffer)
          )
        ),
        inputShape: [1, 2],
        expectedLayers: 1,
        difficulty: 'easy',
        expectedTimeMs: 50,
        groundTruthKey: 'gt-key',
        labels: ['a', 'b'],
        onProgress: progressCallback,
      };

      await engine.executeShards(task);

      expect(progressCallback).toHaveBeenCalledWith(1);
    });

    it('executes grouped-query attention payloads from the server', async () => {
      const identity = [1, 0, 0, 1];
      const layer: NeuralLayerConfig = {
        name: 'tiny_gqa',
        type: 'gqa_attention',
        weights: [],
        weightsB64: encodeInt8([
          ...identity,
          ...identity,
          ...identity,
          ...identity,
        ]),
        scales: Array<number>(8).fill(1),
        biases: Array<number>(6).fill(0),
        inputShape: [2, 2],
        outputShape: [24],
        activation: 'linear',
        seq: 2,
        dModel: 2,
        nHeads: 1,
        nKvHeads: 1,
        headDim: 2,
        ropeTheta: 10000,
        inputOps: [],
        postOps: [{ op: 'residual_input' }],
      };
      const task: ShardTask = {
        taskId: 'gqa-task',
        sampleId: 'gqa-sample',
        modelName: 'tiny-transformer',
        modelVersion: '1',
        shards: [
          {
            index: 0,
            name: 'tiny_gqa',
            layerType: 'gqa_attention',
            inputShape: [2, 2],
            outputShape: [24],
            layers: [layer],
          },
        ],
        inputData: encodeFloat32([1, 0, 0, 1]),
        inputShape: [2, 2],
        expectedLayers: 1,
        totalLayers: 2,
        difficulty: 'normal',
        expectedTimeMs: 100,
        labels: ['negative', 'positive'],
        padLen: 0,
      };

      const result = await engine.executeShards(task);
      const proofValues = result.layerOutputs[0];
      expect(proofValues).toHaveLength(24);
      expect(Array.from(proofValues).every(Number.isFinite)).toBe(true);
      // Z is the final seq*d block and identity Wo preserves token 0.
      expect(proofValues[20]).toBeCloseTo(1, 5);
      expect(proofValues[21]).toBeCloseTo(0, 5);
      expect(result.isFinalSegment).toBe(false);
    });

    it('keeps GQA output partials in custody until all head groups finish', async () => {
      const identity = [1, 0, 0, 1];
      const makeChunk = (chunkIndex: number): NeuralLayerConfig => ({
        name: `tiny_gqa_part_${chunkIndex}`,
        type: 'gqa_attention_chunk',
        weights: [],
        weightsB64: encodeInt8([
          ...identity,
          ...identity,
          ...identity,
          ...identity,
        ]),
        scales: Array<number>(8).fill(1),
        biases: Array<number>(6).fill(0),
        inputShape: [1, chunkIndex === 0 ? 2 : 4],
        outputShape: [11],
        activation: 'linear',
        seq: 1,
        dModel: 2,
        nHeads: 1,
        nKvHeads: 1,
        headDim: 2,
        ropeTheta: 10000,
        chunkIndex,
        chunkCount: 2,
        inputOps: [],
        postOps: chunkIndex === 1 ? [{ op: 'residual_input' }] : [],
      });
      const head: NeuralLayerConfig = {
        name: 'identity_after_gqa',
        type: 'dense',
        weights: [1, 0, 0, 1],
        biases: [0, 0],
        inputShape: [1, 2],
        outputShape: [1, 2],
        activation: 'softmax',
      };
      const layers = [makeChunk(0), makeChunk(1), head];
      const task: ShardTask = {
        taskId: 'gqa-custody-task',
        sampleId: 'gqa-custody-sample',
        modelName: 'tiny-transformer',
        modelVersion: '1+gqa2',
        shards: layers.map((layer, index) => ({
          index,
          name: layer.name,
          layerType: layer.type,
          inputShape: layer.inputShape,
          outputShape: layer.outputShape,
          layers: [layer],
        })),
        inputData: encodeFloat32([1, 2]),
        inputShape: [1, 2],
        expectedLayers: 3,
        totalLayers: 3,
        difficulty: 'normal',
        expectedTimeMs: 100,
        labels: ['negative', 'positive'],
      };

      const result = await engine.executeShards(task);
      expect(result.layerOutputs[0]).toHaveLength(11);
      expect(result.layerOutputs[1]).toHaveLength(11);
      expect(result.layerOutputs[2][0]).toBeCloseTo(3, 5);
      expect(result.layerOutputs[2][1]).toBeCloseTo(6, 5);
    });

    it('executes SwiGLU payloads and returns G, U, and D proof blocks', async () => {
      const identity = [1, 0, 0, 1];
      const layer: NeuralLayerConfig = {
        name: 'tiny_mlp',
        type: 'swiglu_mlp',
        weights: [],
        weightsB64: encodeInt8([...identity, ...identity, ...identity]),
        scales: Array<number>(6).fill(1),
        biases: [],
        inputShape: [1, 2],
        outputShape: [6],
        activation: 'linear',
        seq: 1,
        dModel: 2,
        ffnDim: 2,
        inputOps: [],
        postOps: [{ op: 'residual_input' }],
      };
      const task: ShardTask = {
        taskId: 'mlp-task',
        sampleId: 'mlp-sample',
        modelName: 'tiny-transformer',
        modelVersion: '1',
        shards: [
          {
            index: 1,
            name: 'tiny_mlp',
            layerType: 'swiglu_mlp',
            inputShape: [1, 2],
            outputShape: [6],
            layers: [layer],
          },
        ],
        inputData: encodeFloat32([1, 2]),
        inputShape: [1, 2],
        segmentStart: 1,
        expectedLayers: 1,
        totalLayers: 3,
        difficulty: 'normal',
        expectedTimeMs: 100,
        labels: ['negative', 'positive'],
      };

      const result = await engine.executeShards(task);
      const proofValues = result.layerOutputs[0];
      expect(proofValues).toHaveLength(6);
      expect(proofValues[0]).toBeCloseTo(1, 5);
      expect(proofValues[1]).toBeCloseTo(2, 5);
      expect(proofValues[4]).toBeCloseTo(0.7310586, 5);
      expect(proofValues[5]).toBeCloseTo(3.523188, 5);
    });

    it('keeps partial SwiGLU sums in custody until the final microshard', async () => {
      const makeChunk = (
        chunkIndex: number,
        weights: number[],
        postOps: NeuralLayerConfig['postOps']
      ): NeuralLayerConfig => ({
        name: `tiny_mlp_part_${chunkIndex}`,
        type: 'swiglu_mlp_chunk',
        weights: [],
        weightsB64: encodeInt8(weights),
        scales: [1, 1, 1, 1],
        biases: [],
        inputShape: [1, chunkIndex === 0 ? 2 : 4],
        outputShape: [4],
        activation: 'linear',
        seq: 1,
        dModel: 2,
        ffnDim: 1,
        chunkIndex,
        chunkCount: 2,
        inputOps: [],
        postOps,
      });
      const chunk0 = makeChunk(0, [1, 0, 1, 0, 1, 0], []);
      const chunk1 = makeChunk(
        1,
        [0, 1, 0, 1, 0, 1],
        [{ op: 'residual_input' }]
      );
      const head: NeuralLayerConfig = {
        name: 'identity_head',
        type: 'dense',
        weights: [1, 0, 0, 1],
        biases: [0, 0],
        inputShape: [1, 2],
        outputShape: [1, 2],
        activation: 'softmax',
      };
      const layers = [chunk0, chunk1, head];
      const task: ShardTask = {
        taskId: 'microshard-task',
        sampleId: 'microshard-sample',
        modelName: 'tiny-transformer',
        modelVersion: '1+ms2',
        shards: layers.map((layer, index) => ({
          index,
          name: layer.name,
          layerType: layer.type,
          inputShape: layer.inputShape,
          outputShape: layer.outputShape,
          layers: [layer],
        })),
        inputData: encodeFloat32([1, 2]),
        inputShape: [1, 2],
        expectedLayers: 3,
        totalLayers: 3,
        difficulty: 'normal',
        expectedTimeMs: 100,
        labels: ['negative', 'positive'],
      };

      const result = await engine.executeShards(task);
      expect(result.layerOutputs[0]).toHaveLength(4);
      expect(result.layerOutputs[1]).toHaveLength(4);
      expect(result.layerOutputs[2][0]).toBeCloseTo(1.7310586, 5);
      expect(result.layerOutputs[2][1]).toBeCloseTo(5.523188, 5);
      expect(result.prediction?.label).toBe('positive');
    });

    it('executes the last-token RMSNorm candidate logits head', async () => {
      const layer: NeuralLayerConfig = {
        name: 'tiny_head',
        type: 'candidate_logits',
        weights: [1, 0, 0, 1],
        biases: [],
        inputShape: [2, 2],
        outputShape: [1, 2],
        activation: 'softmax',
        dModel: 2,
        inputOps: [
          { op: 'last_token', seq: 2, dim: 2 },
          { op: 'rmsnorm', seq: 1, weight: [1, 1], eps: 0 },
        ],
        postOps: [{ op: 'softmax' }],
      };
      const task: ShardTask = {
        taskId: 'head-task',
        sampleId: 'head-sample',
        modelName: 'tiny-transformer',
        modelVersion: '1',
        shards: [
          {
            index: 2,
            name: 'tiny_head',
            layerType: 'candidate_logits',
            inputShape: [2, 2],
            outputShape: [1, 2],
            layers: [layer],
          },
        ],
        inputData: encodeFloat32([9, 9, 3, 4]),
        inputShape: [2, 2],
        segmentStart: 2,
        expectedLayers: 1,
        totalLayers: 3,
        difficulty: 'normal',
        expectedTimeMs: 100,
        labels: ['negative', 'positive'],
      };

      const result = await engine.executeShards(task);
      expect(result.layerOutputs[0][0]).toBeCloseTo(3 / Math.sqrt(12.5), 5);
      expect(result.layerOutputs[0][1]).toBeCloseTo(4 / Math.sqrt(12.5), 5);
      expect(result.prediction?.label).toBe('positive');
    });
  });

  describe('generatePrediction', () => {
    it('should generate correct top-k predictions', async () => {
      // Create a task with known output
      const output = new Float32Array([0.1, 0.5, 0.3, 0.05, 0.05]);
      const labels = ['A', 'B', 'C', 'D', 'E'];

      // Use reflection to test private method
      const engineAny = engine as any;
      const prediction = engineAny.generatePrediction(output, labels);

      expect(prediction.label).toBe('B');
      // Confidence is rounded to 3 decimal places
      expect(prediction.topK[0]).toEqual({ label: 'B', confidence: 0.5 });
    });
  });

  describe('proof generation', () => {
    it('should generate deterministic proof hashes', async () => {
      const layer: NeuralLayerConfig = {
        name: 'dense_1',
        type: 'dense',
        weights: [0.1, 0.2],
        biases: [0.1],
        inputShape: [1, 2],
        outputShape: [1, 1],
        activation: 'linear',
      };

      const shard: ModelShard = {
        index: 0,
        name: 'shard_0',
        layerType: 'dense',
        inputShape: [1, 2],
        outputShape: [1, 1],
        layers: [layer],
      };

      const task: ShardTask = {
        taskId: 'same-task-id',
        sampleId: 'same-sample',
        modelName: 'test',
        modelVersion: '1.0',
        shards: [shard],
        inputData: btoa(
          String.fromCharCode(
            ...new Uint8Array(new Float32Array([1, 2]).buffer)
          )
        ),
        inputShape: [1, 2],
        expectedLayers: 1,
        difficulty: 'easy',
        expectedTimeMs: 50,
        groundTruthKey: 'gt',
        labels: ['x'],
      };

      const result1 = await engine.executeShards(task);

      // Create new engine instance for second run
      const engine2 = new ShardInferenceEngine(mockConfig);
      const result2 = await engine2.executeShards(task);

      // Same inputs should produce same proof hash
      expect(result1.proof.proofHash).toBe(result2.proof.proofHash);
    });

    it('binds an otherwise identical proof to the server nonce', async () => {
      const layer: NeuralLayerConfig = {
        name: 'dense_nonce',
        type: 'dense',
        weights: [1, 0],
        biases: [0],
        inputShape: [1, 2],
        outputShape: [1, 1],
        activation: 'linear',
      };
      const baseTask: ShardTask = {
        taskId: 'nonce-task',
        sampleId: 'nonce-sample',
        modelName: 'test',
        modelVersion: '1',
        shards: [
          {
            index: 0,
            name: 'dense_nonce',
            layerType: 'dense',
            inputShape: [1, 2],
            outputShape: [1, 1],
            layers: [layer],
          },
        ],
        inputData: encodeFloat32([1, 2]),
        inputShape: [1, 2],
        expectedLayers: 1,
        difficulty: 'normal',
        expectedTimeMs: 50,
        labels: ['x'],
      };

      const first = await engine.executeShards({
        ...baseTask,
        verificationNonce: 'challenge-a',
      });
      const second = await engine.executeShards({
        ...baseTask,
        verificationNonce: 'challenge-b',
      });
      expect(first.proof.outputHashes).toEqual(second.proof.outputHashes);
      expect(first.proof.proofHash).not.toBe(second.proof.proofHash);
    });
  });
});
