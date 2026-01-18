# API 参考

## 概览

- 默认服务地址：`http://<host>:8000`
- 内容类型：`application/json`
- 鉴权：
  - 若已配置 `settings.api_key`：需要 `Authorization: Bearer <api_key>`
  - 若未配置 `settings.api_key`：默认放行
  - SSE 特例：`GET /api/trace/conversations/{id}/events` 可用 `?token=<api_key>`

## OpenAI 兼容（`/v1/*`）

### `GET /v1/models`

- 说明：返回上游（NewAPI 或 ProviderRouter）模型列表。
- 响应：OpenAI `ListModels` 风格 `{object:'list', data:[{id,...}]}`（以实际上游为准）

### `POST /v1/chat/completions`

- 说明：OpenAI ChatCompletions 兼容入口，额外支持 Profile 与 RAG 扩展。
- 头：
  - `x-fass-profile: <profile_id>`（可选；也可在 body 里用 `profile_id`）
- 请求（最小示例）：

```json
{
  "model": "default",
  "messages": [
    {"role": "user", "content": "你好，介绍一下 FASS。"}
  ]
}
```

- RAG 扩展（可选）：

```json
{
  "model": "default",
  "messages": [{"role":"user","content":"总结一下昨天的要点"}],
  "rag": {
    "collection": "shared",
    "top_k": 5,
    "auto_research": false
  }
}
```

- 行为要点：
  - 若 profile 生效：可覆盖 `model`、注入 `system_prompt` 与默认参数（只补缺省字段）
  - RAG：对用户最后一句做 embedding（可降级为纯文本）并检索 memory，命中则追加 system 上下文
  - 若未命中且 `auto_research=true`：会尝试入队 research job
- 响应：OpenAI `ChatCompletion` 风格（以实际上游返回为准）
- 错误：
  - 400：payload 不合法（如 messages 不是 list）
  - 401/403：鉴权失败
  - 502：上游错误

### `POST /v1/embeddings`

- 说明：OpenAI Embeddings 兼容入口，默认模型可由 `model.defaults.embedding_model_id` 提供。
- 请求（示例）：

```json
{
  "model": "default",
  "input": ["hello", "world"]
}
```

- 响应：OpenAI `Embeddings` 风格（以实际上游返回为准）
- 错误：同上；上游错误会包含 `request_id`

## 控制台与业务 API（`/api/*`）

### Chat

#### `POST /api/chat/roundtable`

- 说明：圆桌讨论：按参与者列表依次调用 chat completions。
- 请求：

```json
{
  "topic": "请讨论：Hybrid RAG 的优势与局限",
  "participants": [
    {"name": "A", "model": "default"},
    {"name": "B", "model": "default"}
  ]
}
```

- 响应：`{messages:[{role:'assistant', name, content}]}`。

### Memory

#### `POST /api/memory/upsert`

- 说明：写入/更新记忆条目（会尝试生成向量；失败则只写文本）。
- 请求：

```json
{
  "collection": "shared",
  "items": [
    {"path": "note://demo/1", "content": "这是一条知识片段"}
  ]
}
```

- 响应：`{changed:int}`

#### `POST /api/memory/search`

- 说明：检索记忆；默认启用向量检索（可降级）。
- 请求：

```json
{
  "collection": "shared",
  "query": "知识片段",
  "top_k": 8,
  "use_vector": true
}
```

- 响应：`{results:[{id,collection,path,content,score,source}]}`（`source` 可能为 `hybrid/bm25/ann/fallback/...`）。

#### `POST /api/memory/ingest`

- 说明：从目录摄取文本文件写入 memory。
- 请求：`{diary_root?:string, workspace_root?:string}`
- 响应：`{diary?:{changed,files}, workspace?:{changed,files}}`

#### `POST /api/memory/rebuild`

- 说明：从 `fs_store_dir` 扫描文本并重建索引（按 collection 分组）。
- 请求：`{collection?: string|null}`
- 响应：`{[collection]: {changed:int, files:int}}`

### Plugins（外部 stdio 工具）

#### `GET /api/plugins/tools`

- 响应：`[{plugin_id,name,description,parameters}]`

#### `POST /api/plugins/invoke`

- 请求：`{tool_name:string, arguments:object}`
- 响应：`{result:any}`

### Settings

#### `GET /api/settings`

- 响应：`{stored:object, effective:object}`

#### `POST /api/settings`

- 说明：批量写入 settings（同时更新运行时 `settings` 对象中的相关字段）。
- 请求：任意 JSON object（key/value）；常用键：`api_key`、`embedding_provider`、`embedding_model_path`、`llm_base_url`、`llm_model` 等。
- 响应：`{ok:true}`

### Tasks

#### `GET /api/tasks`

- 响应：`[{id,name,cron,payload_json,enabled,...}]`

#### `POST /api/tasks`

- 请求：`{name:string, cron?:string|null, payload?:object}`
- 响应：创建后的 task 行（dict）

#### `POST /api/tasks/{task_id}`

- 请求：`{name?, cron?, enabled?, payload?}`
- 响应：更新后的 task 行（dict）

#### `DELETE /api/tasks/{task_id}`

- 响应：`{ok:true}`

### Timeline

#### `POST /api/timeline/build`

- 请求：`{diary_root, project_base_path, timeline_dir?, summary_model?, min_content_length?, max_files?, wait_ms_if_busy?}`
- 响应：`{ok, status:'done'|'busy', changed, skipped, entries_written, timeline_files, elapsed_ms}`

