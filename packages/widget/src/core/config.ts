/**
 * Configuration management for PoUW CAPTCHA Widget
 */

import type {
  CaptchaConfig,
  CaptchaError,
  CaptchaProgress,
  VerificationData,
} from '../types';

/**
 * Default configuration values
 */
export const DEFAULT_CONFIG: Required<
  Omit<
    CaptchaConfig,
    | 'container'
    | 'siteKey'
    | 'onSuccess'
    | 'onError'
    | 'onExpire'
    | 'onProgress'
    | 'onVerificationRequired'
  >
> & Pick<CaptchaConfig, 'container' | 'siteKey'> = {
  apiUrl: 'https://api.pouw.dev/v1',
  siteKey: '',
  container: '',
  theme: 'auto',
  language: 'en',
  debug: false,
  modelUrl: '',
  timeout: 30000,
  invisible: false,
};

/**
 * Supported themes
 */
export const THEMES = ['light', 'dark', 'auto'] as const;

/**
 * Supported languages
 */
export const LANGUAGES = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
  de: 'Deutsch',
  ja: '日本語',
  zh: '中文',
  ko: '한국어',
  pt: 'Português',
  it: 'Italiano',
  ru: 'Русский',
} as const;

/**
 * Configuration manager class
 */
export class Config {
  private config: Required<CaptchaConfig>;
  private callbacks: {
    onSuccess?: (token: string) => void;
    onError?: (error: CaptchaError) => void;
    onExpire?: () => void;
    onProgress?: (progress: CaptchaProgress) => void;
    onVerificationRequired?: (data: VerificationData) => void;
  };

  constructor(userConfig: CaptchaConfig) {
    this.validateConfig(userConfig);
    
    this.callbacks = {
      onSuccess: userConfig.onSuccess,
      onError: userConfig.onError,
      onExpire: userConfig.onExpire,
      onProgress: userConfig.onProgress,
      onVerificationRequired: userConfig.onVerificationRequired,
    };

    this.config = {
      ...DEFAULT_CONFIG,
      ...userConfig,
      onSuccess: userConfig.onSuccess,
      onError: userConfig.onError,
      onExpire: userConfig.onExpire,
      onProgress: userConfig.onProgress,
      onVerificationRequired: userConfig.onVerificationRequired,
    } as Required<CaptchaConfig>;

    // Resolve container
    if (typeof this.config.container === 'string') {
      const element = document.querySelector(this.config.container);
      if (!element) {
        throw new Error(`Container element not found: ${this.config.container}`);
      }
      this.config.container = element as HTMLElement;
    }

    // Auto-detect theme
    if (this.config.theme === 'auto') {
      this.config.theme = this.detectTheme();
    }

    // Auto-detect language
    if (!userConfig.language) {
      this.config.language = this.detectLanguage();
    }
  }

  /**
   * Validate configuration
   */
  private validateConfig(config: CaptchaConfig): void {
    if (!config.siteKey) {
      throw new Error('siteKey is required');
    }

    if (!config.container) {
      throw new Error('container is required');
    }

    if (config.apiUrl && !this.isValidUrl(config.apiUrl)) {
      throw new Error('Invalid apiUrl');
    }

    if (config.theme && !THEMES.includes(config.theme)) {
      throw new Error(`Invalid theme: ${config.theme}. Must be one of: ${THEMES.join(', ')}`);
    }

    if (config.timeout && (config.timeout < 5000 || config.timeout > 120000)) {
      throw new Error('timeout must be between 5000 and 120000 ms');
    }
  }

  /**
   * Check if URL is valid
   */
  private isValidUrl(url: string): boolean {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Detect system theme preference
   */
  private detectTheme(): 'light' | 'dark' {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light';
    }
    return 'light';
  }

  /**
   * Detect browser language
   */
  private detectLanguage(): string {
    if (typeof navigator !== 'undefined') {
      const lang = navigator.language.split('-')[0];
      if (lang in LANGUAGES) {
        return lang;
      }
    }
    return 'en';
  }

  /**
   * Get configuration value
   */
  get<K extends keyof CaptchaConfig>(key: K): CaptchaConfig[K] {
    return this.config[key];
  }

  /**
   * Get all configuration
   */
  getAll(): Required<CaptchaConfig> {
    return { ...this.config };
  }

  /**
   * Get container element
   */
  getContainer(): HTMLElement {
    return this.config.container as HTMLElement;
  }

  /**
   * Get callbacks
   */
  getCallbacks() {
    return this.callbacks;
  }

  /**
   * Check if debug mode is enabled
   */
  isDebug(): boolean {
    return this.config.debug ?? false;
  }

  /**
   * Log debug message
   */
  debug(message: string, ...args: unknown[]): void {
    if (this.isDebug()) {
      console.log(`[PoUW CAPTCHA] ${message}`, ...args);
    }
  }

  /**
   * Log error message
   */
  error(message: string, ...args: unknown[]): void {
    console.error(`[PoUW CAPTCHA] ${message}`, ...args);
  }
}
