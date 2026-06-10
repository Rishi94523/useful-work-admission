/**
 * Main PoUW CAPTCHA class
 *
 * Entry point for the CAPTCHA widget. Orchestrates the entire
 * CAPTCHA flow from initialization to completion.
 */

import type {
  CaptchaConfig,
  CaptchaError,
  CaptchaErrorCode,
  CaptchaResult,
  Prediction,
  ProofOfWork,
  TimingData,
  VerificationResponse,
  CaptchaTask,
  CaptchaProgress,
  PipelineProgress,
} from '../types';
import { ApiClient, getClientMetadata } from './api-client';
import { Config } from './config';
import { CaptchaSession } from './session';
import { MLEngine } from '../ml/engine';
import { CaptchaWidget } from '../ui/widget';
import { generatePoWHash } from '../utils/crypto';
import { PerformanceTimer } from '../utils/timing';

/**
 * Main PoUW CAPTCHA class
 *
 * @example
 * ```typescript
 * const captcha = new PoUWCaptcha({
 *   siteKey: 'your-site-key',
 *   container: '#captcha-container',
 *   onSuccess: (token) => {
 *     console.log('CAPTCHA solved:', token);
 *   },
 * });
 *
 * await captcha.execute();
 * ```
 */
export class PoUWCaptcha {
  private config: Config;
  private apiClient: ApiClient;
  private mlEngine: MLEngine;
  private widget: CaptchaWidget;
  private session: CaptchaSession | null = null;
  private isExecuting = false;

  /**
   * Create a new PoUW CAPTCHA instance
   */
  constructor(userConfig: CaptchaConfig) {
    this.config = new Config(userConfig);
    this.apiClient = new ApiClient(this.config);
    this.mlEngine = new MLEngine(this.config);
    this.widget = new CaptchaWidget(this.config, {
      onRetry: () => this.execute(),
      onVerificationSubmit: (response) => this.handleVerification(response),
    });

    this.config.debug('PoUW CAPTCHA initialized');
  }

  /**
   * Execute the CAPTCHA challenge
   *
   * This is the main entry point that starts the CAPTCHA flow:
   * 1. Initialize session with server
   * 2. Load ML model
   * 3. Run inference
   * 4. Submit result
   * 5. Handle verification if required
   * 6. Return token
   */
  async execute(): Promise<CaptchaResult> {
    if (this.isExecuting) {
      throw this.createError(
        'VALIDATION_ERROR',
        'CAPTCHA is already executing'
      );
    }

    this.isExecuting = true;
    const timer = new PerformanceTimer();
    timer.start('total');

    try {
      // Step 1: Initialize session
      this.widget.setState('loading');
      this.widget.setMessage('Initializing security check...');
      this.invokeProgress({
        stage: 'initializing',
        progress: 0,
      });

      timer.start('init');
      const metadata = getClientMetadata();
      const initResponse = await this.apiClient.initSession(metadata);
      timer.end('init');

      this.session = new CaptchaSession(initResponse);
      this.session.onStateChange((state) => this.widget.setState(state));

      this.config.debug('Session initialized', {
        sessionId: this.session.sessionId,
        difficulty: this.session.difficulty,
        isShardTask: this.session.isShardTask(),
      });
      this.invokeProgress({
        stage: 'assigned',
        progress: 0,
        difficulty: this.session.difficulty,
        segment: this.getCurrentSegment(),
      });

      // Step 2-4: Execute task (ShardTask or legacy CaptchaTask)
      let submitResponse: import('../types').SubmitResponse;

      if (this.session.isShardTask()) {
        // Shard-based execution flow
        ({ submitResponse } = await this.executeShardTaskFlow(timer));
      } else {
        // Legacy CaptchaTask flow
        ({ submitResponse } = await this.executeLegacyTaskFlow(timer));
      }

      // Step 6: Handle response
      if (submitResponse.requiresVerification && submitResponse.verification) {
        // Human verification required
        this.session.verificationData = submitResponse.verification;
        this.session.state = 'verifying';
        this.invokeProgress({
          stage: 'verifying',
          progress: 1,
          difficulty: this.session.difficulty,
          segment: this.getCurrentSegment(),
          pipeline: submitResponse.pipeline,
        });
        this.widget.showVerification(submitResponse.verification);

        // Wait for verification to complete
        return await this.waitForVerification();
      } else if (submitResponse.captchaToken) {
        // Success without verification
        this.session.captchaToken = submitResponse.captchaToken;
        this.session.state = 'success';
        this.widget.showSuccess();

        const result = this.createResult(
          submitResponse.captchaToken,
          new Date(submitResponse.expiresAt!),
          false,
          submitResponse.pipeline
        );

        this.invokeProgress({
          stage: 'complete',
          progress: 1,
          difficulty: this.session.difficulty,
          segment: this.getCurrentSegment(),
          pipeline: submitResponse.pipeline,
        });
        this.invokeCallback('onSuccess', submitResponse.captchaToken);
        return result;
      } else if (submitResponse.success === false) {
        throw this.createError(
          'VALIDATION_ERROR',
          'CAPTCHA proof validation failed'
        );
      } else {
        throw this.createError('VALIDATION_ERROR', 'Invalid server response');
      }
    } catch (error) {
      this.handleError(error);
      throw error;
    } finally {
      this.isExecuting = false;
      this.mlEngine.dispose();
    }
  }

