#!/usr/bin/env node
/**
 * Thin HTTP wrapper around `gitnexus` CLI for RootSeeker.
 *
 * POST /v1/exec  { args: string[], cwd?: string, timeout_seconds?: number }
 * GET  /healthz
 */
import { spawn } from "node:child_process";
import http from "node:http";
import { existsSync } from "node:fs";

const HOST = process.env.GITNEXUS_HTTP_HOST || "0.0.0.0";
const PORT = Number(process.env.GITNEXUS_HTTP_PORT || 7474);
const DEFAULT_TIMEOUT_MS = Number(process.env.GITNEXUS_HTTP_TIMEOUT_MS || 1_800_000);

function runGitnexus(args, { cwd, timeoutMs }) {
  return new Promise((resolve) => {
    const child = spawn("gitnexus", args, {
      cwd: cwd || process.cwd(),
      env: process.env,
      shell: false,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGKILL");
      resolve({
        ok: false,
        exit_code: 124,
        stdout,
        stderr: `${stderr}\ngitnexus timed out after ${timeoutMs}ms`,
      });
    }, timeoutMs);

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        ok: false,
        exit_code: 127,
        stdout,
        stderr: String(err),
      });
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        ok: code === 0,
        exit_code: code ?? 1,
        stdout,
        stderr,
      });
    });
  });
}

function parseMaybeJson(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    const obj = trimmed.lastIndexOf("{");
    const arr = trimmed.lastIndexOf("[");
    const start = Math.max(obj, arr);
    if (start >= 0) {
      try {
        return JSON.parse(trimmed.slice(start));
      } catch {
        /* ignore */
      }
    }
  }
  return { text: trimmed };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  if (req.method === "GET" && url.pathname === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, service: "gitnexus-sidecar" }));
    return;
  }
  if (req.method !== "POST" || url.pathname !== "/v1/exec") {
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "not found" }));
    return;
  }

  let body = "";
  for await (const chunk of req) body += chunk;
  let payload;
  try {
    payload = JSON.parse(body || "{}");
  } catch (err) {
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: `invalid json: ${err}` }));
    return;
  }

  const args = Array.isArray(payload.args) ? payload.args.map(String) : [];
  if (!args.length) {
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "args required" }));
    return;
  }
  const cwd = payload.cwd ? String(payload.cwd) : undefined;
  if (cwd && !existsSync(cwd)) {
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: `cwd does not exist: ${cwd}` }));
    return;
  }
  const timeoutSeconds = Number(payload.timeout_seconds || 0);
  const timeoutMs = timeoutSeconds > 0 ? timeoutSeconds * 1000 : DEFAULT_TIMEOUT_MS;
  const result = await runGitnexus(args, { cwd, timeoutMs });
  const data = parseMaybeJson(result.stdout);
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ ...result, data }));
});

server.listen(PORT, HOST, () => {
  console.log(`gitnexus sidecar listening on http://${HOST}:${PORT}`);
});
