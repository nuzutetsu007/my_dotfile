#!/usr/bin/env node
/**
 * KIE Official CLI & Local MCP Server — Zero-dependency Node 18+ tool for discovering,
 * pricing, reading specs, checking per-task catalog price bounds, and running AI models on KIE.
 *
 * Usage:
 *   node kie-cli.mjs list [--task "Text to Image"] [--provider Google] [--q veo] [--json]
 *   node kie-cli.mjs doc <model_id_or_slug>
 *   node kie-cli.mjs price [keyword] [--json]
 *   node kie-cli.mjs balance
 *   node kie-cli.mjs run <model_id> --input '{"prompt":"..."}' [--max-credits 20] [--out ./out.png]
 *   node kie-cli.mjs status <task_id> [--wait 15] [--out ./out.mp4]
 *   node kie-cli.mjs mcp   # Start non-blocking stdio MCP server for Claude Desktop / Cursor / Windsurf
 */

import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { pathToFileURL } from 'node:url';

const getApiBase = () => (process.env.KIE_API_BASE || 'https://api.kie.ai').replace(/\/+$/, '');
const getSiteBase = () => (process.env.KIE_SITE_BASE || 'https://kie.ai').replace(/\/+$/, '');
const getApiKey = () => (process.env.KIE_API_KEY || '').trim();

export function parseFlags(args) {
  const pos = [];
  const flags = {};
  for (let i = 0; i < args.length; i += 1) {
    const a = args[i];
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq !== -1) {
        flags[a.slice(2, eq)] = a.slice(eq + 1);
      } else if (i + 1 < args.length && !args[i + 1].startsWith('--')) {
        flags[a.slice(2)] = args[i + 1];
        i += 1;
      } else {
        flags[a.slice(2)] = 'true';
      }
    } else {
      pos.push(a);
    }
  }
  return { pos, flags };
}

async function getJson(url, opts = {}) {
  const res = await fetch(url, { ...opts, signal: AbortSignal.timeout(30000) });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`HTTP ${res.status} non-JSON from ${url}: ${text.slice(0, 200)}`);
  }
  if (!res.ok || (data.code !== undefined && data.code !== 200)) {
    throw new Error(`API error (${data.code ?? res.status}): ${data.msg || text.slice(0, 200)}`);
  }
  return data.data;
}

