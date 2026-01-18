# 仓库排除清单（GitHub 上传前必读）

## 目标

- 防止把大文件（模型权重）、运行态数据（SQLite/索引/fs_store）、第三方依赖（node_modules/target）与 IDE 过程文件（.trae）上传到 GitHub。
- 保证公开仓库“可克隆、可读、可复现”，并降低泄露隐私/密钥/个人数据风险。

## 必须排除（硬性要求）

- `assets/models/**`：全部排除（模型权重/大文件不入库）

## 可选排除（按仓库策略）

- `webui/dist/**`：前端构建产物（推荐不入库，走 CI/CD 或本地 build）
- `*.sqlite`：如果仓库内存在任何 SQLite 文件，应确认是否是运行态数据（一般应排除）

## 推荐 `.gitignore` 片段（可直接追加）

```gitignore
# ---- FASS public repo excludes ----
/assets/models/
/data/
/fass_gateway/data/

/webui/node_modules/
/webui/dist/
/memoscore/target/

__pycache__/
.pytest_cache/
.venv/
dist/
build/
*.sqlite
```

## 上传前自检清单

- 确认 `assets/models/` 目录下没有任何文件被纳入提交记录（包括 `.safetensors/.bin/.pt` 等）。
- 确认 `data/` 与 `fass_gateway/data/` 不在提交记录中（包含个人 diary、timeline、fs_store 片段等）。
- 确认未提交任何密钥：`config.env`、token、API Key（建议只提交 `config.env.example`）。
