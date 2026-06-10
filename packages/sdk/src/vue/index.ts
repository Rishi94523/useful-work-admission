/**
 * Vue composable for PoUW CAPTCHA
 */

import { ref, onMounted, onUnmounted, Ref } from 'vue';
import {
  PoUWCaptcha,
  CaptchaConfig,
  CaptchaResult,
  CaptchaError,
} from '@pouw/widget';

/**
 * Composable options
 */
export interface UsePoUWCaptchaOptions {
  siteKey: string;
  apiUrl?: string;
  theme?: 'light' | 'dark' | 'auto';
  language?: string;
  invisible?: boolean;
  onProgress?: CaptchaConfig['onProgress'];
}

/**
 * Composable return value
 */
export interface UsePoUWCaptchaReturn {
  token: Ref<string | null>;
  isLoading: Ref<boolean>;
  isVerified: Ref<boolean>;
  error: Ref<CaptchaError | null>;
  containerRef: Ref<HTMLElement | null>;
  execute: () => Promise<CaptchaResult | null>;
  reset: () => void;
}

/**
 * Vue composable for PoUW CAPTCHA
 *
 * @example
 * ```vue
 * <script setup>
 * import { usePoUWCaptcha } from '@pouw/sdk/vue';
 *
 * const { token, isVerified, containerRef, execute } = usePoUWCaptcha({
 *   siteKey: 'your-site-key',
 * });
 * </script>
 *
 * <template>
 *   <form>
 *     <div ref="containerRef" />
 *     <button :disabled="!isVerified">Submit</button>
 *   </form>
 * </template>
 * ```
 */
export function usePoUWCaptcha(
  options: UsePoUWCaptchaOptions
): UsePoUWCaptchaReturn {
  const token = ref<string | null>(null);
  const isLoading = ref(false);
  const isVerified = ref(false);
  const error = ref<CaptchaError | null>(null);
  const containerRef = ref<HTMLElement | null>(null);

  let captcha: PoUWCaptcha | null = null;

  onMounted(() => {
    if (!containerRef.value) return;

    const config: CaptchaConfig = {
      siteKey: options.siteKey,
      container: containerRef.value,
      apiUrl: options.apiUrl,
      theme: options.theme,
      language: options.language,
      invisible: options.invisible,
      onSuccess: (t) => {
        token.value = t;
        isVerified.value = true;
        error.value = null;
      },
      onError: (e) => {
        error.value = e;
      },
      onExpire: () => {
        token.value = null;
        isVerified.value = false;
      },
      onProgress: options.onProgress,
    };

    captcha = new PoUWCaptcha(config);
  });

  onUnmounted(() => {
    captcha?.destroy();
    captcha = null;
  });

  async function execute(): Promise<CaptchaResult | null> {
    if (!captcha) return null;

    isLoading.value = true;
    error.value = null;

    try {
      const result = await captcha.execute();
      token.value = result.token;
      isVerified.value = true;
      return result;
    } catch (err) {
      error.value = err as CaptchaError;
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  function reset(): void {
    captcha?.reset();
    token.value = null;
    isVerified.value = false;
    error.value = null;
    isLoading.value = false;
  }

  return {
    token,
    isLoading,
    isVerified,
    error,
    containerRef,
    execute,
    reset,
  };
}

export default usePoUWCaptcha;
