# FASS 技术白皮书（Technical Whitepaper）

## 0. 摘要

FASS 是一个面向生产环境的 AI 知识中枢/网关：以 FastAPI 提供 OpenAI 兼容接口，统一多 Provider 接入与熔断回退；以 SQLite-as-Truth 作为可审计的真值存储；以 `memoscore`（Rust + PyO3）实现“全文检索 + 向量 ANN”的 Hybrid-RAG；以 MCP/插件机制提供可控、可隔离的工具执行；并通过 Research/Dreaming 形成自动化知识回灌闭环。

## 1. 系统架构与技术栈

### 1.1 组件图（数据流）

```mermaid
flowchart LR
  User[Client / WebUI / cURL] -->|HTTP /v1 /api| Gateway[FastAPI Gateway]

  subgraph Core[Backend Core]
    Gateway --> Routers[Routers]
    Routers --> Services[Services]
    Services --> DB[(SQLite: fass_gateway.sqlite)]
    Services --> FS[(FS Store: data/fs_store)]
    Services --> Mem[MemoryStore]
    Mem -->|PyO3| MemosCore[memoscore (Rust)]
    MemosCore --> Tantivy[Tantivy Text Index]
    MemosCore --> USearch[USearch ANN Index]
    MemosCore --> MemDB[(SQLite: memoscore.sqlite)]
  end

  Services -->|NewAPI/OpenAI Compat| NewAPI[(Upstream: /v1/*)]
  Services -->|Ollama Compat| Ollama[(Upstream: /api/*)]

  Services -->|MCP execute| MCPProc[Isolated Process]
  MCPProc --> Searx[(SearxNG JSON API)]
  Services -->|Plugins stdio| PluginProc[External Tools]
```

### 1.2 技术栈说明

- Web 框架：FastAPI + Uvicorn（入口：[main.py](file:///home/saki/FASS/FASS/fass_gateway/app/main.py#L1-L67)）
- 上游 HTTP：httpx（NewAPI/Ollama/抓取等）
- 持久化：SQLite（WAL、外键、busy_timeout；见 [db.py](file:///home/saki/FASS/FASS/fass_gateway/app/db.py#L7-L93)）
- Hybrid-RAG 核心：
  - 文本索引：Tantivy（BM25 类检索；见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L23-L69) 与 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L402-L428)）
  - 向量索引：USearch（L2sq 距离；见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L72-L121) 与 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L430-L458)）
  - 真值库：SQLite `documents` + `index_tasks`（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L123-L168)）
- 自动化：Research（SearxNG 搜索 + 抓取）与 Dreaming（总结回灌；见 [research.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/research.py#L37-L138) / [dreaming.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/dreaming.py#L23-L68)）
- 工具链：
  - MCP：装饰器注册 + 子进程隔离执行（见 [mcp_registry.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/mcp_registry.py#L7-L55) / [mcp_executor.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/mcp_executor.py#L21-L58)）
  - Plugins：stdio 子进程执行（见 [plugins.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/plugins.py#L115-L179)）

## 2. 自研 Hybrid-RAG 算法原理详解（数学公式 + 流程图）

本节所有“算法主张”均可在 `memoscore` 实现中直接验证（核心入口：[`MemosCore.search`](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L388-L508)）。

### 2.1 设计目标

- 同时利用：
  - 关键词/全文匹配能力（适合精确术语、路径、代码片段）
  - 语义相似能力（适合改写、同义表达、上下文语义检索）
- 在工程上保证：SQLite 作为真值存储，索引作为派生（可重建），并且具备最终一致性与可审计性。

### 2.2 Hybrid 打分与归一化（可验证公式）

记：

- 文本检索得到候选集合 $\mathcal{D}_{text}$，每个候选有原始得分 $s_{text}(d)$（由 Tantivy 返回）
- 向量检索得到候选集合 $\mathcal{D}_{vec}$，每个候选有距离 $dist(d)$（USearch 的 L2sq 距离）

#### (1) 文本得分归一化

实现：先取 top_k 的扩展候选（top_k×4），计算最大分，再做除法归一化（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L407-L427)）。

$$
\hat{s}_{text}(d)=\frac{s_{text}(d)}{\max_{d'\in\mathcal{D}_{text}} s_{text}(d')+\epsilon}
$$

其中当最大值为 0 时实现等价于 $\epsilon=1$ 的安全分母处理。

#### (2) 向量相似度与归一化

实现：把距离映射为相似度 $sim(d)=\frac{1}{1+dist(d)}$，再用 best 做归一化（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L443-L457)）。

$$
sim(d)=\frac{1}{1+dist(d)}
$$

$$
\hat{s}_{vec}(d)=\frac{sim(d)}{\max_{d'\in\mathcal{D}_{vec}} sim(d')+\epsilon}
$$

#### (3) 融合打分（Hybrid Score）

实现：线性融合，权重固定为 0.55/0.45（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L460-L471)）。

