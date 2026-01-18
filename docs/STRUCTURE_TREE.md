# 代码文件结构树

## 说明

- 本文档展示用于公开仓库的“源码/发布结构树”（以可公开提交/分发为目标）。为保证可读性与避免大文件入库，已排除第三方依赖、构建产物与运行态数据目录。
- `webui/` 按要求标记为实验性/失败代码：保留上传供参考，不做详细文档。
- 注意：本文结构树按“可公开的源码/文档”整理，不包含本地 IDE 配置（如 `.vscode/`）、虚拟环境（如 `.venv/`）、运行数据（如 `data/`）与本地模型（如 `assets/models/`）。

## 源码/发布结构树（根目录）

```text
.
├── docs
│   ├── API_REFERENCE.md
│   ├── BACKEND_FILE_INDEX.md
│   ├── DEPLOYMENT_BAREMETAL.md
│   ├── INDEX.md
│   ├── REPO_EXCLUDES.md
│   ├── STRUCTURE_TREE.md
│   ├── TECHNICAL_WHITEPAPER.md
│   └── assets
│       └── logo.svg
├── fass_gateway
│   ├── app
│   │   ├── mcp_tools
│   │   │   ├── __init__.py
│   │   │   ├── system_tools.py
│   │   │   └── web_tools.py
│   │   ├── models
│   │   │   ├── __init__.py
│   │   │   └── control.py
│   │   ├── newapi_test
│   │   │   ├── __init__.py
│   │   │   └── main.py
│   │   ├── routers
│   │   │   ├── __init__.py
│   │   │   ├── automations_api.py
│   │   │   ├── chat_api.py
│   │   │   ├── config_api.py
│   │   │   ├── control_api.py
│   │   │   ├── legacy_ollama_api.py
│   │   │   ├── mcp_api.py
│   │   │   ├── memory_api.py
│   │   │   ├── models_api.py
│   │   │   ├── openai_compat.py
│   │   │   ├── plugins_api.py
│   │   │   ├── settings_api.py
│   │   │   ├── tasks_api.py
│   │   │   ├── timeline_api.py
│   │   │   └── trace_api.py
│   │   ├── scripts
│   │   │   ├── __init__.py
│   │   │   └── rebuild_memory.py
│   │   ├── services
│   │   │   ├── __init__.py
│   │   │   ├── audit_log.py
│   │   │   ├── context_packs.py
│   │   │   ├── control_store.py
│   │   │   ├── dreaming.py
│   │   │   ├── embedding.py
│   │   │   ├── file_store.py
│   │   │   ├── ingest.py
│   │   │   ├── llm_proxy.py
│   │   │   ├── matching_engine.py
│   │   │   ├── mcp_executor.py
│   │   │   ├── mcp_loader.py
│   │   │   ├── mcp_registry.py
│   │   │   ├── memory.py
│   │   │   ├── model_catalog.py
│   │   │   ├── model_defaults.py
│   │   │   ├── model_registry.py
│   │   │   ├── newapi_client.py
│   │   │   ├── plugins.py
│   │   │   ├── provider_health.py
│   │   │   ├── provider_registry.py
│   │   │   ├── provider_router.py
│   │   │   ├── research.py
│   │   │   ├── self_heal.py
│   │   │   ├── task_runner.py
│   │   │   ├── timeline.py
│   │   │   ├── trace_hub.py
│   │   │   └── upstream_config.py
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── migrations.py
│   │   └── settings.py
│   ├── migrations
│   │   └── 0001_self_heal.sql
│   ├── tests
│   │   ├── __init__.py
│   │   └── test_memoscore_index_tasks.py
│   ├── config.env.example
│   └── requirements.txt
├── legacy_plugins
│   └── ThoughtClusterManager
│       ├── ThoughtClusterManager.js
│       └── plugin-manifest.json
├── memoscore
│   ├── .cargo
│   │   └── config.toml
│   ├── scripts
│   │   └── wsl_setup_aliyun.sh
│   ├── src
│   │   └── lib.rs
│   ├── Cargo.lock
│   ├── Cargo.toml
│   └── pyproject.toml
├── plugins
│   ├── hello_tool
│   │   ├── main.py
│   │   └── plugin.json
│   └── memory_writer
│       ├── main.py
│       └── plugin.json
├── scripts
│   └── vendor_embeddinggemma.ps1
├── webui  (EXPERIMENTAL/FAILED; keep for reference; no detailed docs)
│   ├── src
│   │   ├── ui
│   │   │   ├── components
│   │   │   │   ├── ApiKeyBanner.tsx
│   │   │   │   ├── PromptProvider.tsx
│   │   │   │   └── SnowflakeField.tsx
│   │   │   ├── lib
│   │   │   │   └── api.ts
│   │   │   ├── pages
│   │   │   │   ├── AutomationsPage.tsx
│   │   │   │   ├── ChatPage.tsx
│   │   │   │   ├── McpPage.tsx
│   │   │   │   ├── ModelCatalogPage.tsx
│   │   │   │   ├── ModelsPage.tsx
│   │   │   │   ├── ProfilesPage.tsx
│   │   │   │   ├── ProvidersPage.tsx
│   │   │   │   ├── SettingsPage.tsx
│   │   │   │   └── UpstreamsPage.tsx
│   │   │   ├── App.tsx
│   │   │   └── styles.css
│   │   └── main.tsx
│   ├── eslint.config.js
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.cjs
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── vite.config.ts
├── .dockerignore
├── .gitignore
├── Dockerfile
├── LICENSE
├── README.md
└── docker-compose.yml
```

## 后端结构树（`fass_gateway/app/`）

```text
.
└── fass_gateway
    └── app
        ├── mcp_tools
        │   ├── __init__.py
        │   ├── system_tools.py
        │   └── web_tools.py
        ├── models
        │   ├── __init__.py
        │   └── control.py
        ├── newapi_test
        │   ├── __init__.py
        │   └── main.py
        ├── routers
        │   ├── __init__.py
        │   ├── automations_api.py
        │   ├── chat_api.py
        │   ├── config_api.py
        │   ├── control_api.py
        │   ├── legacy_ollama_api.py
        │   ├── mcp_api.py
        │   ├── memory_api.py
        │   ├── models_api.py
        │   ├── openai_compat.py
        │   ├── plugins_api.py
        │   ├── settings_api.py
        │   ├── tasks_api.py
        │   ├── timeline_api.py
        │   └── trace_api.py
        ├── scripts
        │   ├── __init__.py
        │   └── rebuild_memory.py
        ├── services
        │   ├── __init__.py
        │   ├── audit_log.py
        │   ├── context_packs.py
        │   ├── control_store.py
        │   ├── dreaming.py
        │   ├── embedding.py
        │   ├── file_store.py
        │   ├── ingest.py
        │   ├── llm_proxy.py
        │   ├── matching_engine.py
        │   ├── mcp_executor.py
        │   ├── mcp_loader.py
        │   ├── mcp_registry.py
        │   ├── memory.py
        │   ├── model_catalog.py
        │   ├── model_defaults.py
        │   ├── model_registry.py
        │   ├── newapi_client.py
        │   ├── plugins.py
        │   ├── provider_health.py
        │   ├── provider_registry.py
        │   ├── provider_router.py
        │   ├── research.py
        │   ├── self_heal.py
        │   ├── task_runner.py
        │   ├── timeline.py
        │   ├── trace_hub.py
        │   └── upstream_config.py
        ├── __init__.py
        ├── db.py
        ├── main.py
        ├── migrations.py
        └── settings.py
```
