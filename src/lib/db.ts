import "server-only";

import mysql from "mysql2/promise";
import type { Pool } from "mysql2/promise";

type GlobalWithPool = typeof globalThis & { plus11MysqlPool?: Pool };

function connectionOptions(): mysql.PoolOptions {
  const raw = process.env.DATABASE_URL;
  if (!raw) throw new Error("The managed database connection is not configured.");

  const url = new URL(raw);
  if (url.protocol !== "mysql:") throw new Error("The managed database connection must use MySQL.");
  const database = decodeURIComponent(url.pathname.replace(/^\//, ""));
  if (!database) throw new Error("The managed database name is missing.");

  return {
    host: url.hostname,
    port: url.port ? Number(url.port) : 3306,
    user: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
    database,
    waitForConnections: true,
    connectionLimit: 6,
    maxIdle: 3,
    idleTimeout: 60_000,
    queueLimit: 50,
    timezone: "Z",
    dateStrings: true,
    ssl: { rejectUnauthorized: true },
  };
}

export function getPool(): Pool {
  const globalPool = globalThis as GlobalWithPool;
  if (!globalPool.plus11MysqlPool) {
    const pool = mysql.createPool(connectionOptions());
    pool.on("connection", (connection) => {
      connection.query("SET time_zone = '+00:00'");
    });
    globalPool.plus11MysqlPool = pool;
  }
  return globalPool.plus11MysqlPool;
}
