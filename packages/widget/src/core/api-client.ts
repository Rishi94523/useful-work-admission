/**
 * API Client for communicating with PoUW CAPTCHA server
 */

import type {
  InitResponse,
  Prediction,
  ProofOfWork,
  SubmitResponse,
  TimingData,
  VerificationResponse,
  VerifyResponse,
  InferenceProof,
} from '../types';

import { Config } from './config';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * API Client for PoUW CAPTCHA server communication
 */
export class ApiClient {
  private config: Config;
  private baseUrl: string;

  constructor(config: Config) {
    this.config = config;
    this.baseUrl = config.get('apiUrl') || 'https://api.pouw.dev/v1';
  }

  /**
   * Initialize a new CAPTCHA session
   */
  async initSession(metadata: ClientMetadata): Promise<InitResponse> {
    const response = await this.request<Record<string, unknown>>(
      '/captcha/init',
      {
        method: 'POST',
        body: JSON.stringify({
          site_key: this.config.get('siteKey'),
          client_metadata: {
            user_agent: metadata.userAgent,
            language: metadata.language,
            timezone: metadata.timezone,
            screen_width: metadata.screenWidth,
            screen_height: metadata.screenHeight,
          },
          preferred_model: this.config.get('preferredModel') || undefined,
        }),
      }
    );

    return this.normalizeInitResponse(response);
  }

  /**
   * Submit prediction result
   */
  async submitPrediction(
    sessionId: string,
    taskId: string,
    prediction: Prediction,
    proofOfWork: ProofOfWork,
    timing: TimingData
  ): Promise<SubmitResponse> {
    const response = await this.request<Record<string, unknown>>(
      '/captcha/submit',
      {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          task_id: taskId,
          prediction: {
            label: prediction.label,
            confidence: prediction.confidence,
            top_k: prediction.topK,
          },
          proof_of_work: {
            hash: proofOfWork.hash,
            nonce: proofOfWork.nonce,
            model_checksum: proofOfWork.modelChecksum,
            input_hash: proofOfWork.inputHash,
            output_hash: proofOfWork.outputHash,
          },
          timing: {
            model_load_ms: timing.modelLoadMs,
            inference_ms: timing.inferenceMs,
            total_ms: timing.totalMs,
            started_at: timing.startedAt,
            completed_at: timing.completedAt,
          },
        }),
      }
    );

    return this.normalizeSubmitResponse(response);
  }

  /**
   * Submit human verification response
   */
  async submitVerification(
    sessionId: string,
    verificationId: string,
    response: VerificationResponse
  ): Promise<VerifyResponse> {
    const result = await this.request<Record<string, unknown>>(
      '/captcha/verify',
      {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          verification_id: verificationId,
          response: response.responseType,
          corrected_label: response.correctedLabel,
          response_time_ms: response.responseTimeMs,
        }),
      }
    );

    return this.normalizeVerifyResponse(result);
  }

  /**
   * Submit inference proof result (replaces submitPrediction for shard-based verification)
   */
  async submitInferenceProof(
    sessionId: string,
    taskId: string,
    prediction: Prediction | null,
    proof: InferenceProof,
    timing: TimingData
  ): Promise<SubmitResponse> {
    const response = await this.request<Record<string, unknown>>(
      '/captcha/submit',
      {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          task_id: taskId,
          prediction: prediction
            ? {
                label: prediction.label,
                confidence: prediction.confidence,
                top_k: prediction.topK,
              }
            : null,
          proof: {
            task_id: proof.taskId,
            sample_id: proof.sampleId,
            segment_start: proof.segmentStart,
            layer_count: proof.layerCount,
            pre_activations: proof.preActivations,
            output_hashes: proof.outputHashes,
            prediction_hash: proof.predictionHash,
            proof_hash: proof.proofHash,
            timestamp: proof.timestamp,
          },
          timing: {
            model_load_ms: timing.modelLoadMs,
            inference_ms: timing.inferenceMs,
            total_ms: timing.totalMs,
            started_at: timing.startedAt,
            completed_at: timing.completedAt,
          },
        }),
      }
    );

    return this.normalizeSubmitResponse(response);
  }

  /**
   * Fetch sample data
   */
  async fetchSample(url: string): Promise<ArrayBuffer> {
    const response = await fetch(url, {
      method: 'GET',
      mode: 'cors',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch sample: ${response.status}`);
    }

    return response.arrayBuffer();
  }

  /**
   * Fetch model
   */
  async fetchModel(url: string): Promise<Response> {
    const response = await fetch(url, {
      method: 'GET',
      mode: 'cors',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch model: ${response.status}`);
    }

    return response;
  }

  /**
   * Make an authenticated request
   */
  private async request<T>(endpoint: string, options: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const timeout = this.config.get('timeout') || 30000;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      this.config.debug(`API Request: ${endpoint}`, options.body);

      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-POUW-Site-Key': this.config.get('siteKey') || '',
          ...options.headers,
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const rawError: unknown = await response.json().catch(() => ({}));
        const errorData = isRecord(rawError) ? rawError : {};
        const message =
          typeof errorData.message === 'string'
            ? errorData.message
            : `HTTP ${response.status}`;
        throw new ApiError(response.status, message, errorData);
      }

      const data: unknown = await response.json();
      this.config.debug(`API Response: ${endpoint}`, data);

      return data as T;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof ApiError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new ApiError(0, 'Request timeout', { timeout });
        }
        throw new ApiError(0, error.message, { originalError: error.message });
      }

      throw new ApiError(0, 'Unknown error', {});
    }
  }

  private normalizeInitResponse(
    response: Record<string, unknown>
  ): InitResponse {
    return this.normalizeKeys(response) as InitResponse;
  }

  private normalizeVerifyResponse(
    response: Record<string, unknown>
  ): VerifyResponse {
    return this.normalizeKeys(response) as VerifyResponse;
  }

  private normalizeSubmitResponse(
    response: Record<string, unknown>
  ): SubmitResponse {
    const normalized = this.normalizeKeys(response) as SubmitResponse;
    const verification = normalized.verification as
      | (Record<string, unknown> & {
          displayData?: { type?: string; url?: string; content?: string };
        })
      | undefined;

    if (verification?.displayData) {
      normalized.verification = {
        ...(verification as object),
        displayType: verification.displayData.type || 'image',
        displayContent:
          verification.displayData.url ||
          verification.displayData.content ||
          '',
      } as SubmitResponse['verification'];
    }

    return normalized;
  }

  private normalizeKeys(value: unknown): unknown {
    if (Array.isArray(value)) {
      return value.map((item) => this.normalizeKeys(item));
    }

    if (value && typeof value === 'object') {
      const result: Record<string, unknown> = {};
      for (const [key, nestedValue] of Object.entries(
        value as Record<string, unknown>
      )) {
        result[this.toCamelCase(key)] = this.normalizeKeys(nestedValue);
      }
      return result;
    }

    return value;
  }

  private toCamelCase(value: string): string {
    return value.replace(/_([a-z])/g, (_, letter: string) =>
      letter.toUpperCase()
    );
  }
}

/**
 * Client metadata for session initialization
 */
export interface ClientMetadata {
  userAgent: string;
  language: string;
  timezone: string;
  screenWidth: number;
  screenHeight: number;
}

/**
 * API Error class
 */
export class ApiError extends Error {
  public readonly status: number;
  public readonly details: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    details: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

/**
 * Get client metadata
 */
export function getClientMetadata(): ClientMetadata {
  return {
    userAgent: navigator.userAgent,
    language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    screenWidth: window.screen.width,
    screenHeight: window.screen.height,
  };
}
