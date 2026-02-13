from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class InsightConfig:
    timezone: str = "Asia/Shanghai"
    codex_db_path: str = ""
    codex_sessions_dir: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_review_model: str = "gpt-4o"

    def with_overrides(
        self,
        *,
        timezone: str | None = None,
        db_path: str | None = None,
        sessions_dir: str | None = None,
    ) -> "InsightConfig":
        return InsightConfig(
            timezone=(timezone if timezone is not None else self.timezone),
            codex_db_path=(db_path if db_path is not None else self.codex_db_path),
            codex_sessions_dir=(sessions_dir if sessions_dir is not None else self.codex_sessions_dir),
            ai_base_url=self.ai_base_url,
            ai_api_key=self.ai_api_key,
            ai_review_model=self.ai_review_model,
        )


def _default_config_path() -> Path:
    return Path.home() / ".codex-insight" / "config.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    import tomllib

    data = path.read_bytes()
    obj = tomllib.loads(data.decode("utf-8"))
    return obj if isinstance(obj, dict) else {}


def _auto_discover_codex_db_path() -> str:
    candidates: list[Path] = []
    appdata = (Path.home() / "AppData" / "Roaming")  # fallback if env missing
    try:
        import os

        if os.environ.get("APPDATA"):
            appdata = Path(os.environ["APPDATA"])
    except Exception:
        pass
    candidates.append(appdata / "codex" / "state_5.sqlite")
    candidates.append(Path.home() / ".codex" / "state_5.sqlite")
    for p in candidates:
        if p.exists():
            return str(p)
    return ""

def _auto_discover_codex_sessions_dir() -> str:
    candidates = [Path.home() / ".codex" / "sessions"]
    try:
        import os

        v = os.environ.get("CODEX_HOME")
        if isinstance(v, str) and v.strip():
            candidates.insert(0, Path(v) / "sessions")
    except Exception:
        pass
    for p in candidates:
        if p.exists() and p.is_dir():
            return str(p)
    return ""


def _load_codex_cli_config_defaults() -> tuple[str | None, str | None, str | None]:
    """Infer (base_url, model, api_key) from ~/.codex/config.toml (best-effort).

    Note: for convenience we fall back to OPENAI_API_KEY when the provider-specific
    env key is not available. This may fail for some gateways, but keeps the
    zero-config experience smoother.
    """
    codex_cfg = Path.home() / ".codex" / "config.toml"
    if not codex_cfg.exists():
        return None, None, None
    try:
        obj = _load_toml(codex_cfg)
    except Exception:
        return None, None, None

    model_provider = obj.get("model_provider")
    model = obj.get("model")
    if not isinstance(model_provider, str) or not model_provider.strip():
        return None, None, None
    model_provider = model_provider.strip()

    model_out: str | None = None
    if isinstance(model, str) and model.strip():
        model_out = model.strip()
        notice = obj.get("notice")
        if isinstance(notice, dict):
            mig = notice.get("model_migrations")
            if isinstance(mig, dict):
                mv = mig.get(model_out)
                if isinstance(mv, str) and mv.strip():
                    model_out = mv.strip()

    base_url: str | None = None
    env_key: str | None = None
    providers = obj.get("model_providers")
    if isinstance(providers, dict):
        p = providers.get(model_provider)
        if isinstance(p, dict):
            bu = p.get("base_url") or p.get("baseUrl") or p.get("baseURL")
            if isinstance(bu, str) and bu.strip():
                base_url = bu.strip()
            ek = p.get("env_key") or p.get("envKey")
            if isinstance(ek, str) and ek.strip():
                env_key = ek.strip()

    api_key: str | None = None
    try:
        import os

        if env_key:
            v = os.environ.get(env_key)
            if isinstance(v, str) and v.strip():
                api_key = v.strip()
    except Exception:
        api_key = None

    if not api_key and env_key:
        auth_json = Path.home() / ".codex" / "auth.json"
        if auth_json.exists():
            try:
                import json

                auth = json.loads(auth_json.read_text(encoding="utf-8"))
                if isinstance(auth, dict):
                    v = auth.get(env_key)
                    if isinstance(v, str) and v.strip():
                        api_key = v.strip()
            except Exception:
                pass

    if not api_key:
        try:
            import os

            v = os.environ.get("OPENAI_API_KEY")
            if isinstance(v, str) and v.strip():
                api_key = v.strip()
        except Exception:
            api_key = None

    if not api_key:
        auth_json = Path.home() / ".codex" / "auth.json"
        if auth_json.exists():
            try:
                import json

                auth = json.loads(auth_json.read_text(encoding="utf-8"))
                if isinstance(auth, dict):
                    v = auth.get("OPENAI_API_KEY")
                    if isinstance(v, str) and v.strip():
                        api_key = v.strip()
            except Exception:
                pass

    return base_url, model_out, api_key


def load_config(path: Path | None = None) -> InsightConfig:
    cfg_path = path or _default_config_path()
    timezone = "Asia/Shanghai"
    codex_db_path = ""
    codex_sessions_dir = ""
    ai_base_url = "https://api.openai.com/v1"
    ai_api_key = ""
    ai_review_model = "gpt-4o"

    if cfg_path.exists():
        try:
            obj = _load_toml(cfg_path)
            display = obj.get("display") if isinstance(obj, dict) else None
            if isinstance(display, dict):
                tz = display.get("timezone")
                if isinstance(tz, str) and tz.strip():
                    timezone = tz.strip()
            codex = obj.get("codex") if isinstance(obj, dict) else None
            if isinstance(codex, dict):
                db_path = codex.get("db_path")
                if isinstance(db_path, str) and db_path.strip():
                    codex_db_path = db_path.strip()
                sessions_dir = codex.get("sessions_dir")
                if isinstance(sessions_dir, str) and sessions_dir.strip():
                    codex_sessions_dir = sessions_dir.strip()

            ai = obj.get("ai") if isinstance(obj, dict) else None
            if isinstance(ai, dict):
                base_url = ai.get("base_url") or ai.get("baseURL") or ai.get("baseUrl")
                if isinstance(base_url, str) and base_url.strip():
                    ai_base_url = base_url.strip()
                api_key = ai.get("api_key") or ai.get("apiKey")
                if isinstance(api_key, str) and api_key.strip():
                    ai_api_key = api_key.strip()
                review_model = ai.get("review_model") or ai.get("reviewModel")
                if isinstance(review_model, str) and review_model.strip():
                    ai_review_model = review_model.strip()
        except Exception:
            pass

    if not codex_db_path:
        codex_db_path = _auto_discover_codex_db_path()
    if not codex_sessions_dir:
        codex_sessions_dir = _auto_discover_codex_sessions_dir()

    inferred_base_url, inferred_model, inferred_api_key = _load_codex_cli_config_defaults()
    if inferred_base_url and ai_base_url == "https://api.openai.com/v1":
        ai_base_url = inferred_base_url
    if inferred_model and ai_review_model == "gpt-4o":
        ai_review_model = inferred_model
    if inferred_api_key and not ai_api_key:
        ai_api_key = inferred_api_key

    if not ai_api_key and ai_base_url == "https://api.openai.com/v1":
        try:
            import os

            val = os.environ.get("OPENAI_API_KEY")
            if isinstance(val, str) and val.strip():
                ai_api_key = val.strip()
        except Exception:
            pass

    return InsightConfig(
        timezone=timezone,
        codex_db_path=codex_db_path,
        codex_sessions_dir=codex_sessions_dir,
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key,
        ai_review_model=ai_review_model,
    )
