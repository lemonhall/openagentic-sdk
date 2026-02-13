from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
import getpass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .auth import WellKnownAuth, all_auth


# OpenCode-compatible substitution tokens.
_ENV_RE = re.compile(r"\{env:([^}]+)\}")
_FILE_TOKEN_RE = re.compile(r"\{file:[^}]+\}")


def _home_dir() -> Path:
    # OpenCode supports overriding home in tests.
    test_home = os.environ.get("OPENCODE_TEST_HOME")
    if test_home:
        return Path(test_home).expanduser().resolve()
    return Path.home().expanduser().resolve()


def _xdg_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser().resolve() if xdg else (_home_dir() / ".config")
    return base / "opencode"


def _opencode_config_dir() -> Path | None:
    p = os.environ.get("OPENCODE_CONFIG_DIR")
    if not p:
        return None
    return Path(p).expanduser().resolve()


def _env_flag(name: str) -> bool:
    # OpenCode flags are boolean by presence. We also accept common truthy forms.
    v = os.environ.get(name)
    if v is None:
        return False
    if v == "":
        return True
    return v.strip().lower() not in {"0", "false", "no", "off"}


def _find_worktree_root(start: Path) -> Path:
    # Best-effort boundary similar to OpenCode's Instance.worktree.
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    # Non-git projects can scan to filesystem root in OpenCode.
    return Path(cur.anchor or "/").resolve()


def _iter_up(start: Path, stop: Path) -> Iterable[Path]:
    """Yield directories from start up to stop (inclusive)."""

    cur = start.resolve()
    stop_r = stop.resolve()
    while True:
        yield cur
        if cur == stop_r:
            break
        if cur.parent == cur:
            break
        cur = cur.parent


def _find_up(filename: str, *, start: Path, stop: Path) -> list[Path]:
    """OpenCode-like findUp: returns matches from start->stop."""

    out: list[Path] = []
    for d in _iter_up(start, stop):
        p = d / filename
        if p.exists() and p.is_file():
            out.append(p)
    return out


def _up_dirs(target: str, *, start: Path, stop: Path) -> list[Path]:
    """OpenCode-like up() for a single directory target."""

    out: list[Path] = []
    for d in _iter_up(start, stop):
        p = d / target
        if p.exists() and p.is_dir():
            out.append(p)
    return out


def _strip_jsonc_comments(text: str) -> str:
    """Strip // and /* */ comments while preserving strings."""

    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    str_quote = ""
    esc = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == str_quote:
                in_str = False
                str_quote = ""
            i += 1
            continue

        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ] (outside strings)."""

    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    str_quote = ""
    esc = False

    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == str_quote:
                in_str = False
                str_quote = ""
            i += 1
            continue

        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < n and text[j] in (" ", "\t", "\r", "\n"):
                j += 1
            if j < n and text[j] in ("}", "]"):
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _dedupe_keep_first(items: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for x in items:
        key = json.dumps(x, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def _plugin_canonical_name(specifier: str) -> str:
    # Match OpenCode's `getPluginName`.
    if specifier.startswith("file://"):
        try:
            # file:// URLs may include percent-encoding; Path won't decode, but
            # canonical name only needs the last path segment.
            path_part = specifier[len("file://") :]
            return Path(path_part).name.rsplit(".", 1)[0]
        except Exception:  # noqa: BLE001
            return specifier

    last_at = specifier.rfind("@")
    if last_at > 0:
        return specifier[:last_at]
    return specifier


def _dedupe_plugins_by_name(plugins: list[str]) -> list[str]:
    # Match OpenCode's behavior: later (higher precedence) wins.
    seen: set[str] = set()
    unique: list[str] = []
    for spec in reversed(plugins):
        name = _plugin_canonical_name(spec)
        if name in seen:
            continue
        seen.add(name)
        unique.append(spec)
    unique.reverse()
    return unique


def _fetch_json(url: str, *, timeout_s: float = 5.0) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            raw = resp.read()
    except Exception:  # noqa: BLE001
        return None
    try:
        obj = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


def _merge_deep_replace_arrays(a: Any, b: Any) -> Any:
    """OpenCode-like deep merge: objects merge, arrays are replaced."""

    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if k in out:
                out[k] = _merge_deep_replace_arrays(out[k], v)
            else:
                out[k] = v
        return out

    # Arrays are not concatenated by default.
    if isinstance(b, list):
        return list(b)
    return b


def _merge_config_concat_arrays(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Match OpenCode merge behavior for plugin/instructions."""

    merged: dict[str, Any] = _merge_deep_replace_arrays(target, source)

    for key in ("plugin", "instructions"):
        a = target.get(key)
        b = source.get(key)
        if isinstance(a, list) and isinstance(b, list):
            merged[key] = _dedupe_keep_first([*a, *b])

    return merged