  /**
   * Reset the CAPTCHA widget
   */
  reset(): void {
    this.session?.dispose();
    this.session = null;
    this.isExecuting = false;
    this.mlEngine.dispose();
    this.widget.reset();
    this.config.debug('CAPTCHA reset');
  }

  /**
   * Destroy the CAPTCHA instance
   */
  destroy(): void {
    this.reset();
    this.widget.destroy();
    this.config.debug('CAPTCHA destroyed');
  }

  /**
   * Get the current session
   */
  getSession(): CaptchaSession | null {
    return this.session;
  }

  /**
   * Execute shard-based task flow
   */
  private async executeShardTaskFlow(timer: PerformanceTimer): Promise<{
    prediction: Prediction;
    submitResponse: import('../types').SubmitResponse;
  }> {
    const shardTask = this.session!.getShardTask()!;

    // Step 2: Set up progress callback
    this.widget.setState('processing');
    this.widget.setMessage('Running security check...');
    const externalProgress = shardTask.onProgress;
    shardTask.onProgress = (progress) => {
      this.widget.setProgress(progress * 100);
      this.invokeProgress({
        stage: 'computing',
        progress,
        difficulty: this.session!.difficulty,
        segment: this.getCurrentSegment(),
      });
      externalProgress?.(progress);
    };

    // Step 3: Execute shard task
    timer.start('inference');
    const shardResult = await this.mlEngine.executeShardTask(shardTask);
    timer.end('inference');

    // Mid-pipeline segments have no prediction — the user contributed a
    // verified slice of a distributed inference instead.
    const prediction: Prediction = shardResult.prediction ?? {
      label: '(partial segment)',
      confidence: 0,
      topK: [],
    };
    this.session!.prediction = prediction;
    this.widget.setProgress(100);

    this.config.debug('Shard inference complete', {
      label: prediction.label,
      confidence: prediction.confidence,
      layerCount: shardResult.layerOutputs.length,
      isFinalSegment: shardResult.isFinalSegment,
    });

    // Step 4: Get proof from shard result
    const proof = shardResult.proof;
    this.session!.inferenceProof = proof;

    // Step 5: Submit result
    timer.end('total');
    const timing: TimingData = {
      modelLoadMs: 0, // Shards are loaded during execution
      inferenceMs: timer.get('inference'),
      totalMs: timer.get('total'),
      startedAt: timer.getStartTime('total'),
      completedAt: Date.now(),
    };
    this.session!.timing = timing;

    const submitResponse = await this.apiClient.submitInferenceProof(
      this.session!.sessionId,
      shardTask.taskId,
      shardResult.prediction ?? null,
      proof,
      timing
    );
    this.invokeProgress({
      stage: 'submitted',
      progress: 1,
      difficulty: this.session!.difficulty,
      segment: this.getCurrentSegment(),
      pipeline: submitResponse.pipeline,
    });

    return { prediction, submitResponse };
  }

