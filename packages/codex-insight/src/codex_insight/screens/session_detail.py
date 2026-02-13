from __future__ import annotations

from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Markdown, Static

from ..ai.reviewer import review_messages
from ..config import InsightConfig
from ..db.cache_db import CacheDb
from ..db.codex_db import CodexDb
from ..db.codex_sessions import CodexSessionsFs
from ..parser.rollout import load_rollout_messages


class SessionDetailScreen(Screen[None]):
    BINDINGS = [("r", "refresh", "Refresh"), ("escape", "back", "Back")]

    def __init__(self, cfg: InsightConfig, *, session_id: str) -> None:
        super().__init__()
        self.cfg = cfg
        self.session_id = session_id
        self._db = CodexDb(cfg.codex_db_path)
        self._fs = CodexSessionsFs(cfg.codex_sessions_dir)
        self._cache = CacheDb()
        self._last_messages: list[dict[str, str]] = []

    def compose(self):
        with Horizontal():
            with VerticalScroll(id="chat"):
                yield Static(f"Level 2: Session 详情：{self.session_id}", id="title")
                yield Static("", id="chat_body")
            with VerticalScroll(id="review"):
                yield Static("AI Review（按 r 生成，走 openagentic-sdk）", id="review_title")
                yield Markdown("进入这里后再按需生成 review，并缓存到本地。", id="review_body")

    def on_mount(self) -> None:
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        body = self.query_one("#chat_body", Static)
        rollout_path: str | None = None
        if self._db.exists():
            sessions = {s.session_id: s for s in self._db.recent_sessions(limit=5000)}
            row = sessions.get(self.session_id)
            rollout_path = row.rollout_path if row is not None else None
        if not rollout_path and self._fs.exists():
            rollout_path = self._fs.rollout_path_for_session(self.session_id)
        if not rollout_path:
            body.update("未找到该 session 的 rollout 文件（SQLite/FS 都没有）。")
            return

        msgs = load_rollout_messages(rollout_path)
        if not msgs:
            body.update("rollout 解析为空或失败。")
            return
        self._last_messages = msgs[-200:]  # 控制 prompt 体积

        lines: list[str] = []
        for m in msgs:
            role = m.get("role", "?")
            content = m.get("content", "")
            lines.append(f"[{role}] {content}".strip())
            lines.append("")
        body.update("\n".join(lines).strip())

        cached = self._cache.get_review(self.session_id)
        if cached is not None:
            md = self.query_one("#review_body", Markdown)
            md.update(cached.review_markdown)

    async def action_refresh(self) -> None:
        self._refresh_detail()
        md = self.query_one("#review_body", Markdown)
        md.update("生成 AI Review 中…（可缓存到 `~/.codex-insight/cache.sqlite`）")
        try:
            rr = await review_messages(cfg=self.cfg, messages=self._last_messages)
        except Exception as e:  # noqa: BLE001
            md.update(f"AI Review 失败：{e}")
            return
        self._cache.upsert_review(session_id=self.session_id, review_markdown=rr.markdown, model=rr.model)
        md.update(rr.markdown)

    def action_back(self) -> None:
        self.app.action_back()
