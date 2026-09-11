import { NextResponse } from 'next/server';
import { env } from '@/lib/env';

export const dynamic = 'force-dynamic';

/**
 * Aggregated health for the web app: reports the frontend as up and proxies the
 * backend readiness probe so the UI can show one combined status.
 */
export async function GET() {
  const started = Date.now();
  try {
    const res = await fetch(`${env.NEXT_PUBLIC_API_BASE_URL}/health/ready`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });
    const body = (await res.json()) as {
      status: string;
      checks?: Record<string, { status: string }>;
    };

    return NextResponse.json({
      status: res.ok ? 'ok' : 'degraded',
      detail: res.ok
        ? `API reachable in ${Date.now() - started}ms`
        : `API readiness returned ${res.status}`,
      checks: body.checks,
    });
  } catch {
    return NextResponse.json(
      { status: 'error', detail: 'API unreachable from the web server' },
      { status: 200 },
    );
  }
}