  /**
   * Execute legacy CaptchaTask flow
   */
  private async executeLegacyTaskFlow(timer: PerformanceTimer): Promise<{
    prediction: Prediction;
    submitResponse: import('../types').SubmitResponse;
  }> {
    const task = this.session!.task as CaptchaTask;

    // Step 2: Load ML model
    this.widget.setMessage('Loading ML model...');
    timer.start('modelLoad');

    const model = await this.mlEngine.loadModel({
      url: task.modelUrl,
      meta: task.modelMeta,
    });

    timer.end('modelLoad');
    this.config.debug('Model loaded', { modelId: model.id });

    // Step 3: Run inference
    this.widget.setState('processing');
    this.widget.setMessage('Running security check...');
    this.widget.setProgress(0);

    timer.start('inference');

    // Prepare input
    const input = await this.prepareInput(task);

    // Run prediction
    const prediction = await model.predict(input);
    timer.end('inference');

    this.session!.prediction = prediction;
    this.widget.setProgress(100);

    this.config.debug('Inference complete', {
      label: prediction.label,
      confidence: prediction.confidence,
    });

    // Step 4: Generate proof of work
    timer.start('pow');
    const proofOfWork = await this.generatePoWProof(task, prediction);
    timer.end('pow');

    this.session!.proofOfWork = proofOfWork;

    // Step 5: Submit result
    timer.end('total');
    const timing: TimingData = {
      modelLoadMs: timer.get('modelLoad'),
      inferenceMs: timer.get('inference'),
      totalMs: timer.get('total'),
      startedAt: timer.getStartTime('total'),
      completedAt: Date.now(),
    };
    this.session!.timing = timing;

    const submitResponse = await this.apiClient.submitPrediction(
      this.session!.sessionId,
      task.taskId,
      prediction,
      proofOfWork,
      timing
    );
    this.invokeProgress({
      stage: 'submitted',
      progress: 1,
      difficulty: this.session!.difficulty,
      pipeline: submitResponse.pipeline,
    });

    return { prediction, submitResponse };
  }

  /**
   * Prepare input data for model (legacy CaptchaTask only)
   */
  private async prepareInput(
    task: CaptchaTask
  ): Promise<Float32Array | ImageData | string> {
    if (task.sampleType === 'image') {
      if (task.sampleData && task.sampleData.startsWith('data:')) {
        return await this.decodeImageData(task.sampleData);
      }
      if (task.sampleUrl) {
        return await this.fetchImageData(task.sampleUrl);
      }
      if (!task.sampleData) {
        throw new Error('Missing image sample data');
      }
      return await this.decodeImageData(
        `data:image/jpeg;base64,${task.sampleData}`
      );
    } else {
      // Text input
      return task.sampleData;
    }
  }