export async function fetchLiveModels({ task = '', provider = '', q = '' } = {}) {
  const apiKey = getApiKey();
  if (apiKey) {
    const params = new URLSearchParams();
    if (task) params.set('taskType', task);
    if (provider) params.set('provider', provider);
    if (q) params.set('q', q);
    const qs = params.toString();
    const data = await getJson(`${getApiBase()}/api/v1/models${qs ? `?${qs}` : ''}`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    return data?.models || [];
  }

  // Unauthenticated fallback: public playground groups catalog
  const raw = await getJson(`${getApiBase()}/api/v1/playground/pagePlaygroundGroup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pageNum: 1, pageSize: 500, groupName: q || '', tasks: [], provider: [] }),
  });
  const list = Array.isArray(raw) ? raw : raw?.records || [];
  const taskLower = task.toLowerCase();
  const provLower = provider.toLowerCase();
  const qLower = q.toLowerCase();

  return list
    .filter((g) => {
      const name = String(g.groupName || '');
      if (/\(\s*coming\s+soon\s*\)\s*$/i.test(name) || Number(g.count) === 0) return false;
      if (provLower && !String(g.provider || '').toLowerCase().includes(provLower)) return false;
      if (taskLower && !JSON.stringify(g.taskType || []).toLowerCase().includes(taskLower))
        return false;
      if (
        qLower &&
        !`${g.path || ''} ${name} ${g.provider || ''}`.toLowerCase().includes(qLower)
      ) {
        return false;
      }
      return true;
    })
    .map((g) => ({
      model: String(g.path || '').replace(/^\/+/, ''),
      slug: String(g.path || '').replace(/^\/+/, ''),
      title: g.groupName,
      provider: g.provider,
      taskType: g.taskType || [],
    }));
}

export async function fetchPricingRows(kw = '') {
  const data = await getJson(`${getApiBase()}/client/v1/model-pricing/page`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pageNum: 1,
      pageSize: 100,
      modelDescription: kw.trim(),
      interfaceType: '',
    }),
  });
  return data?.records || data?.list || [];
}

export async function fetchCreditBalance() {
  const apiKey = getApiKey();
  if (!apiKey) {
    throw new Error(
      'Missing KIE_API_KEY. Create one at https://kie.ai/api-key and export KIE_API_KEY=your_key'
    );
  }
  return getJson(`${getApiBase()}/api/v1/chat/credit`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
}

export async function fetchModelDocText(rawTarget) {
  const target = String(rawTarget || '').replace(/^\/+/, '');
  if (!target) throw new Error('Usage: kie-cli.mjs doc <model_id_or_page_slug>');

  const apiKey = getApiKey();
  if (apiKey) {
    try {
      const schemaRes = await fetch(`${getApiBase()}/api/v1/models/${target}/schema`, {
        headers: { Authorization: `Bearer ${apiKey}` },
        signal: AbortSignal.timeout(20000),
      });
      if (schemaRes.ok) {
        const parsed = await schemaRes.json();
        if (parsed?.code === 200 && parsed?.data?.openapi) {
          return JSON.stringify(parsed.data, null, 2);
        }
      }
    } catch {
      // Fall back to public .md endpoint
    }
  }

  const mdRes = await fetch(`${getSiteBase()}/model/${target}.md`, {
    signal: AbortSignal.timeout(20000),
  });
  if (mdRes.ok) return mdRes.text();

  throw new Error(`No schema or Markdown spec found for "${target}"`);
}

function extractResultUrls(taskData) {
  const rj = taskData?.resultJson;
  if (!rj) return [];
  const obj = typeof rj === 'string' ? JSON.parse(rj) : rj;
  if (Array.isArray(obj?.resultUrls)) return obj.resultUrls;
  if (Array.isArray(obj?.result_urls)) return obj.result_urls;
  if (Array.isArray(obj?.data?.resultUrls)) return obj.data.resultUrls;
  if (Array.isArray(obj?.data?.result_urls)) return obj.data.result_urls;
  if (Array.isArray(obj?.data?.origin_urls)) return obj.data.origin_urls;
  if (typeof obj?.resultUrl === 'string') return [obj.resultUrl];
  if (typeof obj?.video_url === 'string') return [obj.video_url];
  if (typeof obj?.audio_url === 'string') return [obj.audio_url];
  return [];
}

const VENDOR_PREFIXES = new Set([
  'google',
  'bytedance',
  'black-forest-labs',
  'kling',
  'wan',
  'hailuo',
  'ideogram',
  'recraft',
  'topaz',
  'elevenlabs',
  'suno',
  'minimax',
  'qwen',
  'openai',
]);

function normWords(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/(\d)-(\d)/g, '$1.$2')
    .replace(/[^a-z0-9.]+/g, ' ')
    .trim();
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function hasBoundaryToken(haystack, token) {
  const t = String(token || '').trim().toLowerCase();
  if (!t) return false;
  const re = new RegExp(`(^|[^a-z0-9])${escapeRe(t)}($|[^a-z0-9])`, 'i');
  return re.test(String(haystack || ''));
}

function normalizeModelTierHint(raw) {
  const v = String(raw || '').trim().toLowerCase();
  if (!v) return '';
  if (v === 'veo3') return 'quality';
  return v.replace(/^veo3_/, '');
}

/**
 * Per-task catalog price check (`--max-credits` / `KIE_MAX_CREDITS`):
 * Queries live KIE catalog rows, isolates the exact model family & sub-endpoint, narrows by explicit
 * `input` tier/resolution hints, multiplies by duration/quantity, and takes the CONSERVATIVE UPPER BOUND
 * (`Math.max`) so higher-priced tiers cannot slip past. Exits locally with code 3 before sending if exceeded.
 */
export async function checkMaxCreditsGuard(model, input, maxCreditsRaw) {
  const effectiveRaw =
    maxCreditsRaw !== undefined && maxCreditsRaw !== ''
      ? maxCreditsRaw
      : (process.env.KIE_MAX_CREDITS || '').trim() || undefined;
  if (effectiveRaw === undefined) return;

  const ceiling = Number(effectiveRaw);
  if (!Number.isFinite(ceiling) || ceiling < 0) {
    const err = new Error(`Invalid --max-credits value: ${effectiveRaw}`);
    err.exitCode = 2;
    throw err;
  }

  const rawModel = String(model || '').trim();
  const [slashLeft, slashRight = ''] = rawModel.split('/');
  const strippedModality = rawModel.replace(
    /[-/](?:text-to-image|image-to-image|text-to-video|image-to-video)$/i,
    ''
  );
  const coreSlug =
    slashRight && VENDOR_PREFIXES.has(slashLeft.toLowerCase()) ? slashRight : strippedModality;
  const coreWords = normWords(coreSlug.replace(/^veo3_/, 'veo-3-1'));
  const modalityMatch = rawModel.match(/(text-to-image|image-to-image|text-to-video|image-to-video)/i);
  const explicitSub =
    slashRight && !VENDOR_PREFIXES.has(slashLeft.toLowerCase()) && !modalityMatch
      ? normWords(slashRight)
      : '';

  const leftWords = normWords(slashLeft).split(' ').filter(Boolean);
  const reorderedImageQuery =
    leftWords.length >= 2 && /image/i.test(slashRight)
      ? `${leftWords[0]} image ${leftWords.slice(1).join(' ')}`
      : '';
  const familyRoot = slashLeft.includes('-') ? slashLeft.split('-')[0] : '';

  const candidateQueries = [
    ...new Set(
      [
        rawModel,
        reorderedImageQuery,
        coreWords,
        coreSlug,
        normWords(slashLeft),
        familyRoot,
        !VENDOR_PREFIXES.has(slashLeft.toLowerCase()) ? slashLeft : '',
      ]
        .map((q) => String(q || '').trim())
        .filter((q) => q.length >= 2)
    ),
  ];

  let rows = [];
  for (const q of candidateQueries) {
    const fetched = await fetchPricingRows(q);
    if (!fetched.length) continue;
    const reqTokens = coreWords.split(' ').filter(Boolean);
    const tokMatched = fetched.filter((r) => {
      const descNorm = normWords(r.modelDescription || '');
      const words = descNorm.split(' ');
      if (!reqTokens.every((tk) => words.includes(tk))) return false;
      if (explicitSub) {
        const segs = String(r.modelDescription || '')
          .split(',')
          .map((s) => normWords(s));
        return segs.includes(explicitSub);
      }
      return true;
    });
    if (tokMatched.length) {
      rows = tokMatched;
      break;
    }
    if (!rows.length && !explicitSub) rows = fetched;
  }

  // Exclude token-billed chat rows & isolate exact model head when possible (e.g. "google nano banana" vs "google nano banana pro")
  const mediaRows = rows.filter(
    (r) => !String(r.creditUnit || '').toLowerCase().includes('million tokens')
  );
  if (mediaRows.length) rows = mediaRows;

  const exactHead = rows.filter((r) => {
    const head = normWords(String(r.modelDescription || '').split(',')[0]);
    return head === coreWords || head.endsWith(` ${coreWords}`);
  });
  if (exactHead.length) rows = exactHead;

  // Separate per-reference-image add-on rows (e.g. "(each)") from base generation rows
  const addonRows = rows.filter((r) => /\(each\)/i.test(String(r.modelDescription || '')));
  const baseRows = rows.filter((r) => !/\(each\)/i.test(String(r.modelDescription || '')));
  if (baseRows.length) rows = baseRows;

  // Narrow by sub-endpoint / modality (comma-segment or boundary match so "image" never matches "long-image")
  const subEndpointHints = [
    slashRight && !VENDOR_PREFIXES.has(slashLeft.toLowerCase()) ? slashRight : '',
    modalityMatch ? modalityMatch[1] : '',
  ].filter(Boolean);

  for (const subH of subEndpointHints) {
    const normSub = normWords(subH);
    const exactSeg = rows.filter((r) =>
      String(r.modelDescription || '')
        .split(',')
        .slice(1)
        .some((seg) => normWords(seg) === normSub)
    );
    if (exactSeg.length) {
      rows = exactSeg;
      continue;
    }
    const boundSeg = rows.filter((r) => hasBoundaryToken(r.modelDescription, subH));
    if (boundSeg.length) rows = boundSeg;
  }

  // Video reference-input disambiguation ("with video" vs "no video", e.g. Seedance)
  const hasRefVideo = Boolean(
    input?.video_url || (Array.isArray(input?.video_urls) && input.video_urls.length > 0)
  );
  const videoRefTag = hasRefVideo ? 'with video' : 'no video';
  const videoRefSub = rows.filter((r) =>
    String(r.modelDescription || '')
      .toLowerCase()
      .includes(videoRefTag)
  );
  if (videoRefSub.length) rows = videoRefSub;

  const rawDur = input?.duration !== undefined && input?.duration !== '' ? Number(input.duration) : NaN;
  const durHint = Number.isFinite(rawDur) && rawDur > 0 ? `${rawDur.toFixed(1)}s` : '';

  // Narrow by explicit input tier/resolution/skill/length/duration hints on token boundaries
  const hints = [
    normalizeModelTierHint(rawModel.startsWith('veo3') ? rawModel : ''),
    normalizeModelTierHint(input?.model),
    input?.skill,
    input?.length,
    input?.mode,
    input?.quality,
    input?.resolution,
    durHint,
  ]
    .filter((v) => typeof v === 'string' && v.trim())
    .map((v) => v.trim().toLowerCase());

  for (const h of hints) {
    const sub = rows.filter((r) => {
      const desc = String(r.modelDescription || '');
      if (hasBoundaryToken(desc, h)) return true;
      // Handle combined shorthand like "1/2K" when hint is "1k" or "2k"
      if ((h === '1k' || h === '2k') && /1\/2k/i.test(desc)) return true;
      return false;
    });
    if (sub.length > 0) rows = sub;
  }

  const durSec = Number(input?.duration) > 0 ? Number(input.duration) : 15;
  const qty = Math.max(
    1,
    Number(
      input?.count ?? input?.num_images ?? input?.n ?? input?.num_outputs ?? input?.batch_size ?? 1
    ) || 1
  );
  const refImgCount = Array.isArray(input?.image_urls) ? input.image_urls.length : 0;
  const addonPerImg = addonRows.length
    ? Math.max(...addonRows.map((r) => Number(r.creditPrice) || 0))
    : 0;
  const addonTotal = refImgCount > 0 && addonPerImg > 0 ? refImgCount * addonPerImg : 0;

  const estimated = rows
    .map((r) => {
      const unitPrice = Number(r.creditPrice);
      if (!Number.isFinite(unitPrice) || unitPrice <= 0) return NaN;
      const unit = String(r.creditUnit || '').toLowerCase();
      if (unit.includes('per second')) return unitPrice * durSec * qty + addonTotal;
      return unitPrice * qty + addonTotal;
    })
    .filter((n) => Number.isFinite(n) && n > 0);

  if (!estimated.length) {
    const err = new Error(
      `Per-task price check blocked request: no verified catalog price found for "${model}". Omit --max-credits only if you intend to proceed without a pre-flight catalog check.`
    );
    err.exitCode = 3;
    throw err;
  }

  const upperBound = Math.max(...estimated);
  if (upperBound > ceiling) {
    const err = new Error(
      `Per-task price check blocked request: "${model}" can cost up to ${upperBound} credits in the catalog for these parameters, which exceeds --max-credits ${ceiling}. Nothing was sent.`
    );
    err.exitCode = 3;
    throw err;
  }
}

/**
 * In MCP mode the caller is an LLM, not a human typing at a shell:
 * confine output paths strictly inside `KIE_OUTPUT_DIR` (or `process.cwd()`) and refuse overwrites.
 */
export function resolveSafeMcpOutputPath(
  rawOutPath,
  baseDir = process.env.KIE_OUTPUT_DIR || process.cwd()
) {
  const rootDir = path.resolve(baseDir);
  fs.mkdirSync(rootDir, { recursive: true });
  const rootReal = fs.realpathSync(rootDir);

  const candidate = path.resolve(rootReal, String(rawOutPath));
  const relCheck = path.relative(rootReal, candidate);
  if (relCheck.startsWith('..') || path.isAbsolute(relCheck)) {
    throw new Error(
      `Refused outPath "${rawOutPath}": MCP file writes must stay inside ${rootReal}`
    );
  }

  const parentDir = path.dirname(candidate);
  fs.mkdirSync(parentDir, { recursive: true });
  const parentReal = fs.realpathSync(parentDir);
  const parentRel = path.relative(rootReal, parentReal);
  if (parentRel.startsWith('..') || path.isAbsolute(parentRel)) {
    throw new Error(`Refused outPath "${rawOutPath}": symlink escapes ${rootReal}`);
  }

  const finalDest = path.join(parentReal, path.basename(candidate));
  if (fs.existsSync(finalDest)) {
    throw new Error(`Refused outPath "${rawOutPath}": file already exists (overwrite not allowed)`);
  }
  return finalDest;
}

async function saveUrlToFile(url, outPath, { mcpSandbox = false } = {}) {
  const dest = mcpSandbox ? resolveSafeMcpOutputPath(outPath) : path.resolve(outPath);
  if (!mcpSandbox) {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
  }
  const fileRes = await fetch(url, { signal: AbortSignal.timeout(60000) });
  if (!fileRes.ok) throw new Error(`Failed to download ${url}: HTTP ${fileRes.status}`);
  const buf = Buffer.from(await fileRes.arrayBuffer());
  fs.writeFileSync(dest, buf, mcpSandbox ? { flag: 'wx' } : undefined);
  return dest;
}

export async function submitTask({ model, input, maxCredits }) {
  const apiKey = getApiKey();
  if (!apiKey) {
    throw new Error(
      'Missing KIE_API_KEY. Create one at https://kie.ai/api-key and export KIE_API_KEY=your_key'
    );
  }
  await checkMaxCreditsGuard(model, input, maxCredits);

  const created = await getJson(`${getApiBase()}/api/v1/jobs/createTask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ model, input }),
  });
  const taskId = created?.taskId;
  if (!taskId) throw new Error(`Unexpected task response: ${JSON.stringify(created)}`);
  return taskId;
}

