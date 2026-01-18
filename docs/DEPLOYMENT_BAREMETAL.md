# 实体机部署指南（Bare Metal）

## 适用范围

- 本文档面向实体机（或 VM）直接部署：不依赖 Docker。
- 仓库默认不分发大模型/权重：`assets/models/**` 已按要求排除；部署时需要选择一种 Embedding 方案（见下文）。

## 1. 环境与依赖

### 1.1 操作系统与基础依赖

- Linux（推荐 Ubuntu/Debian 系）
- Python：推荐 3.12（Dockerfile 亦使用 3.12）；最低建议 3.11+
- Node.js：仅在需要构建前端时需要（前端为实验性参考实现，可选）

### 1.2 Python 依赖（后端）

后端依赖定义在 `fass_gateway/requirements.txt`，其中已内置国内镜像源（阿里云）：

```bash
pip install -r fass_gateway/requirements.txt
```

### 1.3 Rust（可选）

当你希望使用高性能 Hybrid-RAG 核心 `memoscore`（Rust + PyO3）时，需要 Rust toolchain（`rustc/cargo`）与编译依赖。

如果不安装 `memoscore`：后端会自动降级到 `memory.py` 的 `_FallbackCore`（可用但性能/能力有限，且不具备 Tantivy/USearch 的混合检索特性）。

## 2. 配置（`config.env`）

后端使用 `pydantic-settings` 从 `config.env` 读取配置（见 `fass_gateway/app/settings.py`）。仓库提供 `fass_gateway/config.env.example` 作为参考。

### 2.1 关键配置项

- `api_key`：用于保护 `/api/*` 与 `/v1/*`（未设置则默认放行）
- 上游 LLM：
  - `newapi_base_url` / `newapi_api_key`（OpenAI/New-API 兼容上游）
  - 或 `ollama_base_url`（本地 Ollama）
- Embedding：由于 `assets/models/**` 不入库，推荐两种方式之一：
  - 方式 A（推荐）：`embedding_provider=openai_compat`，走上游 embedding（`llm_base_url` + `llm_api_key`）
  - 方式 B：`embedding_provider=local` 并将 `embedding_model_path` 指向你本地准备好的 SentenceTransformer 模型目录

## 3. 启动（后端）

```bash
python3 -m uvicorn fass_gateway.app.main:app --host 0.0.0.0 --port 8000
```

验证：

- `GET http://localhost:8000/v1/models`
- `POST http://localhost:8000/v1/chat/completions`

## 4. 前端（可选，实验性）

`webui/` 目录按项目要求标记为实验性/失败代码：

- 保留上传供参考
- 不作为稳定交付的运行界面

如需构建（仅供参考）：

```bash
cd webui
npm install
npm run build
```

构建后由 FastAPI 静态托管（`/` 挂载到 `webui/dist`）。

## 5. 持久化数据目录说明（运行态）

- `fass_gateway/data/fass_gateway.sqlite`：后端控制面板/任务/追踪/审计等数据库（SQLite/WAL）
- `data/fs_store/`：可选的文件系统真值存储（按 collection 分目录）
- `data/memoscore/`：`memoscore` 的 SQLite 真值库 + Tantivy/USearch 索引（若启用）

建议这些目录都不要提交到 GitHub（见 `docs/REPO_EXCLUDES.md`）。

## 6. 与 Docker 方案的差异与优势

### 6.1 差异

- Docker 方案通常在镜像构建阶段编译 Rust/PyO3（`memoscore`），并把前端构建产物打包进镜像；实体机方案把这些链路放到宿主机完成。
- Compose 方案还可配套 `searxng` 作为 WebSearch 服务；实体机同样可以独立部署 `searxng`（或用现成实例）。

### 6.2 实体机优先的工程优势（本项目建议）

- 编译链与 ABI 可控：Rust/PyO3 扩展在宿主机上更容易按目标机器优化、减少容器层引入的 ABI/依赖差异。
- 模型与驱动接入更直接：本地模型目录、GPU 驱动、文件系统持久化、性能分析工具链更易用。
- 受限网络更可维护：可统一配置 pip/npm 镜像源与缓存；对镜像拉取/构建依赖更少。
- 排障更高效：直接用系统日志、进程管理、IO/网络诊断工具进行定位。



## 8.（可选）以 systemd 方式托管

建议在生产环境用 systemd 管理 uvicorn 进程，并将 `config.env` 以环境变量或工作目录文件形式注入。

该部分可根据你们服务器规范在落地时补充（例如：WorkingDirectory、Restart=always、日志轮转等）。
