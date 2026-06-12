/**
 * Type definitions for PoUW CAPTCHA Widget
 */

/**
 * Model shard configuration from server
 */
export interface ModelShard {
  /** Shard index (layer depth) */
  index: number;
  /** Layer name */
  name: string;
  /** Layer type (Conv2D, Dense, etc.) */
  layerType: string;
  /** Serialized weights (if provided) */
  weights?: Record<string, number[]>;
  /** Expected input shape */
  inputShape: number[];
  /** Expected output shape */
  outputShape: number[];
  /** Activation function */
  activation?: string;
  /** SHA-256 over the layer's float32 wire bytes; verified before execution */
  checksum?: string;
  /** Layer configurations for shard execution */
  layers: NeuralLayerConfig[];
}

/**
 * A cheap transform applied after a provable layer's affine computation
 * (mirrored server-side during verification)
 */
export interface PostOpConfig {
  /** Operation: relu, softmax, sigmoid, tanh, maxpool2d, flatten */
  op: string;
  /** Pool size for maxpool2d (default 2) */
  pool?: number;
  /** (C, H, W) shape of the tensor entering a maxpool2d op */
  shape?: number[];
}

/**
 * Neural layer configuration for shard execution
 */
export interface NeuralLayerConfig {
  /** Layer name */
  name: string;
  /** Provable layer type (dense, conv2d) */
  type: string;
  /** Layer weights as flat array (dense: [out][in]; conv2d: [oc][ic][kh][kw]) */
  weights: number[];
  /** Layer biases as flat array */
  biases: number[];
  /** Input shape (dense: [1, in]; conv2d: [C, H, W]) */
  inputShape: number[];
  /** Output shape (dense: [1, out]; conv2d: [OC, OH, OW]) */
  outputShape: number[];
  /** Activation function (legacy single-op form) */
  activation: string;
  /** Kernel size (kh, kw) for conv2d layers */
  kernel?: number[];
  /** Post-op chain applied after the affine computation */
  postOps?: PostOpConfig[];
}

/**
 * Shard-based task assignment from server
 */
export interface ShardTask {
  /** Unique task ID */
  taskId: string;
  /** Sample ID for this task */
  sampleId: string;
  /** Model name */
  modelName: string;
  /** Model version */
  modelVersion: string;
  /** Assigned shards (layers) to compute */
  shards: ModelShard[];
  /** Input data as base64 string */
  inputData: string;
  /** Input shape */
  inputShape: number[];
  /** Number of layers client should compute */
  expectedLayers: number;
  /** Index of the first layer in this segment (distributed pipeline) */
  segmentStart?: number;
  /** Total layers in the model */
  totalLayers?: number;
  /** Pipeline run this segment contributes to */
  runId?: string;
  /** Difficulty tier */
  difficulty: string;
  /** Expected computation time in ms */
  expectedTimeMs: number;
  /** Class labels for prediction */
  labels: string[];
  /** Model checksum (hash of layer checksums) */
  modelChecksum?: string;
  /** Optional test/known-label key for seeded evaluation samples */
  groundTruthKey?: string;
  /** Progress callback */
  onProgress?: (progress: number) => void;
}

/**
 * Proof of inference computation (replaces PoW)
 */
export interface InferenceProof {
  /** Task ID */
  taskId: string;
  /** Sample ID */
  sampleId: string;
  /** First layer index of the computed segment */
  segmentStart: number;
  /** Number of layers computed */
  layerCount: number;
  /**
   * Pre-activation output of each computed layer. The server verifies these
   * with secret projection checks without re-running the computation.
   */
  preActivations: number[][];
  /** Commitment hashes of each pre-activation vector */
  outputHashes: string[];
  /** Hash of prediction (empty for mid-pipeline segments) */
  predictionHash: string;
  /** Combined proof hash binding everything to this task */
  proofHash: string;
  /** Timestamp when proof was generated */
  timestamp: number;
}

/**
 * Configuration options for the CAPTCHA widget
 */
export interface CaptchaConfig {
  /** Server API endpoint */
  apiUrl?: string;
  /** Site API key (public) */
  siteKey: string;
  /** Container element or selector */
  container: HTMLElement | string;
  /** Theme: 'light' | 'dark' | 'auto' */
  theme?: 'light' | 'dark' | 'auto';
  /** Language code (e.g., 'en', 'es', 'fr') */
  language?: string;
  /** Callback when CAPTCHA is solved */
  onSuccess?: (token: string) => void;
  /** Callback when CAPTCHA fails */
  onError?: (error: CaptchaError) => void;
  /** Callback when CAPTCHA expires */
  onExpire?: () => void;
  /** Callback for progress and pipeline contribution updates */
  onProgress?: (progress: CaptchaProgress) => void;
  /** Callback for verification UI */
  onVerificationRequired?: (data: VerificationData) => void;
  /** Enable debug logging */
  debug?: boolean;
  /** Custom model URL override */
  modelUrl?: string;
  /** Timeout in milliseconds */
  timeout?: number;
  /** Invisible mode (no UI) */
  invisible?: boolean;
}

/**
 * Result returned after successful CAPTCHA completion
 */
export interface CaptchaResult {
  /** JWT token to validate on server */
  token: string;
  /** When the token expires */
  expiresAt: Date;
  /** Session ID for tracking */
  sessionId: string;
  /** Whether human verification was performed */
  verificationPerformed: boolean;
  /** Distributed pipeline progress, when returned by the server */
  pipeline?: PipelineProgress;
}

/**
 * Progress callback payload for integration observability
 */