export async function pollTaskWindow({
  taskId,
  waitSec = 600,
  pollIntervalMs = 2500,
  outPath,
  mcpSandbox = false,
  throwOnTimeout = true,
}) {
  const apiKey = getApiKey();
  if (!apiKey) throw new Error('Missing KIE_API_KEY.');
  const deadline = Date.now() + Math.max(0, Number(waitSec)) * 1000;

  while (true) {
    const status = await getJson(
      `${getApiBase()}/api/v1/jobs/recordInfo?taskId=${encodeURIComponent(taskId)}`,
      {
        headers: { Authorization: `Bearer ${apiKey}` },
      }
    );
    const state = String(status?.state || '').toLowerCase();
    if (state === 'success') {
      const urls = extractResultUrls(status);
      let savedFile = null;
      if (outPath && urls[0]) {
        savedFile = await saveUrlToFile(urls[0], outPath, { mcpSandbox });
      }
      return {
        taskId,
        state,
        creditsConsumed: status?.creditsConsumed ?? null,
        urls,
        savedFile,
        resultJson: status.resultJson,
      };
    }
    if (state === 'fail' || state === 'failed') {
      throw new Error(
        `Task ${taskId} failed: ${status?.failMsg || status?.failCode || JSON.stringify(status)}`
      );
    }
    if (Date.now() >= deadline) {
      if (throwOnTimeout) {
        throw new Error(
          `Timed out waiting for task ${taskId}. Resume polling with: node kie-cli.mjs status ${taskId}`
        );
      }
      return {
        taskId,
        state: state || 'generating',
        hint: 'Task is still running on KIE. Call kie_task_status with this taskId to check progress — do NOT resubmit.',
      };
    }
    const remaining = deadline - Date.now();
    await new Promise((r) => setTimeout(r, Math.min(pollIntervalMs, Math.max(200, remaining))));
  }
}

