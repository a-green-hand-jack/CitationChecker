/** Pi 0.85.1 thin adapter. All scientific decisions remain in SKILL.md. */
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, writeFileSync } from "node:fs";
import { join, relative, resolve, isAbsolute } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Obj = Record<string, any>;
const workspace = realpathSync(process.cwd());
const runDir = process.env.CITATIONCHECKER_RUN_DIR!;
const outputDir = join(workspace, "output");
const searchEnabled = process.env.CITATIONCHECKER_ENABLE_PAPER_SEARCH !== "0";
const maxSteps = Number(process.env.CITATIONCHECKER_MAX_STEPS || 12);
const maxTokens = process.env.CITATIONCHECKER_MAX_TOKENS === "none" ? null : Number(process.env.CITATIONCHECKER_MAX_TOKENS || 80000);
const maxOutput = Number(process.env.CITATIONCHECKER_MAX_OUTPUT_TOKENS || 4096);
const state: Obj = {
  schema_version: 2, steps: 0, processed_citation_ids: [], pending_citation_ids: [],
  citation_aliases: {},
  registered: false, tool_counts: {}, artifacts: [], errors: [], last_error: null,
  usage: { input: 0, output: 0, cache_read: 0, cache_write: 0, total: 0 }, usage_known: true,
  max_steps: maxSteps, max_tokens: maxTokens, max_output_tokens: maxOutput,
  stop_reason: null, report_verified: false, final_assistant_stop: null,
};
let artifactIndex = 0;
let failureFeedbacks = 0;
const failureCounts = new Map<string, number>();
const seenMessages = new Set<string>();

export function redact(value: any): any {
  if (typeof value === "string") return value
    .replace(/(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password)(\s*[:=]\s*)(?:Bearer\s+)?["']?[^\s,"'}]+/gi, "$1$2[REDACTED]")
    .replace(/\bsk-[A-Za-z0-9_-]{16,}/g, "[REDACTED]");
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    /^(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|password|credentials?)$/i.test(key) ? "[REDACTED]" : redact(item)]));
  return value;
}
function save() {
  writeFileSync(join(runDir, "state.json.tmp"), JSON.stringify(redact(state), null, 2));
  renameSync(join(runDir, "state.json.tmp"), join(runDir, "state.json"));
}
function emit(type: string, data: Obj) {
  process.stdout.write(JSON.stringify(redact({ type, timestamp: Date.now(), ...data })) + "\n");
}
function snapshot() {
  return { ...state, remaining_steps: Math.max(0, maxSteps - state.steps),
    remaining_tokens: maxTokens === null || !state.usage_known ? null : Math.max(0, maxTokens - state.usage.total) };
}
function budgetReason(): string | null {
  if (state.stop_reason) return state.stop_reason;
  if (!state.usage_known && maxTokens !== null) return "usage_unknown";
  if (maxTokens !== null && state.usage.total >= maxTokens) return "token_limit";
  if (state.steps >= maxSteps) return "step_limit";
  return null;
}
function safePath(path: string, roots = ["input", "output"]): string {
  if (!path || isAbsolute(path)) throw new Error("Use a relative staged workspace path");
  const target = realpathSync(resolve(workspace, path));
  const rel = relative(workspace, target).split("/");
  if (!roots.includes(rel[0]) || rel.includes("..") || rel.some(p => p.startsWith("."))) throw new Error("Path outside allowed staged files");
  return target;
}
function bounded(text: string, limit = 6000): Obj {
  return { observation: redact(text.slice(0, limit)), truncated: text.length > limit };
}
function artifact(prefix: string, text: string): string {
  mkdirSync(join(outputDir, "tool-artifacts"), { recursive: true });
  const path = `./output/tool-artifacts/${prefix}-${String(++artifactIndex).padStart(3, "0")}.txt`;
  writeFileSync(join(workspace, path), redact(text));
  state.artifacts.push(path);
  return path;
}
function result(payload: Obj, terminate = false): Obj {
  const safe = redact(payload);
  return { content: [{ type: "text", text: JSON.stringify(safe) }], details: safe, terminate };
}
function error(kind: string, message: string, retryable = false): Obj {
  return { ok: false, error: { kind, message, retryable,
    next_action: retryable ? "Change the query or source; at most one retry of the identical request is allowed." : "Correct the parameters or report insufficient evidence; do not repeat this request unchanged." } };
}

