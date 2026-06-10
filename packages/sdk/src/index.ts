/**
 * PoUW CAPTCHA SDK
 *
 * Framework integrations for React, Vue, and Vanilla JS
 */

// Re-export from widget
export { PoUWCaptcha, Config, DEFAULT_CONFIG } from '@pouw/widget';

// Export types
export type {
  CaptchaConfig,
  CaptchaResult,
  CaptchaError,
  CaptchaProgress,
  WidgetState,
} from '@pouw/widget';

// Vanilla JS wrapper
export { createCaptcha } from './vanilla';
export {
  validateCaptchaToken,
  type ValidateCaptchaTokenOptions,
  type ValidateCaptchaTokenResult,
} from './server';
