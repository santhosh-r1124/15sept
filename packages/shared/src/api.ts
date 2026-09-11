/**
 * API contract types shared by the frontends. These mirror the response
 * envelopes produced by `apps/api` (see `app/core/errors.py` and
 * `app/api/v1/routes/health.py`).
 */

/** Standard error envelope returned by the API for every non-2xx response. */
export interface ApiError {
  error: {
    /** Stable machine-readable code, e.g. `not_found`, `validation_error`. */
    code: string;
    /** Human-readable summary, safe to surface to end users. */
    message: string;
    /** Optional field-level details for validation errors. */
    details?: Array<{ field: string; message: string }>;
    /** Correlates with the `X-Request-ID` response header and server logs. */
    request_id: string;
  };
}

export type HealthState = 'ok' | 'degraded' | 'error';

export interface HealthCheckComponent {
  status: HealthState;
  latency_ms?: number;
  detail?: string;
}

export interface ReadinessResponse {
  status: HealthState;
  version: string;
  environment: 'development' | 'staging' | 'production';
  checks: Record<string, HealthCheckComponent>;
}

export interface LivenessResponse {
  status: 'ok';
  service: string;
  version: string;
}

export function isApiError(value: unknown): value is ApiError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error: unknown }).error === 'object'
  );
}