async function cmdList(flags) {
  const live = await fetchLiveModels({
    task: flags.task || '',
    provider: flags.provider || '',
    q: flags.q || '',
  });
  if (flags.json === 'true') {
    console.log(JSON.stringify(live, null, 2));
    return;
  }
  console.log(`Live models on KIE (${live.length}):`);
  for (const m of live) {
    const id = String(m.model || m.slug || '');
    console.log(
      `  ${id.padEnd(36)} | ${String(m.provider || '-').padEnd(14)} | ${m.title || ''}`
    );
  }
}

async function cmdDoc(pos) {
  console.log(await fetchModelDocText(pos[0]));
}

async function cmdPrice(pos, flags = {}) {
  const rows = await fetchPricingRows(pos[0] || '');
  if (flags.json === 'true') {
    console.log(JSON.stringify(rows, null, 2));
    return;
  }
  console.log(`Pricing matches (${rows.length}):`);
  for (const r of rows) {
    console.log(
      `  ${String(r.modelDescription || '').padEnd(48)} | ${r.creditPrice} credits ($${r.usdPrice}) ${r.creditUnit || ''}`
    );
  }
}

async function cmdBalance(flags = {}) {
  const bal = await fetchCreditBalance();
  if (flags.json === 'true') {
    console.log(JSON.stringify({ credits: bal }, null, 2));
    return;
  }
  console.log(`Available credits: ${bal}`);
}

