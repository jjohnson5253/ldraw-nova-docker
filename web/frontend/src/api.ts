// Typed client for the FastAPI backend (web/backend/main.py).

export type SnapshotStatus = "ready" | "queued" | "rendering" | "failed" | "missing";

/** A model file in data/generated, or in the bundled gallery. */
export type ModelFile = {
  file: string;
  name: string;
  description: string; // the model's title line (line 2 of an .mpd)
  model_url: string | null; // null if the file is gone
  image_url: string | null; // the sibling .png, once it exists
  bom_url: string | null; // the sibling .csv bill of materials, once it exists
  parts: number | null; // total parts, from the BOM
  info_url: string | null; // the sibling .md: notes about the model (its prompt, say), if any
  info_heading: string | null; // the first H2 in the sibling .md, without the heading markers
  gallery: boolean; // a bundled model from models-gallery/
  size: number;
  mtime: number;
  status: SnapshotStatus; // of the snapshot
  error: string | null;
  bom_status: SnapshotStatus;
  bom_error: string | null;
  chats?: { id: string; title: string }[]; // chats that produced it (My Models page)
  use_only_my_parts?: boolean;
};

/** A model a chat produced: a reference into data/generated. */
export type ChatModel = ModelFile & { id: string; warnings: string[]; created_at: number };

export type Chat = {
  id: string;
  title: string;
  llm_model_id: string | null;
  created_at: number;
  updated_at: number;
  running?: boolean;
  options?: TurnOptions;
  models?: ChatModel[];
};

export type ToolCall = { id: string; type: "function"; function: { name: string; arguments: string } };

export type Message = {
  id: number;
  created_at: number;
  role: "user" | "assistant" | "tool" | "system";
  content: string | null | unknown[];
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  _models?: string[];
  _image_urls?: string[];
  _documents?: { name: string; size: number; url: string | null }[];
  _hidden?: boolean;
  _ui_only?: boolean;
  _error?: boolean;
  _notice?: boolean;
  _reasoning?: string;
};

export type ChatDetail = { chat: Chat; messages: Message[]; models: Record<string, ChatModel> };

export type Capability = boolean | "auto";
export type EnvironmentVariable = { id: string; name: string; value: null; has_value: boolean; fixed: boolean };
export type EnvironmentUpdate = { id?: string; name: string; value: string | null };
export type DocumentUpload = { name: string; data: string };
export type ConnectionStatus = "not_tested" | "connected" | "not_connected";
export type TurnOptions = { mode: "plan" | "agent"; permissions: "ask" | "full" | "read_only"; effort?: string | null; context_tokens?: number | null; use_only_my_parts?: boolean };
export type OwnedPart = { part: string | null; colour: number | null; quantity: number; description?: string; provider_part?: string; provider_color?: number };
export type PartsSource = { id?: string; name: string; set_num?: string; copies: number; available: boolean; parts: OwnedPart[] };
export type InventoryReport = { required: number; owned: number; missing: number; unresolved: number; unmapped_inventory: number; matches: boolean; has_collection: boolean; has_available_parts: boolean;
  rows: { part: string; colour: number; description?: string; colour_name?: string; required: number; owned: number; missing: number; unresolved: number }[] };
