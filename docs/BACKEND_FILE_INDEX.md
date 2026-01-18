# 后端文件索引（逐 `.py`）

## 使用说明

- 本文档覆盖后端主应用目录 `fass_gateway/app/`，以及外部插件示例 `plugins/*/main.py`。
- “文档位置”用于满足“在文档中的创建位置”要求：每个文件都有对应小节标题，可直接在本文目录中定位。
- “API/调用方式”按文件类型区分：
  - Router：HTTP 调用（method + path + 关键字段 + 鉴权）
  - Service/Model：Python import 调用（被哪些 Router/服务引用）
  - Script/Plugin：CLI 或 stdio 调用方式

## 通用鉴权约定（适用于大多数 `/api/*` 与 `/v1/*`）

- 若 `settings.api_key` 已配置：请求需携带 `Authorization: Bearer <api_key>`；缺失返回 401；错误 key 返回 403。
- 若 `settings.api_key` 未配置：默认放行。
- SSE 特例：`GET /api/trace/conversations/{id}/events` 支持 query 参数 `?token=<api_key>` 代替 Header。

## 目录

- [应用入口与基础设施](#应用入口与基础设施)
- [Routers（HTTP API）](#routershttp-api)
- [Services（内部服务层）](#services内部服务层)
- [Models（Pydantic 数据模型）](#modelspydantic-数据模型)
- [MCP Tools（内置工具实现）](#mcp-tools内置工具实现)
- [Scripts（命令行脚本）](#scripts命令行脚本)
- [Plugins（外部 stdio 工具）](#plugins外部-stdio-工具)

## 应用入口与基础设施

### fass_gateway/app/main.py

- 功能用途：FastAPI 应用入口；注册所有 Router；启动时加载 Provider/Model 配置、加载内置 MCP 工具、启动后台 TaskRunner；挂载静态站点（`/`）。
- 文档位置：本文档 → 应用入口与基础设施 → `fass_gateway/app/main.py`
- API/调用方式：
  - 运行：`python3 -m uvicorn fass_gateway.app.main:app --host 0.0.0.0 --port 8000`
  - HTTP：通过被 include 的各 Router 对外提供服务

### fass_gateway/app/__init__.py

- 功能用途：后端 Python 包标识；用于稳定 import 路径（`fass_gateway.app.*`）。
- 文档位置：本文档 → 应用入口与基础设施 → `fass_gateway/app/__init__.py`
- API/调用方式：通常无需直接调用；被 Python import 机制使用（内部）

### fass_gateway/app/settings.py

- 功能用途：运行时配置（pydantic-settings），从 `config.env` 读取；包含 API Key、Embedding/LLM 上游、CORS 等。
- 文档位置：本文档 → 应用入口与基础设施 → `fass_gateway/app/settings.py`
- API/调用方式：
  - 内部 import：`from fass_gateway.app.settings import settings`
  - 关键字段：`api_key`、`embedding_provider`、`embedding_model_path`、`llm_base_url`、`newapi_base_url/newapi_api_key` 等

### fass_gateway/app/db.py

- 功能用途：SQLite 连接与基础表初始化；应用 migrations；提供 `open_db()` 给 Router/服务使用。
- 文档位置：本文档 → 应用入口与基础设施 → `fass_gateway/app/db.py`
- API/调用方式：
  - 内部 import：`from fass_gateway.app.db import open_db`
  - 返回：`sqlite3.Connection`（WAL、foreign_keys、busy_timeout 已设置）

### fass_gateway/app/migrations.py

- 功能用途：应用 schema migrations（目前包含 version=1 的多张控制/追踪/审计表）。
- 文档位置：本文档 → 应用入口与基础设施 → `fass_gateway/app/migrations.py`
- API/调用方式：由 `db.py:open_db()` 调用 `apply_migrations(conn)`（内部使用）

## Routers（HTTP API）

### fass_gateway/app/routers/__init__.py

- 功能用途：Router 包标识；集中导出/组织路由模块（便于 `main.py` 统一注册）。
- 文档位置：本文档 → Routers → `routers/__init__.py`
- API/调用方式：内部 import（由 `fass_gateway/app/main.py` 或其他模块引用）

### fass_gateway/app/routers/openai_compat.py

- 功能用途：OpenAI 兼容层（`/v1/models`、`/v1/chat/completions`、`/v1/embeddings`）；支持 Profile 注入、RAG 检索上下文注入、RAG miss 自动入队 research。
- 文档位置：本文档 → Routers → `openai_compat.py`
- API/调用方式：
  - `GET /v1/models`：透传上游模型列表（NewAPI 兼容）
  - `POST /v1/chat/completions`：
    - 入参：OpenAI ChatCompletions 标准字段 + 可选 `profile_id`/`x-fass-profile`、可选 `rag: {collection, top_k, auto_research}`
    - 行为：按 profile 补全 `model/params/system_prompt`；对用户最后一句做 embedding+search 并注入 system 上下文
  - `POST /v1/embeddings`：透传到 NewAPI `/v1/embeddings`（默认模型可由 `model_defaults` 提供）

### fass_gateway/app/routers/chat_api.py

- 功能用途：多参与者圆桌讨论（多次调用 chat completions）。
- 文档位置：本文档 → Routers → `chat_api.py`
- API/调用方式：
  - `POST /api/chat/roundtable`
    - 入参：`{topic: string, participants: [{name, model}]}`（participants 非空）
    - 返回：`{messages: [{role:'assistant', name, content}]}`（逐参与者发言）

### fass_gateway/app/routers/memory_api.py

- 功能用途：记忆库写入/检索/摄取/重建（Hybrid RAG 的数据入口）。
- 文档位置：本文档 → Routers → `memory_api.py`
- API/调用方式：
  - `POST /api/memory/upsert`：`{collection: string, items: [{path, content}]}` → `{changed}`
  - `POST /api/memory/search`：`{query, collection?, top_k?, use_vector?}` → `{results}`（默认启用向量）
  - `POST /api/memory/ingest`：`{diary_root?, workspace_root?}` → 摄取并写入 collection（diary/workspace）
  - `POST /api/memory/rebuild`：`{collection?: string|null}` → 从 `fs_store_dir` 读取文件重建索引

### fass_gateway/app/routers/plugins_api.py

- 功能用途：外部插件工具（stdio 协议）列表与调用。
- 文档位置：本文档 → Routers → `plugins_api.py`
- API/调用方式：
  - `GET /api/plugins/tools`：返回可用工具 spec（参数 schema、描述）
  - `POST /api/plugins/invoke`：`{tool_name, arguments:{...}}` → `{result}`（由插件子进程执行）

### fass_gateway/app/routers/settings_api.py

- 功能用途：读取/写入设置（settings 表 + 同步到运行时 `settings` 对象）。
- 文档位置：本文档 → Routers → `settings_api.py`
- API/调用方式：
  - `GET /api/settings`：返回 `stored`（数据库）与 `effective`（运行时）
  - `POST /api/settings`：以 JSON body 批量写入；会同步影响 embedding/llm/api_key 等运行时字段

### fass_gateway/app/routers/tasks_api.py

- 功能用途：后台任务（tasks 表）CRUD。
- 文档位置：本文档 → Routers → `tasks_api.py`
- API/调用方式：
  - `GET /api/tasks`：列出任务
  - `POST /api/tasks`：创建任务（`{name, cron?, payload?}`）
  - `POST /api/tasks/{task_id}`：更新（name/cron/enabled/payload）
  - `DELETE /api/tasks/{task_id}`：删除

### fass_gateway/app/routers/timeline_api.py

- 功能用途：基于日记文件构建 timeline（摘要 + 结构化输出 + 写入 memory）。
- 文档位置：本文档 → Routers → `timeline_api.py`
- API/调用方式：
  - `POST /api/timeline/build`
    - 入参：`{diary_root, project_base_path, timeline_dir?, summary_model?, min_content_length?, max_files?, wait_ms_if_busy?}`
    - 返回：构建状态、写入数量、输出文件列表

### fass_gateway/app/routers/control_api.py

- 功能用途：控制面板 API（Provider/ModelAlias/Profile 管理、Catalog 同步、Layer presets、审计日志、自愈、WebSearch 配置）。
- 文档位置：本文档 → Routers → `control_api.py`
- API/调用方式（节选）：
  - Providers：`GET/POST /api/control/providers`、`DELETE /api/control/providers/{provider_id}`、`POST /api/control/providers/{provider_id}/test`
  - Defaults：`POST /api/control/defaults`（切换默认 provider，并触发 catalog/preset 同步）
  - Catalog：`GET /api/control/model_catalog`、`POST /api/control/model_catalog/sync`
  - Presets：`GET /api/control/layer_presets`
  - Audit：`GET /api/control/audit_logs`
  - Self-heal：`POST /api/control/self_heal/*`
  - ModelAlias：`GET/POST/DELETE /api/control/models*`
  - Profiles：`GET/POST/DELETE /api/control/profiles*`、`POST /api/control/profiles/default`
  - WebSearch：`GET/POST /api/control/websearch`
### fass_gateway/app/routers/mcp_api.py

- 功能用途：内置 MCP 工具（列出/启用/执行）与 provider 模型概览。
- 文档位置：本文档 → Routers → `mcp_api.py`
- API/调用方式：
  - `GET /api/mcp/tools`：列出工具（含 enabled/read_only/dangerous/timeout）
  - `POST /api/mcp/tools/{tool_name}/enable`：`{enabled: boolean}`（危险工具固定禁用）
  - `POST /api/mcp/execute`：`{tool_name, arguments:{...}}` → `{ok,result|error}`（子进程隔离执行）
  - `GET /api/mcp/models`：列出 providers 与其缓存模型 id

### fass_gateway/app/routers/automations_api.py

- 功能用途：Research job 队列管理与 Dreaming 触发。
- 文档位置：本文档 → Routers → `automations_api.py`
- API/调用方式：
  - `GET /api/automations/research/jobs`：最近 50 条 research_jobs
  - `POST /api/automations/research/enqueue`：`{query, collection?}` 入队
  - `POST /api/automations/dreaming/run`：`{max_items?, collection?}` 触发“梦境消化”

### fass_gateway/app/routers/trace_api.py

- 功能用途：对话追踪与事件流（SSE）；同时提供“伪流式” L2/L1 分层事件回放能力。
- 文档位置：本文档 → Routers → `trace_api.py`
- API/调用方式：
  - `POST /api/trace/conversations`：创建会话 → `{conversation_id}`
  - `GET /api/trace/conversations/{conversation_id}/events`：SSE（支持 `?token=`）
    - 事件：`ready`、`trace`（data 为 JSON）
  - `POST /api/trace/conversations/{conversation_id}/send`：`{text}` → `{ok, assistant, trace_id}`（内部会产生多条 trace 事件并写入 DB）

### fass_gateway/app/routers/config_api.py

- 功能用途：上游（NewAPI/Ollama）配置读取与写入（落库到 settings）。
- 文档位置：本文档 → Routers → `config_api.py`
- API/调用方式：
  - `GET /api/config/upstreams`：返回 base_url 与是否配置 key（不回传明文 key）
  - `POST /api/config/upstreams`：写入 `{newapi_base_url,newapi_api_key,ollama_base_url,ollama_api_key}`

### fass_gateway/app/routers/models_api.py

- 功能用途：聚合返回 NewAPI + Ollama 模型列表（供前端选择）。
- 文档位置：本文档 → Routers → `models_api.py`
- API/调用方式：
  - `GET /api/models/list`：返回 `{items:[{id,source,newapi|ollama,legacy}], errors:{...}}`

### fass_gateway/app/routers/legacy_ollama_api.py

- 功能用途：兼容层：把 Ollama `/api/chat` 包装成 OpenAI `chat.completion` 响应。
- 文档位置：本文档 → Routers → `legacy_ollama_api.py`
- API/调用方式：
  - `POST /legacy/ollama/chat`：入参 `{model, messages:[...]}` → OpenAI 结构响应（`x_fass_legacy=ollama`）

## Services（内部服务层）

### fass_gateway/app/services/__init__.py

- 功能用途：Services 包标识；组织内部服务模块命名空间。
- 文档位置：本文档 → Services → `services/__init__.py`
- API/调用方式：通常无需直接调用；内部 import 依赖其包结构（内部）

### fass_gateway/app/services/embedding.py

- 功能用途：统一 embedding 抽象。
  - `local`：`sentence-transformers` 本地模型
  - `openai_compat`：请求 `llm_base_url` 的 `/v1/embeddings`（或回退到 Ollama `/api/embeddings`）
- 文档位置：本文档 → Services → `embedding.py`
- API/调用方式：内部调用 `await embed_texts(list[str]) -> list[list[float]]`（被 memory/rag/research 使用）

### fass_gateway/app/services/memory.py

- 功能用途：记忆存储封装。
  - 优先使用 `memoscore.MemosCore`（SQLite 真值 + Tantivy 文本索引 + USearch 向量 ANN）
  - 失败则降级 `_FallbackCore`（SQLite + 简易向量余弦/LIKE）
  - 可选把写入同步到 `fs_store_dir` 文件系统
- 文档位置：本文档 → Services → `memory.py`
- API/调用方式：
  - `await store.upsert_texts(collection, items)`
  - `store.search(collection=..., query_text=..., query_vec=..., top_k=...)`
  - `store.sync_indexes(limit=...)`（如果 core 支持 index_tasks 同步）

### fass_gateway/app/services/file_store.py

- 功能用途：fs_store 文件写入与遍历；负责路径清洗与跨平台兼容（反斜杠、盘符等）。
- 文档位置：本文档 → Services → `file_store.py`
- API/调用方式：`write_text()`、`iter_texts()`（被 memory_api/rebuild、memory 写入使用）

### fass_gateway/app/services/ingest.py

- 功能用途：摄取 diary/workspace 目录文本文件并写入 memory（带扩展名白名单与 ignore 目录）。
- 文档位置：本文档 → Services → `ingest.py`
- API/调用方式：`await ingest_diary(Path)`、`await ingest_workspace(Path)`（由 `/api/memory/ingest` 调用）

### fass_gateway/app/services/newapi_client.py

- 功能用途：NewAPI（OpenAI 兼容）HTTP 客户端；统一 request_id、超时、错误封装为 `UpstreamError`。
- 文档位置：本文档 → Services → `newapi_client.py`
- API/调用方式：`await list_models()` / `await chat_completions()` / `await embeddings()`（被 llm_proxy/models_api/openai_compat 使用）

### fass_gateway/app/services/llm_proxy.py

- 功能用途：对 NewAPI 的轻量代理；注入默认 chat/embedding 模型（`model_defaults`）。
- 文档位置：本文档 → Services → `llm_proxy.py`
- API/调用方式：`await proxy_models()`、`await proxy_chat_completions(payload)`

### fass_gateway/app/services/upstream_config.py

- 功能用途：管理 NewAPI/Ollama 的 base_url/api_key（存入 control_store.settings）。
- 文档位置：本文档 → Services → `upstream_config.py`
- API/调用方式：`get_upstreams()`、`set_upstreams(...)`（被 config_api/models_api 使用）

### fass_gateway/app/services/control_store.py

- 功能用途：settings 表 JSON KV 的通用读写；支持 pydantic model 的 load/save。
- 文档位置：本文档 → Services → `control_store.py`
- API/调用方式：`get_json/set_json/get_model/set_model`（被 control_api/mcp_api/upstream_config 等使用）

### fass_gateway/app/services/provider_registry.py

- 功能用途：Provider 配置与运行时状态（health/circuit）注册表；默认会生成 `default` provider。
- 文档位置：本文档 → Services → `provider_registry.py`
- API/调用方式：`registry.load/save/get/list_enabled/runtime/set_health`（被 main/provider_router/provider_health/control_api 使用）

### fass_gateway/app/services/provider_router.py

- 功能用途：按 provider/model 选择并代理 `/v1/models` 与 `/v1/chat/completions`；支持：
  - `provider_id::model` 显式选择器
  - ModelAlias priority 路由
  - 失败回退与简易熔断
  - 上游不支持 `/v1/*` 时回退到 Ollama `/api/*`
- 文档位置：本文档 → Services → `provider_router.py`
- API/调用方式：内部 `await proxy_models()`、`await proxy_chat_completions(payload)`（被 model_catalog/provider_health 复用）

### fass_gateway/app/services/provider_health.py

- 功能用途：周期性探测 enabled providers 健康状态（默认 30s 间隔），写入 registry.runtime.health。
- 文档位置：本文档 → Services → `provider_health.py`
- API/调用方式：`await monitor.tick()`（由 task_runner 周期调用）

### fass_gateway/app/services/model_registry.py

- 功能用途：ModelAlias 与 ModelProfile 的持久化与默认值管理（存入 control_store）。
- 文档位置：本文档 → Services → `model_registry.py`
- API/调用方式：`model_registry.list_aliases/get_alias/save_aliases/list_profiles/get_profile/save_profiles/default_profile_id`

### fass_gateway/app/services/model_defaults.py

- 功能用途：默认 chat/embedding 模型 id（settings 表中的 `model.defaults.*`）。
- 文档位置：本文档 → Services → `model_defaults.py`
- API/调用方式：`get_defaults()` / `set_defaults(...)`（被 llm_proxy/openai_compat/newapi_test 使用）

### fass_gateway/app/services/model_catalog.py

- 功能用途：对 provider 模型列表进行缓存（model_catalog 表）；支持 etag/hash 去重、离线标记、过期清理，并写审计日志。
- 文档位置：本文档 → Services → `model_catalog.py`
- API/调用方式：`await fetch_and_cache(provider, actor=...)`、`list_cached(provider_id, ...)`（被 control_api/mcp_api 使用）

### fass_gateway/app/services/matching_engine.py

- 功能用途：根据 provider 模型名列表，生成/更新 L1/L2/L3 layer presets（layer_presets 表），并对敏感信息做脱敏。
- 文档位置：本文档 → Services → `matching_engine.py`
- API/调用方式：`upsert_layer_presets(provider_id, models, actor)`、`list_layer_presets()`（被 control_api 调用）

### fass_gateway/app/services/audit_log.py

- 功能用途：审计日志写入与查询（audit_logs 表）；payload 采用 Fernet 加密（密钥来自 `audit_log_key` 或由 `api_key` 派生）。
- 文档位置：本文档 → Services → `audit_log.py`
- API/调用方式：`write(actor, action, payload)`、`list_logs(...)`、`prune_expired()`（被 control_api/self_heal/model_catalog/matching_engine 使用）

### fass_gateway/app/services/self_heal.py

- 功能用途：SQLite 自愈：备份、`PRAGMA integrity_check`、校验和、回滚、日常维护（含 prune catalog/audit）。
- 文档位置：本文档 → Services → `self_heal.py`
- API/调用方式：由 main startup 与 control_api/task_runner 触发 `backup/integrity_check/daily_tick/run_full_check/rollback_latest`

### fass_gateway/app/services/trace_hub.py

- 功能用途：SSE 事件分发中心（按 conversation_id 管理订阅队列）。
- 文档位置：本文档 → Services → `trace_hub.py`
- API/调用方式：内部 `hub.subscribe/unsubscribe/publish`（由 trace_api 使用）

### fass_gateway/app/services/task_runner.py

- 功能用途：后台轮询任务执行器：
  - 执行 tasks（timeline_build/dreaming）
  - 周期 tick：provider health、memory index sync、research jobs、self-heal daily
- 文档位置：本文档 → Services → `task_runner.py`
- API/调用方式：由 main startup 启动 `runner.start()`，shutdown `await runner.stop()`

### fass_gateway/app/services/research.py

- 功能用途：Research job 管道：
  - enqueue：写入 research_jobs，并用 embedding 去重（cosine>=0.92 复用近 1h 结果）
  - tick：调用 MCP `web.search/web.fetch` 抓取并写入 memory
- 文档位置：本文档 → Services → `research.py`
- API/调用方式：`await enqueue_research(query, collection=...)`、`await tick_research_jobs(searxng_base_url)`

### fass_gateway/app/services/dreaming.py

- 功能用途：Dreaming：把 research_history 汇总为结构化 Markdown，并写回 memory（默认 `dream://{ts}` 路径）。
- 文档位置：本文档 → Services → `dreaming.py`
- API/调用方式：`await run_dreaming(max_items=..., collection=...)`（由 automations_api/task_runner 调用）

### fass_gateway/app/services/timeline.py

- 功能用途：根据 diary 文件生成 timeline JSON；对每条日记调用 LLM 摘要（带锁与去重 hash），并写入 memory。
- 文档位置：本文档 → Services → `timeline.py`
- API/调用方式：`await build_timeline(TimelineBuildConfig, wait_ms_if_busy=...)`（由 timeline_api/task_runner 调用）

### fass_gateway/app/services/context_packs.py

- 功能用途：读取 settings 中的 `context_pack`，作为 system prompt 注入 OpenAI 兼容入口。
- 文档位置：本文档 → Services → `context_packs.py`
- API/调用方式：`get_context_pack()`（由 openai_compat 使用）

### fass_gateway/app/services/mcp_registry.py

- 功能用途：MCP 工具注册表与装饰器 `@mcp_tool`。
- 文档位置：本文档 → Services → `mcp_registry.py`
- API/调用方式：
  - 定义工具：`@mcp_tool(name=..., parameters=...)`
  - 查询工具：`list_tools()`/`get_tool()`

### fass_gateway/app/services/mcp_loader.py

- 功能用途：加载内置 MCP 工具模块（遍历 `mcp_tools` 子模块并 import）。
- 文档位置：本文档 → Services → `mcp_loader.py`
- API/调用方式：`load_builtin_tools()`（由 main startup 与 mcp_executor 子进程调用）

### fass_gateway/app/services/mcp_executor.py

- 功能用途：MCP 工具执行器：子进程隔离执行、超时、输出截断。
- 文档位置：本文档 → Services → `mcp_executor.py`
- API/调用方式：`await execute_tool(tool_name, arguments)`（由 mcp_api/research 调用）

### fass_gateway/app/services/plugins.py

- 功能用途：外部插件（v2/legacy）发现与 stdio 执行；支持 postprocess 写入 memory。
- 文档位置：本文档 → Services → `plugins.py`
- API/调用方式：`list_tools()`、`await invoke_tool(tool_name, arguments)`（由 plugins_api 调用）

## Models（Pydantic 数据模型）

### fass_gateway/app/models/__init__.py

- 功能用途：Models 包标识；组织 pydantic 数据模型命名空间。
- 文档位置：本文档 → Models → `models/__init__.py`
- API/调用方式：内部 import（例如 `from fass_gateway.app.models.control import ...`）

### fass_gateway/app/models/control.py

- 功能用途：控制面板核心数据模型：Provider/Auth/Runtime、ModelAlias/Candidate、ModelProfile。
- 文档位置：本文档 → Models → `control.py`
- API/调用方式：供 `control_api/provider_registry/model_registry/provider_router` 使用（内部 import）

## MCP Tools（内置工具实现）

### fass_gateway/app/mcp_tools/__init__.py

- 功能用途：内置 MCP 工具包标识；便于 `mcp_loader` 遍历/导入子模块。
- 文档位置：本文档 → MCP Tools → `mcp_tools/__init__.py`
- API/调用方式：通常无需直接调用；由 `services/mcp_loader.py` 通过 import 机制加载（内部）

### fass_gateway/app/mcp_tools/system_tools.py

- 功能用途：只读系统工具：服务器状态、读取文件前 N 行。
- 文档位置：本文档 → MCP Tools → `system_tools.py`
- API/调用方式：通过 `/api/mcp/execute` 调用（`tool_name` 为 `system.get_server_stats` / `system.read_file_head`）

### fass_gateway/app/mcp_tools/web_tools.py

- 功能用途：Web 工具：SearxNG 搜索、抓取页面正文、同域链接过滤。
- 文档位置：本文档 → MCP Tools → `web_tools.py`
- API/调用方式：通过 `/api/mcp/execute` 调用（`web.search`/`web.fetch`/`web.extract_links`）；Research pipeline 会直接调用这些工具

## Scripts（命令行脚本）

### fass_gateway/app/scripts/__init__.py

- 功能用途：Scripts 包标识；使脚本可通过 `python -m fass_gateway.app.scripts.*` 方式运行。
- 文档位置：本文档 → Scripts → `scripts/__init__.py`
- API/调用方式：通常无需直接调用；由 Python 模块运行与 import 使用（内部）

### fass_gateway/app/scripts/rebuild_memory.py

- 功能用途：从 fs_store 读取内容并重建 memory 索引（可限定 collection；可禁用向量生成）。
- 文档位置：本文档 → Scripts → `rebuild_memory.py`
- API/调用方式：
  - `python3 -m fass_gateway.app.scripts.rebuild_memory --collection shared --fs-store-dir /path/to/fs_store`
  - 或直接执行该文件（依赖 Python path）

## Plugins（外部 stdio 工具）

### plugins/hello_tool/main.py

- 功能用途：stdio 示例插件：读取 stdin 一行 JSON，输出 hello 消息。
- 文档位置：本文档 → Plugins → `hello_tool/main.py`
- API/调用方式：
  - 被 `/api/plugins/invoke` 间接调用（由 `services/plugins.py` 子进程执行）
  - 直接测试：`echo '{\"name\":\"Alice\"}' | python3 plugins/hello_tool/main.py`

### plugins/memory_writer/main.py

- 功能用途：stdio 示例插件：把输入 `{path, content}` 写入 `data/external/`，并回传写入结果。
- 文档位置：本文档 → Plugins → `memory_writer/main.py`
- API/调用方式：
  - 被 `/api/plugins/invoke` 间接调用
  - 直接测试：`echo '{\"path\":\"demo/a.txt\",\"content\":\"hi\"}' | python3 plugins/memory_writer/main.py`

## 备注：newapi_test 子应用

### fass_gateway/app/newapi_test/__init__.py

- 功能用途：newapi_test 包标识；便于以模块形式启动测试应用。
- 文档位置：本文档 → 备注 → `newapi_test/__init__.py`
- API/调用方式：通常无需直接调用；配合 `uvicorn fass_gateway.app.newapi_test.main:app` 使用（内部）

### fass_gateway/app/newapi_test/main.py

- 功能用途：用于本地测试 NewAPI 连接与默认模型配置的独立 FastAPI 应用（带 CORS 与 `LOCAL_TEST_API_KEY` 鉴权）。
- 文档位置：本文档 → 备注 → `newapi_test/main.py`
- API/调用方式：以 `uvicorn fass_gateway.app.newapi_test.main:app` 形式启动后，提供 `/api/config/*`、`/api/models/list`、`/v1/*` 等测试端点
