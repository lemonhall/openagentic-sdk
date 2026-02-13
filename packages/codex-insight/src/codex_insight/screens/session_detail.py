from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from rich.markdown import Markdown as RichMarkdown
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import DataTable, Markdown, Static
from textual.worker import Worker, WorkerState

from ..ai.reviewer import ReviewResult, review_turns_stream
from ..config import InsightConfig
from ..db.cache_db import CacheDb
from ..db.codex_db import CodexDb
from ..db.codex_sessions import CodexSessionsFs
from ..parser.turns import Turn, load_turns


class SessionDetailScreen(Screen[None]):
    DEFAULT_CSS = """
    SessionDetailScreen #left {
        width: 1fr;
    }

    SessionDetailScreen #turns_table {
        height: 14;
    }

    SessionDetailScreen #turn_detail_scroll {
        height: 1fr;
        border: round $primary;
    }

    SessionDetailScreen #turn_detail {
        padding: 1 2;
        height: auto;
    }

    SessionDetailScreen #review {
        width: 1fr;
        border-left: solid $panel;
    }
    """

    BINDINGS = [
        ("escape", "back", "Back"),
        ("c", "toggle_collapse_user", "折叠/展开"),
        ("t", "toggle_context", "含/不含上下文"),
        ("m", "toggle_monitor", "监控最新"),
        Binding("up", "nav_up", "", show=False),
        Binding("down", "nav_down", "", show=False),
        ("enter", "open_turn_detail", "详情"),
        ("space", "toggle_select", "选择/取消"),
        ("shift+up", "select_range_up", "区间选择↑"),
        ("shift+down", "select_range_down", "区间选择↓"),
        ("x", "clear_selection", "清空选择"),
        ("r", "review_turn", "评审当前"),
        ("R", "review_selection", "评审所选"),
        ("a", "review_session", "评审全局"),
        ("k", "cancel_review", "取消评审"),
    ]

    def __init__(self, cfg: InsightConfig, *, session_id: str) -> None:
        super().__init__()
        self.cfg = cfg
        self.session_id = session_id
        self._db = CodexDb(cfg.codex_db_path)
        self._fs = CodexSessionsFs(cfg.codex_sessions_dir)
        self._cache = CacheDb()
        self._turns_lock = threading.Lock()
        self._turns: list[Turn] = []
        self._rollout_path: str | None = None
        self._include_context_user_messages = False
        self._collapse_user = True

        self._selected_turn_indices: set[int] = set()
        self._selection_anchor_row: int | None = None

        self._review_worker: Worker[ReviewResult] | None = None
        self._review_params: _ReviewParams | None = None
        self._review_started_monotonic: float | None = None
        self._review_timer: Timer | None = None
        self._review_abort_event: threading.Event | None = None
        self._review_delta_queue: queue.SimpleQueue[str] | None = None
        self._review_stream_text: str = ""
        self._review_last_render_monotonic: float = 0.0
        self._review_last_delta_monotonic: float | None = None

        self._monitor_enabled = False
        self._monitor_timer: Timer | None = None
        self._monitor_interval_s = 5.0
        self._monitor_last_stat: tuple[int, int] | None = None  # (mtime_ns, size)
        self._monitor_last_latest_signature: tuple[int, int] | None = None  # (turn_idx, hash(assistant_text))
        self._monitor_stable_polls: int = 0
        self._monitor_last_auto_attempt_signature: tuple[int, int] | None = None

    def compose(self):
        with Horizontal():
            with Vertical(id="left"):
                yield Static(f"Level 2: Session 详情：{self.session_id}", id="title")
                table = DataTable(id="turns_table")
                table.cursor_type = "row"
                table.show_cursor = True
                yield table
                with VerticalScroll(id="turn_detail_scroll"):
                    yield Static("", id="turn_detail", markup=False)
            with VerticalScroll(id="review"):
                yield Static("AI Review（按 r 生成，走 openagentic-sdk）", id="review_title")
                yield Static("监控：OFF（m 开关；5s 轮询；稳定 2 次后自动评审最新 turn）", id="monitor_status")
                yield Markdown(_KEY_HELP_MD.strip() + "\n", id="key_help")
                yield Markdown("进入这里后再按需生成 review，并缓存到本地。", id="review_body")

    def on_mount(self) -> None:
        self._refresh_detail()
        self._focus_turns_table()
        self._update_monitor_status()

    def on_show(self) -> None:
        # Ensure arrow-key navigation feels "terminal-native" without needing mouse focus.
        self._focus_turns_table()

    def on_unmount(self) -> None:
        self._stop_monitor()
        if self._review_timer is not None:
            self._review_timer.stop()
            self._review_timer = None

    def _focus_turns_table(self) -> None:
        try:
            table = self.query_one("#turns_table", DataTable)
        except Exception:
            return
        self.call_after_refresh(table.focus)

    def _refresh_detail(self) -> None:
        rollout_path: str | None = None
        if self._db.exists():
            sessions = {s.session_id: s for s in self._db.recent_sessions(limit=5000)}
            row = sessions.get(self.session_id)
            rollout_path = row.rollout_path if row is not None else None
        if not rollout_path and self._fs.exists():
            rollout_path = self._fs.rollout_path_for_session(self.session_id)
        self._rollout_path = rollout_path
        table = self.query_one("#turns_table", DataTable)
        detail = self.query_one("#turn_detail", Static)

        if not table.columns:
            table.clear(columns=True)
            table.add_column("✓", key="sel", width=2)
            table.add_column("#", key="idx", width=4)
            # Fixed widths avoid horizontal scrolling for typical terminals.
            table.add_column("User", key="user", width=48)
            table.add_column("Assistant(final)", key="assistant", width=64)
        else:
            table.clear(columns=False)

        if not rollout_path:
            detail.update("未找到该 session 的 rollout 文件（SQLite/FS 都没有）。")
            return

        turns = load_turns(
            rollout_path,
            include_context_user_messages=self._include_context_user_messages,
        )
        with self._turns_lock:
            self._turns = turns
        self._selected_turn_indices.clear()
        self._selection_anchor_row = None
        self._monitor_last_stat = None
        self._monitor_last_latest_signature = None
        self._monitor_stable_polls = 0
        self._monitor_last_auto_attempt_signature = None

        if not self._turns:
            detail.update("未解析到 turn（仅展示 user 输入 + assistant 最终回复）。\n按 t 可切换是否包含 context user 消息。")
            return

        for t in self._turns:
            table.add_row(
                "",
                str(t.index),
                _preview(t.user_text, limit=120),
                _preview(t.assistant_text, limit=200),
                key=str(t.index),
            )
        table.cursor_coordinate = (0, 0)
        self._render_turn_detail(row_index=0)
        self._focus_turns_table()

    def _render_turn_detail(self, *, row_index: int) -> None:
        detail = self.query_one("#turn_detail", Static)
        if row_index < 0 or row_index >= len(self._turns):
            detail.update("")
            return
        t = self._turns[row_index]
        user_text = t.user_text
        if self._collapse_user:
            user_text = _collapse_text(user_text)

        detail.update(RichMarkdown(_turn_detail_markdown(user_text=user_text, assistant_text=t.assistant_text or "")))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:  # noqa: N802
        if event.data_table.id != "turns_table":
            return
        self._render_turn_detail(row_index=event.cursor_row)

    def action_nav_up(self) -> None:
        table = self.query_one("#turns_table", DataTable)
        table.action_cursor_up()

    def action_nav_down(self) -> None:
        table = self.query_one("#turns_table", DataTable)
        table.action_cursor_down()

    def action_open_turn_detail(self) -> None:
        table = self.query_one("#turns_table", DataTable)
        row_index = table.cursor_row
        if row_index < 0 or row_index >= len(self._turns):
            return
        t = self._turns[row_index]
        self.app.push_screen(_TurnDetailModal(turn=t))

    def action_toggle_collapse_user(self) -> None:
        self._collapse_user = not self._collapse_user
        table = self.query_one("#turns_table", DataTable)
        self._render_turn_detail(row_index=table.cursor_row)

    def action_toggle_context(self) -> None:
        self._include_context_user_messages = not self._include_context_user_messages
        self._refresh_detail()
        self._update_monitor_status()

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
        self._selection_anchor_row = row_index

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
        new_sel: set[int] = set()
        for row in range(start, end + 1):
            if 0 <= row < len(self._turns):
                new_sel.add(self._turns[row].index)
        self._selected_turn_indices = new_sel
        self._sync_selection_table()

    def action_clear_selection(self) -> None:
        self._selected_turn_indices.clear()
        self._selection_anchor_row = None
        self._sync_selection_table()

    def _sync_selection_table(self) -> None:
        table = self.query_one("#turns_table", DataTable)
        for t in self._turns:
            table.update_cell(str(t.index), "sel", ("✓" if t.index in self._selected_turn_indices else ""))

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
        title = self.query_one("#review_title", Static)
        if self._review_worker is not None and self._review_worker.state == WorkerState.RUNNING:
            self.notify("AI Review 正在生成中…（按 k 可取消）", title="Review")
            return

        selection = "all" if scope == "session" else ",".join(str(x) for x in indices)
        cached = self._cache.get_review_scoped(session_id=self.session_id, scope=scope, selection=selection)
        if cached is not None:
            md.update(cached.review_markdown)
            return

        self._review_started_monotonic = time.monotonic()
        self._review_last_delta_monotonic = None
        self._review_abort_event = threading.Event()
        self._review_delta_queue = queue.SimpleQueue()
        self._review_stream_text = ""
        self._review_last_render_monotonic = 0.0
        title.update("AI Review（生成中…）")
        md.update("生成 AI Review 中…（streaming；按 k 可取消）")
        self._review_params = _ReviewParams(scope=scope, indices=indices)
        self._review_worker = self.run_worker(self._review_sync, name="review", thread=True, exclusive=True)
        if self._review_timer is not None:
            self._review_timer.stop()
        self._review_timer = self.set_interval(1.0, self._tick_review_status, name="review_status")

    def _review_sync(self) -> ReviewResult:
        assert self._review_params is not None
        with self._turns_lock:
            all_turns = list(self._turns)
        turns = [t for t in all_turns if t.index in set(self._review_params.indices)]
        abort_event = self._review_abort_event
        q = self._review_delta_queue

        def on_delta(delta: str) -> None:
            if q is not None:
                q.put(delta)

        return asyncio.run(
            review_turns_stream(
                cfg=self.cfg,
                scope=self._review_params.scope,
                turns=turns,
                rollout_path=self._rollout_path,
                include_context_user_messages=self._include_context_user_messages,
                on_delta=on_delta,
                abort_event=abort_event,
            )
        )

    def on_worker_state_changed(self, message: Worker.StateChanged) -> None:  # noqa: N802
        if message.worker.name != "review":
            return
        md = self.query_one("#review_body", Markdown)
        title = self.query_one("#review_title", Static)
        if self._review_timer is not None:
            self._review_timer.stop()
            self._review_timer = None
        if message.state == WorkerState.CANCELLED:
            title.update("AI Review（已取消）")
            md.update("AI Review 已取消。")
            return
        if message.state == WorkerState.ERROR:
            err = message.worker.error
            title.update("AI Review（失败）")
            md.update(f"AI Review 失败：{err}")
            return
        if message.state != WorkerState.SUCCESS:
            return
        rr = message.worker.result
        if rr is None or self._review_params is None:
            title.update("AI Review（空结果）")
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
        title.update("AI Review")
        md.update(rr.markdown)
        self._review_abort_event = None
        self._review_delta_queue = None

    def action_cancel_review(self) -> None:
        if self._review_worker is None:
            return
        if self._review_worker.state == WorkerState.RUNNING:
            if self._review_abort_event is not None:
                self._review_abort_event.set()
            self._review_worker.cancel()
            md = self.query_one("#review_body", Markdown)
            md.update("正在取消 AI Review…")
            if self._review_timer is not None:
                self._review_timer.stop()
                self._review_timer = None

    def _tick_review_status(self) -> None:
        if self._review_worker is None or self._review_worker.state != WorkerState.RUNNING:
            if self._review_timer is not None:
                self._review_timer.stop()
                self._review_timer = None
            return
        start = self._review_started_monotonic
        if start is None:
            return
        elapsed_s = int(time.monotonic() - start)
        title = self.query_one("#review_title", Static)
        title.update(f"AI Review（生成中 {elapsed_s}s；k 取消）")

        q = self._review_delta_queue
        if q is None:
            return
        got_any = False
        chunks: list[str] = []
        while True:
            try:
                chunks.append(q.get_nowait())
                got_any = True
            except Exception:
                break
        if got_any:
            self._review_last_delta_monotonic = time.monotonic()
            self._review_stream_text += "".join(chunks)

        # Throttle Markdown re-render.
        now = time.monotonic()
        if got_any and (now - self._review_last_render_monotonic) >= 0.5:
            self._review_last_render_monotonic = now
            md = self.query_one("#review_body", Markdown)
            md.update(self._review_stream_text)
        elif not self._review_stream_text and elapsed_s >= 8:
            md = self.query_one("#review_body", Markdown)
            md.update(f"生成 AI Review 中… 已耗时 {elapsed_s}s（尚未收到 stream 内容；按 k 可取消）")

    def action_toggle_monitor(self) -> None:
        if not self._rollout_path:
            self.notify("未找到 rollout 文件，无法开启监控。", title="监控")
            return
        self._monitor_enabled = not self._monitor_enabled
        if self._monitor_enabled:
            if self._monitor_timer is not None:
                self._monitor_timer.stop()
            self._monitor_timer = self.set_interval(self._monitor_interval_s, self._tick_monitor, name="monitor")
            self._monitor_last_stat = None
            self._monitor_last_latest_signature = None
            self._monitor_stable_polls = 0
            self._monitor_last_auto_attempt_signature = None
        else:
            self._stop_monitor()
        self._update_monitor_status()

    def _stop_monitor(self) -> None:
        self._monitor_enabled = False
        if self._monitor_timer is not None:
            self._monitor_timer.stop()
            self._monitor_timer = None

    def _update_monitor_status(self, *, note: str | None = None) -> None:
        try:
            st = self.query_one("#monitor_status", Static)
        except Exception:
            return
        if not self._monitor_enabled:
            st.update("监控：OFF（m 开关；5s 轮询；稳定 2 次后自动评审最新 turn）")
            return
        extra = f"；{note}" if note else ""
        st.update(f"监控：ON（5s；稳定 2 次后自动评审最新 turn）{extra}")

    def _tick_monitor(self) -> None:
        if not self._monitor_enabled:
            self._stop_monitor()
            self._update_monitor_status()
            return
        if not self._rollout_path:
            self._update_monitor_status(note="未找到 rollout")
            return

        p = Path(self._rollout_path)
        try:
            st = p.stat()
        except OSError:
            self._update_monitor_status(note="rollout 不可读")
            return

        stat_sig = (int(st.st_mtime_ns), int(st.st_size))
        changed = stat_sig != self._monitor_last_stat
        self._monitor_last_stat = stat_sig
        if changed:
            self._refresh_turns_preserve_cursor()

        latest = self._turns[-1] if self._turns else None
        if latest is None:
            self._update_monitor_status(note="无 turn")
            return

        assistant_text = (latest.assistant_text or "").strip()
        latest_sig = (latest.index, hash(assistant_text))
        if not assistant_text:
            self._monitor_last_latest_signature = latest_sig
            self._monitor_stable_polls = 0
            self._update_monitor_status(note=f"等待 Turn {latest.index} assistant(final)…")
            return

        if self._monitor_last_latest_signature == latest_sig:
            self._monitor_stable_polls += 1
        else:
            self._monitor_last_latest_signature = latest_sig
            self._monitor_stable_polls = 1

        if self._monitor_stable_polls < 2:
            self._update_monitor_status(note=f"Turn {latest.index} 稳定中（{self._monitor_stable_polls}/2）")
            return

        if self._review_worker is not None and self._review_worker.state == WorkerState.RUNNING:
            self._update_monitor_status(note=f"Turn {latest.index} 已稳定；review 生成中…")
            return

        if self._monitor_last_auto_attempt_signature == latest_sig:
            self._update_monitor_status(note=f"Turn {latest.index} 已自动评审")
            return

        self._monitor_last_auto_attempt_signature = latest_sig
        self._update_monitor_status(note=f"自动评审 Turn {latest.index}")
        self._start_review(scope="turn", indices=[latest.index])

    def _refresh_turns_preserve_cursor(self) -> None:
        if not self._rollout_path:
            return
        table = self.query_one("#turns_table", DataTable)
        detail = self.query_one("#turn_detail", Static)

        old_cursor = table.cursor_row
        follow_tail = bool(self._turns) and old_cursor >= (len(self._turns) - 1)

        turns = load_turns(
            self._rollout_path,
            include_context_user_messages=self._include_context_user_messages,
        )
        with self._turns_lock:
            self._turns = turns

        table.clear(columns=False)
        if not self._turns:
            detail.update("未解析到 turn（仅展示 user 输入 + assistant 最终回复）。\n按 t 可切换是否包含 context user 消息。")
            return

        valid_indices = {t.index for t in self._turns}
        self._selected_turn_indices = {i for i in self._selected_turn_indices if i in valid_indices}

        for t in self._turns:
            table.add_row(
                ("✓" if t.index in self._selected_turn_indices else ""),
                str(t.index),
                _preview(t.user_text, limit=120),
                _preview(t.assistant_text, limit=200),
                key=str(t.index),
            )

        new_cursor = (len(self._turns) - 1) if follow_tail else min(old_cursor, len(self._turns) - 1)
        table.cursor_coordinate = (new_cursor, 0)
        self._render_turn_detail(row_index=new_cursor)
        self._focus_turns_table()

    def action_back(self) -> None:
        self._stop_monitor()
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