export type ModelProfile = {
  model: string; name: string; context_window: number | null; efforts: string[]; default_effort: string | null; context_budgets: number[];
  max_output_tokens?: number | null; tools?: boolean | null; vision?: boolean | null; reasoning?: boolean | null;
  pricing?: { input: number | null; output: number | null; currency: string; note?: string } | null;
  source_url?: string | null; source_label?: string | null; verified_at?: string | null;
  lookup_status?: "live" | "published" | "unavailable"; recommendation?: string | null;
};
export type AuthStatus = { status: "starting" | "pending" | "connected" | "disconnected" | "error" | "expired"; flow?: "browser" | "device"; url?: string; code?: string; message?: string; expires_at?: number };
export type Approval = { id: string; call_id: string; name: string; arguments: string };
export type LlmEntry = {
  connection_status: ConnectionStatus;
  id: string;
  model_name: string;
  litellm_params: Record<string, unknown>;
  capabilities: { tools: Capability; vision: Capability };
  resolved_capabilities: { tools: boolean | null; vision: boolean | null };
  auth_mode: "api_key" | "browser";
  profile: ModelProfile;
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  const type = res.headers.get("content-type") || "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

const json = (body: unknown) => JSON.stringify(body);

export type SetCatalogStatus = { ready: boolean; inventory_ready: boolean; configured: boolean; state: "empty" | "syncing" | "inventory_syncing" | "ready" | "error"; total_sets?: number; total_parts?: number; total_inventory_rows?: number; updated_at?: string; stage?: string; indexed?: number; error?: string };

export const api = {
  setCatalog: (refresh = false) => request<SetCatalogStatus>("/api/collection/catalog", refresh ? { method: "POST" } : undefined),
  collection: () => request<{ sources: PartsSource[]; catalog_configured: boolean }>("/api/collection"),
  searchSets: (search: string, page = 1) => request<{ sets: { set_num: string; name: string; num_parts: number; year: number }[]; next: boolean }>(`/api/collection/sets?search=${encodeURIComponent(search)}&page=${page}`),
  previewParts: (body: { set?: string; csv?: string; name?: string; include_spares?: boolean }) => request<PartsSource>("/api/collection/preview", { method: "POST", body: json(body) }),
  saveParts: (source: PartsSource) => request<{ sources: PartsSource[] }>(`/api/collection/sources${source.id ? "/" + source.id : ""}`, { method: source.id ? "PUT" : "POST", body: json(source) }),
  removeParts: (id: string) => request<{ sources: PartsSource[] }>(`/api/collection/sources/${id}`, { method: "DELETE" }),
  compareParts: (url: string) => request<InventoryReport>(`/api/collection/compare?url=${encodeURIComponent(url)}`),
  useOnlyParts: (url: string, chat_id?: string) => request<{ chat_id: string }>("/api/collection/adapt", { method: "POST", body: json({ url, chat_id }) }),
  environment: () => request<{ variables: EnvironmentVariable[] }>("/api/environment"),
  checkEnvironment: (name: string, id?: string) => request<{ preconfigured: boolean; saved: boolean }>(`/api/environment/check?name=${encodeURIComponent(name)}&exclude_id=${encodeURIComponent(id ?? "")}`),
  saveEnvironment: (variables: EnvironmentUpdate[]) => request<{ variables: EnvironmentVariable[] }>("/api/environment", { method: "PUT", body: json({ variables }) }),
  chats: () => request<{ chats: Chat[] }>("/api/chats"),
  createChat: (llm_model_id?: string | null) =>
    request<Chat>("/api/chats", { method: "POST", body: json({ llm_model_id }) }),
  chat: (id: string) => request<ChatDetail>(`/api/chats/${id}`),
  renameChat: (id: string, title: string) =>
    request<Chat>(`/api/chats/${id}`, { method: "PATCH", body: json({ title }) }),
  deleteChat: (id: string) => request(`/api/chats/${id}`, { method: "DELETE" }),
  send: (id: string, text: string, llm_model_id?: string | null, options?: TurnOptions, images?: string[], documents?: DocumentUpload[]) =>
    request(`/api/chats/${id}/messages`, { method: "POST", body: json({ text, llm_model_id, options, images, documents }) }),
  approve: (id: string, approval: string, approved: boolean) => request(`/api/chats/${id}/approvals/${approval}`, { method: "POST", body: json({ approved }) }),
  catalog: () => request<{ models: ModelProfile[] }>("/api/model-catalog"),
  authStatus: (provider: string) => request<AuthStatus>(`/api/auth/${provider}`),
  login: (provider: string, flow: "browser" | "device" = "browser") => request<AuthStatus>(`/api/auth/${provider}/login`, { method: "POST", body: json({ flow, restart: true }) }),
  loginCode: (provider: string, code: string) => request(`/api/auth/${provider}/code`, { method: "POST", body: json({ code }) }),
  logout: (provider: string) => request(`/api/auth/${provider}`, { method: "DELETE" }),
  cancel: (id: string) => request(`/api/chats/${id}/cancel`, { method: "POST" }),
  models: (collection: "models" | "gallery" = "models") => request<{ models: ModelFile[]; pending: number }>(`/api/${collection}`),
  deleteModel: (filename: string) => request<{ deleted: string[] }>(`/api/models/${encodeURIComponent(filename)}`, { method: "DELETE" }),

  llmModels: () => request<{ models: LlmEntry[]; default_id: string | null }>("/api/llm-models"),
  editLlm: (id: string) => request<LlmEntry>(`/api/llm-models/${id}/edit`),
  createLlm: (entry: Partial<LlmEntry>) => request<LlmEntry>("/api/llm-models", { method: "POST", body: json(entry) }),
  updateLlm: (id: string, entry: Partial<LlmEntry>) =>
    request<LlmEntry>(`/api/llm-models/${id}`, { method: "PUT", body: json(entry) }),
  deleteLlm: (id: string) => request(`/api/llm-models/${id}`, { method: "DELETE" }),
  defaultLlm: (id: string) => request(`/api/llm-models/${id}/default`, { method: "POST" }),
  testLlm: (id: string) =>
    request<{ ok: boolean; reply?: string; error?: string; connection_status: ConnectionStatus; profile: ModelProfile; capabilities?: LlmEntry["resolved_capabilities"] }>(
      `/api/llm-models/${id}/test`,
      { method: "POST" },
    ),
  importLlm: (yaml: string) =>
    request<{ imported: LlmEntry[] }>("/api/llm-models/import", { method: "POST", body: json({ yaml }) }),
  providers: () => request<{ providers: string[] }>("/api/llm-providers"),
  providerModels: (p: string) => request<{ models: string[] }>(`/api/llm-providers/${encodeURIComponent(p)}/models`),
};

export const downloadUrl = (url: string) => url + (url.includes("?") ? "&" : "?") + "download=1";

/** Convert a model to .glb on the server (mpd2glb) and save it. Can take a minute. */
export async function downloadGlb(modelUrl: string, fileName: string): Promise<void> {
  const res = await fetch(`/api/glb?url=${encodeURIComponent(modelUrl)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : res.statusText);
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await res.blob());
  link.download = fileName.replace(/\.[^.]+$/, "") + ".glb";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 30000);
}

/** The 3D viewer (three.js), or the 3D player that animates the build (Rust/WebAssembly). */
export type ViewerMode = "viewer" | "player";

export const viewerUrl = (modelUrl: string, parts?: number | null, mode: ViewerMode = "viewer") =>
  `/viewer/${mode}.html?model=${encodeURIComponent(modelUrl)}` + (parts != null ? `&parts=${parts}` : "");

/** The mixed-reality viewer (WebXR, Meta Quest 3): a top-level page, the most reliable way to start WebXR. */
export const xrUrl = (modelUrl: string, parts?: number | null) =>
  `/xr/?model=${encodeURIComponent(modelUrl)}` + (parts != null ? `&parts=${parts}` : "");

export const XR_TITLE = "Mixed reality on a Meta Quest 3 (WebXR)";

export const partsLabel = (parts: number) => `${parts.toLocaleString()} part${parts === 1 ? "" : "s"}`;

export const isPending = (m: { status: SnapshotStatus; bom_status: SnapshotStatus }) =>
  m.status === "queued" || m.status === "rendering" || m.bom_status === "queued" || m.bom_status === "rendering";

export function timeAgo(seconds: number): string {
  const diff = Date.now() / 1000 - seconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return new Date(seconds * 1000).toLocaleDateString();
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