export interface CaptchaProgress {
  stage: 'initializing' | 'assigned' | 'computing' | 'submitted' | 'verifying' | 'complete';
  progress: number;
  difficulty?: 'normal' | 'suspicious' | 'bot_like';
  segment?: [number, number];
  pipeline?: PipelineProgress;
}

/**
 * ML task assigned by the server
 */
export interface CaptchaTask {
  /** Unique task ID */
  taskId: string;
  /** URL to load the model from */
  modelUrl: string;
  /** Sample data (base64 or URL) */
  sampleData: string;
  /** Sample URL (alternative to inline data) */
  sampleUrl?: string;
  /** Type of sample */
  sampleType: 'image' | 'text';
  /** Task type */
  taskType: 'inference' | 'gradient' | 'training';
  /** Expected completion time in ms */
  expectedTimeMs: number;
  /** Model metadata */
  modelMeta: ModelMeta;
}

/**
 * Model metadata
 */
export interface ModelMeta {
  /** Model name */
  name: string;
  /** Model version */
  version: string;
  /** Expected input shape */
  inputShape: number[];
  /** Output labels */
  labels: string[];
  /** Checksum for integrity */
  checksum: string;
}

/**
 * Prediction result from ML inference
 */
export interface Prediction {
  /** Predicted label */
  label: string;
  /** Confidence score (0-1) */
  confidence: number;
  /** Top-K predictions */
  topK: Array<{
    label: string;
    confidence: number;
  }>;
  /** Raw output tensor values */
  rawOutput?: number[];
}

/**
 * Data for human verification UI
 */
export interface VerificationData {
  /** Verification ID */
  verificationId: string;
  /** Type of display */
  displayType: 'image' | 'text';
  /** URL or content to display */
  displayContent: string;
  /** Predicted label to verify */
  predictedLabel: string;
  /** Human-readable prompt */
  prompt: string;
  /** Available options */
  options: VerificationOption[];
}

/**
 * Verification option
 */
export interface VerificationOption {
  /** Option ID */
  id: string;
  /** Display label */
  label: string;
  /** Option type */
  type: 'confirm' | 'reject' | 'correct';
}

/**
 * Response from human verification
 */
export interface VerificationResponse {
  /** Response type */
  responseType: 'confirm' | 'reject' | 'correct';
  /** Corrected label if type is 'correct' */
  correctedLabel?: string;
  /** Time taken to respond in ms */
  responseTimeMs: number;
}

/**
 * Proof-of-Work data
 */
export interface ProofOfWork {
  /** SHA-256 hash */
  hash: string;
  /** Nonce used */
  nonce: number;
  /** Model checksum included */
  modelChecksum: string;
  /** Input data hash */
  inputHash: string;
  /** Output hash */
  outputHash: string;
}

/**
 * Timing data for performance tracking
 */
export interface TimingData {
  /** Model load time in ms */
  modelLoadMs: number;
  /** Inference time in ms */
  inferenceMs: number;
  /** Total time in ms */
  totalMs: number;
  /** Timestamp when started */
  startedAt: number;
  /** Timestamp when completed */
  completedAt: number;
}

/**
 * ML Model interface
 */
export interface MLModel {
  /** Model identifier */
  id: string;
  /** Runtime type */
  runtime: RuntimeType;
  /** Run inference on input */
  predict(input: Float32Array | ImageData | string): Promise<Prediction>;
  /** Compute gradient (for training tasks) */
  computeGradient?(
    input: Float32Array | ImageData | string,
    target: number
  ): Promise<Float32Array>;
  /** Dispose model resources */
  dispose(): void;
  /** Model metadata */
  meta: ModelMeta;
}

/**
 * Runtime types supported
 */
export type RuntimeType = 'tfjs' | 'onnx';

/**
 * CAPTCHA error
 */
export interface CaptchaError {
  /** Error code */
  code: CaptchaErrorCode;
  /** Human-readable message */
  message: string;
  /** Additional details */
  details?: Record<string, unknown>;
}

/**
 * Error codes
 */
export type CaptchaErrorCode =
  | 'NETWORK_ERROR'
  | 'MODEL_LOAD_ERROR'
  | 'INFERENCE_ERROR'
  | 'TIMEOUT_ERROR'
  | 'VALIDATION_ERROR'
  | 'SESSION_EXPIRED'
  | 'INVALID_CONFIG'
  | 'WEBGL_NOT_SUPPORTED'
  | 'UNKNOWN_ERROR';

/**
 * Widget state
 */
export type WidgetState =
  | 'idle'
  | 'loading'
  | 'processing'
  | 'verifying'
  | 'success'
  | 'error';

/**
 * API response types
 */
export interface InitResponse {
  sessionId: string;
  challengeToken: string;
  task: CaptchaTask | ShardTask;
  difficulty: 'normal' | 'suspicious' | 'bot_like';
  expiresAt: string;
}

export interface PipelineProgress {
  /** Distributed run identifier */
  runId: string;
  /** Layers completed so far across all contributors */
  layersDone: number;
  /** Total layers in the model */
  totalLayers: number;
  /** Whether the run finished with this submission */
  completed: boolean;
  /** Final label (only when completed) */
  predictedLabel?: string;
  confidence?: number;
  /** Number of solvers whose segments were pieced together */
  contributors: number;
}

export interface SubmitResponse {
  success: boolean;
  requiresVerification: boolean;
  verification?: VerificationData;
  captchaToken?: string;
  expiresAt?: string;
  pipeline?: PipelineProgress;
}

export interface VerifyResponse {
  success: boolean;
  captchaToken: string;
  expiresAt: string;
}

