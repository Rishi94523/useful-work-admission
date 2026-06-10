/**
 * PoUW CAPTCHA Widget
 *
 * Proof-of-Useful-Work CAPTCHA system that replaces traditional
 * puzzle-based CAPTCHAs with productive ML computation.
 *
 * @packageDocumentation
 */

// Core exports
export { PoUWCaptcha } from './core/captcha';
export { CaptchaSession } from './core/session';
export { ApiClient } from './core/api-client';
export { Config, DEFAULT_CONFIG } from './core/config';

// ML Engine exports
export { MLEngine } from './ml/engine';
export { TFJSRuntime } from './ml/tfjs-runtime';
export { ONNXRuntime } from './ml/onnx-runtime';
export { ModelLoader } from './ml/model-loader';

// UI exports
export { CaptchaWidget } from './ui/widget';
export { VerificationUI } from './ui/verification';
export { ProgressIndicator } from './ui/progress';

// Utility exports
export { generatePoWHash, verifyPoWHash } from './utils/crypto';
export { PerformanceTimer } from './utils/timing';
export { announceToScreenReader, trapFocus } from './utils/accessibility';

// Type exports
export type {
  CaptchaConfig,
  CaptchaResult,
  CaptchaTask,
  CaptchaError,
  CaptchaProgress,
  Prediction,
  VerificationResponse,
  WidgetState,
  MLModel,
  RuntimeType,
} from './types';

// Global initialization for script tag usage
import { PoUWCaptcha } from './core/captcha';

declare global {
  interface Window {
    PoUWCaptcha: typeof PoUWCaptcha;
    onPoUWCaptchaLoad?: () => void;
  }
}

// Auto-initialize when loaded via script tag
if (typeof window !== 'undefined') {
  window.PoUWCaptcha = PoUWCaptcha;

  // Call callback if defined
  if (typeof window.onPoUWCaptchaLoad === 'function') {
    window.onPoUWCaptchaLoad();
  }

  // Dispatch custom event for integration
  window.dispatchEvent(new CustomEvent('pouw-captcha-loaded'));
}
