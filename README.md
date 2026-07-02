# 个人知识库系统

一个 Python 3.10+ 本地私有化个人知识库系统，覆盖采集、解析、整理索引与 RAG 对话。默认不依赖真实 LLM、OCR 或外部向量数据库；外部解析库缺失时会写入可解释的降级 Markdown，便于本地测试稳定通过。

## 目录结构

- `common/`：配置、日志、文件操作、断点、LLM 客户端、本地 embedding、异常。
- `data_collection/`：本地/远程文件采集，原始文件保存到 `storage/raw/YYYYMMDD/`，并转换到 `storage/parsed_md/`。
- `data_parsing/`：Markdown 分块、结构化摘要、YAML front matter 写入、迁移到 `storage/processed_md/`。
- `content_refinement/`：按 `config/categories.yaml` 分类，写入/合并 `storage/wiki/`，生成 JSON 全文与向量索引。
- `rag_chat/`：混合检索、多轮查询补全、流式回答和引用来源。
- `app.py`：FastAPI 入口。
- `tests/`：本地确定性单元测试与端到端测试。

## 环境搭建

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果只运行核心测试，缺少可选解析库也不会导致测试崩溃。

## 配置说明

- `PKB_ROOT`：项目/数据根目录，默认当前工作目录。
- `PKB_LLM_CONTEXT_WINDOW`：LLM 上下文窗口，默认 `4096`，分块大小为其 1/4。
- `PKB_LLM_PROVIDER`：LLM 提供方，远程 OpenAI 兼容服务设为 `openai-compatible`。
- `PKB_LLM_MODEL`：LLM 对话/摘要模型名。
- `PKB_LLM_API_KEY`：远程 LLM API Key；未设置时会回退读取 `OPENAI_API_KEY`。
- `PKB_LLM_BASE_URL`：远程 LLM Base URL；未设置时会回退读取 `OPENAI_BASE_URL`。
- `PKB_LLM_TIMEOUT`：远程 LLM 请求超时时间，默认 `60` 秒。
- `PKB_EMBEDDING_PROVIDER`：Embedding 提供方，远程 OpenAI 兼容服务设为 `openai-compatible`。
- `PKB_EMBEDDING_MODEL`：Embedding 模型名。
- `PKB_EMBEDDING_DIMENSION`：本地向量维度，默认 `64`；远程向量维度以模型返回为准。
- `PKB_EMBEDDING_API_KEY`：远程 embedding API Key；未设置时会回退读取 `OPENAI_API_KEY`。
- `PKB_EMBEDDING_BASE_URL`：远程 embedding Base URL；未设置时会回退读取 `OPENAI_BASE_URL`。
- `PKB_EMBEDDING_TIMEOUT`：远程 embedding 请求超时时间，默认 `30` 秒。
- `config/categories.yaml`：自定义分类规则，格式：

```yaml
categories:
  python:
    - Python
    - pytest
  ai:
    - RAG
    - LLM
```

日志写入 `logs/`，按日期切割，保留 30 天。断点信息写入 `storage/checkpoints/`。

## 模块调用

```python
from data_collection.collector import DataCollector
from data_parsing.processor import MarkdownProcessor
from content_refinement.refiner import ContentRefiner
from rag_chat.chat import RAGChat

collector = DataCollector()
collector.collect(["/path/to/note.md", "/path/to/file.pdf"])
MarkdownProcessor().process_all()
ContentRefiner().refine_all()
print(RAGChat().ask("检索 Python 知识").answer)
```

## API 服务

```bash
uvicorn app:app --reload
```

接口：

- `GET /health`
- `POST /collect`：`{"sources": ["/path/to/file.md"]}`
- `POST /process`：`{"paths": null}` 或指定 parsed md 路径
- `POST /refine`：`{"paths": null}` 或指定 processed md 路径
- `POST /chat`：`{"query": "问题", "top_k": 5}`
- `POST /chat/stream`：流式文本回答

## 测试

```bash
pytest
```

若环境缺少 pytest，可先验证语法：

```bash
python -m compileall common data_collection data_parsing content_refinement rag_chat app.py tests
```
