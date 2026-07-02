from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse

from access.hmac_auth import sign as hmac_sign, verify as hmac_verify
from access.screening import PrivacyScreener
from access.store import AccessStore
from alerts.alerter import Alerter
from bootstrap.estimator import CostEstimator
from bootstrap.runner import BootstrapRunner
from bootstrap.store import BootstrapStore
from common.config import load_settings
from common.llm_cache import LLMCache
from common.llm_gateway import LLMGateway
from common.llm_router import ModelRouter
from common.logging_config import setup_logger
from common.prompt_registry import PromptRegistry
from common.prompt_router import PromptRouter
from content_refinement.indexer import Indexer
from content_refinement.markdown_index import build_markdown_indexes
from content_refinement.refiner import ContentRefiner
from data_collection.collector import DataCollector
from data_parsing.processor import PROCESS_STATUS, MarkdownProcessor
from graph.builder import build_graph
from graph.query import GraphQuery
from graph.store import GraphStore
from jobs.recovery import RecoveryService
from jobs.runner import JobRunner
from jobs.store import JobStore
from jobs.worker import JobWorker
from metrics.daily import DailyStatsAggregator
from rag_chat.chat import RAGChat
from rag_chat.iterative_search import IterativeSearch
from rag_chat.session_store import ChatStore
from sync.source_versions import IncrementalSync

settings = load_settings(Path(__file__).resolve().parent)
logger = setup_logger("app", settings)
job_store = JobStore(settings)
job_worker = JobWorker(max_workers=2)
RecoveryService(settings, job_store).recover_stale_jobs()
app = FastAPI(title="Personal Knowledge Base", version="0.1.0")


class CollectRequest(BaseModel):
    sources: list[str]


class ProcessRequest(BaseModel):
    paths: list[str] | None = None


class RefineRequest(BaseModel):
    paths: list[str] | None = None


class ChatRequest(BaseModel):
    query: str
    top_k: int = 5
    session_id: str = ""


class SessionCreateRequest(BaseModel):
    title: str = ""


class BootstrapCreateRequest(BaseModel):
    name: str = ""
    sources: list[str] = []


class BootstrapApproveRequest(BaseModel):
    approved_by: str = "admin"


class DistillRequest(BaseModel):
    sources: list[str] = []


class RetryRequest(BaseModel):
    job_id: str


class SyncScanRequest(BaseModel):
    roots: list[str] = []


class PromptRegisterRequest(BaseModel):
    name: str
    version: str = "v1"
    content: str = ""
    traffic_percent: int = 100
    active: bool = True


class TrafficSplitRequest(BaseModel):
    splits: dict[str, int]


class AlertCreateRequest(BaseModel):
    level: str = "P2"
    event: str
    message: str
    data: dict[str, Any] = {}


class UserCreateRequest(BaseModel):
    name: str
    email: str = ""
    is_admin: bool = False


class ScopeGroupRequest(BaseModel):
    name: str
    topics: list[str] = []
    users: list[str] = []


class ClientRegisterRequest(BaseModel):
    name: str
    callback_url: str = ""


class AccessRequestCreate(BaseModel):
    client_id: str
    user_id: str
    scope: str
    purpose: str = ""


class GrantApproveRequest(BaseModel):
    request_id: str
    ttl_days: int = 7


@app.exception_handler(Exception)
def global_exception_handler(_, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc), "type": exc.__class__.__name__})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _html_page()


@app.get("/status")
def status() -> dict[str, Any]:
    return {
        "process": dict(PROCESS_STATUS),
        "pending_parsed_md": len(list(Path(settings.parsed_md_dir).glob("*.md"))),
        "processed_md": len(list(Path(settings.processed_md_dir).glob("*.md"))),
        "wiki_docs": len(list(Path(settings.wiki_dir).glob("**/*.md"))),
    }


@app.get("/metrics/llm")
def llm_metrics(limit: int = 20) -> dict[str, Any]:
    return {"calls": LLMGateway(settings).recent_calls(limit)}


@app.get("/metrics/models")
def describe_models() -> dict[str, Any]:
    return {"models": ModelRouter(settings).describe()}


@app.get("/metrics/cache")
def llm_cache_stats() -> dict[str, Any]:
    return LLMCache(settings).stats()


@app.post("/metrics/cache/clear-expired")
def clear_expired_cache() -> dict[str, Any]:
    return {"removed": LLMCache(settings).clear_expired()}