export function runExternal(command: string, args: string[], timeoutMs: number, signal?: AbortSignal): Promise<Obj> {
  return new Promise(resolveResult => {
    const started = Date.now();
    let stdout = "", stderr = "", timedOut = false, spawnError = "", closed = false;
    const child = spawn(command, args, { cwd: workspace, shell: false, detached: true, stdio: ["ignore", "pipe", "pipe"] });
    let killTimer: ReturnType<typeof setTimeout> | undefined;
    const terminate = () => {
      try { process.kill(-child.pid!, "SIGTERM"); } catch { child.kill("SIGTERM"); }
      killTimer = setTimeout(() => { if (!closed) { try { process.kill(-child.pid!, "SIGKILL"); } catch { child.kill("SIGKILL"); } } }, 1000);
    };
    const timer = setTimeout(() => { timedOut = true; terminate(); }, timeoutMs);
    const append = (old: string, chunk: Buffer) => (old + chunk.toString("utf8")).slice(0, 5_000_000);
    child.stdout.on("data", chunk => { stdout = append(stdout, chunk); });
    child.stderr.on("data", chunk => { stderr = append(stderr, chunk); });
    signal?.addEventListener("abort", terminate, { once: true });
    if (signal?.aborted) terminate();
    child.on("error", err => { spawnError = err.message; });
    child.on("close", exitCode => {
      closed = true; clearTimeout(timer); if (killTimer) clearTimeout(killTimer);
      signal?.removeEventListener("abort", terminate);
      resolveResult({ exit_code: exitCode, stdout, stderr, timed_out: timedOut, spawn_error: spawnError, latency_ms: Date.now() - started });
    });
  });
}
function commandResult(r: Obj, prefix: string, limit = 6000): Obj {
  const text = [r.stdout, r.stderr].filter(Boolean).join("\n");
  const payload: Obj = { ok: r.exit_code === 0 && !r.timed_out && !r.spawn_error,
    exit_code: r.exit_code, latency_ms: r.latency_ms, artifact_path: artifact(prefix, text), ...bounded(text, limit) };
  if (!payload.ok) Object.assign(payload, error(r.spawn_error ? "missing_executable" : r.timed_out ? "timeout" : "nonzero_exit", r.spawn_error || `Command exited ${r.exit_code}`, !r.spawn_error));
  return payload;
}
const str = (description: string) => ({ type: "string", minLength: 1, description });
const integer = (description: string, minimum: number, maximum: number) => ({ type: "integer", description, minimum, maximum });
const schema = (properties: Obj, required: string[]) => ({ type: "object", additionalProperties: false, properties, required });
const contracts: Obj[] = [];

