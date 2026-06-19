#!/usr/bin/env node
/**
 * Smoke-test Cursor MCP servers: vapi (remote), insforge (stdio), nebius (stdio).
 * Usage: node scripts/test-mcps.mjs
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const mcpEnvPath = join(root, ".cursor", "mcp.env");

function loadEnvFile(path) {
  const env = { ...process.env };
  if (!existsSync(path)) return env;
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const i = trimmed.indexOf("=");
    if (i === -1) continue;
    env[trimmed.slice(0, i)] = trimmed.slice(i + 1);
  }
  return env;
}

const env = loadEnvFile(mcpEnvPath);

async function testRemote(name, url, tokenEnv) {
  const token = env[tokenEnv];
  if (!token) {
    return { name, ok: false, detail: `${tokenEnv} missing in .cursor/mcp.env` };
  }
  const client = new Client({ name: "mcp-test", version: "1.0.0" });
  const transport = new StreamableHTTPClientTransport(new URL(url), {
    requestInit: { headers: { Authorization: `Bearer ${token}` } },
  });
  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    const sample = tools.slice(0, 4).map((t) => t.name).join(", ");
    await client.close();
    return {
      name,
      ok: tools.length > 0,
      detail: `${tools.length} tools (${sample}${tools.length > 4 ? ", …" : ""})`,
    };
  } catch (err) {
    try {
      await client.close();
    } catch {
      /* ignore */
    }
    return { name, ok: false, detail: String(err.message || err) };
  }
}

async function testStdio(name, command, args, extraEnv = {}) {
  const client = new Client({ name: "mcp-test", version: "1.0.0" });
  const transport = new StdioClientTransport({
    command,
    args,
    env: { ...env, ...extraEnv },
  });
  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    const sample = tools.slice(0, 4).map((t) => t.name).join(", ");
    await client.close();
    return {
      name,
      ok: tools.length > 0,
      detail: `${tools.length} tools (${sample}${tools.length > 4 ? ", …" : ""})`,
    };
  } catch (err) {
    try {
      await client.close();
    } catch {
      /* ignore */
    }
    return { name, ok: false, detail: String(err.message || err) };
  }
}

async function testNebiusCli() {
  return new Promise((resolve) => {
    const child = spawn("nebius", ["profile", "list"], { env: process.env });
    child.on("error", (err) => {
      resolve({
        ok: false,
        detail:
          err.code === "ENOENT"
            ? "nebius CLI not installed (MCP needs `nebius` CLI + configured profile)"
            : `nebius CLI error: ${err.message}`,
      });
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", (code) => {
      if (code === 0 && out.trim()) {
        resolve({ ok: true, detail: `CLI profiles: ${out.trim().split("\n")[0].slice(0, 60)}` });
        return;
      }
      resolve({
        ok: false,
        detail: `nebius profile list failed (exit ${code}): ${(err || out).trim().slice(0, 120)}`,
      });
    });
  });
}

async function main() {
  console.log("MCP smoke tests (multimodal-hackathon)\n");

  const results = [];

  results.push(
    await testRemote("vapi", "https://mcp.vapi.ai/mcp", "VAPI_TOKEN"),
  );

  if (!env.API_KEY || !env.API_BASE_URL) {
    results.push({
      name: "insforge",
      ok: false,
      detail: "API_KEY or API_BASE_URL missing in .cursor/mcp.env — run ./scripts/sync-mcp-env.sh",
    });
  } else {
    results.push(
      await testStdio("insforge", "npx", ["-y", "@insforge/mcp@latest"]),
    );
  }

  const nebius = await testStdio("nebius", "uvx", [
    "--refresh-package",
    "nebius-mcp-server",
    "nebius-mcp-server@git+https://github.com/nebius/mcp-server@main",
  ], { SAFE_MODE: "true" }).catch((err) => ({
    name: "nebius",
    ok: false,
    detail: String(err.message || err),
  }));
  if (!nebius.ok) {
    const cli = await testNebiusCli();
    nebius.detail = `${nebius.detail} | ${cli.detail}`;
  }
  results.push(nebius);

  let allOk = true;
  for (const r of results) {
    const mark = r.ok ? "PASS" : "FAIL";
    if (!r.ok) allOk = false;
    console.log(`${mark}  ${r.name.padEnd(10)} ${r.detail}`);
  }

  console.log(allOk ? "\nAll MCP servers OK." : "\nSome MCP servers failed — see above.");
  process.exit(allOk ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