$$
s(d)=0.55\cdot\hat{s}_{text}(d)+0.45\cdot\hat{s}_{vec}(d)
$$

并给出来源标记：`bm25`（仅文本）、`ann`（仅向量）、`hybrid`（两者都有）（同上代码段）。

### 2.3 索引任务与最终一致性（Index Tasks）

`memoscore` 将 SQLite `documents` 视为真值表；文本/向量索引由 `index_tasks` 驱动异步/增量构建。

关键点：

- `upsert_documents` 会写入/更新 documents，并把 `indexed_at_unix_ms` 置空，生成或更新 `index_tasks`（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L240-L249) 以及 `index_tasks` 表定义 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L140-L148)）。
- `sync_index_tasks(limit)` 批处理执行需要更新的文本/向量索引，成功后 commit tantivy、save usearch，并写回 `indexed_at_unix_ms`（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L379-L383)）。

```mermaid
flowchart TD
  A[Upsert docs] --> B[(SQLite documents)]
  A --> C[(SQLite index_tasks)]
  C -->|sync_index_tasks(limit)| D[Build/Update Tantivy]
  C -->|sync_index_tasks(limit)| E[Build/Update USearch]
  D --> F[commit + reader.reload]
  E --> G[save(usearch_index.bin)]
  F --> H[mark task done + set indexed_at_unix_ms]
  G --> H
```

### 2.4 与 Gateway 的 RAG 注入关系