@app.post("/metrics/daily/aggregate")
def aggregate_metrics_daily() -> dict[str, Any]:
    return DailyStatsAggregator(settings).aggregate()


@app.get("/metrics/daily")
def list_metrics_daily(days: int = 7) -> dict[str, Any]:
    return {"daily": DailyStatsAggregator(settings).list_recent(days)}


@app.get("/prompts")
def list_prompt_names() -> dict[str, Any]:
    return {"prompts": PromptRegistry(settings).list_prompts()}


@app.get("/prompts/{name}/versions")
def list_prompt_versions(name: str) -> dict[str, Any]:
    return {"versions": PromptRouter(settings).list(name)}


@app.post("/prompts/register")
def register_prompt(req: PromptRegisterRequest) -> dict[str, Any]:
    return {"prompt": PromptRouter(settings).register(req.name, req.version, req.content, req.traffic_percent, req.active)}


@app.post("/prompts/{name}/traffic")
def set_prompt_traffic(name: str, req: TrafficSplitRequest) -> dict[str, Any]:
    PromptRouter(settings).set_traffic(name, req.splits)
    return {"prompt": PromptRouter(settings).list(name)}


@app.get("/alerts")
def list_alerts(level: str | None = None, resolved: bool | None = None, limit: int = 50) -> dict[str, Any]:
    return {"alerts": Alerter(settings).store.list(level, resolved, limit)}


@app.post("/alerts")
def create_alert(req: AlertCreateRequest) -> dict[str, Any]:
    return {"alert": Alerter(settings).alert(req.level, req.event, req.message, req.data)}


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str) -> dict[str, Any]:
    Alerter(settings).store.resolve(alert_id)
    return {"status": "resolved"}


@app.get("/alerts/stats")
def alert_stats() -> dict[str, Any]:
    return Alerter(settings).store.stats()


@app.post("/collect")
def collect(request: CollectRequest) -> dict[str, Any]:
    results = DataCollector(settings).collect(request.sources)
    return {"results": [r.__dict__ for r in results]}


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    collector = DataCollector(settings)
    results = []
    for file in files:
        content = await file.read()
        results.append(collector.collect_uploaded_file(file.filename or "upload.bin", content).__dict__)
    return {"results": results}


@app.post("/process")
def process(request: ProcessRequest) -> dict[str, Any]:
    processor = MarkdownProcessor(settings)
    if request.paths:
        results = [processor.process_file(path) for path in request.paths]
    else:
        results = processor.process_all()
    return {"results": [r.__dict__ for r in results]}


@app.post("/refine")
def refine(request: RefineRequest) -> dict[str, Any]:
    refiner = ContentRefiner(settings)
    if request.paths:
        results = [refiner.refine_file(path) for path in request.paths]
        Indexer(settings).update_indexes()
    else:
        results = refiner.refine_all()
    return {"results": [r.__dict__ for r in results]}


@app.post("/distill")
def distill(request: DistillRequest) -> dict[str, Any]:
    job = job_store.create_job("distill", {"sources": request.sources})
    runner = JobRunner(settings, job_store)
    job_worker.submit(job.id, lambda: runner.run_distill(job.id))
    return {"job": job_store.to_dict(job)}


@app.post("/jobs/distill")
def create_distill_job(request: DistillRequest) -> dict[str, Any]:
    return distill(request)


@app.get("/jobs")
def list_jobs(limit: int = 20) -> dict[str, Any]:
    return {"jobs": [job_store.to_dict(job) for job in job_store.list_jobs(limit)]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job_store.to_dict(job), "running": job_worker.is_running(job_id)}


@app.get("/jobs/{job_id}/events")
def get_job_events(job_id: str, limit: int = 100) -> dict[str, Any]:
    if not job_store.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"events": job_store.list_events(job_id, limit)}


@app.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, Any]:
    if not job_store.get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    runner = JobRunner(settings, job_store)
    job_worker.submit(job_id, lambda: runner.retry(job_id))
    return {"job": job_store.to_dict(job_store.get_job(job_id))}


@app.post("/jobs/recover")
def recover_jobs() -> dict[str, Any]:
    return {"recovered": RecoveryService(settings, job_store).recover_stale_jobs()}


@app.post("/sync/scan")
def scan_sources(req: SyncScanRequest) -> dict[str, Any]:
    return IncrementalSync(settings).scan(req.roots)