async function cmdRun(pos, flags) {
  const model = pos[0];
  if (!model) {
    throw new Error(
      'Usage: kie-cli.mjs run <model_id> --input \'{"prompt":"..."}\' [--max-credits 20] [--out ./out.png]'
    );
  }
  const input = flags.input
    ? JSON.parse(flags.input)
    : flags.prompt
      ? { prompt: flags.prompt }
      : {};
  console.error(`[kie] Submitting task for model=${model}...`);
  const taskId = await submitTask({ model, input, maxCredits: flags['max-credits'] });
  console.error(`[kie] Task created: ${taskId}. Polling for result...`);
  await new Promise((r) => setTimeout(r, 1500));
  try {
    const res = await pollTaskWindow({
      taskId,
      waitSec: Number(flags.timeout || 600),
      outPath: flags.out,
      mcpSandbox: false,
      throwOnTimeout: true,
    });
    console.log(JSON.stringify(res, null, 2));
  } catch (err) {
    throw new Error(
      `Task ${taskId} was created, then encountered: ${err.message} (check status with: node kie-cli.mjs status ${taskId} — do NOT blindly resubmit)`
    );
  }
}

async function cmdStatus(pos, flags) {
  const taskId = pos[0];
  if (!taskId) throw new Error('Usage: kie-cli.mjs status <task_id> [--wait 15] [--out ./out.mp4]');
  const res = await pollTaskWindow({
    taskId,
    waitSec: Number(flags.wait || 0),
    outPath: flags.out,
    mcpSandbox: false,
    throwOnTimeout: false,
  });
  console.log(JSON.stringify(res, null, 2));
}