在 Gateway 层（[`openai_compat.py`](file:///home/saki/FASS/FASS/fass_gateway/app/routers/openai_compat.py#L58-L104)）：

- 取用户最后一句 `query`
- 生成 embedding（失败可降级为纯文本查询）
- 调用 `store.search(...)` 获取 top_k 命中
- 将命中片段拼装为 system message 注入，驱动上游 LLM 输出“可引用”的答案

## 3. 关键技术突破点与创新性分析（基于可验证实现）

### 3.1 SQLite-as-Truth + 可重建索引

- FASS 把结构化/控制面/追踪等状态统一落地到 SQLite（见 [db.py](file:///home/saki/FASS/FASS/fass_gateway/app/db.py#L15-L93) 与 [migrations.py](file:///home/saki/FASS/FASS/fass_gateway/app/migrations.py#L18-L117)）。
- `memoscore` 把全文/向量索引视为 SQLite 真值的派生，确保：
  - 索引可重建
  - 可做一致性检查（`indexed_at_unix_ms`、`index_tasks`）
  - 便于备份与回滚（见 [self_heal.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/self_heal.py#L38-L121)）

### 3.2 Hybrid 检索融合的工程化落地

- 文本检索与向量检索统一落在同一个 doc_id 空间（SQLite 自增 id），并在搜索阶段融合打分（见 [lib.rs](file:///home/saki/FASS/FASS/memoscore/src/lib.rs#L460-L477)）。
- 归一化策略简单稳定，且在缺失单路信号时自然退化为单路检索（source 标记可追溯）。

### 3.3 可控工具链：MCP 子进程隔离 + 输出截断

- 工具执行放入子进程：避免工具逻辑污染主服务进程，提供超时与输出上限（见 [mcp_executor.py](file:///home/saki/FASS/FASS/fass_gateway/app/services/mcp_executor.py#L40-L58)）。
- 危险工具在 HTTP 层硬禁用（见 [mcp_api.py](file:///home/saki/FASS/FASS/fass_gateway/app/routers/mcp_api.py#L92-L95)）。

## 4. 性能基准测试数据（实验验证）

### 4.1 测试环境

来自本仓库当前实体机的实测输出（可复现）：

- Python：3.12.3
- Kernel/平台：Linux-6.8.0-90-generic-x86_64-with-glibc2.39
- CPU 逻辑核：56
- 内存：约 33.4 GB

（环境探测脚本可见本文末“复现方法”。）

### 4.2 基准任务定义

- 索引：插入 N=200 文档，每个文档含 `content` 与 `embedding`（dim=64），collection=`bench`
- 索引构建：调用 `sync_index_tasks(1000)` 直到返回 0
- 查询：Q=100 次 hybrid 查询（同时给 `query_text` 与 `query_vec`），top_k=8

说明：该基准以“算法与链路可用、可测”为目标，规模较小；用于在受限环境下快速回归与对比。

### 4.3 实测结果

（输出来自本次运行：）

| 指标 | 数值 |
|---|---:|
| Upsert（N=200） | 7.0946 s |
| Sync Index Tasks（N=200） | 7.2913 s |
| Search p50（Q=100） | 0.239 ms |
| Search p95（Q=100） | 0.277 ms |
| Search mean（Q=100） | 0.246 ms |

### 4.4 复现方法（可复制）

```bash
python3 - <<'PY'
import os, platform
mem_total=None
with open('/proc/meminfo','r',encoding='utf-8') as f:
    for ln in f:
        if ln.startswith('MemTotal:'):
            mem_total=int(ln.split()[1])*1024
            break
print('python', platform.python_version())
print('platform', platform.platform())
print('cpu_count', os.cpu_count())
print('mem_total_bytes', mem_total)
PY

python3 - <<'PY'
import os, random, shutil, statistics, time
from pathlib import Path
import memoscore
BASE=Path('/tmp/fass_bench_memoscore_small').resolve()
if BASE.exists(): shutil.rmtree(BASE)
BASE.mkdir(parents=True)
EMB_DIM=64; N_DOCS=200; TOP_K=8; N_QUERIES=100
rnd=random.Random(0)
core=memoscore.MemosCore(str(BASE), EMB_DIM, 10000)
docs=[]
for i in range(N_DOCS):
    tag=f'topic_{i%50}'
    docs.append({'path':f'note://{i}','content':f'[{tag}] document {i} about {tag}.','embedding':[rnd.random() for _ in range(EMB_DIM)]})

t0=time.perf_counter();
core.upsert_documents('bench', docs)
upsert=time.perf_counter()-t0

t0=time.perf_counter();
changed=0
while True:
    c=int(core.sync_index_tasks(1000))
    changed += c
    if c==0: break
sync=time.perf_counter()-t0

lat=[]
for _ in range(N_QUERIES):
    qid=rnd.randrange(N_DOCS)
    qtag=f'topic_{qid%50}'
    qvec=[rnd.random() for _ in range(EMB_DIM)]
    t=time.perf_counter();
    core.search('bench', qtag, qvec, TOP_K)
    lat.append((time.perf_counter()-t)*1000)
lat.sort()
print('upsert_s', round(upsert,4))
print('sync_s', round(sync,4), 'changed', changed)
print('lat_ms.p50', round(lat[int(0.5*(len(lat)-1))],3))
print('lat_ms.p95', round(lat[int(0.95*(len(lat)-1))],3))
print('lat_ms.mean', round(statistics.mean(lat),3))
PY
```

## 5. 与同类方案的对比优势（可验证维度）

| 维度 | FASS | 典型“只向量库”方案 | 典型“只全文检索”方案 |
|---|---|---|---|
| API 形态 | OpenAI 兼容 + 管理 API | 通常非 OpenAI 兼容 | 通常非 OpenAI 兼容 |
| 检索形态 | Hybrid：文本 + 向量融合（固定权重） | 向量为主（可选 metadata） | 文本为主（BM25/TF-IDF） |
| 真值存储 | SQLite-as-Truth（可备份/回滚） | 多为外部 DB/服务 | 多为索引本身 |
| 索引一致性 | index_tasks 最终一致性，可重建 | 依赖外部服务实现 | 依赖索引实现 |
| 工具执行 | MCP 子进程隔离 + 超时 | 不一定提供 | 不一定提供 |
| 部署形态 | 实体机优先（可选 Docker） | 依赖服务化组件 | 依赖服务化组件 |

注：该表只对“能力/接口/架构特性”做对比，不对第三方性能下定论。

## 6. 学术理论支撑（参考文献）

- Robertson, S., & Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond*.
- Malkov, Y. A., & Yashunin, D. A. (2018). *Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs (HNSW)*.
- Lewis, P. et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (RAG)*.
- Karpukhin, V. et al. (2020). *Dense Passage Retrieval (DPR)*.

## 7. 未来技术演进路线（Roadmap）

以下为规划项（非当前已实现）：

- 动态融合权重：从固定 0.55/0.45 走向“按 query 类型自适应/可学习”的融合策略。
- Rerank：在 Hybrid top_k 候选之上引入轻量 reranker（如 MMR/交叉编码器），提升上下文注入质量。
- Chunking 策略：对长文做结构化分块与引用定位（路径+偏移/段落 id），提升可追溯性。
- 评测与回归：沉淀离线评测集（查询-相关文档对），在 CI/实体机上跑检索质量与性能回归。
- 多租户与权限：在 collection 维度上做访问控制与审计策略细化。
