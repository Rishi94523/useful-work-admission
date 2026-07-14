import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../src/core/api-client';
import { Config } from '../src/core/config';

describe('ApiClient model selection', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    Object.defineProperty(globalThis, 'fetch', {
      value: fetchMock,
      writable: true,
    });
  });

  it('sends the explicitly requested transformer model', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    } as Response);
    const container = document.createElement('div');
    const config = new Config({
      siteKey: 'pk_test',
      apiUrl: 'http://localhost:8000/api/v1',
      container,
      preferredModel: 'llm-qwen2-sentiment',
      theme: 'light',
      language: 'en',
    });
    const client = new ApiClient(config);

    await client.initSession({
      userAgent: 'test',
      language: 'en',
      timezone: 'UTC',
      screenWidth: 1280,
      screenHeight: 720,
    });

    const calls = fetchMock.mock.calls as unknown as Array<
      [RequestInfo | URL, RequestInit]
    >;
    const request = calls[0][1];
    const body = JSON.parse(String(request?.body)) as Record<string, unknown>;
    expect(body.preferred_model).toBe('llm-qwen2-sentiment');
  });
});
