from __future__ import annotations

import asyncio
from dataclasses import dataclass

from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Markdown, Static
from textual.worker import Worker, WorkerState

from ..ai.reviewer import ReviewResult, review_turns
from ..config import InsightConfig
from ..db.cache_db import CacheDb
from ..db.codex_db import CodexDb
from ..db.codex_sessions import CodexSessionsFs
from ..parser.turns import Turn, load_turns


class SessionDetailScreen(Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("c", "toggle_collapse_user", "Collapse"),
        ("t", "toggle_context", "Context"),
        ("space", "toggle_select", "Select"),
        ("shift+up", "select_range_up", "RangeUp"),
        ("shift+down", "select_range_down", "RangeDown"),
        ("r", "review_turn", "ReviewTurn"),
        ("R", "review_selection", "ReviewSelection"),
        ("a", "review_session", "ReviewSession"),
    ]

    def __init__(self, cfg: InsightConfig, *, session_id: str) -> None:
        super().__init__()
        self.cfg = cfg
        self.session_id = session_id
        self._db = CodexDb(cfg.codex_db_path)
        self._fs = CodexSessionsFs(cfg.codex_sessions_dir)
        self._cache = CacheDb()
        self._turns: list[Turn] = []
        self._include_context_user_messages = False
        self._collapse_user = True

        self._selected_turn_indices: set[int] = set()
        self._selection_anchor_row: int | None = None

        self._review_worker: Worker[ReviewResult] | None = None
        self._review_params: _ReviewParams | None = None

    def compose(self):
        with Horizontal():
            with VerticalScroll(id="left"):
                yield Static(f"Level 2: Session 详情：{self.session_id}", id="title")
                table = DataTable(id="turns_table")
                table.cursor_type = "row"
                yield table
                with VerticalScroll(id="turn_detail_scroll"):
                    yield Markdown("", id="turn_detail")
            with VerticalScroll(id="review"):
                yield Static("AI Review（按 r 生成，走 openagentic-sdk）", id="review_title")
                yield Markdown("进入这里后再按需生成 review，并缓存到本地。", id="review_body")

    def on_mount(self) -> None:
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        rollout_path: str | None = None
        if self._db.exists():
            sessions = {s.session_id: s for s in self._db.recent_sessions(limit=5000)}
            row = sessions.get(self.session_id)
            rollout_path = row.rollout_path if row is not None else None
        if not rollout_path and self._fs.exists():
            rollout_path = self._fs.rollout_path_for_session(self.session_id)
        table = self.query_one("#turns_table", DataTable)
        detail = self.query_one("#turn_detail", Markdown)

        table.clear(columns=True)
        table.add_column("✓", key="sel", width=2)
        table.add_column("#", key="idx", width=4)
        table.add_column("User", key="user")
        table.add_column("Assistant(final)", key="assistant")

        if not rollout_path:
            detail.update("未找到该 session 的 rollout 文件（SQLite/FS 都没有）。")
            return

        self._turns = load_turns(
            rollout_path,
            include_context_user_messages=self._include_context_user_messages,
        )
        self._selected_turn_indices.clear()
        self._selection_anchor_row = None

        if not self._turns:
            detail.update("未解析到 turn（仅展示 user 输入 + assistant 最终回复）。\n按 t 可切换是否包含 context user 消息。")
            return

        for t in self._turns:
            table.add_row(
                "",
                str(t.index),
                _preview(t.user_text),
                _preview(t.assistant_text),
                key=str(t.index),
            )
        table.cursor_coordinate = (0, 0)
        self._render_turn_detail(row_index=0)

    def _render_turn_detail(self, *, row_index: int) -> None:
        detail = self.query_one("#turn_detail", Markdown)
        if row_index < 0 or row_index >= len(self._turns):
            detail.update("")
            return
        t = self._turns[row_index]
        user_text = t.user_text
        if self._collapse_user:
            user_text = _collapse_text(user_text)

        user_block = _md_fence(user_text)
        assistant_block = _md_fence(t.assistant_text or "")
        extra = "（按 c 展开/收起 user）"
        detail.update(
            "\n".join(
                [
                    f"## Turn {t.index} {extra}",
                    "",
                    "### User",
                    user_block,
                    "",
                    "### Assistant (final)",
                    assistant_block,
                ]
            ).strip()
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # noqa: N802
        try:
            row = int(str(event.row_key.value))
        except Exception:
            return
        self._selection_anchor_row = self.query_one("#turns_table", DataTable).cursor_row
        self._render_turn_detail(row_index=max(0, row - 1))

    def action_toggle_collapse_user(self) -> None:
        self._collapse_user = not self._collapse_user
        table = self.query_one("#turns_table", DataTable)
        self._render_turn_detail(row_index=table.cursor_row)

    def action_toggle_context(self) -> None:
        self._include_context_user_messages = not self._include_context_user_messages
        self._refresh_detail()

    def action_toggle_select(self) -> None:
        table = self.query_one("#turns_table", DataTable)
        row_index = table.cursor_row
        if row_index < 0 or row_index >= len(self._turns):
            return
        turn_idx = self._turns[row_index].index
        if turn_idx in self._selected_turn_indices:
            self._selected_turn_indices.remove(turn_idx)
            table.update_cell(str(turn_idx), "sel", "")
        else:
            self._selected_turn_indices.add(turn_idx)
            table.update_cell(str(turn_idx), "sel", "✓")

    def action_select_range_up(self) -> None:
        self._select_range(delta=-1)

    def action_select_range_down(self) -> None:
        self._select_range(delta=1)

    def _select_range(self, *, delta: int) -> None:
        table = self.query_one("#turns_table", DataTable)
        if self._selection_anchor_row is None:
            self._selection_anchor_row = table.cursor_row
        if delta < 0:
            table.action_cursor_up()
        else:
            table.action_cursor_down()
        start = min(self._selection_anchor_row, table.cursor_row)
        end = max(self._selection_anchor_row, table.cursor_row)
        for row in range(start, end + 1):
            if 0 <= row < len(self._turns):
                idx = self._turns[row].index
                self._selected_turn_indices.add(idx)
                table.update_cell(str(idx), "sel", "✓")
        self._render_turn_detail(row_index=table.cursor_row)

    def action_review_turn(self) -> None:
        table = self.query_one("#turns_table", DataTable)
        if not self._turns:
            return
        idx = self._turns[table.cursor_row].index
        self._start_review(scope="turn", indices=[idx])

    def action_review_selection(self) -> None:
        if not self._selected_turn_indices:
            self.notify("未选中 turn；用 Space 选择，Shift+Up/Down 扩选。", title="Review")
            return
        self._start_review(scope="selection", indices=sorted(self._selected_turn_indices))

    def action_review_session(self) -> None:
        if not self._turns:
            return
        self._start_review(scope="session", indices=[t.index for t in self._turns])

    def _start_review(self, *, scope: str, indices: list[int]) -> None:
        md = self.query_one("#review_body", Markdown)
        if self._review_worker is not None and self._review_worker.state == WorkerState.RUNNING:
            self.notify("AI Review 正在生成中…", title="Review")
            return

        selection = "all" if scope == "session" else ",".join(str(x) for x in indices)
        cached = self._cache.get_review_scoped(session_id=self.session_id, scope=scope, selection=selection)
        if cached is not None:
            md.update(cached.review_markdown)
            return

        md.update("生成 AI Review 中…（后台运行，不阻塞界面）")
        self._review_params = _ReviewParams(scope=scope, indices=indices)
        self._review_worker = self.app.run_worker(self._review_sync, name="review", thread=True, exclusive=True)

    def _review_sync(self) -> ReviewResult:
        assert self._review_params is not None
        turns = [t for t in self._turns if t.index in set(self._review_params.indices)]
        return asyncio.run(review_turns(cfg=self.cfg, scope=self._review_params.scope, turns=turns))

    def on_worker_state_changed(self, message: Worker.StateChanged) -> None:  # noqa: N802
        if message.worker.name != "review":
            return
        md = self.query_one("#review_body", Markdown)
        if message.state == WorkerState.ERROR:
            err = message.worker.error
            md.update(f"AI Review 失败：{err}")
            return
        if message.state != WorkerState.SUCCESS:
            return
        rr = message.worker.result
        if rr is None or self._review_params is None:
            md.update("AI Review 返回为空。")
            return
        selection = "all" if self._review_params.scope == "session" else ",".join(str(x) for x in self._review_params.indices)
        self._cache.upsert_review_scoped(
            session_id=self.session_id,
            scope=self._review_params.scope,
            selection=selection,
            review_markdown=rr.markdown,
            model=rr.model,
        )
        md.update(rr.markdown)

    def action_back(self) -> None:
        self.app.action_back()


@dataclass(frozen=True, slots=True)
class _ReviewParams:
    scope: str
    indices: list[int]


def _preview(text: str, limit: int = 80) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\n", " ").strip()
    return s if len(s) <= limit else (s[:limit] + "…")


def _collapse_text(text: str, *, max_chars: int = 1200, max_lines: int = 40) -> str:
    s = (text or "").replace("\r\n", "\n")
    lines = s.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["…(truncated)"]
    s2 = "\n".join(lines).strip()
    return s2 if len(s2) <= max_chars else (s2[:max_chars] + "…")


def _md_fence(text: str) -> str:
    s = (text or "").replace("```", "``\u200b`").rstrip()
    return f"```text\n{s}\n```"