_KEY_HELP_MD = """
**快捷键**

- `Enter`：打开当前 turn 详情（全屏）
- `m`：实时监控最新 turn（稳定 2 次后自动评审）
- `r`：评审当前 turn
- `R`：评审已选择 turns
- `a`：评审整个 session
- `Space`：选择/取消选择当前 turn
- `Shift+↑/↓`：区间选择（会随光标缩小/扩大）
- `x`：清空选择
- `c`：折叠/展开 user 输入
- `t`：切换是否包含 context user 消息
- `k`：取消正在生成的 review
- `Esc`：返回上一层
"""


class _TurnDetailModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "关闭"),
        Binding("enter", "dismiss", "关闭", show=False),
    ]

    DEFAULT_CSS = """
    _TurnDetailModal {
        align: center middle;
    }

    _TurnDetailModal #panel {
        width: 90%;
        height: 90%;
        border: round $primary;
        background: $surface;
    }

    _TurnDetailModal #body {
        height: 1fr;
        padding: 1 2;
    }

    _TurnDetailModal #body_md {
        height: auto;
    }
    """

    def __init__(self, *, turn: Turn) -> None:
        super().__init__()
        self.turn = turn

    def compose(self):
        with Vertical(id="panel"):
            yield Static(f"Turn {self.turn.index} 详情（Esc/Enter 关闭）", id="title")
            with VerticalScroll(id="body"):
                yield Static(
                    RichMarkdown(_turn_detail_markdown(user_text=self.turn.user_text, assistant_text=self.turn.assistant_text)),
                    id="body_md",
                    markup=False,
                )

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#body", VerticalScroll).focus)

    def action_dismiss(self) -> None:
        self.dismiss(None)


def _turn_detail_markdown(*, user_text: str, assistant_text: str) -> str:
    user = (user_text or "").replace("\r\n", "\n").strip()
    assistant = (assistant_text or "").replace("\r\n", "\n").strip()
    if not user:
        user = "（空）"
    if not assistant:
        assistant = "（空）"

    user_lines = user.split("\n")
    # Preserve user newlines without forcing code fences (avoids horizontal scroll),
    # and keep it visually distinct via blockquote.
    if user_lines:
        rendered_lines: list[str] = []
        for line in user_lines:
            if line == "":
                rendered_lines.append(">")
            else:
                rendered_lines.append(f"> {line}  ")
        user_blockquote = "\n".join(rendered_lines)
    else:
        user_blockquote = "> （空）"

    return "\n".join(
        [
            "## User",
            user_blockquote,
            "",
            "## Assistant (final)",
            assistant,
            "",
        ]
    ).strip() + "\n"
