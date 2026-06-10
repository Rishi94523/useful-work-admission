/**
 * Server-side helpers for validating PoUW CAPTCHA tokens.
 *
 * Never call these helpers from browser code: `secretKey` must stay on the
 * application backend.
 */

export interface ValidateCaptchaTokenOptions {
  token: string;
  secretKey: string;
  apiUrl?: string;
}

export interface ValidateCaptchaTokenResult {
  valid: boolean;
  sessionId?: string;
  domain?: string;
  completedAt?: string;
  difficulty?: 'normal' | 'suspicious' | 'bot_like';
  verificationPerformed?: boolean;
}

export async function validateCaptchaToken(
  options: ValidateCaptchaTokenOptions
): Promise<ValidateCaptchaTokenResult> {
  const apiUrl = options.apiUrl || 'https://api.pouw.dev/v1';
  const response = await fetch(
    `${apiUrl}/captcha/validate/${encodeURIComponent(options.token)}`,
    {
      method: 'GET',
      headers: {
        'X-POUW-Secret-Key': options.secretKey,
      },
    }
  );

  if (!response.ok) {
    return { valid: false };
  }

  return (await response.json()) as ValidateCaptchaTokenResult;
}