export const MCP_MAX_WAIT_SEC = 20;

export const MCP_TOOLS = [
  {
    name: 'kie_list_models',
    description: 'List active AI image, video, music, speech, and chat models on KIE (api.kie.ai).',
    inputSchema: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'Optional task filter, e.g. "Text to Image" or "Video"' },
        provider: { type: 'string', description: 'Optional provider filter, e.g. "Google" or "Kling"' },
        q: { type: 'string', description: 'Optional keyword search, e.g. "veo" or "banana"' },
      },
    },
  },
  {
    name: 'kie_model_spec',
    description:
      'Read the exact OpenAPI schema or Markdown parameter specification for a KIE model or page slug.',
    inputSchema: {
      type: 'object',
      properties: {
        model: {
          type: 'string',
          description: 'Model ID or page slug, e.g. "kling-4-0/image" or "veo-3-1"',
        },
      },
      required: ['model'],
    },
  },
  {
    name: 'kie_pricing',
    description: 'Query live catalog credit and USD prices on KIE.',
    inputSchema: {
      type: 'object',
      properties: {
        keyword: { type: 'string', description: 'Model keyword, e.g. "veo" or "kling"' },
      },
    },
  },
  {
    name: 'kie_credit_balance',
    description: 'Check remaining credit balance on the configured KIE_API_KEY.',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'kie_submit_task',
    description:
      'Submit an async generation task on KIE with an optional pre-flight per-task maxCredits catalog check. Waits up to 20s inline (fast images finish inline; longer video/audio tasks return taskId with state="generating" so you can poll kie_task_status without hitting host timeouts).',
    inputSchema: {
      type: 'object',
      properties: {
        model: { type: 'string', description: 'Exact KIE model identifier' },
        input: { type: 'object', description: 'Model input payload matching kie_model_spec' },
        maxCredits: {
          type: 'number',
          description:
            'Optional pre-flight catalog upper-bound check in credits (also configurable via KIE_MAX_CREDITS env)',
        },
        waitSeconds: {
          type: 'number',
          description: 'Seconds to wait inline before returning taskId (0–20, default 15)',
        },
        outPath: {
          type: 'string',
          description:
            'Optional relative path inside the workspace to save output if finished inline (never overwrites existing files)',
        },
      },
      required: ['model', 'input'],
    },
  },
  {
    name: 'kie_task_status',
    description:
      'Check or short-poll (up to 20s) an existing KIE taskId and optionally save finished media inside the workspace.',
    inputSchema: {
      type: 'object',
      properties: {
        taskId: { type: 'string', description: 'Task ID returned by kie_submit_task' },
        waitSeconds: { type: 'number', description: 'Seconds to short-poll (0–20, default 15)' },
        outPath: {
          type: 'string',
          description:
            'Optional relative path inside the workspace to save output (never overwrites existing files)',
        },
      },
      required: ['taskId'],
    },
  },
];

