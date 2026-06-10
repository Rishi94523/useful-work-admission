/**
 * React hooks and components for PoUW CAPTCHA
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  PoUWCaptcha,
  CaptchaConfig,
  CaptchaResult,
  CaptchaError,
} from '@pouw/widget';

/**
 * Hook options
 */
export interface UsePoUWCaptchaOptions {
  siteKey: string;
  apiUrl?: string;
  theme?: 'light' | 'dark' | 'auto';
  language?: string;
  invisible?: boolean;
  onSuccess?: (token: string) => void;
  onError?: (error: CaptchaError) => void;
  onExpire?: () => void;
  onProgress?: CaptchaConfig['onProgress'];
}

/**
 * Hook return value
 */
export interface UsePoUWCaptchaReturn {
  token: string | null;
  isLoading: boolean;
  isVerified: boolean;
  error: CaptchaError | null;
  execute: () => Promise<CaptchaResult | null>;
  reset: () => void;
  containerRef: React.RefObject<HTMLDivElement>;
}

/**
 * React hook for PoUW CAPTCHA
 *
 * @example
 * ```tsx
 * function MyForm() {
 *   const { token, isVerified, containerRef, execute } = usePoUWCaptcha({
 *     siteKey: 'your-site-key',
 *   });
 *
 *   return (
 *     <form>
 *       <div ref={containerRef} />
 *       <button disabled={!isVerified}>Submit</button>
 *     </form>
 *   );
 * }
 * ```
 */
export function usePoUWCaptcha(
  options: UsePoUWCaptchaOptions
): UsePoUWCaptchaReturn {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<CaptchaError | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const captchaRef = useRef<PoUWCaptcha | null>(null);

  // Initialize CAPTCHA when container is ready
  useEffect(() => {
    if (!containerRef.current) return;

    const config: CaptchaConfig = {
      siteKey: options.siteKey,
      container: containerRef.current,
      apiUrl: options.apiUrl,
      theme: options.theme,
      language: options.language,
      invisible: options.invisible,
      onSuccess: (t) => {
        setToken(t);
        setError(null);
        options.onSuccess?.(t);
      },
      onError: (e) => {
        setError(e);
        options.onError?.(e);
      },
      onExpire: () => {
        setToken(null);
        options.onExpire?.();
      },
      onProgress: options.onProgress,
    };

    captchaRef.current = new PoUWCaptcha(config);

    return () => {
      captchaRef.current?.destroy();
      captchaRef.current = null;
    };
  }, [options.siteKey]);

  const execute = useCallback(async (): Promise<CaptchaResult | null> => {
    if (!captchaRef.current) return null;

    setIsLoading(true);
    setError(null);

    try {
      const result = await captchaRef.current.execute();
      setToken(result.token);
      return result;
    } catch (err) {
      const captchaError = err as CaptchaError;
      setError(captchaError);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    captchaRef.current?.reset();
    setToken(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return {
    token,
    isLoading,
    isVerified: token !== null,
    error,
    execute,
    reset,
    containerRef,
  };
}

/**
 * Export component wrapper
 */
export { usePoUWCaptcha as default };