@app.get("/sync/changed")
def list_changed_sources() -> dict[str, Any]:
    return {"paths": IncrementalSync(settings).get_changed_paths()}


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    response = RAGChat(settings).ask(request.query, request.top_k, session_id=request.session_id)
    return response.__dict__


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    return StreamingResponse(
        RAGChat(settings).stream_ask(request.query, request.top_k, session_id=request.session_id),
        media_type="text/event-stream",
    )


@app.post("/chat/iterative")
def iterative_chat(request: ChatRequest) -> dict[str, Any]:
    results, trace = IterativeSearch(settings).search(request.query, request.top_k)
    return {"sources": [r.__dict__ for r in results], "trace": trace}


@app.get("/chat/sessions")
def list_chat_sessions(limit: int = 50) -> dict[str, Any]:
    return {"sessions": ChatStore(settings).list_sessions(limit)}


@app.post("/chat/sessions")
def create_chat_session(request: SessionCreateRequest) -> dict[str, Any]:
    return {"session": ChatStore(settings).create_session(request.title)}


@app.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str) -> dict[str, Any]:
    session = ChatStore(settings).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    messages = ChatStore(settings).list_messages(session_id)
    return {"session": session, "messages": messages}


@app.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str) -> dict[str, Any]:
    if not ChatStore(settings).get_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    ChatStore(settings).delete_session(session_id)
    return {"status": "deleted"}


@app.post("/index/markdown/rebuild")
def rebuild_markdown_index() -> dict[str, Any]:
    return build_markdown_indexes(settings)


@app.get("/graph")
def get_graph() -> dict[str, Any]:
    stored = GraphStore(settings).load()
    if stored is None:
        stored = build_graph(settings)
        GraphStore(settings).update(stored)
    return stored.to_dict()


@app.post("/graph/rebuild")
def rebuild_graph() -> dict[str, Any]:
    graph = build_graph(settings)
    GraphStore(settings).update(graph)
    return graph.to_dict()


@app.get("/graph/node/{name}")
def get_graph_node(name: str, depth: int = 1) -> dict[str, Any]:
    graph = GraphStore(settings).load() or build_graph(settings)
    query = GraphQuery(graph)
    node = query.find(name)
    if not node:
        raise HTTPException(status_code=404, detail="node not found")
    neighbors = query.neighbors(name, depth=depth)
    return {"node": node.__dict__, "neighbors": [n.__dict__ for n in neighbors]}


@app.post("/bootstrap/plans")
def create_bootstrap_plan(req: BootstrapCreateRequest) -> dict[str, Any]:
    return {"plan": BootstrapStore(settings).create_plan(req.name, req.sources)}


@app.get("/bootstrap/plans")
def list_bootstrap_plans(limit: int = 50) -> dict[str, Any]:
    return {"plans": BootstrapStore(settings).list_plans(limit)}


@app.get("/bootstrap/plans/{plan_id}")
def get_bootstrap_plan(plan_id: str) -> dict[str, Any]:
    plan = BootstrapStore(settings).get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return {"plan": plan}


@app.post("/bootstrap/plans/{plan_id}/estimate")
def estimate_bootstrap_plan(plan_id: str) -> dict[str, Any]:
    store = BootstrapStore(settings)
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    estimation = CostEstimator(settings).estimate(plan["sources"])
    updated = store.update_plan(
        plan_id,
        status="estimated",
        total_files=estimation["total_files"],
        total_chars=estimation["total_chars"],
        estimated_tokens=estimation["estimated_tokens"],
        estimated_cost_usd=estimation["estimated_cost_usd"],
    )
    return {"plan": updated, "estimation": estimation}


@app.post("/bootstrap/plans/{plan_id}/approve")
def approve_bootstrap_plan(plan_id: str, req: BootstrapApproveRequest) -> dict[str, Any]:
    store = BootstrapStore(settings)
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return {"plan": store.update_plan(plan_id, status="approved", approved_by=req.approved_by)}


@app.post("/bootstrap/plans/{plan_id}/execute")
def execute_bootstrap_plan(plan_id: str) -> dict[str, Any]:
    return {"plan": BootstrapRunner(settings).execute(plan_id)}


@app.post("/users")
def create_user_ep(req: UserCreateRequest) -> dict[str, Any]:
    return {"user": AccessStore(settings).create_user(req.name, req.email, req.is_admin)}


@app.get("/users")
def list_users_ep() -> dict[str, Any]:
    return {"users": AccessStore(settings).list_users()}


@app.get("/users/me")
def get_me(request: Request) -> dict[str, Any]:
    api_key = request.headers.get("x-api-key", "")
    user = AccessStore(settings).get_user_by_api_key(api_key) if api_key else None
    if not user:
        raise HTTPException(status_code=401, detail="invalid api key")
    return {"user": user}