export async function handleMcpRequest(msg) {
  if (!msg || typeof msg !== 'object') return null;
  const { id, method, params } = msg;
  if (id === undefined) return null;

  try {
    if (method === 'initialize') {
      return {
        jsonrpc: '2.0',
        id,
        result: {
          protocolVersion: '2024-11-05',
          capabilities: { tools: {} },
          serverInfo: { name: 'kie-mcp-server', version: '1.0.0' },
        },
      };
    }
    if (method === 'ping') {
      return { jsonrpc: '2.0', id, result: {} };
    }
    if (method === 'tools/list') {
      return { jsonrpc: '2.0', id, result: { tools: MCP_TOOLS } };
    }
    if (method === 'tools/call') {
      const name = params?.name;
      const args = params?.arguments || {};
      let outText = '';
      if (name === 'kie_list_models') {
        const models = await fetchLiveModels({
          task: args.task || '',
          provider: args.provider || '',
          q: args.q || '',
        });
        outText = JSON.stringify(models, null, 2);
      } else if (name === 'kie_model_spec') {
        outText = await fetchModelDocText(args.model);
      } else if (name === 'kie_pricing') {
        outText = JSON.stringify(await fetchPricingRows(args.keyword || ''), null, 2);
      } else if (name === 'kie_credit_balance') {
        outText = JSON.stringify({ credits: await fetchCreditBalance() }, null, 2);
      } else if (name === 'kie_submit_task') {
        // Pre-validate outPath before spending any credits so invalid/existing paths fail free
        if (args.outPath) resolveSafeMcpOutputPath(args.outPath);
        const taskId = await submitTask({
          model: args.model,
          input: args.input || {},
          maxCredits: args.maxCredits,
        });
        const waitSec = Math.min(
          MCP_MAX_WAIT_SEC,
          Math.max(0, args.waitSeconds === undefined ? 15 : Number(args.waitSeconds) || 0)
        );
        try {
          if (waitSec > 0) await new Promise((r) => setTimeout(r, 1000));
          const res = await pollTaskWindow({
            taskId,
            waitSec,
            outPath: args.outPath,
            mcpSandbox: true,
            throwOnTimeout: false,
          });
          outText = JSON.stringify(res, null, 2);
        } catch (pollErr) {
          outText = JSON.stringify(
            {
              taskId,
              state: 'submitted_poll_error',
              pollError: pollErr.message,
              hint: 'Task WAS created on KIE — do NOT resubmit. Call kie_task_status with this taskId to check progress or retry saving.',
            },
            null,
            2
          );
        }
      } else if (name === 'kie_task_status') {
        if (args.outPath) resolveSafeMcpOutputPath(args.outPath);
        const waitSec = Math.min(
          MCP_MAX_WAIT_SEC,
          Math.max(0, args.waitSeconds === undefined ? 15 : Number(args.waitSeconds) || 0)
        );
        const res = await pollTaskWindow({
          taskId: args.taskId,
          waitSec,
          outPath: args.outPath,
          mcpSandbox: true,
          throwOnTimeout: false,
        });
        outText = JSON.stringify(res, null, 2);
      } else {
        throw new Error(`Unknown MCP tool: ${name}`);
      }
      return {
        jsonrpc: '2.0',
        id,
        result: { content: [{ type: 'text', text: outText }] },
      };
    }
    return {
      jsonrpc: '2.0',
      id,
      error: { code: -32601, message: `Method not found: ${method}` },
    };
  } catch (err) {
    return {
      jsonrpc: '2.0',
      id,
      result: {
        isError: true,
        content: [{ type: 'text', text: err.message }],
      },
    };
  }
}

