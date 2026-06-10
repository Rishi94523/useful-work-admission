export interface Env {
  POUW_API_ORIGIN?: string;
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers':
    'Content-Type,X-POUW-Site-Key,X-POUW-Secret-Key,X-POUW-Admin-Key',
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (!env.POUW_API_ORIGIN) {
      return json(
        {
          error: 'gateway_not_configured',
          message: 'Set POUW_API_ORIGIN to the public FastAPI backend origin.',
        },
        503
      );
    }

    const incoming = new URL(request.url);
    const upstream = new URL(env.POUW_API_ORIGIN);
    upstream.pathname = incoming.pathname;
    upstream.search = incoming.search;

    const headers = new Headers(request.headers);
    const cfConnectingIp = request.headers.get('CF-Connecting-IP');
    if (cfConnectingIp) {
      headers.set('X-Forwarded-For', cfConnectingIp);
    }
    headers.set('X-POUW-Gateway', 'cloudflare-workers');

    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? null : request.body,
      redirect: 'manual',
    });

    const responseHeaders = new Headers(response.headers);
    for (const [key, value] of Object.entries(CORS_HEADERS)) {
      responseHeaders.set(key, value);
    }
    responseHeaders.set('X-POUW-Gateway', 'cloudflare-workers');

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...CORS_HEADERS,
      'Content-Type': 'application/json',
    },
  });
}
