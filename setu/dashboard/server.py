"""Local-only dashboard API and static application server."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
import re
import secrets
from threading import Lock
import time
from typing import Any
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from setu.agents.orchestrator import Orchestrator
from setu.config import Config, load_config
from setu.dashboard.ingestion import IngestionCoordinator, OrchestratorFactory, Submitter
from setu.db import get_session
from setu.extraction import ExtractedPolicy, policy_identity_issues
from setu.insurance import calculate_maturity_outlook
from setu.models import (
    Account,
    Balance,
    Holding,
    IngestionRun,
    InsurancePolicy,
    Obligation,
    PolicyType,
    PolicyValue,
    RiskProfile,
    Statement,
    Transaction,
)
from setu.tools.calc import Position, compute_net_worth
from setu.tools.insights import (
    build_portfolio_insights,
    compute_investment_performance,
    compute_portfolio_health,
)

SessionFactory = Callable[[], Session]
QuestionRunner = Callable[[str, Session, Config], dict[str, Any]]
STATIC_DIR = Path(__file__).with_name("static")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_RUN_STATUSES = {"queued", "processing", "review", "completed", "rejected", "failed"}
SESSION_COOKIE = "setu_dashboard_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
LOGIN_ATTEMPT_WINDOW_SECONDS = 60
MAX_LOGIN_ATTEMPTS = 5
PUBLIC_PATHS = {
    "/login",
    "/login.css",
    "/login.js",
    "/api/auth/login",
    "/api/health",
}
ANSWER_MARKDOWN = MarkdownIt(
    "commonmark",
    {"html": False, "linkify": False, "typographer": False},
)
# Setu answers do not need external links or images. Disabling them keeps the renderer small and
# prevents model-authored content from creating navigation or remote-content surfaces.
ANSWER_MARKDOWN.disable(["link", "image", "autolink"])


class ReviewDecision(BaseModel):
    decision: str


class SourceActivation(BaseModel):
    active: bool


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


AGENTS = [
    {
        "id": "financial",
        "name": "Financial Agent",
        "description": "Portfolio, policies, allocation, and net worth",
        "status": "active",
        "capabilities": ["ingestion", "reconciliation", "valuation", "reporting"],
    },
    {
        "id": "forms",
        "name": "Form Assistant",
        "description": "Prepare forms from approved personal data",
        "status": "planned",
        "capabilities": ["field mapping", "review", "PDF output"],
    },
    {
        "id": "research",
        "name": "Research Agent",
        "description": "Evidence-backed stock and fund research",
        "status": "planned",
        "capabilities": ["research", "citations", "watchlists"],
    },
]


def create_app(
    config: Config | None = None,
    session_factory: SessionFactory | None = None,
    orchestrator_factory: OrchestratorFactory | None = None,
    ingestion_submitter: Submitter | None = None,
    question_runner: QuestionRunner | None = None,
) -> FastAPI:
    """Create the local dashboard app with injectable dependencies for tests."""
    config = config or load_config()
    if config.dashboard_password is None:
        raise RuntimeError(
            "Setu dashboard authentication is not configured. "
            "Add SETU_DASHBOARD_PASSWORD to the project-local .env file."
        )
    dashboard_password = config.dashboard_password.get_secret_value()
    if len(dashboard_password) < 12:
        raise RuntimeError("SETU_DASHBOARD_PASSWORD must contain at least 12 characters.")

    sessions = session_factory or (lambda: get_session(config))
    answer_question = question_runner or _answer_portfolio_question
    request_token = secrets.token_urlsafe(32)
    login_sessions: dict[str, float] = {}
    failed_logins: dict[str, list[float]] = {}
    auth_lock = Lock()
    ingestion = IngestionCoordinator(
        config,
        sessions,
        orchestrator_factory=orchestrator_factory,
        submitter=ingestion_submitter,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        ingestion.close()

    app = FastAPI(
        title="Setu Local Workspace",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def session_digest(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    def authenticated(token: str | None) -> bool:
        if not token:
            return False
        digest = session_digest(token)
        now = time.monotonic()
        with auth_lock:
            expires_at = login_sessions.get(digest)
            if expires_at is None:
                return False
            if expires_at <= now:
                login_sessions.pop(digest, None)
                return False
        return True

    def create_login_session() -> str:
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        with auth_lock:
            expired = [digest for digest, expiry in login_sessions.items() if expiry <= now]
            for digest in expired:
                login_sessions.pop(digest, None)
            login_sessions[session_digest(token)] = now + SESSION_TTL_SECONDS
        return token

    def remove_login_session(token: str | None) -> None:
        if not token:
            return
        with auth_lock:
            login_sessions.pop(session_digest(token), None)

    def login_is_rate_limited(client_id: str) -> bool:
        now = time.monotonic()
        with auth_lock:
            attempts = [
                attempted_at
                for attempted_at in failed_logins.get(client_id, [])
                if now - attempted_at < LOGIN_ATTEMPT_WINDOW_SECONDS
            ]
            failed_logins[client_id] = attempts
            return len(attempts) >= MAX_LOGIN_ATTEMPTS

    def record_failed_login(client_id: str) -> None:
        with auth_lock:
            failed_logins.setdefault(client_id, []).append(time.monotonic())

    def clear_failed_logins(client_id: str) -> None:
        with auth_lock:
            failed_logins.pop(client_id, None)

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        path = request.url.path
        is_public = path in PUBLIC_PATHS
        if not is_public and not authenticated(request.cookies.get(SESSION_COOKIE)):
            if path.startswith("/api/"):
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Dashboard authentication required."},
                )
            else:
                response = RedirectResponse(url="/login", status_code=303)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; img-src 'self' data:"
        )
        return response

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        if authenticated(request.cookies.get(SESSION_COOKIE)):
            return RedirectResponse(url="/", status_code=303)
        return FileResponse(STATIC_DIR / "login.html")

    @app.get("/login.css", include_in_schema=False)
    def login_styles():
        return FileResponse(STATIC_DIR / "login.css", media_type="text/css")

    @app.get("/login.js", include_in_schema=False)
    def login_script():
        return FileResponse(STATIC_DIR / "login.js", media_type="text/javascript")

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest, request: Request):
        client_id = request.client.host if request.client else "local"
        if login_is_rate_limited(client_id):
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(LOGIN_ATTEMPT_WINDOW_SECONDS)},
                content={"detail": "Too many login attempts. Try again in one minute."},
            )
        if not secrets.compare_digest(payload.password, dashboard_password):
            record_failed_login(client_id)
            await asyncio.sleep(0.05)
            raise HTTPException(status_code=401, detail="Incorrect password.")

        clear_failed_logins(client_id)
        token = create_login_session()
        response = JSONResponse(content={"authenticated": True})
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        with sessions() as session:
            nw = compute_net_worth(session, config)
            contracts = _active_source_rows(session, InsurancePolicy)
            policy_values = _active_source_rows(session, PolicyValue)
            obligations = _active_source_rows(session, Obligation)
            account_ids = {position.account_id for position in nw.positions}
            account_ids.update(policy.account_id for policy in contracts)
            account_ids.update(value.account_id for value in policy_values)
            account_ids.update(
                obligation.account_id
                for obligation in obligations
                if obligation.account_id is not None
            )
            accounts = (
                session.scalars(
                    select(Account)
                    .where(Account.id.in_(account_ids))
                    .order_by(Account.name, Account.id)
                ).all()
                if account_ids
                else []
            )
            contract_keys = {(policy.statement_id, policy.policy_name) for policy in contracts}
            policy_count = len(contracts) + sum(
                (value.statement_id, value.policy_name) not in contract_keys
                for value in policy_values
            )
            holding_count = sum(position.kind == "holding" for position in nw.positions)
            balance_count = sum(position.kind == "balance" for position in nw.positions)
            profile = session.scalar(select(RiskProfile).order_by(RiskProfile.id.desc()))
            performance = compute_investment_performance(nw)
            insights = build_portfolio_insights(
                session,
                config,
                net_worth=nw,
                profile=profile,
            )
            health = compute_portfolio_health(
                session,
                config,
                net_worth=nw,
                profile=profile,
            )

            return {
                "base_currency": nw.base_currency,
                "net_worth": str(nw.total),
                "allocation": {
                    "asset_class": _string_map(nw.by_asset_class),
                    "geography": _string_map(nw.by_geography),
                    "currency": _string_map(nw.by_currency),
                },
                "positions": [
                    _position_payload(position)
                    for position in sorted(nw.positions, key=lambda item: item.base_value, reverse=True)
                ],
                "accounts": [
                    {
                        "id": account.id,
                        "name": account.name,
                        "institution": account.institution.name,
                        "geography": account.institution.geography.value,
                        "type": account.account_type.value,
                        "currency": account.currency,
                        "reference": account.account_ref,
                    }
                    for account in accounts
                ],
                "counts": {
                    "accounts": len(accounts),
                    "holdings": holding_count,
                    "balances": balance_count,
                    "policies": policy_count,
                    "obligations": len(obligations),
                },
                "risk_profile": _risk_profile(profile),
                "performance": performance.as_dict(),
                "insights": [insight.as_dict() for insight in insights],
                "health": health.as_dict(),
            }

    @app.get("/api/agents")
    def agents() -> dict[str, Any]:
        return {"agents": AGENTS}

    @app.get("/api/policies")
    def policies() -> dict[str, Any]:
        with sessions() as session:
            contracts = _active_source_rows(
                session,
                InsurancePolicy,
                InsurancePolicy.created_at.desc(),
                InsurancePolicy.id.desc(),
            )
            values = _active_source_rows(
                session,
                PolicyValue,
                PolicyValue.as_of_date.desc(),
                PolicyValue.id.desc(),
            )
            runs = session.scalars(
                select(IngestionRun)
                .where(IngestionRun.document_kind == "POLICY")
                .order_by(IngestionRun.created_at.desc())
            ).all()
            contract_keys = {(policy.statement_id, policy.policy_name) for policy in contracts}
            details = [_contract_detail(session, policy, runs) for policy in contracts]
            details.extend(
                _policy_detail(session, policy, runs)
                for policy in values
                if (policy.statement_id, policy.policy_name) not in contract_keys
            )
            return {"policies": details}

    @app.get("/api/session")
    def browser_session() -> dict[str, str]:
        """Return an ephemeral same-origin token required for local state-changing requests."""
        return {"request_token": request_token}

    def require_request_token(
        supplied: str | None = Header(default=None, alias="X-Setu-Request-Token"),
    ) -> None:
        if supplied is None or not secrets.compare_digest(supplied, request_token):
            raise HTTPException(status_code=403, detail="Invalid local request token.")

    @app.post("/api/auth/logout")
    def logout(
        request: Request,
        x_setu_request_token: str | None = Header(
            default=None,
            alias="X-Setu-Request-Token",
            include_in_schema=False,
        ),
    ):
        require_request_token(x_setu_request_token)
        remove_login_session(request.cookies.get(SESSION_COOKIE))
        response = JSONResponse(content={"authenticated": False})
        response.delete_cookie(key=SESSION_COOKIE, path="/", samesite="strict")
        return response

    @app.post("/api/ask")
    def ask_setu(
        payload: AskRequest,
        x_setu_request_token: str | None = Header(
            default=None,
            alias="X-Setu-Request-Token",
            include_in_schema=False,
        ),
    ) -> dict[str, Any]:
        require_request_token(x_setu_request_token)
        question = _mask_long_identifiers(payload.question.strip())
        try:
            with sessions() as session:
                result = answer_question(question, session, config)
                return _format_ask_response(result, config)
        except Exception as exc:
            from setu.llm.claude import ClaudeError

            if isinstance(exc, ClaudeError):
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            raise

    @app.get("/api/sources")
    def data_sources() -> dict[str, Any]:
        with sessions() as session:
            return _source_inventory(session, config)

    @app.patch("/api/sources/{source_id}")
    def update_data_source(
        source_id: int,
        payload: SourceActivation,
        x_setu_request_token: str | None = Header(
            default=None,
            alias="X-Setu-Request-Token",
            include_in_schema=False,
        ),
    ) -> dict[str, Any]:
        require_request_token(x_setu_request_token)
        with sessions() as session:
            source = session.get(Statement, source_id)
            if source is None:
                raise HTTPException(status_code=404, detail="Unknown data source.")
            source.is_active = payload.active
            session.commit()
            inventory = _source_inventory(session, config)
            updated = next(item for item in inventory["sources"] if item["id"] == source_id)
            return {"source": updated}

    @app.post("/api/ingestions", status_code=202)
    async def upload_ingestion(
        file: UploadFile = File(...),
        x_setu_request_token: str | None = Header(
            default=None,
            alias="X-Setu-Request-Token",
            include_in_schema=False,
        ),
    ) -> dict[str, Any]:
        require_request_token(x_setu_request_token)
        source_name = _safe_pdf_name(file.filename)
        path = await _store_upload(file, config.paths.inbox_dir)
        return ingestion.start(path, source_name)

    @app.get("/api/ingestions")
    def ingestion_runs(status: str | None = None) -> dict[str, Any]:
        if status is not None and status not in ALLOWED_RUN_STATUSES:
            raise HTTPException(status_code=422, detail="Unknown ingestion status.")
        return {"runs": ingestion.list(status=status)}

    @app.post("/api/ingestions/{run_id}/decision", status_code=202)
    def decide_ingestion(
        run_id: str,
        payload: ReviewDecision,
        x_setu_request_token: str | None = Header(
            default=None,
            alias="X-Setu-Request-Token",
            include_in_schema=False,
        ),
    ) -> dict[str, Any]:
        require_request_token(x_setu_request_token)
        decision = payload.decision.strip().lower()
        if decision not in {"accept", "reject"}:
            raise HTTPException(status_code=422, detail="Decision must be accept or reject.")
        try:
            return ingestion.resume(run_id, decision)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/activity")
    def activity() -> dict[str, Any]:
        with sessions() as session:
            statements = session.scalars(
                select(Statement).order_by(Statement.ingested_at.desc(), Statement.id.desc()).limit(30)
            ).all()
            return {"events": [_statement_event(statement) for statement in statements]}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "scope": "local"}

    @app.websocket("/ws/activity")
    async def activity_socket(websocket: WebSocket):
        session_token = websocket.cookies.get(SESSION_COOKIE)
        if not authenticated(session_token):
            raise WebSocketException(code=4401, reason="Dashboard authentication required.")
        await websocket.accept()
        last_id: int | None = None
        try:
            while True:
                if not authenticated(session_token):
                    await websocket.close(code=4401)
                    return
                with sessions() as session:
                    latest_id = session.scalar(select(func.max(Statement.id)))
                if latest_id != last_id:
                    await websocket.send_json({"type": "ledger_changed", "statement_id": latest_id})
                    last_id = latest_id
                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=2)
                    if message.get("type") == "websocket.disconnect":
                        return
                except TimeoutError:
                    pass
        except WebSocketDisconnect:
            return

    @app.exception_handler(Exception)
    async def safe_error(_request, _exc):
        return JSONResponse(status_code=500, content={"detail": "Local dashboard request failed."})

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
    return app


def _string_map(values: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _mask_long_identifiers(text: str) -> str:
    """Mask likely account/policy identifiers before a typed question reaches Claude."""
    return re.sub(r"(?<![A-Za-z0-9])([A-Za-z]*\d[A-Za-z0-9/-]{7,})(?![A-Za-z0-9])", _masked_match, text)


def _masked_match(match: re.Match) -> str:
    value = match.group(1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    alphanumeric = "".join(character for character in value if character.isalnum())
    return f"****{alphanumeric[-4:]}"


def _format_ask_response(result: dict[str, Any], config: Config) -> dict[str, Any]:
    """Add safe rendered Markdown and explicit response limits to an Ask Setu result."""
    answer = str(result.get("answer") or "").strip()
    payload = {
        key: value
        for key, value in result.items()
        if key not in {"answer", "answer_html", "answer_format", "limits"}
    }
    payload.update({
        "answer": answer,
        "answer_html": ANSWER_MARKDOWN.render(answer),
        "answer_format": "commonmark",
        "truncated": bool(result.get("truncated", False)),
        "limits": {
            "max_output_tokens": config.claude.max_output_tokens,
            "max_tool_rounds": config.claude.max_tool_rounds,
            "target_answer_words": config.claude.target_answer_words,
        },
    })
    return payload


def _answer_portfolio_question(
    question: str,
    session: Session,
    config: Config,
) -> dict[str, Any]:
    """Run the personal Claude tool loop over sanitized deterministic tools only."""
    from setu.llm.claude import ClaudeClient
    from setu.tools.registry import TOOL_SCHEMAS, build_executor

    system = (
        "You are Setu, a read-only cross-border wealth assistant. Use a provided tool for every "
        "portfolio number; do not calculate or estimate figures yourself. Clearly distinguish "
        "current value, cost basis, unrealized return, insurance coverage, and unknown values. "
        "Do not recommend or execute trades. State important data-coverage limitations. "
        "Treat Setu's health score as an explainable diagnostic, never as a suitability rating. "
        f"The base currency is {config.base_currency}. "
        "Return CommonMark Markdown only, never HTML. For a non-trivial answer use these short "
        "sections: '### Answer', '### Key evidence', and when relevant '### What to watch' or "
        "'### Data limits'. Put the direct answer first, use bullets for evidence, and do not use "
        f"tables. Keep the response under {config.claude.target_answer_words} words."
    )
    client = ClaudeClient(config)
    result = client.run_tool_loop(
        question,
        TOOL_SCHEMAS,
        build_executor(session, config),
        system=system,
    )
    tools_used = list(dict.fromkeys(
        step.tool_name
        for step in result.trace
        if step.kind == "tool_call" and step.tool_name is not None
    ))
    return {
        "answer": result.answer,
        "tools_used": tools_used,
        "rounds": result.rounds,
        "stop_reason": result.stop_reason,
        "truncated": result.truncated,
        "privacy": "Only sanitized ledger calculations were sent to Claude.",
    }


def _position_payload(position: Position) -> dict[str, Any]:
    cost = position.base_cost_basis
    gain = position.base_value - cost if cost is not None else None
    roi = gain / cost if gain is not None and cost > 0 else None
    return {
        "label": position.label,
        "kind": "insurance" if position.kind == "insurance" else position.kind,
        "asset_class": position.asset_class.value,
        "geography": position.geography.value,
        "currency": position.currency,
        "native_value": str(position.native_value),
        "base_value": str(position.base_value),
        "base_cost_basis": None if cost is None else str(cost),
        "unrealized_gain": None if gain is None else str(gain),
        "roi_fraction": None if roi is None else str(roi),
        "source_id": position.statement_id,
    }


def _active_source_rows(session: Session, model, *order_by):
    """Read rows allowed by source control; unlinked legacy/synthetic rows stay active."""
    source_id = model.statement_id
    query = (
        select(model)
        .outerjoin(Statement, source_id == Statement.id)
        .where(or_(source_id.is_(None), Statement.is_active.is_(True)))
    )
    if order_by:
        query = query.order_by(*order_by)
    return session.scalars(query).all()


def _count_by_source(session: Session, model) -> dict[int, int]:
    rows = session.execute(
        select(model.statement_id, func.count(model.id))
        .where(model.statement_id.is_not(None))
        .group_by(model.statement_id)
    ).all()
    return {source_id: count for source_id, count in rows}


def _policy_counts_by_source(session: Session) -> dict[int, int]:
    """Count policy identities once when both a contract and value snapshot exist."""
    keys: dict[int, set[tuple[int, str]]] = {}
    for model in (InsurancePolicy, PolicyValue):
        rows = session.execute(
            select(model.statement_id, model.account_id, model.policy_name)
            .where(model.statement_id.is_not(None))
        ).all()
        for source_id, account_id, policy_name in rows:
            keys.setdefault(source_id, set()).add((account_id, policy_name))
    return {source_id: len(policy_keys) for source_id, policy_keys in keys.items()}


def _source_inventory(session: Session, config: Config) -> dict[str, Any]:
    """Return every imported source and whether it currently influences a portfolio view."""
    statements = session.scalars(
        select(Statement).order_by(Statement.ingested_at.desc(), Statement.id.desc())
    ).all()
    net_worth = compute_net_worth(session, config)
    active_contracts = _active_source_rows(session, InsurancePolicy)
    active_values = _active_source_rows(session, PolicyValue)
    active_obligations = _active_source_rows(session, Obligation)

    used_source_ids = {
        position.statement_id
        for position in net_worth.positions
        if position.statement_id is not None
    }
    used_source_ids.update(
        policy.statement_id
        for policy in (*active_contracts, *active_values)
        if policy.statement_id is not None
    )
    used_source_ids.update(
        obligation.statement_id
        for obligation in active_obligations
        if obligation.statement_id is not None
    )

    holding_counts = _count_by_source(session, Holding)
    balance_counts = _count_by_source(session, Balance)
    policy_counts = _policy_counts_by_source(session)
    obligation_counts = _count_by_source(session, Obligation)
    transaction_counts = _count_by_source(session, Transaction)

    sources = []
    for statement in statements:
        counts = {
            "holdings": holding_counts.get(statement.id, 0),
            "balances": balance_counts.get(statement.id, 0),
            "policies": policy_counts.get(statement.id, 0),
            "obligations": obligation_counts.get(statement.id, 0),
            "transactions": transaction_counts.get(statement.id, 0),
        }
        active = bool(statement.is_active)
        used = active and statement.id in used_source_ids
        if not active:
            status = "inactive"
        elif used:
            status = "included"
        else:
            status = "available"
        if counts["policies"] and counts["holdings"]:
            document_kind = "FINANCIAL"
        elif counts["policies"]:
            document_kind = "POLICY"
        elif counts["balances"] and not counts["holdings"]:
            document_kind = "BANK"
        elif counts["holdings"]:
            document_kind = "HOLDINGS"
        else:
            document_kind = "DOCUMENT"
        sources.append({
            "id": statement.id,
            "file_name": statement.file_name or "Imported document",
            "institution": statement.institution,
            "document_kind": document_kind,
            "period_end": statement.period_end.isoformat(),
            "ingested_at": (
                statement.ingested_at.isoformat() if statement.ingested_at else None
            ),
            "active": active,
            "used_in_portfolio": used,
            "status": status,
            "record_count": sum(counts.values()),
            "records": counts,
        })

    unlinked_policy_keys = {
        (policy.account_id, policy.policy_name)
        for model in (InsurancePolicy, PolicyValue)
        for policy in session.scalars(
            select(model).where(model.statement_id.is_(None))
        ).all()
    }
    unlinked = {
        "holdings": session.scalar(
            select(func.count(Holding.id)).where(Holding.statement_id.is_(None))
        ) or 0,
        "balances": session.scalar(
            select(func.count(Balance.id)).where(Balance.statement_id.is_(None))
        ) or 0,
        "policies": len(unlinked_policy_keys),
        "obligations": session.scalar(
            select(func.count(Obligation.id)).where(Obligation.statement_id.is_(None))
        ) or 0,
        "transactions": session.scalar(
            select(func.count(Transaction.id)).where(Transaction.statement_id.is_(None))
        ) or 0,
    }
    return {
        "sources": sources,
        "active_count": sum(source["active"] for source in sources),
        "used_count": sum(source["used_in_portfolio"] for source in sources),
        "unlinked_records": {**unlinked, "total": sum(unlinked.values())},
    }


def _policy_obligation(
    session: Session,
    *,
    account_id: int,
    policy_name: str,
    statement_id: int | None,
) -> Obligation | None:
    """Find the premium created by the same source, with an unlinked legacy fallback."""
    description = f"Premium: {policy_name}"
    if statement_id is not None:
        exact = session.scalar(
            select(Obligation)
            .where(
                Obligation.account_id == account_id,
                Obligation.statement_id == statement_id,
                Obligation.description == description,
            )
            .order_by(Obligation.id.desc())
        )
        if exact is not None:
            return exact
    return session.scalar(
        select(Obligation)
        .where(
            Obligation.account_id == account_id,
            Obligation.statement_id.is_(None),
            Obligation.description == description,
        )
        .order_by(Obligation.id.desc())
    )


def _risk_profile(profile: RiskProfile | None) -> dict[str, str] | None:
    if profile is None:
        return None
    return {
        "label": profile.label,
        "target_equity": str(profile.target_equity),
        "target_debt": str(profile.target_debt),
        "target_cash": str(profile.target_cash),
        "max_usd_fraction": (
            None if profile.max_usd_fraction is None else str(profile.max_usd_fraction)
        ),
    }


def _statement_event(statement: Statement) -> dict[str, Any]:
    active = bool(statement.is_active)
    return {
        "id": statement.id,
        "kind": "document_ingested",
        "title": f"Imported {statement.institution} document",
        "source": statement.file_name,
        "period_end": statement.period_end.isoformat(),
        "occurred_at": statement.ingested_at.isoformat() if statement.ingested_at else None,
        "status": "active" if active else "inactive",
    }


def _policy_detail(
    session: Session,
    policy: PolicyValue,
    runs: list[IngestionRun],
) -> dict[str, Any]:
    statement = session.get(Statement, policy.statement_id) if policy.statement_id else None
    obligation = _policy_obligation(
        session,
        account_id=policy.account_id,
        policy_name=policy.policy_name,
        statement_id=policy.statement_id,
    )
    identity = ExtractedPolicy(
        policy_name=policy.policy_name,
        policy_type=policy.policy_type,
        sum_assured=None if policy.sum_assured is None else str(policy.sum_assured),
        currency=policy.currency,
    )
    issues = policy_identity_issues(identity)
    insurer = policy.account.institution.name
    insurer_normalized = insurer.lower()
    if "collecting branch" in insurer_normalized or "servicing branch" in insurer_normalized:
        issues.append("The insurer name was not reliably extracted from the document header.")
    if obligation and obligation.due_date and statement and statement.ingested_at:
        if obligation.due_date < statement.ingested_at.date():
            issues.append("The recorded premium due date predates this import and should be verified.")

    return {
        "id": policy.id,
        "policy_name": (
            f"{policy.policy_type.value.title()} policy — name not identified"
            if any("specific policy or product name" in issue for issue in issues)
            else policy.policy_name
        ),
        "extracted_policy_name": policy.policy_name,
        "policy_type": policy.policy_type.value,
        "insurer": (
            "Insurer not identified"
            if "collecting branch" in insurer_normalized or "servicing branch" in insurer_normalized
            else insurer
        ),
        "sum_assured": None if policy.sum_assured is None else str(policy.sum_assured),
        "asset_value": None if issues else str(policy.asset_value),
        "currency": policy.currency,
        "as_of_date": policy.as_of_date.isoformat(),
        "valuation_basis": "unverified_legacy_value" if issues else (
            "protection_only"
            if policy.policy_type.value == "TERM"
            else "stated_current_value"
        ),
        "premium_amount": None if obligation is None else str(obligation.amount),
        "premium_currency": None if obligation is None else obligation.currency,
        "premium_due_date": (
            None
            if obligation is None or obligation.due_date is None
            else obligation.due_date.isoformat()
        ),
        "premium_recurring": False if obligation is None else obligation.recurring,
        "source_name": _policy_source_name(statement, runs),
        "ingested_at": (
            statement.ingested_at.isoformat()
            if statement is not None and statement.ingested_at is not None
            else None
        ),
        "quality_status": "needs_review" if issues else "verified",
        "quality_issues": issues,
        "evidence_status": "legacy",
        "projection": _maturity_projection(
            policy_type=policy.policy_type.value,
            quality_issues=issues,
        ),
    }


def _contract_detail(
    session: Session,
    policy: InsurancePolicy,
    runs: list[IngestionRun],
) -> dict[str, Any]:
    statement = session.get(Statement, policy.statement_id) if policy.statement_id else None
    value = session.scalar(
        select(PolicyValue)
        .where(
            PolicyValue.statement_id == policy.statement_id,
            PolicyValue.policy_name == policy.policy_name,
        )
        .order_by(PolicyValue.id.desc())
    )
    obligation = _policy_obligation(
        session,
        account_id=policy.account_id,
        policy_name=policy.policy_name,
        statement_id=policy.statement_id,
    )
    identity = ExtractedPolicy(
        policy_name=policy.policy_name,
        policy_type=policy.policy_type,
        plan_number=policy.plan_number,
        sum_assured=None if policy.sum_assured is None else str(policy.sum_assured),
        currency=policy.currency,
    )
    issues = policy_identity_issues(identity, policy.document_type)
    if policy.current_value_status == "not_provided" and policy.policy_type.value != "TERM":
        field = "fund value" if policy.policy_type.value == "ULIP" else "surrender value"
        issues.append(
            f"No current {field} was provided; this policy is excluded from current net worth."
        )
    projection = _maturity_projection(
        policy_type=policy.policy_type.value,
        quality_issues=issues,
        policy_name=policy.policy_name,
        stated_maturity=policy.stated_maturity_value,
        maturity_4pct=policy.maturity_benefit_4pct,
        maturity_8pct=policy.maturity_benefit_8pct,
        plan_number=policy.plan_number,
        maturity_date=policy.maturity_date,
        sum_assured=policy.sum_assured,
        vested_bonus=policy.vested_bonus,
        guaranteed_additions=policy.guaranteed_additions,
        policy_term_years=policy.policy_term_years,
        premium_payment_term_years=policy.premium_payment_term_years,
    )
    generic_name = any("specific policy or product name" in issue for issue in issues)
    return {
        "id": f"contract-{policy.id}",
        "policy_name": (
            f"{policy.policy_type.value.title()} policy — name not identified"
            if generic_name
            else policy.policy_name
        ),
        "extracted_policy_name": policy.policy_name,
        "policy_type": policy.policy_type.value,
        "insurer": policy.account.institution.name,
        "plan_number": policy.plan_number,
        "status": policy.status,
        "sum_assured": None if policy.sum_assured is None else str(policy.sum_assured),
        "asset_value": (
            "0.0000"
            if policy.policy_type == PolicyType.TERM
            else None if value is None else str(value.asset_value)
        ),
        "currency": policy.currency,
        "as_of_date": (
            value.as_of_date.isoformat()
            if value is not None
            else statement.period_end.isoformat()
            if statement is not None
            else None
        ),
        "valuation_basis": (
            "protection_only"
            if policy.policy_type.value == "TERM"
            else "stated_current_value"
            if value is not None
            else "current_value_not_provided"
        ),
        "premium_amount": (
            str(policy.premium_amount)
            if policy.premium_amount is not None
            else None if obligation is None else str(obligation.amount)
        ),
        "premium_currency": policy.currency,
        "premium_due_date": (
            policy.premium_due_date.isoformat()
            if policy.premium_due_date is not None
            else None
            if obligation is None or obligation.due_date is None
            else obligation.due_date.isoformat()
        ),
        "premium_recurring": obligation is not None and obligation.recurring,
        "premium_mode": policy.premium_mode,
        "commencement_date": (
            None if policy.commencement_date is None else policy.commencement_date.isoformat()
        ),
        "maturity_date": None if policy.maturity_date is None else policy.maturity_date.isoformat(),
        "policy_term_years": policy.policy_term_years,
        "premium_payment_term_years": policy.premium_payment_term_years,
        "vested_bonus": None if policy.vested_bonus is None else str(policy.vested_bonus),
        "guaranteed_additions": (
            None if policy.guaranteed_additions is None else str(policy.guaranteed_additions)
        ),
        "source_name": _policy_source_name(statement, runs),
        "ingested_at": (
            statement.ingested_at.isoformat()
            if statement is not None and statement.ingested_at is not None
            else None
        ),
        "quality_status": "verified" if not issues else "partial",
        "quality_issues": issues,
        "evidence_status": policy.evidence_status,
        "current_value_status": policy.current_value_status,
        "document_type": policy.document_type,
        "projection": projection,
    }


def _maturity_projection(
    *,
    policy_type: str,
    quality_issues: list[str],
    policy_name: str = "",
    stated_maturity: Any = None,
    maturity_4pct: Any = None,
    maturity_8pct: Any = None,
    plan_number: str | None = None,
    maturity_date: Any = None,
    sum_assured: Any = None,
    vested_bonus: Any = None,
    guaranteed_additions: Any = None,
    policy_term_years: int | None = None,
    premium_payment_term_years: int | None = None,
) -> dict[str, Any]:
    if maturity_4pct is not None and maturity_8pct is not None:
        return {
            "status": "official_scenarios",
            "lower_amount": str(maturity_4pct),
            "upper_amount": str(maturity_8pct),
            "method": "Official benefit illustration at 4% and 8% gross investment returns",
            "guaranteed": False,
            "missing_fields": [],
        }
    if stated_maturity is not None:
        return {
            "status": "stated",
            "amount": str(stated_maturity),
            "method": "Maturity value explicitly stated in the source document",
            "guaranteed": None,
            "missing_fields": [],
        }
    calculated = calculate_maturity_outlook(
        policy_name=policy_name,
        plan_number=plan_number,
        sum_assured=sum_assured,
        vested_bonus=vested_bonus,
        guaranteed_additions=guaranteed_additions,
        policy_term_years=policy_term_years,
        premium_payment_term_years=premium_payment_term_years,
        maturity_date=maturity_date,
    )
    if calculated is not None:
        return calculated
    if policy_type == "TERM" and not quality_issues:
        return {
            "status": "not_applicable",
            "method": "No maturity value for pure protection unless the specific plan states otherwise",
            "guaranteed": None,
            "missing_fields": [],
        }
    missing = []
    if not plan_number:
        missing.append("plan number or product name")
    if maturity_date is None:
        missing.append("maturity date")
    missing.append("official benefit illustration or bonus statement")
    return {
        "status": "insufficient_evidence",
        "method": "No return is calculated until plan-specific evidence is available",
        "guaranteed": None,
        "missing_fields": missing,
    }


def _policy_source_name(
    statement: Statement | None,
    runs: list[IngestionRun],
) -> str | None:
    if statement is None:
        return "Synthetic seed"
    if not statement.file_name.startswith(".ui-upload-"):
        return statement.file_name
    if statement.ingested_at is None:
        return "Uploaded PDF"
    candidates = [
        run for run in runs
        if run.created_at is not None
        and abs((statement.ingested_at - run.created_at).total_seconds()) <= 300
    ]
    if not candidates:
        return "Uploaded PDF"
    nearest = min(
        candidates,
        key=lambda run: abs((statement.ingested_at - run.created_at).total_seconds()),
    )
    return nearest.source_name


def _safe_pdf_name(filename: str | None) -> str:
    name = Path((filename or "document.pdf").replace("\\", "/")).name.replace("\x00", "")
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Setu currently accepts PDF documents only.")
    return name[:255] or "document.pdf"


async def _store_upload(file: UploadFile, inbox_dir: Path) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    path = inbox_dir / f".ui-upload-{uuid4().hex}.pdf"
    size = 0
    first_bytes = b""
    try:
        with path.open("xb") as target:
            while chunk := await file.read(1024 * 1024):
                if not first_bytes:
                    first_bytes = chunk[:8]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF exceeds the 25 MB upload limit.")
                target.write(chunk)
        if not first_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=415, detail="The selected file is not a valid PDF.")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