/**
 * Non-blocking stdio dispatcher: concurrent requests (e.g. `ping` while `kie_submit_task`
 * short-polls) resolve independently without stalling the transport.
 */
export function startMcpStdioServer(input = process.stdin, output = process.stdout) {
  const rl = readline.createInterface({ input, terminal: false });
  const inFlight = new Set();
  let closed = false;

  return new Promise((resolve) => {
    const maybeDone = () => {
      if (closed && inFlight.size === 0) resolve();
    };

    rl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let msg;
      try {
        msg = JSON.parse(trimmed);
      } catch {
        return;
      }
      const p = Promise.resolve(handleMcpRequest(msg))
        .then((reply) => {
          if (reply) output.write(`${JSON.stringify(reply)}\n`);
        })
        .finally(() => {
          inFlight.delete(p);
          maybeDone();
        });
      inFlight.add(p);
    });

    rl.on('close', () => {
      closed = true;
      maybeDone();
    });
  });
}

function isDirectRun() {
  if (!process.argv[1]) return false;
  try {
    return pathToFileURL(fs.realpathSync(process.argv[1])).href === import.meta.url;
  } catch {
    return pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url;
  }
}

async function main() {
  const { pos, flags } = parseFlags(process.argv.slice(2));
  const cmd = pos[0] || 'help';
  if (cmd === 'list') return cmdList(flags);
  if (cmd === 'doc') return cmdDoc(pos.slice(1));
  if (cmd === 'price') return cmdPrice(pos.slice(1), flags);
  if (cmd === 'balance') return cmdBalance(flags);
  if (cmd === 'run') return cmdRun(pos.slice(1), flags);
  if (cmd === 'status') return cmdStatus(pos.slice(1), flags);
  if (cmd === 'mcp') return startMcpStdioServer();

  console.log(`KIE CLI & Local MCP Server (https://kie.ai/cli)
Commands:
  list [--task "Image"] [--provider Google] [--q kw]    List live AI models on KIE
  doc <model_id_or_slug>                                Read exact OpenAPI / Markdown spec
  price [keyword] [--json]                              Query live catalog credit & USD prices
  balance [--json]                                      Check remaining credits on KIE_API_KEY
  run <model_id> --input '{...}' [--max-credits N]      Submit task with optional per-task check & save output
  status <task_id> [--wait 15] [--out ./out.mp4]        Check or resume polling an existing task
  mcp                                                   Start non-blocking stdio MCP server`);
}

if (isDirectRun()) {
  main().catch((err) => {
    console.error(`[kie] Error: ${err.message}`);
    process.exit(err.exitCode || 1);
  });
}
