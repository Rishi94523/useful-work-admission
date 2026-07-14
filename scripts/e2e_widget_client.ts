/**
 * Exercise the production widget shard engine against a live API assignment.
 * Run: npm run e2e:widget -- --model llm-qwen2-sentiment
 */

import type { Config } from '../packages/widget/src/core/config';
import { ShardInferenceEngine } from '../packages/widget/src/ml/shard-engine';
import type { ShardTask } from '../packages/widget/src/types';

interface InitResponse {
  sessionId: string;
  task: ShardTask;
}

interface SubmitResponse {
  success: boolean;
  pipeline?: {
    runId: string;
    layersDone: number;
    totalLayers: number;
    completed: boolean;
    predictedLabel?: string | null;
    confidence?: number | null;
    contributors: number;
  };
}

function argument(name: string, fallback: string): string {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1]
    ? process.argv[index + 1]
    : fallback;
}

async function requestJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return (await response.json()) as T;
}

async function main(): Promise<void> {
  const api = argument('--api', 'http://127.0.0.1:8000/api/v1');
  const model = argument('--model', 'llm-qwen2-sentiment');
  const solves = Number.parseInt(argument('--solves', '1'), 10);
  if (!Number.isFinite(solves) || solves < 1) {
    throw new Error('--solves must be a positive integer');
  }
  const segments: Array<Record<string, unknown>> = [];
  let finalPipeline: SubmitResponse['pipeline'];
  let totalComputeMs = 0;

  for (let solve = 0; solve < solves; solve++) {
    const init = await requestJson<InitResponse>(`${api}/captcha/init`, {
      siteKey: 'pk_demo_1234567890',
      preferredModel: model,
      clientMetadata: {
        userAgent: `widget-e2e/${solve + 1}`,
        language: 'en-US',
        timezone: 'UTC',
        screenWidth: 1920,
        screenHeight: 1080,
      },
    });

    const engine = new ShardInferenceEngine({
      debug: () => undefined,
    } as unknown as Config);
    const startedAt = Date.now();
    const result = await engine.executeShards(init.task);
    const completedAt = Date.now();
    const inferenceMs = Math.max(20, Math.ceil(result.timing.totalMs));
    const submit = await requestJson<SubmitResponse>(`${api}/captcha/submit`, {
      sessionId: init.sessionId,
      taskId: init.task.taskId,
      prediction: result.prediction ?? null,
      proof: result.proof,
      timing: {
        modelLoadMs: 0,
        inferenceMs,
        totalMs: inferenceMs,
        startedAt,
        completedAt,
      },
    });
    if (!submit.success) {
      throw new Error(`server rejected segment ${init.task.segmentStart ?? 0}`);
    }
    totalComputeMs += result.timing.totalMs;
    finalPipeline = submit.pipeline;
    segments.push({
      segment: [
        init.task.segmentStart ?? 0,
        (init.task.segmentStart ?? 0) + init.task.expectedLayers,
      ],
      layerType: init.task.shards[0]?.layerType,
      proofValues: result.layerOutputs.reduce(
        (sum, values) => sum + values.length,
        0
      ),
      computeMs: Math.round(result.timing.totalMs),
    });
    if (submit.pipeline?.completed) break;
  }

  process.stdout.write(
    `${JSON.stringify(
      {
        model,
        solves: segments.length,
        totalComputeMs: Math.round(totalComputeMs),
        segments,
        pipeline: finalPipeline,
      },
      null,
      2
    )}\n`
  );
}

main().catch((error: unknown) => {
  process.stderr.write(
    `${error instanceof Error ? error.stack : String(error)}\n`
  );
  process.exitCode = 1;
});