def _annotate_json_error(text: str, err: json.JSONDecodeError) -> str:
    # Mimic OpenCode's annotated error style.
    line_no = int(getattr(err, "lineno", 1))
    col_no = int(getattr(err, "colno", 1))
    lines = text.splitlines()
    problem = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
    caret = " " * (col_no + 8) + "^" if col_no > 0 else "^"
    return "\n".join(
        [
            f"JSON parse error at line {line_no}, column {col_no}: {err.msg}",
            f"   Line {line_no}: {problem}",
            caret,
        ]
    )


def _substitute_env(text: str) -> str:
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), text)


def _substitute_file_tokens(*, text: str, config_file: Path) -> str:
    # OpenCode finds all {file:...} tokens and replaces them in-order.
    # It also skips tokens on lines commented out with //.
    matches = list(dict.fromkeys(_FILE_TOKEN_RE.findall(text)))
    if not matches:
        return text

    base_dir = config_file.parent
    home = _home_dir()
    lines = text.split("\n")

    out = text
    for token in matches:
        # FindIndex semantics: first line containing this token decides comment-skip.
        try:
            idx = next(i for i, line in enumerate(lines) if token in line)
        except StopIteration:
            idx = -1
        if idx != -1 and lines[idx].strip().startswith("//"):
            continue

        raw = token.removeprefix("{file:").removesuffix("}")
        file_path = raw.strip()
        if file_path.startswith("~/"):
            resolved = home / file_path[2:]
        else:
            p = Path(file_path)
            resolved = p if p.is_absolute() else (base_dir / p)
        try:
            file_content = resolved.read_text(encoding="utf-8", errors="replace").strip()
        except FileNotFoundError as e:
            raise ValueError(f"bad file reference: {token} {resolved} does not exist") from e
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"bad file reference: {token}") from e

        # Escape as JSON string literal, then strip the surrounding quotes.
        repl = json.dumps(file_content, ensure_ascii=False)[1:-1]

        # OpenCode replaces a single occurrence per token iteration.
        out = out.replace(token, repl, 1)

    return out


