import postgres, { type Sql } from 'postgres';

export type DbClient = Sql;

export interface DbClientOptions {
  /** Postgres connection string, e.g. `postgresql://user:pass@host:5432/db`. */
  connectionString?: string;
  /** Max pool size. Defaults to 10. */
  max?: number;
  /** Statement timeout in seconds. Defaults to 30. */
  statementTimeoutSeconds?: number;
}

/**
 * Create a pooled Postgres client. Reads `DATABASE_URL_TS` then `DATABASE_URL`
 * from the environment when no `connectionString` is supplied.
 *
 * Note: the app's `DATABASE_URL` uses a SQLAlchemy-style scheme
 * (`postgresql+asyncpg://...`); strip the `+driver` suffix for this client.
 */
export function createDbClient(options: DbClientOptions = {}): DbClient {
  const raw =
    options.connectionString ??
    process.env.DATABASE_URL_TS ??
    process.env.DATABASE_URL ??
    '';

  if (!raw) {
    throw new Error(
      'createDbClient: no connection string provided and DATABASE_URL is not set',
    );
  }

  const connectionString = raw.replace(/^postgresql\+\w+:\/\//, 'postgresql://');

  return postgres(connectionString, {
    max: options.max ?? 10,
    idle_timeout: 20,
    connect_timeout: 10,
    connection: {
      statement_timeout: (options.statementTimeoutSeconds ?? 30) * 1000,
    },
  });
}