  /**
   * Decode base64 image to ImageData
   */
  private async decodeImageData(dataUrl: string): Promise<ImageData> {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';

      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;

        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('Failed to get canvas context'));
          return;
        }

        ctx.drawImage(img, 0, 0);
        const imageData = ctx.getImageData(0, 0, img.width, img.height);
        resolve(imageData);
      };

      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = dataUrl;
    });
  }

  /**
   * Fetch image data from URL
   */
  private async fetchImageData(url: string): Promise<ImageData> {
    const response = await fetch(url);
    const blob = await response.blob();
    const dataUrl = await this.blobToDataUrl(blob);
    return this.decodeImageData(dataUrl);
  }

  /**
   * Convert blob to data URL
   */
  private blobToDataUrl(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /**
   * Generate proof of work hash (legacy CaptchaTask)
   */
  private async generatePoWProof(
    task: CaptchaTask,
    prediction: Prediction
  ): Promise<ProofOfWork> {
    return generatePoWHash({
      modelChecksum: task.modelMeta.checksum,
      inputData: task.sampleData,
      outputData: JSON.stringify(prediction.topK),
      sessionId: this.session!.sessionId,
    });
  }

  /**
   * Handle verification submission
   */
  private async handleVerification(
    response: VerificationResponse
  ): Promise<void> {
    if (!this.session || !this.session.verificationData) {
      throw this.createError('VALIDATION_ERROR', 'No verification pending');
    }

    try {
      const verifyResponse = await this.apiClient.submitVerification(
        this.session.sessionId,
        this.session.verificationData.verificationId,
        response
      );

      this.session.captchaToken = verifyResponse.captchaToken;
      this.session.state = 'success';
      this.widget.showSuccess();

      this.invokeCallback('onSuccess', verifyResponse.captchaToken);
    } catch (error) {
      this.handleError(error);
    }
  }

  /**
   * Wait for verification to complete
   */
  private waitForVerification(): Promise<CaptchaResult> {
    return new Promise((resolve, reject) => {
      const checkComplete = setInterval(() => {
        if (!this.session) {
          clearInterval(checkComplete);
          reject(this.createError('SESSION_EXPIRED', 'Session was disposed'));
          return;
        }

        if (this.session.isCompleted()) {
          clearInterval(checkComplete);
          resolve(
            this.createResult(
              this.session.captchaToken!,
              this.session.expiresAt,
              true
            )
          );
        }

        if (this.session.state === 'error') {
          clearInterval(checkComplete);
          reject(
            this.session.error ||
              this.createError('UNKNOWN_ERROR', 'Verification failed')
          );
        }

        if (this.session.isExpired()) {
          clearInterval(checkComplete);
          reject(this.createError('SESSION_EXPIRED', 'Session expired'));
        }
      }, 100);

      // Timeout after session expiry
      setTimeout(() => {
        clearInterval(checkComplete);
        if (!this.session?.isCompleted()) {
          reject(this.createError('TIMEOUT_ERROR', 'Verification timeout'));
        }
      }, this.session?.getTimeRemaining() || 60000);
    });
  }

  /**
   * Create result object
   */
  private createResult(
    token: string,
    expiresAt: Date,
    verificationPerformed: boolean,
    pipeline?: PipelineProgress
  ): CaptchaResult {
    return {
      token,
      expiresAt,
      sessionId: this.session!.sessionId,
      verificationPerformed,
      pipeline,
    };
  }

  /**
   * Create error object
   */
  private createError(code: CaptchaErrorCode, message: string): CaptchaError {
    return { code, message };
  }

  /**
   * Handle errors
   */
  private handleError(error: unknown): void {
    this.config.error('CAPTCHA error:', error);

    if (this.session) {
      this.session.error =
        error instanceof Error ? error : new Error(String(error));
    }

    this.widget.showError(
      error instanceof Error ? error.message : 'An error occurred'
    );

    const captchaError: CaptchaError =
      error && typeof error === 'object' && 'code' in error
        ? (error as CaptchaError)
        : {
            code: 'UNKNOWN_ERROR',
            message: error instanceof Error ? error.message : String(error),
          };

    this.invokeCallback('onError', captchaError);
  }

  /**
   * Invoke callback safely
   */
  private invokeCallback<K extends 'onSuccess' | 'onError' | 'onExpire'>(
    name: K,
    ...args: Parameters<NonNullable<CaptchaConfig[K]>>
  ): void {
    const callbacks = this.config.getCallbacks();
    const callback = callbacks[name];
    if (typeof callback === 'function') {
      try {
        (callback as (...args: unknown[]) => void)(...args);
      } catch (error) {
        this.config.error(`Callback ${name} error:`, error);
      }
    }
  }

  private invokeProgress(progress: CaptchaProgress): void {
    const callback = this.config.getCallbacks().onProgress;
    if (typeof callback === 'function') {
      try {
        callback(progress);
      } catch (error) {
        this.config.error('Callback onProgress error:', error);
      }
    }
  }

  private getCurrentSegment(): [number, number] | undefined {
    const shardTask = this.session?.getShardTask();
    if (!shardTask) return undefined;
    const segmentStart = shardTask.segmentStart ?? 0;
    return [
      segmentStart,
      segmentStart + shardTask.expectedLayers,
    ];
  }

  /**
   * Dispose the CAPTCHA instance and cleanup resources
   */
  dispose(): void {
    if (this.session) {
      this.session.dispose();
      this.session = null;
    }
    if (this.mlEngine) {
      this.mlEngine.dispose();
    }
    this.widget.destroy();
  }
}
