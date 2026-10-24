import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import mysql from "mysql2/promise";

function connectionOptions() {
  const raw = process.env.DATABASE_URL;
  if (!raw) throw new Error("DATABASE_URL is not available in this runtime.");
  const url = new URL(raw);
  if (url.protocol !== "mysql:") throw new Error("DATABASE_URL must use the mysql: protocol.");
  const options = {
    host: url.hostname,
    port: url.port ? Number(url.port) : 3306,
    user: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
    database: decodeURIComponent(url.pathname.replace(/^\//, "")),
    waitForConnections: true,
    connectionLimit: 1,
    timezone: "Z",
    ssl: { rejectUnauthorized: true },
  };
  return options;
}

let pool;
const migrationName = "001_plus11_learning";
const sqlPath = fileURLToPath(new URL("../migrations/001_plus11_learning.sql", import.meta.url));

try {
  pool = mysql.createPool(connectionOptions());
  await pool.query(`CREATE TABLE IF NOT EXISTS plus11_schema_migrations (
    migration_name VARCHAR(120) NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (migration_name)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`);

  const sql = await readFile(sqlPath, "utf8");
  const checksum = createHash("sha256").update(sql).digest("hex");
  const [existing] = await pool.execute(
    "SELECT checksum FROM plus11_schema_migrations WHERE migration_name = ? LIMIT 1",
    [migrationName],
  );

  if (existing.length) {
    if (existing[0].checksum !== checksum) {
      throw new Error(`Migration ${migrationName} has already been applied with a different checksum.`);
    }
    console.log(`${migrationName} is already applied; no changes made.`);
  } else {
    const statements = sql.split(/;\s*(?:\n|$)/).map((part) => part.trim()).filter(Boolean);
    for (const statement of statements) await pool.query(statement);
    await pool.execute(
      "INSERT INTO plus11_schema_migrations (migration_name, checksum) VALUES (?, ?)",
      [migrationName, checksum],
    );
    console.log(`${migrationName} applied successfully (${statements.length} additive statements).`);
  }
} catch (error) {
  console.error("Plus11 database migration failed. No credential values were logged.");
  const errorCode = error && typeof error === "object" && "code" in error ? String(error.code) : "unknown";
  console.error(`Migration error code: ${errorCode}`);
  process.exitCode = 1;
} finally {
  await pool?.end();
}