@app.post("/scope-groups")
def create_scope_group_ep(req: ScopeGroupRequest) -> dict[str, Any]:
    return {"group": AccessStore(settings).create_scope_group(req.name, req.topics, req.users)}


@app.get("/scope-groups")
def list_scope_groups_ep() -> dict[str, Any]:
    return {"groups": AccessStore(settings).list_scope_groups()}


@app.post("/access/clients")
def register_access_client_ep(req: ClientRegisterRequest) -> dict[str, Any]:
    return {"client": AccessStore(settings).register_client(req.name, req.callback_url)}


@app.get("/access/clients")
def list_access_clients_ep() -> dict[str, Any]:
    return {"clients": AccessStore(settings).list_clients()}


@app.post("/access/requests")
def create_access_request_ep(req: AccessRequestCreate) -> dict[str, Any]:
    ok, reason = PrivacyScreener().filter_scope(req.scope, ["password", "secret", "salary"])
    if not ok:
        raise HTTPException(status_code=403, detail=f"scope rejected: {reason}")
    return {"request": AccessStore(settings).create_request(req.client_id, req.user_id, req.scope, req.purpose)}


@app.get("/access/requests")
def list_access_requests_ep(user_id: str = "", status: str = "") -> dict[str, Any]:
    return {"requests": AccessStore(settings).list_requests(user_id or None, status or None)}


@app.post("/access/grants/approve")
def approve_access_grant_ep(req: GrantApproveRequest) -> dict[str, Any]:
    store = AccessStore(settings)
    request = store.get_request(req.request_id)
    if not request:
        raise HTTPException(status_code=404, detail="request not found")
    store.update_request(req.request_id, status="approved")
    return {"grant": store.create_grant(req.request_id, request["client_id"], request["user_id"], request["scope"], req.ttl_days)}


@app.get("/access/grants")
def list_access_grants_ep(user_id: str = "", client_id: str = "") -> dict[str, Any]:
    return {"grants": AccessStore(settings).list_grants(user_id or None, client_id or None)}


@app.delete("/access/grants/{grant_id}")
def revoke_access_grant_ep(grant_id: str) -> dict[str, Any]:
    AccessStore(settings).revoke_grant(grant_id)
    return {"status": "revoked"}