def load_config_file(path: str) -> dict[str, Any]:
    p = Path(path)
    original = p.read_text(encoding="utf-8", errors="replace")

    text = _substitute_env(original)
    text = _substitute_file_tokens(text=text, config_file=p)

    cleaned = _strip_trailing_commas(_strip_jsonc_comments(text))
    try:
        data = json.loads(cleaned) if cleaned.strip() else {}
    except json.JSONDecodeError as e:
        raise ValueError(_annotate_json_error(text, e)) from e

    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")

    # OpenCode inserts $schema if missing and tries to write it back.
    if not data.get("$schema"):
        data["$schema"] = "https://opencode.ai/config.json"
        try:
            updated = re.sub(
                r"^\s*\{",
                '{\n  "$schema": "https://opencode.ai/config.json",',
                original,
                count=1,
            )
            if updated != original:
                p.write_text(updated, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # Best-effort normalize plugin paths: if a plugin looks like a relative path,
    # resolve it relative to the config file.
    plugins = data.get("plugin")
    if isinstance(plugins, list):
        out: list[Any] = []
        for item in plugins:
            if not isinstance(item, str) or not item:
                continue
            s = item
            if s.startswith("file://"):
                out.append(s)
                continue
            pp = Path(s)
            if not pp.is_absolute() and ("/" in s or "\\" in s or s.endswith((".js", ".ts", ".py"))):
                out.append("file://" + str((p.parent / pp).resolve()))
            else:
                out.append(s)
        data["plugin"] = out

    return data


def _load_global_config(global_dir: Path) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    # OpenCode merges config.json/opencode.json/opencode.jsonc in that order.
    for name in ("config.json", "opencode.json", "opencode.jsonc"):
        p = global_dir / name
        if p.exists() and p.is_file():
            merged = _merge_config_concat_arrays(merged, load_config_file(str(p)))
    return merged


def _parse_inline_json(text: str) -> dict[str, Any]:
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("OPENCODE_CONFIG_CONTENT must be a JSON object")
    return obj


def _load_markdown_frontmatter(md_text: str) -> tuple[dict[str, Any], str]:
    """Parse a very small subset of gray-matter YAML frontmatter.

    OpenCode uses gray-matter with preprocessing to handle colons; we match the
    same subset here without adding dependencies.
    """

    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", md_text)
    if not m:
        return {}, md_text

    fm_raw = m.group(1)
    body = md_text[m.end() :]

    # Preprocess: convert `key: value:with:colon` into a block scalar.
    lines = fm_raw.split("\n")
    processed: list[str] = []
    for line in lines:
        t = line.strip()
        if t.startswith("#") or t == "":
            processed.append(line)
            continue
        if re.match(r"^\s+", line):
            processed.append(line)
            continue
        kv = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$", line)
        if not kv:
            processed.append(line)
            continue
        key = kv.group(1)
        value = kv.group(2).strip()
        if value in ("", ">", "|") or value.startswith(('"', "'")):
            processed.append(line)
            continue
        if ":" in value:
            processed.append(f"{key}: |")
            processed.append(f"  {value}")
            continue
        processed.append(line)

    fm = "\n".join(processed)

    # Minimal YAML mapping parse.
    data: dict[str, Any] = {}
    i = 0
    fm_lines = fm.split("\n")
    while i < len(fm_lines):
        line = fm_lines[i]
        t = line.strip()
        if t == "" or t.startswith("#"):
            i += 1
            continue
        if re.match(r"^\s+", line):
            i += 1
            continue
        kv = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$", line)
        if not kv:
            i += 1
            continue
        key = kv.group(1)
        value = kv.group(2)
        if value.strip() in ("|", ">"):
            i += 1
            block: list[str] = []
            while i < len(fm_lines) and re.match(r"^\s+", fm_lines[i]):
                block.append(re.sub(r"^\s+", "", fm_lines[i]))
                i += 1
            data[key] = "\n".join(block).rstrip("\n")
            continue

        v = value.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if v.lower() in ("true", "false"):
            data[key] = v.lower() == "true"
        else:
            data[key] = v
        i += 1

    return data, body


def _scan_files_recursive(root: Path, *, suffix: str) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.name.endswith(suffix):
            out.append(p)
    return out


def _load_commands_from_dir(dir_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for folder in (dir_path / "command", dir_path / "commands"):
        if not folder.exists() or not folder.is_dir():
            continue
        for p in _scan_files_recursive(folder, suffix=".md"):
            raw = p.read_text(encoding="utf-8", errors="replace")
            meta, body = _load_markdown_frontmatter(raw)
            rel = p.relative_to(folder).as_posix()
            name = rel[: -len(p.suffix)]
            rec: dict[str, Any] = {"template": body.strip()}
            for k in ("description", "agent", "model", "subtask"):
                if k in meta:
                    rec[k] = meta[k]
            out[name] = rec
    return out


def _load_agents_from_dir(dir_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for folder in (dir_path / "agent", dir_path / "agents"):
        if not folder.exists() or not folder.is_dir():
            continue
        for p in _scan_files_recursive(folder, suffix=".md"):
            raw = p.read_text(encoding="utf-8", errors="replace")
            meta, body = _load_markdown_frontmatter(raw)
            rel = p.relative_to(folder).as_posix()
            name = rel[: -len(p.suffix)]
            rec = dict(meta)
            rec["prompt"] = body.strip()
            out[name] = rec
    return out


def _load_modes_from_dir(dir_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for folder in (dir_path / "mode", dir_path / "modes"):
        if not folder.exists() or not folder.is_dir():
            continue
        for p in folder.glob("*.md"):
            if not p.is_file():
                continue
            raw = p.read_text(encoding="utf-8", errors="replace")
            meta, body = _load_markdown_frontmatter(raw)
            name = p.stem
            rec = dict(meta)
            rec["prompt"] = body.strip()
            out[name] = rec
    return out


def _load_plugins_from_dir(dir_path: Path) -> list[str]:
    out: list[str] = []
    for folder in (dir_path / "plugin", dir_path / "plugins"):
        if not folder.exists() or not folder.is_dir():
            continue
        for p in folder.iterdir():
            if not p.is_file():
                continue
            if p.suffix not in (".ts", ".js"):
                continue
            out.append(p.resolve().as_uri())
    return out


@dataclass(frozen=True, slots=True)
class OpencodeConfigState:
    config: dict[str, Any]
    directories: list[str]


def load_state(*, cwd: str, global_config_dir: str | None = None) -> OpencodeConfigState:
    cwd_p = Path(cwd).resolve()
    worktree = _find_worktree_root(cwd_p)

    cfg: dict[str, Any] = {}

    # 1) Remote well-known config (lowest precedence).
    for provider_base, info in all_auth().items():
        if not isinstance(info, WellKnownAuth):
            continue
        # OpenCode exports the token to env for downstream substitution.
        if info.key:
            os.environ[info.key] = info.token

        url = provider_base.rstrip("/") + "/.well-known/opencode"
        payload = _fetch_json(url, timeout_s=5.0)
        if not payload:
            continue
        remote_cfg = payload.get("config")
        if not isinstance(remote_cfg, dict):
            continue
        # Prevent schema write-back attempts.
        remote_cfg = dict(remote_cfg)
        remote_cfg.setdefault("$schema", "https://opencode.ai/config.json")
        cfg = _merge_config_concat_arrays(cfg, remote_cfg)

    # 2) Global config.
    global_dir = Path(global_config_dir).resolve() if global_config_dir else _xdg_config_dir()
    if global_dir.exists():
        cfg = _merge_config_concat_arrays(cfg, _load_global_config(global_dir))

    # 3) Custom config path.
    custom_path = os.environ.get("OPENCODE_CONFIG")
    if custom_path:
        cfg = _merge_config_concat_arrays(cfg, load_config_file(custom_path))

    # 4) Project config (highest precedence among base layers).
    if not _env_flag("OPENCODE_DISABLE_PROJECT_CONFIG"):
        for name in ("opencode.jsonc", "opencode.json"):
            found = _find_up(name, start=cwd_p, stop=worktree)
            for p in reversed(found):
                cfg = _merge_config_concat_arrays(cfg, load_config_file(str(p)))

    # 5) Inline config content.
    inline = os.environ.get("OPENCODE_CONFIG_CONTENT")
    if inline:
        cfg = _merge_config_concat_arrays(cfg, _parse_inline_json(inline))

    # Normalize basics for downstream merges.
    if not isinstance(cfg.get("agent"), dict):
        cfg["agent"] = {}
    if not isinstance(cfg.get("mode"), dict):
        cfg["mode"] = {}
    if not isinstance(cfg.get("plugin"), list):
        cfg["plugin"] = []

    # Directory packs (OpenCode Config.directories()).
    dirs: list[Path] = [global_dir]
    if not _env_flag("OPENCODE_DISABLE_PROJECT_CONFIG"):
        dirs.extend(_up_dirs(".opencode", start=cwd_p, stop=worktree))
    dirs.append(_home_dir() / ".opencode")
    cfg_dir = _opencode_config_dir()
    if cfg_dir is not None:
        dirs.append(cfg_dir)

    # Unique preserving order.
    uniq: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)

    for d in uniq:
        # Only load opencode.json{c,json} from actual .opencode packs (or OPENCODE_CONFIG_DIR).
        if d.name == ".opencode" or (cfg_dir is not None and d == cfg_dir):
            for name in ("opencode.jsonc", "opencode.json"):
                p = d / name
                if p.exists() and p.is_file():
                    cfg = _merge_config_concat_arrays(cfg, load_config_file(str(p)))
                    cfg.setdefault("agent", {})
                    cfg.setdefault("mode", {})
                    cfg.setdefault("plugin", [])

        # Merge directory-provided commands/agents/modes/plugins.
        cmd_map = _load_commands_from_dir(d)
        if cmd_map:
            cfg["command"] = _merge_deep_replace_arrays(cfg.get("command") or {}, cmd_map)
        agent_map = _load_agents_from_dir(d)
        if agent_map:
            cfg["agent"] = _merge_deep_replace_arrays(cfg.get("agent") or {}, agent_map)
        mode_map = _load_modes_from_dir(d)
        if mode_map:
            cfg["agent"] = _merge_deep_replace_arrays(cfg.get("agent") or {}, mode_map)
        plugins = _load_plugins_from_dir(d)
        if plugins:
            existing_plugins = cfg.get("plugin")
            existing_list: list[Any] = list(existing_plugins) if isinstance(existing_plugins, list) else []
            cfg["plugin"] = _dedupe_keep_first([*existing_list, *plugins])

    # Migrate deprecated `mode` to `agent`.
    mode_cfg = cfg.get("mode")
    if isinstance(mode_cfg, dict) and mode_cfg:
        agent_cfg = cfg.get("agent")
        if not isinstance(agent_cfg, dict):
            agent_cfg = {}
        for name, mode in mode_cfg.items():
            if not isinstance(name, str) or not isinstance(mode, dict):
                continue
            agent_cfg[name] = {**mode, "mode": "primary"}
        cfg["agent"] = agent_cfg

    # Back-compat: legacy top-level `tools` -> `permission`.
    tools_cfg = cfg.get("tools")
    if isinstance(tools_cfg, dict):
        perms: dict[str, Any] = {}
        for tool, enabled in tools_cfg.items():
            if not isinstance(tool, str):
                continue
            action = "allow" if bool(enabled) else "deny"
            if tool in {"write", "edit", "patch", "multiedit"}:
                perms["edit"] = action
            else:
                perms[tool] = action
        existing = cfg.get("permission")
        if isinstance(existing, dict):
            perms = _merge_deep_replace_arrays(perms, existing)
        cfg["permission"] = perms

    # OPENCODE_PERMISSION env override (JSON).
    perm_override = os.environ.get("OPENCODE_PERMISSION")
    if perm_override:
        try:
            perm_obj = json.loads(perm_override)
        except Exception as e:  # noqa: BLE001
            raise ValueError("OPENCODE_PERMISSION must be valid JSON") from e
        if isinstance(perm_obj, dict):
            existing = cfg.get("permission")
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged = _merge_deep_replace_arrays(merged, perm_obj)
            cfg["permission"] = merged

    # Back-compat: autoshare -> share.
    if cfg.get("autoshare") is True and not cfg.get("share"):
        cfg["share"] = "auto"

    if not cfg.get("username"):
        try:
            cfg["username"] = getpass.getuser()
        except Exception:  # noqa: BLE001
            pass

    # Apply flag overrides for compaction settings.
    if _env_flag("OPENCODE_DISABLE_AUTOCOMPACT"):
        comp = cfg.get("compaction")
        comp2 = dict(comp) if isinstance(comp, dict) else {}
        comp2["auto"] = False
        cfg["compaction"] = comp2
    if _env_flag("OPENCODE_DISABLE_PRUNE"):
        comp = cfg.get("compaction")
        comp2 = dict(comp) if isinstance(comp, dict) else {}
        comp2["prune"] = False
        cfg["compaction"] = comp2

    # Canonical plugin-name dedupe (later wins).
    plugin_list = cfg.get("plugin")
    if isinstance(plugin_list, list) and plugin_list:
        cfg["plugin"] = _dedupe_plugins_by_name([str(x) for x in plugin_list if isinstance(x, str) and x])

    return OpencodeConfigState(config=cfg, directories=[str(d) for d in uniq])


def load_merged_config(*, cwd: str, global_config_dir: str | None = None) -> dict[str, Any]:
    return load_state(cwd=cwd, global_config_dir=global_config_dir).config