### Control（控制面板）

#### `GET /api/control/providers`

- 响应：`{schema_version, default_provider_id, providers:[...masked...], runtime:{provider_id:runtime}}`

#### `POST /api/control/providers`

- 说明：upsert Provider；若未显式提交 auth.token，则保留旧 token（避免前端回显）。
- 请求：Provider JSON（参考 `models/control.py`）
- 响应：`{ok:true}`

#### `DELETE /api/control/providers/{provider_id}`

- 响应：`{ok:true}`

#### `POST /api/control/providers/{provider_id}/test`

- 响应：`{ok:true, models_sample:[...]}` 或 502

#### `POST /api/control/defaults`

- 请求：`{default_provider_id?: string|null}`
- 响应：`{ok:true, model_catalog:..., layer_presets:?}`

#### `GET /api/control/model_catalog`

- 查询：`provider_id=<id>&status=online|offline`
- 响应：`{provider_id,status,items:[...]}`（items 包含 raw/capabilities）

#### `POST /api/control/model_catalog/sync`

- 请求：`{provider_id?: string}`
- 响应：`{ok:true, cache:..., layer_presets:...}`

#### `GET /api/control/layer_presets`

- 响应：`{items:[{layer, selected_model_id, selection_reason,...}]}`。

#### `GET /api/control/audit_logs`

- 查询：`since_unix_ms? until_unix_ms? action? limit?`
- 响应：`{items:[{id,actor,action,created_at_unix_ms,...}]}`（默认不解密 payload）

#### `POST /api/control/self_heal/daily_tick`
#### `POST /api/control/self_heal/rollback_latest`
#### `POST /api/control/self_heal/run_full_check`

- 响应：各自返回自愈结果（含 integrity/checksums/prune 等）

#### `GET /api/control/models`
#### `POST /api/control/models`
#### `DELETE /api/control/models/{alias_id}`

- 说明：ModelAlias 列表/写入/删除

#### `GET /api/control/profiles`
#### `POST /api/control/profiles`
#### `POST /api/control/profiles/default`
#### `DELETE /api/control/profiles/{profile_id}`

- 说明：ModelProfile 管理与默认 profile 设定

#### `GET /api/control/websearch`
#### `POST /api/control/websearch`

- 说明：读写 `web.searxng_base_url`（供 Research pipeline 使用）

### MCP（内置工具）

#### `GET /api/mcp/tools`

- 响应：`{tools:[{name,description,parameters,read_only,dangerous,timeout_seconds,enabled}]}`。

#### `POST /api/mcp/tools/{tool_name}/enable`

- 请求：`{enabled:boolean}`
- 响应：`{ok:true}`

#### `POST /api/mcp/execute`

- 请求：`{tool_name:string, arguments:object}`
- 响应：`{ok:boolean, result?:any, error?:string}`（子进程执行；超时 `error=timeout`）

#### `GET /api/mcp/models`

- 响应：`{providers:{provider_id:{models:[model_id...]}}}`

### Automations

#### `GET /api/automations/research/jobs`
#### `POST /api/automations/research/enqueue`
#### `POST /api/automations/dreaming/run`

- 说明：Research 入队与 Dreaming 触发（详见 `BACKEND_FILE_INDEX.md` 对应文件段落）。

### Trace（SSE）

#### `POST /api/trace/conversations`

- 请求：`{l3_id?, persona_id?, title?}`
- 响应：`{conversation_id:int}`

#### `GET /api/trace/conversations/{conversation_id}/events`

- 鉴权：Header Bearer 或 `?token=<api_key>`
- SSE 事件：
  - `ready`：连接就绪
  - `trace`：`data` 为 JSON（见 `trace_api.py` 写入字段：layer/from_agent/to_agent/event_kind/content/ts/status 等）

#### `POST /api/trace/conversations/{conversation_id}/send`

- 请求：`{text:string}`
- 响应：`{ok:true, assistant:string, trace_id:string}`

### Config

#### `GET /api/config/upstreams`
#### `POST /api/config/upstreams`

- 说明：读写 NewAPI/Ollama 上游配置；返回只包含 `*_has_key` 不包含明文 key。

### Models（聚合）

#### `GET /api/models/list`

- 说明：聚合 NewAPI 与 Ollama 模型列表。
- 响应：`{items:[{id,source,legacy}], errors:{newapi?,ollama?}}`

## Legacy（兼容）

### `POST /legacy/ollama/chat`

- 说明：兼容 Ollama `/api/chat` 输入，但输出为 OpenAI `chat.completion`。
- 请求：`{model, messages:[{role,content,...}]}`（`stream` 固定为 false）
- 响应：OpenAI `chat.completion` 风格，含 `x_fass_legacy=ollama`

## 快速调用示例（curl）

```bash
# (1) OpenAI 兼容 Chat
curl -sS http://localhost:8000/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{\"model\":\"default\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}' | jq

# (2) 写入记忆
curl -sS http://localhost:8000/api/memory/upsert \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{\"collection\":\"shared\",\"items\":[{\"path\":\"note://demo/1\",\"content\":\"FASS 是一个网关\"}]}' | jq

# (3) 检索记忆
curl -sS http://localhost:8000/api/memory/search \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{\"collection\":\"shared\",\"query\":\"网关\",\"top_k\":5}' | jq
```