def _html_page() -> str:
    return r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>KaaS Neon Console</title>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&display=swap');
    :root{--bg:#05060f;--panel:rgba(13,19,38,.72);--panel2:rgba(20,30,60,.58);--line:rgba(109,231,255,.22);--cyan:#6de7ff;--pink:#ff4fd8;--lime:#b8ff5a;--orange:#ffb86b;--text:#eaf6ff;--muted:#8ba6c9;--danger:#ff5a7a}
    *{box-sizing:border-box} body{margin:0;color:var(--text);background:radial-gradient(circle at 10% 5%,rgba(109,231,255,.18),transparent 28%),radial-gradient(circle at 90% 0%,rgba(255,79,216,.16),transparent 32%),linear-gradient(135deg,#03040a,#071326 55%,#04050e);font-family:Rajdhani,system-ui,sans-serif;min-height:100vh;overflow-x:hidden} body:before{content:"";position:fixed;inset:0;background-image:linear-gradient(rgba(109,231,255,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(109,231,255,.04) 1px,transparent 1px);background-size:42px 42px;mask-image:linear-gradient(to bottom,rgba(0,0,0,.9),rgba(0,0,0,.18));pointer-events:none} body:after{content:"";position:fixed;inset:0;background:repeating-linear-gradient(0deg,rgba(255,255,255,.025) 0 1px,transparent 1px 4px);mix-blend-mode:overlay;pointer-events:none}
    .shell{position:relative;display:grid;grid-template-columns:280px 1fr;min-height:100vh}.sidebar{padding:24px 18px;border-right:1px solid var(--line);background:linear-gradient(180deg,rgba(4,9,24,.92),rgba(9,14,30,.74));backdrop-filter:blur(18px);position:sticky;top:0;height:100vh}.brand{display:flex;gap:12px;align-items:center;margin-bottom:24px}.logo{width:48px;height:48px;border-radius:16px;background:conic-gradient(from 180deg,var(--cyan),var(--pink),var(--lime),var(--cyan));box-shadow:0 0 36px rgba(109,231,255,.4);position:relative}.logo:after{content:"";position:absolute;inset:8px;border-radius:11px;background:#071326}.brand h1{font-family:Orbitron;margin:0;font-size:18px;letter-spacing:.08em}.brand p{margin:3px 0 0;color:var(--muted);font-size:13px}.nav{display:grid;gap:8px}.nav button{display:flex;align-items:center;gap:10px;width:100%;border:1px solid transparent;background:transparent;color:var(--muted);border-radius:14px;padding:12px 14px;font:600 15px Rajdhani;cursor:pointer;text-align:left}.nav button.active,.nav button:hover{color:var(--text);border-color:var(--line);background:linear-gradient(90deg,rgba(109,231,255,.15),rgba(255,79,216,.08));box-shadow:inset 0 0 22px rgba(109,231,255,.06)}.main{padding:26px;position:relative}.hero{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:18px}.hero h2{font-family:Orbitron;margin:0;font-size:36px;letter-spacing:.04em;text-shadow:0 0 22px rgba(109,231,255,.45)}.hero p{color:var(--muted);font-size:16px;margin:10px 0 0}.chip{border:1px solid var(--line);border-radius:999px;padding:8px 12px;background:rgba(109,231,255,.08);color:var(--cyan);font-weight:700}.grid{display:grid;grid-template-columns:420px 1fr;gap:18px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:18px}.stat,.card{border:1px solid var(--line);background:linear-gradient(160deg,var(--panel),rgba(5,10,24,.62));backdrop-filter:blur(18px);border-radius:24px;box-shadow:0 24px 80px rgba(0,0,0,.32),inset 0 1px 0 rgba(255,255,255,.08)}.stat{padding:16px;position:relative;overflow:hidden}.stat:before{content:"";position:absolute;inset:-60px;background:radial-gradient(circle,rgba(109,231,255,.16),transparent 45%);transform:translateX(50%)}.stat label{color:var(--muted);font-size:13px}.stat strong{display:block;font-family:Orbitron;font-size:24px;margin-top:6px}.card{padding:18px;margin-bottom:18px}.card h3{font-family:Orbitron;margin:0 0 14px;font-size:16px;letter-spacing:.06em}.muted{color:var(--muted)}textarea,input,select{width:100%;background:rgba(1,6,18,.72);border:1px solid var(--line);color:var(--text);border-radius:16px;padding:12px 14px;font:500 15px Rajdhani;outline:none}textarea{min-height:120px;resize:vertical}textarea:focus,input:focus{border-color:var(--cyan);box-shadow:0 0 0 3px rgba(109,231,255,.1)}.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}button.primary,.ghost,.danger{border:0;border-radius:14px;padding:10px 15px;font:800 14px Rajdhani;letter-spacing:.03em;cursor:pointer;color:#04111c}.primary{background:linear-gradient(135deg,var(--cyan),#8dffea);box-shadow:0 0 26px rgba(109,231,255,.26)}.ghost{background:rgba(255,255,255,.06);color:var(--text);border:1px solid var(--line)}.danger{background:linear-gradient(135deg,var(--danger),var(--pink));color:white}.console{background:rgba(1,4,12,.78);border:1px solid rgba(109,231,255,.16);border-radius:18px;padding:14px;white-space:pre-wrap;word-break:break-word;max-height:320px;overflow:auto;color:#c7f6ff;font:13px ui-monospace,Menlo,monospace}.chat-layout{display:grid;grid-template-columns:320px 1fr;gap:18px}.sessions{max-height:640px;overflow:auto}.session{padding:12px;border:1px solid rgba(109,231,255,.14);border-radius:16px;margin-bottom:10px;cursor:pointer;background:rgba(255,255,255,.035)}.session.active{border-color:var(--cyan);box-shadow:0 0 24px rgba(109,231,255,.16)}.session b{display:block}.session span{color:var(--muted);font-size:12px}.messages{height:560px;overflow:auto;padding:18px;background:rgba(1,4,12,.5);border:1px solid rgba(109,231,255,.12);border-radius:20px}.msg{max-width:84%;padding:13px 15px;border-radius:18px;margin-bottom:12px;white-space:pre-wrap;line-height:1.55}.msg.user{margin-left:auto;background:linear-gradient(135deg,rgba(109,231,255,.23),rgba(109,231,255,.08));border:1px solid rgba(109,231,255,.28)}.msg.bot{background:linear-gradient(135deg,rgba(255,79,216,.13),rgba(255,255,255,.04));border:1px solid rgba(255,79,216,.2)}.chatbar{display:grid;grid-template-columns:1fr 96px;gap:10px;margin-top:12px}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid rgba(109,231,255,.12);padding:10px;text-align:left;color:#dcefff}th{color:var(--cyan);font-weight:800}.badge{display:inline-block;border-radius:999px;padding:2px 9px;font-weight:800;font-size:12px}.ok{background:rgba(184,255,90,.18);color:var(--lime)}.err{background:rgba(255,90,122,.2);color:#ff8aa1}.run{background:rgba(255,184,107,.18);color:var(--orange)}.view{animation:rise .35s ease both}@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@media(max-width:1000px){.shell{grid-template-columns:1fr}.sidebar{height:auto;position:relative}.grid,.chat-layout,.cards{grid-template-columns:1fr}}
  </style>
</head>
<body><div id="root"></div>
<script type="text/babel">
const {useEffect,useMemo,useState,useRef}=React;
const nav=[['chat','对话中枢','✦'],['ingest','采集蒸馏','⬡'],['jobs','任务编排','◈'],['metrics','成本指标','◍'],['graph','知识图谱','✣'],['bootstrap','初始化','▣'],['access','权限授权','⛨'],['prompts','提示词','⌘'],['settings','系统','◎']];
const api={async json(url,opts={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...opts});const t=await r.text();let d={};try{d=t?JSON.parse(t):{}}catch{d={raw:t}}if(!r.ok)throw new Error(JSON.stringify(d));return d},post(url,body){return this.json(url,{method:'POST',body:JSON.stringify(body)})},del(url){return this.json(url,{method:'DELETE'})}};
function Shell(){const[view,setView]=useState('chat');const[status,setStatus]=useState({});useEffect(()=>{loadStatus();const id=setInterval(loadStatus,3000);return()=>clearInterval(id)},[]);async function loadStatus(){try{setStatus(await api.json('/status'))}catch{}}return <div className="shell"><aside className="sidebar"><div className="brand"><div className="logo"/><div><h1>KaaS NEON</h1><p>personal knowledge cockpit</p></div></div><div className="nav">{nav.map(n=><button key={n[0]} onClick={()=>setView(n[0])} className={view===n[0]?'active':''}><span>{n[2]}</span>{n[1]}</button>)}</div></aside><main className="main"><div className="hero"><div><h2>{nav.find(n=>n[0]===view)?.[1]}</h2><p>RAG · Knowledge Graph · Worker Pipeline · Cost Control · Access Gateway</p></div><div className="chip">ONLINE / 8001</div></div><Stats status={status}/>{view==='chat'&&<Chat/>}{view==='ingest'&&<Ingest/>}{view==='jobs'&&<Jobs/>}{view==='metrics'&&<Metrics/>}{view==='graph'&&<Graph/>}{view==='bootstrap'&&<Bootstrap/>}{view==='access'&&<Access/>}{view==='prompts'&&<Prompts/>}{view==='settings'&&<Settings/>}</main></div>}
function Stats({status}){return <div className="cards"><div className="stat"><label>Wiki Docs</label><strong>{status.wiki_docs??'—'}</strong></div><div className="stat"><label>Processed</label><strong>{status.processed_md??'—'}</strong></div><div className="stat"><label>Pending</label><strong>{status.pending_parsed_md??'—'}</strong></div><div className="stat"><label>Pipeline</label><strong>{status.process?.state||'idle'}</strong></div></div>}
function Chat(){const[sessions,setSessions]=useState([]),[sid,setSid]=useState(''),[msgs,setMsgs]=useState([]),[q,setQ]=useState('');const box=useRef(null);useEffect(()=>{loadSessions()},[]);async function loadSessions(){const d=await api.json('/chat/sessions');setSessions(d.sessions||[])}async function open(s){setSid(s.id);const d=await api.json('/chat/sessions/'+s.id);setMsgs((d.messages||[]).map(m=>({role:m.role,text:m.content})))}async function newS(){const d=await api.post('/chat/sessions',{title:'新会话'});setSid(d.session.id);setMsgs([]);loadSessions()}async function send(){if(!q.trim())return;const query=q;setQ('');setMsgs(m=>[...m,{role:'user',text:query},{role:'assistant',text:''}]);const res=await fetch('/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,top_k:5,session_id:sid})});const reader=res.body.getReader();const dec=new TextDecoder();while(true){const {done,value}=await reader.read();if(done)break;const chunk=dec.decode(value,{stream:true});setMsgs(m=>{const cp=[...m];cp[cp.length-1]={...cp[cp.length-1],text:cp[cp.length-1].text+chunk};return cp});setTimeout(()=>box.current&&(box.current.scrollTop=box.current.scrollHeight),0)}loadSessions()}return <div className="chat-layout"><div className="card"><h3>会话矩阵</h3><button className="primary" onClick={newS}>新建会话</button><div className="sessions" style={{marginTop:12}}>{sessions.map(s=><div className={'session '+(s.id===sid?'active':'')} onClick={()=>open(s)} key={s.id}><b>{s.title||s.id}</b><span>{s.updated_at}</span></div>)}</div></div><div className="card"><h3>神经对话流</h3><div className="messages" ref={box}>{msgs.map((m,i)=><div key={i} className={'msg '+(m.role==='user'?'user':'bot')}>{m.text}</div>)}</div><div className="chatbar"><input value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>e.key==='Enter'&&send()} placeholder="输入问题，启动检索..."/><button className="primary" onClick={send}>发送</button></div></div></div>}
function Ingest(){const[src,setSrc]=useState(''),[out,setOut]=useState('等待任务');const[file,setFile]=useState(null);const sources=()=>src.split('\n').map(x=>x.trim()).filter(Boolean);async function run(name,fn){setOut('执行中...');try{setOut(JSON.stringify(await fn(),null,2))}catch(e){setOut(String(e))}}async function upload(){if(!file?.length)return setOut('请选择文件');const form=new FormData();[...file].forEach(f=>form.append('files',f));const r=await fetch('/upload',{method:'POST',body:form});setOut(JSON.stringify(await r.json(),null,2))}return <div className="grid"><div className="card"><h3>数据源入口</h3><textarea value={src} onChange={e=>setSrc(e.target.value)} placeholder={'https://...\n/Users/me/Documents\n/Users/me/file.md'}/><div className="btns"><button className="primary" onClick={()=>run('collect',()=>api.post('/collect',{sources:sources()}))}>采集</button><button className="ghost" onClick={()=>run('distill',()=>api.post('/jobs/distill',{sources:sources()}))}>后台蒸馏</button><button className="ghost" onClick={()=>run('process',()=>api.post('/process',{paths:null}))}>解析</button><button className="ghost" onClick={()=>run('refine',()=>api.post('/refine',{paths:null}))}>索引</button></div><h3>上传文件</h3><input type="file" multiple onChange={e=>setFile(e.target.files)}/><button className="primary" style={{marginTop:12}} onClick={upload}>上传并采集</button></div><div className="card"><h3>执行输出</h3><div className="console">{out}</div></div></div>}
function Jobs(){const[jobs,setJobs]=useState([]),[events,setEvents]=useState('');useEffect(()=>{load()},[]);async function load(){setJobs((await api.json('/jobs?limit=40')).jobs||[])}async function ev(id){const d=await api.json('/jobs/'+id+'/events');setEvents((d.events||[]).map(e=>`[${e.level}] ${e.event} - ${e.message}`).join('\n'))}return <div className="card"><h3>Worker Timeline</h3><button className="ghost" onClick={load}>刷新</button><Table rows={jobs} cols={['id','type','status','stage','current','total']} action={j=><button className="ghost" onClick={()=>ev(j.id)}>事件</button>}/><div className="console">{events||'选择任务查看事件'}</div></div>}
function Metrics(){const[calls,setCalls]=useState([]),[daily,setDaily]=useState([]),[cache,setCache]=useState({});useEffect(()=>{load()},[]);async function load(){setCalls((await api.json('/metrics/llm?limit=30')).calls||[]);setDaily((await api.json('/metrics/daily')).daily||[]);setCache(await api.json('/metrics/cache'))}return <div className="grid"><div className="card"><h3>Cache / Daily</h3><button className="primary" onClick={()=>api.post('/metrics/daily/aggregate',{}).then(load)}>聚合日报</button><div className="console">{JSON.stringify({cache,daily},null,2)}</div></div><div className="card"><h3>LLM Calls</h3><button className="ghost" onClick={load}>刷新</button><Table rows={calls} cols={['created_at','purpose','model','prompt_tokens','completion_tokens','status']}/></div></div>}
function Graph(){const[g,setG]=useState(null),[node,setNode]=useState(''),[res,setRes]=useState('');async function load(rebuild=false){setG(await api[rebuild?'post':'json'](rebuild?'/graph/rebuild':'/graph',{}))}async function query(){setRes(JSON.stringify(await api.json('/graph/node/'+encodeURIComponent(node)),null,2))}return <div className="grid"><div className="card"><h3>Graph Core</h3><button className="primary" onClick={()=>load(false)}>加载</button><button className="ghost" onClick={()=>load(true)} style={{marginLeft:8}}>重建</button><div className="console">{g?`Nodes: ${g.nodes?.length||0}\nEdges: ${g.edges?.length||0}`:'未加载'}</div></div><div className="card"><h3>Node Probe</h3><input value={node} onChange={e=>setNode(e.target.value)} placeholder="RAG / Python / 项目名"/><button className="primary" onClick={query} style={{marginTop:12}}>查询邻居</button><div className="console">{res}</div></div></div>}
function Bootstrap(){const[name,setName]=useState(''),[src,setSrc]=useState(''),[plans,setPlans]=useState([]),[out,setOut]=useState('');useEffect(()=>{load()},[]);async function load(){setPlans((await api.json('/bootstrap/plans')).plans||[])}async function create(){const d=await api.post('/bootstrap/plans',{name,sources:src.split('\n').filter(Boolean)});setOut(JSON.stringify(d,null,2));load()}async function act(id,a){const url='/bootstrap/plans/'+id+'/'+a;const body=a==='approve'?{approved_by:'admin'}:{};setOut(JSON.stringify(await api.post(url,body),null,2));load()}return <div className="grid"><div className="card"><h3>Bootstrap Plan</h3><input value={name} onChange={e=>setName(e.target.value)} placeholder="计划名称"/><textarea value={src} onChange={e=>setSrc(e.target.value)} placeholder="数据源，每行一个"/><button className="primary" onClick={create}>创建计划</button></div><div className="card"><h3>Plans</h3><Table rows={plans} cols={['id','name','status','total_files','estimated_cost_usd']} action={p=><><button className="ghost" onClick={()=>act(p.id,'estimate')}>估算</button> <button className="ghost" onClick={()=>act(p.id,'approve')}>批准</button> <button className="primary" onClick={()=>act(p.id,'execute')}>执行</button></>}/><div className="console">{out}</div></div></div>}
function Access(){const[out,setOut]=useState(''),[users,setUsers]=useState([]),[clients,setClients]=useState([]);useEffect(()=>{load()},[]);async function load(){setUsers((await api.json('/users')).users||[]);setClients((await api.json('/access/clients')).clients||[])}async function cu(){setOut(JSON.stringify(await api.post('/users',{name:'Neon User',email:'user@local'}),null,2));load()}async function cc(){setOut(JSON.stringify(await api.post('/access/clients',{name:'client',callback_url:''}),null,2));load()}return <div className="grid"><div className="card"><h3>Identity / Clients</h3><button className="primary" onClick={cu}>创建用户</button><button className="ghost" onClick={cc} style={{marginLeft:8}}>注册客户端</button><div className="console">{out}</div></div><div className="card"><h3>Users</h3><Table rows={users} cols={['id','name','email','api_key']}/><h3>Clients</h3><Table rows={clients} cols={['client_id','name','hmac_secret']}/></div></div>}
function Prompts(){const[p,setP]=useState([]),[out,setOut]=useState('');useEffect(()=>{load()},[]);async function load(){setP((await api.json('/prompts')).prompts||[])}async function reg(){setOut(JSON.stringify(await api.post('/prompts/register',{name:'chat_system',version:'v1',traffic_percent:100,active:true}),null,2));load()}return <div className="card"><h3>Prompt Router</h3><button className="primary" onClick={reg}>注册 chat_system:v1</button><div className="console">{JSON.stringify(p,null,2)}\n\n{out}</div></div>}
function Settings(){const[models,setModels]=useState({});useEffect(()=>{api.json('/metrics/models').then(setModels)},[]);return <div className="card"><h3>Runtime Settings</h3><div className="console">{JSON.stringify(models,null,2)}\n\n.env controls: PKB_LLM_MODEL_LIGHT / DEFAULT / HEAVY / PKB_LLM_CACHE_ENABLED / PKB_ALERT_LARK_WEBHOOK</div></div>}
function Table({rows=[],cols=[],action}){return <table><thead><tr>{cols.map(c=><th key={c}>{c}</th>)}{action&&<th>Action</th>}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{cols.map(c=><td key={c}>{String(r[c]??'').slice(0,80)}</td>)}{action&&<td>{action(r)}</td>}</tr>)}</tbody></table>}
ReactDOM.createRoot(document.getElementById('root')).render(<Shell/>);
</script></body></html>
"""