export default function extension(pi: ExtensionAPI) {
  mkdirSync(outputDir, { recursive: true });
  save();
  function register(name: string, description: string, parameters: Obj, execute: (p: Obj, signal?: AbortSignal) => Promise<Obj>) {
    contracts.push({ name, description, parameters });
    pi.registerTool({ name, label: name, description, parameters: parameters as any, executionMode: "sequential",
      async execute(callId, params, signal) {
        const key = `${name}:${JSON.stringify(params)}`;
        if ((failureCounts.get(key) || 0) >= 2) {
          state.stop_reason = "tool_failure"; save();
          return result(error("circuit_open", "Repeated identical failed request"), true);
        }
        let payload: Obj;
        try { payload = await execute(params as Obj, signal); }
        catch (err) { payload = error("invalid_input", String(err)); }
        if (!payload.ok) {
          state.last_error = { tool: name, call_id: callId, ...payload.error };
          state.errors.push(state.last_error);
          failureCounts.set(key, (failureCounts.get(key) || 0) + (payload.error?.retryable ? 1 : 2));
        }
        save();
        return result(payload, state.report_verified || state.stop_reason !== null);
      },
    });
  }
  register("inspect_workspace", "Read staged manuscript/evidence text or register the citation IDs extracted from it. Start with manifest; register IDs before scholarly tools. No shell or network access.", schema({
    operation: { type: "string", enum: ["manifest", "list", "read", "register"] }, path: { type: "string", pattern: "^(input|output)(/|$)", description: "Relative path beginning input/ or output/" },
    offset: integer("Character offset for bounded reading", 0, 5_000_000), max_chars: integer("Maximum returned text characters", 500, 12000),
    citation_ids: { type: "array", uniqueItems: true, maxItems: 1000, items: str("Exact citation key or stable citation-context ID") },
  }, ["operation"]), async p => {
    if (p.operation === "register") {
      if (!Array.isArray(p.citation_ids) || !p.citation_ids.length || p.citation_ids.some((x: any) => typeof x !== "string" || !x.trim())) throw new Error("Register at least one nonempty citation ID");
      state.registered = true;
      state.pending_citation_ids = [...new Set([...state.pending_citation_ids, ...p.citation_ids])].filter(x => !state.processed_citation_ids.includes(x));
      return { ok: true, pending_citation_ids: state.pending_citation_ids };
    }
    const target = safePath(p.operation === "manifest" ? "input/manifest.json" : p.path || "input");
    if (p.operation === "list") return { ok: true, entries: readdirSync(target).slice(0, 100) };
    if (p.operation === "manifest") return { ok: true, manifest: JSON.parse(readFileSync(target, "utf8")) };
    if (p.operation !== "read") throw new Error("Invalid operation");
    const text = readFileSync(target, "utf8");
    const offset = p.offset || 0;
    return { ok: true, path: p.path, offset, total_chars: text.length, ...bounded(text.slice(offset), p.max_chars || 6000) };
  });
  register("verify_references", "Delegate bibliography authenticity/metadata checking to RefChecker. Use the staged manifest target, or a staged .bib file if TeX bibliography extraction fails. Requires registered citation IDs.", schema({
    target: str("Exact staged input path; no URLs, code or external paths"), timeout_seconds: integer("External tool timeout", 5, 180),
  }, []), async (p, signal) => {
    if (!state.registered) throw new Error("Register citation IDs first");
    const manifest = JSON.parse(readFileSync(join(workspace, "input/manifest.json"), "utf8"));
    const target = safePath(p.target || manifest.refchecker_target, ["input"]);
    if (!/\.(tex|bib|pdf|md|txt)$/i.test(target)) throw new Error("Unsupported RefChecker input");
    const reportPath = `./output/refchecker-${artifactIndex + 1}.json`;
    const r = await runExternal("academic-refchecker", ["--paper", target, "--report-file", reportPath, "--report-format", "json"], (p.timeout_seconds || 120) * 1000, signal);
    const payload = commandResult(r, "refchecker");
    // RefChecker can use a nonzero exit for bibliographic findings. Preserve them as observations.
    try {
      const report = JSON.parse(readFileSync(join(workspace, reportPath), "utf8"));
      payload.report_path = reportPath;
      if (!r.timed_out && !r.spawn_error && report.summary?.total_references_processed > 0) { payload.ok = true; delete payload.error; }
    } catch { /* CLI failure retains its exact output and exit code. */ }
    return payload;
  });
  if (searchEnabled) register("retrieve_paper", "Delegate targeted scholarly search/read/download to paper-search. Use after RefChecker identifies a credible source. Returns bounded text and saved evidence artifact; no general network access.", schema({
    operation: { type: "string", enum: ["search", "read", "download"] }, query: str("Title, DOI or identifying search query"),
    source: { type: "string", enum: ["semantic", "crossref", "openalex", "arxiv"] }, paper_id: str("Provider paper ID returned by a search or verified bibliography"),
    max_results: integer("Results per source", 1, 5), max_chars: integer("Observation character cap", 500, 12000), timeout_seconds: integer("External tool timeout", 5, 180),
  }, ["operation"]), async (p, signal) => {
    if (!state.registered) throw new Error("Register citation IDs first");
    let args: string[];
    if (p.operation === "search") {
      if (typeof p.query !== "string" || !p.query.trim()) throw new Error("search requires query");
      args = ["search", p.query, "-n", String(p.max_results || 3), "-s", p.source || "semantic,crossref,openalex,arxiv"];
    } else {
      if (!["read", "download"].includes(p.operation) || !p.source || !p.paper_id) throw new Error("read/download require one source and paper_id");
      args = [p.operation, p.source, p.paper_id, "-o", "./output/papers"];
    }
    const r = await runExternal("paper-search", args, (p.timeout_seconds || 120) * 1000, signal);
    const payload = commandResult(r, `paper-${p.operation}`, p.max_chars || 6000);
    if (payload.ok && p.operation !== "read") {
      try {
        const parsed = JSON.parse(r.stdout);
        if (p.operation === "search" && !Array.isArray(parsed.papers)) Object.assign(payload, error("bad_json", "Search JSON missing papers list"));
        else if (p.operation === "search" && parsed.papers.length === 0 && Object.keys(parsed.errors || {}).length) Object.assign(payload, error("network_error", JSON.stringify(parsed.errors), true));
      } catch { Object.assign(payload, error("bad_json", "Tool output is not valid JSON")); }
    }
    return payload;
  });
  register("write_report", "Submit final citation-report.md and citation-report.json. Uses the mechanical verifier and registered ID coverage. On error repair the report; a verified submission ends the run.", schema({
    markdown: str("Complete Markdown starting with # Citation Audit Report"), report_json: {
      type: "object", properties: { manuscript: str("Manuscript name"), summary: { type: "object" }, citations: { type: "array", items: { type: "object" } } }, required: ["manuscript", "summary", "citations"],
    },
  }, ["markdown", "report_json"]), async (p, signal) => {
    if (!state.registered) throw new Error("Register citation IDs first");
    writeFileSync(join(outputDir, "citation-report.md"), redact(p.markdown));
    writeFileSync(join(outputDir, "citation-report.json"), JSON.stringify(redact(p.report_json), null, 2));
    const r = await runExternal(process.env.CITATIONCHECKER_PYTHON!, ["-m", "citation_checker.runtime.main", "verify", "./output/citation-report.md"], 10000, signal);
    let validation: Obj;
    try { validation = JSON.parse(r.stdout); } catch { return error("invalid_report", `Verifier failed: ${r.stderr || r.stdout}`); }
    const ids = (p.report_json.citations || []).map((x: Obj) => x.citation);
    const expected = [...state.pending_citation_ids, ...state.processed_citation_ids];
    const aliases: Obj = {};
    expected.forEach((id: string, index: number) => { aliases[id] = id; aliases[`[${index + 1}]`] = id; });
    const normalized = ids.map((id: string) => aliases[id] || id);
    const coverage = normalized.length === expected.length && expected.every(x => normalized.includes(x));
    if (!validation.ok || !coverage) return error("invalid_report", JSON.stringify({ errors: validation.errors, missing: expected.filter(x => !normalized.includes(x)), unexpected: ids.filter((x: string) => !aliases[x]) }));
    const used = state.tool_counts.verify_references || 0;
    if (!used) return error("invalid_report", "Report requires an actual RefChecker observation");
    state.citation_aliases = aliases;
    state.processed_citation_ids = expected; state.pending_citation_ids = []; state.report_verified = true; state.stop_reason = "completed";
    return { ok: true, markdown_path: "./output/citation-report.md", json_path: "./output/citation-report.json", total_citations: ids.length };
  });
  writeFileSync(join(runDir, "tool-contracts.json"), JSON.stringify(contracts, null, 2));

  pi.on("context", (event, ctx) => {
    const reason = budgetReason();
    if (reason) { state.stop_reason = reason; save(); ctx.abort(); return; }
    const snap = snapshot();
    emit("citation_state", { state: snap });
    const message = { role: "custom", customType: "citation_state", content: JSON.stringify(snap), display: false, timestamp: Date.now() };
    save();
    return { messages: [...event.messages, message] as any };
  });
  pi.on("before_provider_request", (event, ctx) => {
    const reason = budgetReason();
    if (reason) { state.stop_reason = reason; save(); ctx.abort(); return; }
    const payload = { ...(event.payload as Obj) };
    const cap = Math.min(maxOutput, maxTokens === null ? maxOutput : Math.max(1, maxTokens - state.usage.total));
    if (ctx.model?.api === "openai-completions") {
      if ("max_completion_tokens" in payload) payload.max_completion_tokens = cap;
      else payload.max_tokens = cap;
    } else if (ctx.model?.api?.includes("responses")) payload.max_output_tokens = cap;
    else if (ctx.model?.api === "anthropic-messages") payload.max_tokens = cap;
    else { state.stop_reason = "unsupported_provider_api"; save(); ctx.abort(); return; }
    state.steps += 1;
    emit("citation_request", { step: state.steps, payload });
    save();
    return payload;
  });
  pi.on("message_end", event => {
    const message = event.message as Obj;
    if (message.role !== "assistant") return;
    const id = message.responseId || String(message.timestamp);
    if (seenMessages.has(id)) return;
    seenMessages.add(id);
    const u = message.usage;
    if (!u || !Number.isFinite(u.totalTokens)) state.usage_known = false;
    else if (u.totalTokens > 0) for (const [source, target] of Object.entries({ input: "input", output: "output", cacheRead: "cache_read", cacheWrite: "cache_write", totalTokens: "total" })) state.usage[target] += u[source] || 0;
    state.final_assistant_stop = message.stopReason;
    if (message.stopReason === "error") state.stop_reason = "provider_error";
    if (maxTokens !== null && state.usage.total >= maxTokens) state.stop_reason = "token_limit";
    save();
  });
  pi.on("tool_call", event => {
    // A model response may cross the token cap; never execute its tools afterwards.
    if (state.stop_reason) return { block: true, terminate: true, reason: `CitationChecker stopped: ${state.stop_reason}` };
    state.tool_counts[event.toolName] = (state.tool_counts[event.toolName] || 0) + 1;
    save();
  });
  pi.on("agent_end", (_event, ctx) => {
    if (state.report_verified || state.stop_reason) return;
    const reason = budgetReason();
    if (reason) state.stop_reason = reason;
    else if (failureFeedbacks++ < 1 && state.final_assistant_stop !== "error") {
      pi.sendMessage({ customType: "validation_feedback", content: "No mechanically valid, complete report was submitted. Inspect pending citation IDs and use write_report; repair validation errors within the remaining budget.", display: false }, { triggerTurn: true, deliverAs: "followUp" });
    } else state.stop_reason = "invalid_report";
    save();
  });
  pi.on("agent_settled", () => { emit("citation_final_state", { state }); save(); });
}
