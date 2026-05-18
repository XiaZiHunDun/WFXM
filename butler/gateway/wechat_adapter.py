"""WeChat adapter via Tencent iLink Bot API.

Connects Butler to personal WeChat accounts through the iLink Bot HTTP API.
Design follows hermes-agent's proven approach:
- QR code login (terminal ASCII + fallback URL)
- Long-poll `getupdates` for inbound messages
- HTTP `sendmessage` for outbound replies
- Context token management per peer
- Session persistence and auto-reconnect

Works on Linux, macOS, Windows — no desktop WeChat or Wine required.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import struct
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from butler.config.settings import settings
from butler.core.butler import Butler
from butler.gateway.base import BaseAdapter, UnifiedMessage

logger = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

# ── iLink API constants ──────────────────────────────────────────────

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
QR_TIMEOUT_MS = 35_000

MAX_CONSECUTIVE_FAILURES = 3
RETRY_DELAY_SECONDS = 2
BACKOFF_DELAY_SECONDS = 30
SESSION_EXPIRED_ERRCODE = -14
RATE_LIMIT_ERRCODE = -2

MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2
ITEM_TEXT = 1

_WECHAT_MSG_MAX_LEN = 2000
_TRIGGER_PREFIX = "@管家"
_TRIGGER_KEYWORDS = {"管家", settings.butler_name, "butler"}

MESSAGE_DEDUP_TTL = 300


# ── Low-level helpers ────────────────────────────────────────────────

def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _base_info() -> Dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _headers(token: Optional[str], body: str) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _make_ssl_connector() -> Optional[Any]:
    try:
        import ssl
        import certifi
    except ImportError:
        return None
    if not AIOHTTP_AVAILABLE:
        return None
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    return aiohttp.TCPConnector(ssl=ssl_ctx)


# ── Credential persistence ──────────────────────────────────────────

def _account_dir() -> Path:
    d = settings.butler_home / "weixin" / "accounts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _account_file(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.json"


def _sync_buf_path(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.sync.json"


def _context_tokens_path(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.context-tokens.json"


def save_account(
    *,
    account_id: str,
    token: str,
    base_url: str,
    user_id: str = "",
) -> None:
    payload = {
        "token": token,
        "base_url": base_url,
        "user_id": user_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _account_file(account_id)
    path.write_text(_json_dumps(payload), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_account(account_id: str) -> Optional[Dict[str, Any]]:
    path = _account_file(account_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_sync_buf(account_id: str) -> str:
    path = _sync_buf_path(account_id)
    if not path.exists():
        return ""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("get_updates_buf", "")
    except Exception:
        return ""


def _save_sync_buf(account_id: str, sync_buf: str) -> None:
    path = _sync_buf_path(account_id)
    path.write_text(_json_dumps({"get_updates_buf": sync_buf}), encoding="utf-8")


# ── Context token store (per-peer conversational continuity) ────────

class ContextTokenStore:
    def __init__(self):
        self._tokens: Dict[str, str] = {}

    def get(self, account_id: str, peer_id: str) -> Optional[str]:
        return self._tokens.get(f"{account_id}:{peer_id}")

    def set(self, account_id: str, peer_id: str, token: str) -> None:
        self._tokens[f"{account_id}:{peer_id}"] = token

    def save(self, account_id: str) -> None:
        path = _context_tokens_path(account_id)
        path.write_text(_json_dumps(self._tokens), encoding="utf-8")

    def restore(self, account_id: str) -> None:
        path = _context_tokens_path(account_id)
        if path.exists():
            try:
                self._tokens = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass


# ── Message deduplication ───────────────────────────────────────────

class _MessageDedup:
    def __init__(self, ttl: int = MESSAGE_DEDUP_TTL):
        self._seen: Dict[str, float] = {}
        self._ttl = ttl

    def is_duplicate(self, key: str) -> bool:
        now = time.monotonic()
        self._seen = {k: v for k, v in self._seen.items() if now - v < self._ttl}
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


# ── iLink API calls ─────────────────────────────────────────────────

async def _api_get(
    session: Any,
    *,
    base_url: str,
    endpoint: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{endpoint}"
    headers = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.get(url, headers=headers, timeout=timeout) as response:
        raw = await response.text()
        if not response.ok:
            raise RuntimeError(f"iLink GET {endpoint} HTTP {response.status}: {raw[:200]}")
        return json.loads(raw)


async def _api_post(
    session: Any,
    *,
    base_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    token: Optional[str],
    timeout_ms: int,
) -> Dict[str, Any]:
    body = _json_dumps({**payload, "base_info": _base_info()})
    url = f"{base_url.rstrip('/')}/{endpoint}"
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.post(url, data=body, headers=_headers(token, body), timeout=timeout) as response:
        raw = await response.text()
        if not response.ok:
            raise RuntimeError(f"iLink POST {endpoint} HTTP {response.status}: {raw[:200]}")
        return json.loads(raw)


async def _get_updates(
    session: Any,
    *,
    base_url: str,
    token: str,
    sync_buf: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    try:
        return await _api_post(
            session,
            base_url=base_url,
            endpoint=EP_GET_UPDATES,
            payload={"get_updates_buf": sync_buf},
            token=token,
            timeout_ms=timeout_ms,
        )
    except asyncio.TimeoutError:
        return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}


async def _send_text(
    session: Any,
    *,
    base_url: str,
    token: str,
    to: str,
    text: str,
    context_token: Optional[str],
) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("text must not be empty")
    message: Dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": to,
        "client_id": str(uuid.uuid4()),
        "message_type": MSG_TYPE_BOT,
        "message_state": MSG_STATE_FINISH,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
    }
    if context_token:
        message["context_token"] = context_token
    return await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_SEND_MESSAGE,
        payload={"msg": message},
        token=token,
        timeout_ms=API_TIMEOUT_MS,
    )


def _extract_text(item_list: List[Dict[str, Any]]) -> str:
    for item in item_list:
        if item.get("type") == ITEM_TEXT:
            return str((item.get("text_item") or {}).get("text") or "")
    return ""


def _is_stale_session(ret: Optional[int], errcode: Optional[int], errmsg: Optional[str]) -> bool:
    if ret != RATE_LIMIT_ERRCODE and errcode != RATE_LIMIT_ERRCODE:
        return False
    return (errmsg or "").lower() == "unknown error"


# ── QR Login ────────────────────────────────────────────────────────

async def qr_login(
    *,
    bot_type: str = "3",
    timeout_seconds: int = 480,
) -> Optional[Dict[str, str]]:
    """Interactive iLink QR login flow. Returns credentials or None."""
    if not AIOHTTP_AVAILABLE:
        raise RuntimeError("aiohttp is required: pip install aiohttp")

    async with aiohttp.ClientSession(trust_env=True, connector=_make_ssl_connector()) as session:
        try:
            qr_resp = await _api_get(
                session,
                base_url=ILINK_BASE_URL,
                endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
                timeout_ms=QR_TIMEOUT_MS,
            )
        except Exception as exc:
            logger.error("Failed to fetch QR code: %s", exc)
            return None

        qrcode_value = str(qr_resp.get("qrcode") or "")
        qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
        if not qrcode_value:
            logger.error("QR response missing qrcode token")
            return None

        qr_scan_data = qrcode_url if qrcode_url else qrcode_value

        print("\n请使用微信扫描以下二维码：")
        if qrcode_url:
            print(qrcode_url)
        try:
            import qrcode as _qrcode
            qr = _qrcode.QRCode()
            qr.add_data(qr_scan_data)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        except Exception as e:
            print(f"（终端二维码渲染失败: {e}，请直接打开上面的链接）")

        deadline = time.monotonic() + timeout_seconds
        current_base_url = ILINK_BASE_URL
        refresh_count = 0

        while time.monotonic() < deadline:
            try:
                status_resp = await _api_get(
                    session,
                    base_url=current_base_url,
                    endpoint=f"{EP_GET_QR_STATUS}?qrcode={qrcode_value}",
                    timeout_ms=QR_TIMEOUT_MS,
                )
            except asyncio.TimeoutError:
                await asyncio.sleep(1)
                continue
            except Exception as exc:
                logger.warning("QR poll error: %s", exc)
                await asyncio.sleep(1)
                continue

            status = str(status_resp.get("status") or "wait")

            if status == "wait":
                print(".", end="", flush=True)
            elif status == "scaned":
                print("\n已扫码，请在微信里确认...")
            elif status == "scaned_but_redirect":
                redirect_host = str(status_resp.get("redirect_host") or "")
                if redirect_host:
                    current_base_url = f"https://{redirect_host}"
            elif status == "expired":
                refresh_count += 1
                if refresh_count > 3:
                    print("\n二维码多次过期，请重新登录。")
                    return None
                print(f"\n二维码已过期，正在刷新... ({refresh_count}/3)")
                try:
                    qr_resp = await _api_get(
                        session,
                        base_url=ILINK_BASE_URL,
                        endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
                        timeout_ms=QR_TIMEOUT_MS,
                    )
                    qrcode_value = str(qr_resp.get("qrcode") or "")
                    qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
                    qr_scan_data = qrcode_url if qrcode_url else qrcode_value
                    if qrcode_url:
                        print(qrcode_url)
                    try:
                        import qrcode as _qr
                        qr = _qr.QRCode()
                        qr.add_data(qr_scan_data)
                        qr.make(fit=True)
                        qr.print_ascii(invert=True)
                    except Exception:
                        pass
                except Exception as exc:
                    logger.error("QR refresh failed: %s", exc)
                    return None
            elif status == "confirmed":
                account_id = str(status_resp.get("ilink_bot_id") or "")
                token = str(status_resp.get("bot_token") or "")
                base_url = str(status_resp.get("baseurl") or ILINK_BASE_URL)
                user_id = str(status_resp.get("ilink_user_id") or "")
                if not account_id or not token:
                    logger.error("QR confirmed but credentials incomplete")
                    return None
                save_account(
                    account_id=account_id,
                    token=token,
                    base_url=base_url,
                    user_id=user_id,
                )
                print(f"\n微信连接成功! account_id={account_id}")
                return {
                    "account_id": account_id,
                    "token": token,
                    "base_url": base_url,
                    "user_id": user_id,
                }
            await asyncio.sleep(1)

        print("\n微信登录超时。")
        return None


# ── WeChat Adapter (iLink Bot API) ──────────────────────────────────

class WeChatAdapter(BaseAdapter):
    """WeChat messaging adapter using iLink Bot API with long-polling."""

    name = "wechat"

    def __init__(
        self,
        account_id: str = "",
        token: str = "",
        base_url: str = "",
        allowed_users: list[str] | None = None,
        allowed_groups: list[str] | None = None,
    ):
        self._account_id = account_id or os.environ.get("WEIXIN_ACCOUNT_ID", "")
        self._token = token or os.environ.get("WEIXIN_TOKEN", "")
        self._base_url = base_url or os.environ.get("WEIXIN_BASE_URL", ILINK_BASE_URL)
        self.allowed_users = set(allowed_users or [])
        self.allowed_groups = set(allowed_groups or [])

        self._butlers: dict[str, Butler] = {}
        self._running = False
        self._poll_session: Any = None
        self._send_session: Any = None
        self._poll_task: asyncio.Task | None = None
        self._token_store = ContextTokenStore()
        self._dedup = _MessageDedup()

    async def start(self) -> None:
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp is required for WeChat: pip install aiohttp")
            return

        if not self._token or not self._account_id:
            print("未找到微信凭证，启动 QR 扫码登录...")
            creds = await qr_login()
            if not creds:
                logger.error("WeChat login failed")
                return
            self._account_id = creds["account_id"]
            self._token = creds["token"]
            self._base_url = creds.get("base_url", ILINK_BASE_URL)

        self._running = True
        self._poll_session = aiohttp.ClientSession(
            trust_env=True, connector=_make_ssl_connector(),
        )
        self._send_session = aiohttp.ClientSession(
            trust_env=True, connector=_make_ssl_connector(),
            timeout=aiohttp.ClientTimeout(total=None),
        )
        self._token_store.restore(self._account_id)

        self._poll_task = asyncio.create_task(self._poll_loop(), name="weixin-poll")
        logger.info("WeChat connected: account=%s base=%s", self._account_id[:8], self._base_url)
        print(f"微信网关已启动 (account={self._account_id[:8]}...)")

    async def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        self._token_store.save(self._account_id)

        for butler in self._butlers.values():
            await butler.close()
        self._butlers.clear()

        if self._poll_session:
            await self._poll_session.close()
        if self._send_session:
            await self._send_session.close()

    async def send(self, user_id: str, content: str, **kwargs: Any) -> None:
        chunks = self._chunk_message(content)
        for chunk in chunks:
            ctx_token = self._token_store.get(self._account_id, user_id)
            try:
                await _send_text(
                    self._send_session,
                    base_url=self._base_url,
                    token=self._token,
                    to=user_id,
                    text=chunk,
                    context_token=ctx_token,
                )
            except Exception as e:
                logger.error("Failed to send message to %s: %s", user_id[:8], e)
            if len(chunks) > 1:
                await asyncio.sleep(0.5)

    # ── Poll loop ────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        assert self._poll_session is not None
        sync_buf = _load_sync_buf(self._account_id)
        timeout_ms = LONG_POLL_TIMEOUT_MS
        consecutive_failures = 0

        while self._running:
            try:
                response = await _get_updates(
                    self._poll_session,
                    base_url=self._base_url,
                    token=self._token,
                    sync_buf=sync_buf,
                    timeout_ms=timeout_ms,
                )

                suggested_timeout = response.get("longpolling_timeout_ms")
                if isinstance(suggested_timeout, int) and suggested_timeout > 0:
                    timeout_ms = suggested_timeout

                ret = response.get("ret", 0)
                errcode = response.get("errcode", 0)
                if ret not in (0, None) or errcode not in (0, None):
                    errmsg = response.get("errmsg", "")
                    if (ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE
                            or _is_stale_session(ret, errcode, errmsg)):
                        logger.error("WeChat session expired; pausing 10 min")
                        await asyncio.sleep(600)
                        consecutive_failures = 0
                        continue
                    consecutive_failures += 1
                    logger.warning(
                        "getUpdates failed ret=%s errcode=%s (%d/%d)",
                        ret, errcode, consecutive_failures, MAX_CONSECUTIVE_FAILURES,
                    )
                    delay = BACKOFF_DELAY_SECONDS if consecutive_failures >= MAX_CONSECUTIVE_FAILURES else RETRY_DELAY_SECONDS
                    await asyncio.sleep(delay)
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        consecutive_failures = 0
                    continue

                consecutive_failures = 0
                new_sync_buf = str(response.get("get_updates_buf") or "")
                if new_sync_buf:
                    sync_buf = new_sync_buf
                    _save_sync_buf(self._account_id, sync_buf)

                for message in response.get("msgs") or []:
                    asyncio.create_task(self._process_message_safe(message))

            except asyncio.CancelledError:
                break
            except Exception as exc:
                consecutive_failures += 1
                logger.error("Poll error (%d/%d): %s", consecutive_failures, MAX_CONSECUTIVE_FAILURES, exc)
                delay = BACKOFF_DELAY_SECONDS if consecutive_failures >= MAX_CONSECUTIVE_FAILURES else RETRY_DELAY_SECONDS
                await asyncio.sleep(delay)
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0

    # ── Message processing ───────────────────────────────────────────

    async def _process_message_safe(self, message: Dict[str, Any]) -> None:
        try:
            await self._process_message(message)
        except Exception as exc:
            logger.error("Unhandled inbound error: %s", exc, exc_info=True)

    async def _process_message(self, message: Dict[str, Any]) -> None:
        sender_id = str(message.get("from_user_id") or "").strip()
        if not sender_id:
            return
        if sender_id == self._account_id:
            return

        message_id = str(message.get("message_id") or "").strip()
        if message_id and self._dedup.is_duplicate(message_id):
            return

        item_list = message.get("item_list") or []
        text = _extract_text(item_list)

        if text:
            content_key = f"content:{sender_id}:{hashlib.md5(text.encode()).hexdigest()}"
            if self._dedup.is_duplicate(content_key):
                return

        if not text:
            return

        context_token = str(message.get("context_token") or "").strip()
        if context_token:
            self._token_store.set(self._account_id, sender_id, context_token)

        unified = UnifiedMessage(
            source="wechat",
            user_id=sender_id,
            content=text,
            metadata={
                "message_id": message_id,
                "context_token": context_token,
                "is_group": False,
                "sender_id": sender_id,
            },
        )
        await self._handle_message(unified)

    async def _handle_message(self, msg: UnifiedMessage) -> None:
        if not self._should_respond(msg):
            return

        content = self._strip_trigger(msg.content)
        if not content.strip():
            return

        butler = self._get_butler(msg.user_id)
        reply_to = msg.metadata.get("sender_id", msg.user_id)

        if content.startswith("/"):
            cmd_response = self._handle_slash_command(content, butler)
            if cmd_response:
                await self.send(reply_to, cmd_response)
                return

        drilldown = self._detect_drilldown(content, butler)
        if drilldown:
            await self.send(reply_to, drilldown)
            return

        try:
            milestone_buffer: list[str] = []
            last_push_time = [time.monotonic()]
            _PUSH_INTERVAL = 30

            async def _maybe_push_progress():
                if not milestone_buffer:
                    return
                now = time.monotonic()
                if now - last_push_time[0] >= _PUSH_INTERVAL:
                    progress_msg = "进度:\n" + "\n".join(milestone_buffer[-3:])
                    await self.send(reply_to, progress_msg)
                    milestone_buffer.clear()
                    last_push_time[0] = now

            milestone_count = [0]

            def on_agent_progress(turn: int, tool_name: str, brief: str):
                from butler.executors.agent_runner import MILESTONE_TOOLS
                if tool_name in MILESTONE_TOOLS:
                    milestone_count[0] += 1
                    milestone_buffer.append(f"[{milestone_count[0]}] {tool_name}: {brief[:40]}")
                    if len(milestone_buffer) >= 3:
                        asyncio.ensure_future(_maybe_push_progress())

            butler.set_progress_handler(on_agent_progress)
            response = await butler.chat(content)
            butler.set_progress_handler(None)
            await self.send(reply_to, response)
        except Exception as e:
            logger.error("Error processing WeChat message: %s", e)
            butler.set_progress_handler(None)
            await self.send(reply_to, f"处理出错: {e}")

    # ── Drilldown / Slash / Helpers ──────────────────────────────────

    def _detect_drilldown(self, content: str, butler: Butler) -> str | None:
        result = butler.get_last_report()
        if result is None:
            return None

        content_lower = content.strip().lower()
        from butler.core.report_formatter import format_detail

        detail_keywords = {"详细", "详细说说", "详情", "展开说说", "完整报告"}
        change_keywords = {"改了什么", "改了哪些文件", "变更", "文件变更", "改动"}
        decision_keywords = {"为什么", "为什么这么做", "决策", "理由", "原因"}
        log_keywords = {"过程", "步骤", "执行过程", "日志", "完整过程"}

        for kw in detail_keywords:
            if content_lower == kw or content_lower.startswith(kw):
                return format_detail(result.report, "")
        for kw in change_keywords:
            if kw in content_lower:
                return format_detail(result.report, "changes")
        for kw in decision_keywords:
            if kw in content_lower:
                return format_detail(result.report, "decisions")
        for kw in log_keywords:
            if kw in content_lower:
                if result.milestones:
                    return "执行步骤:\n" + "\n".join(result.milestones)
                return "没有执行步骤记录。"
        return None

    def _handle_slash_command(self, content: str, butler: Butler) -> str | None:
        parts = content.split()
        cmd = parts[0].lower()

        if cmd == "/projects":
            from butler.core.project_manager import project_manager
            projects = project_manager.list_projects()
            if not projects:
                return "暂无项目"
            lines = []
            for p in projects:
                marker = " ★" if p.name == project_manager.current_project else ""
                lines.append(f"[{p.status}] {p.name} ({p.type}){marker}")
            return "\n".join(lines)

        if cmd == "/switch" and len(parts) >= 2:
            from butler.core.project_manager import project_manager
            name = parts[1]
            if project_manager.switch_project(name):
                return f"已切换到项目: {project_manager.current_project}"
            return f"未找到项目: {name}"

        if cmd == "/new":
            butler.new_session()
            return "已开始新会话"

        if cmd == "/model":
            return self._handle_model_cmd(parts, butler)

        if cmd == "/detail":
            section = parts[1] if len(parts) > 1 else ""
            return self._handle_detail_cmd(butler, section)

        if cmd == "/status":
            from butler.core.project_manager import project_manager
            current = project_manager.current_project or "未选择"
            butler_mc = settings.get_model_config("butler")
            return f"项目: {current}\n管家模型: {butler_mc.provider}:{butler_mc.model}"

        return None

    def _handle_detail_cmd(self, butler: Butler, section: str = "") -> str:
        from butler.core.report_formatter import format_detail
        result = butler.get_last_report()
        if result is None:
            return "没有最近的 Agent 执行记录。"

        if section == "log":
            if result.milestones:
                return "执行步骤:\n" + "\n".join(result.milestones)
            return "没有执行步骤记录。"

        return format_detail(result.report, section)

    def _handle_model_cmd(self, parts: list[str], butler: Butler) -> str:
        from butler.config.settings import ModelConfig
        from butler.core.project_manager import project_manager

        if len(parts) == 1:
            butler_mc = settings.get_model_config("butler")
            lines = [f"管家: {butler_mc.provider}:{butler_mc.model}"]
            proj = project_manager.get_current()
            if proj:
                for role in ("dev_agent", "content_agent", "review_agent"):
                    mc = proj.resolve_model(role)
                    lines.append(f"{role}: {mc.provider}:{mc.model}")
            return "\n".join(lines)

        if len(parts) < 3:
            return "用法: /model <层> <provider:model>\n层: butler, project, dev, content, review"

        layer, model_spec = parts[1], parts[2]
        provider, model = (model_spec.split(":", 1) + [""])[:2] if ":" in model_spec else ("", model_spec)
        config = ModelConfig(provider=provider, model=model)

        if layer == "butler":
            settings.models.butler = config
            settings.save_butler_config()
            return f"管家模型已设为: {model_spec}"

        if layer in ("project", "dev", "content", "review"):
            proj = project_manager.get_current()
            if not proj:
                return "请先切换到一个项目"
            role_map = {"project": "dev_agent", "dev": "dev_agent", "content": "content_agent", "review": "review_agent"}
            role = role_map.get(layer, "dev_agent")
            proj.set_model(role, config)
            return f"项目【{proj.name}】{role} 模型已设为: {model_spec}"

        return f"未知层: {layer}"

    # ── Filtering & Chunking ─────────────────────────────────────────

    def _get_butler(self, user_id: str) -> Butler:
        if user_id not in self._butlers:
            self._butlers[user_id] = Butler(channel="wechat", user_id=user_id)
        return self._butlers[user_id]

    def _should_respond(self, msg: UnifiedMessage) -> bool:
        if self.allowed_users and msg.user_id not in self.allowed_users:
            return False

        is_group = msg.metadata.get("is_group", False)
        if is_group:
            group_id = msg.metadata.get("group_id", "")
            if self.allowed_groups and group_id not in self.allowed_groups:
                return False
            return self._is_triggered(msg.content)

        return True

    def _is_triggered(self, content: str) -> bool:
        content_lower = content.lower().strip()
        for keyword in _TRIGGER_KEYWORDS:
            if content_lower.startswith(keyword):
                return True
        return content_lower.startswith(_TRIGGER_PREFIX)

    def _strip_trigger(self, content: str) -> str:
        content = content.strip()
        for keyword in sorted(_TRIGGER_KEYWORDS, key=len, reverse=True):
            if content.lower().startswith(keyword):
                content = content[len(keyword):].strip()
                break
        if content.startswith(_TRIGGER_PREFIX):
            content = content[len(_TRIGGER_PREFIX):].strip()
        return content

    def _chunk_message(self, content: str) -> list[str]:
        if len(content) <= _WECHAT_MSG_MAX_LEN:
            return [content]

        chunks: list[str] = []
        lines = content.split("\n")
        current: list[str] = []
        current_len = 0

        for line in lines:
            while len(line) > _WECHAT_MSG_MAX_LEN:
                if current:
                    chunks.append("\n".join(current))
                    current = []
                    current_len = 0
                chunks.append(line[:_WECHAT_MSG_MAX_LEN])
                line = line[_WECHAT_MSG_MAX_LEN:]

            if current_len + len(line) + 1 > _WECHAT_MSG_MAX_LEN and current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line) + 1

        if current:
            chunks.append("\n".join(current))

        return chunks
