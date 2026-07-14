import { afterEach, describe, expect, it, vi } from 'vitest';

import { validateCaptchaToken } from '../src/server';

describe('validateCaptchaToken', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the secret only in the backend validation header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ valid: true, sessionId: 'session-1' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await validateCaptchaToken({
      token: 'token/value',
      secretKey: 'sk_private',
      apiUrl: 'https://captcha.example/v1',
    });

    expect(result).toEqual({ valid: true, sessionId: 'session-1' });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://captcha.example/v1/captcha/validate/token%2Fvalue',
      {
        method: 'GET',
        headers: { 'X-POUW-Secret-Key': 'sk_private' },
      }
    );
  });

  it('returns invalid when the API rejects the token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));

    await expect(
      validateCaptchaToken({ token: 'bad', secretKey: 'sk_private' })
    ).resolves.toEqual({ valid: false });
  });
});
