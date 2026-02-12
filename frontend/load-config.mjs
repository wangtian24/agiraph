/**
 * Reads ../config.toml and writes .env.local so Next.js picks up the config.
 * Run before `next dev` or `next build`.
 */

import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tomlPath = resolve(__dirname, "..", "config.toml");

function parseMiniToml(text) {
  const result = {};
  let current = result;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const tableMatch = line.match(/^\[(.+)]$/);
    if (tableMatch) {
      const key = tableMatch[1].trim();
      result[key] = result[key] || {};
      current = result[key];
      continue;
    }
    const kvMatch = line.match(/^(\w+)\s*=\s*(.+)$/);
    if (kvMatch) {
      let val = kvMatch[2].trim();
      // strip inline comments
      const commentIdx = val.indexOf("#");
      if (commentIdx > 0 && val[commentIdx - 1] === " ") {
        val = val.slice(0, commentIdx).trim();
      }
      // strip quotes
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      current[kvMatch[1]] = val;
    }
  }
  return result;
}

try {
  const text = readFileSync(tomlPath, "utf-8");
  const cfg = parseMiniToml(text);

  const serverPort = cfg.server?.port || "8000";
  const frontendPort = cfg.frontend?.port || "3000";

  const envLines = [
    `# Auto-generated from config.toml — do not edit manually`,
    `NEXT_PUBLIC_API_URL=http://localhost:${serverPort}`,
  ];

  writeFileSync(resolve(__dirname, ".env.local"), envLines.join("\n") + "\n");
  console.log(`[config] Loaded config.toml → backend=:${serverPort}, frontend=:${frontendPort}`);
} catch (err) {
  console.warn(`[config] Could not read config.toml, using defaults: ${err.message}`);
}
