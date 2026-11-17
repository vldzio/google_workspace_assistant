// Vercel build step: write demo/config.js from environment variables.
//   DEMO_API_URL   base URL of the Hugging Face Space API (required for live LLM features)
//   DEMO_TITLE / DEMO_SOURCE_URL / DEMO_NOTE  optional overrides
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const target = join(dir, "config.js");
const base = existsSync(target) ? readFileSync(target, "utf8") : "";
const m = base.match(/window\.DEMO_CONFIG\s*=\s*(\{[\s\S]*?\})\s*;/);
let cfg = {};
try { cfg = m ? JSON.parse(m[1]) : {}; } catch { cfg = {}; }

const env = process.env;
if (env.DEMO_API_URL) cfg.API_URL = env.DEMO_API_URL.replace(/\/+$/, "");
if (env.DEMO_TITLE) cfg.TITLE = env.DEMO_TITLE;
if (env.DEMO_SOURCE_URL) cfg.SOURCE_URL = env.DEMO_SOURCE_URL;
if (env.DEMO_NOTE) cfg.NOTE = env.DEMO_NOTE;

writeFileSync(target, "// Generated at build time (see write-config.mjs)\nwindow.DEMO_CONFIG = " + JSON.stringify(cfg, null, 2) + ";\n");
console.log("demo/config.js ->", cfg.API_URL || "(no API_URL set)");
