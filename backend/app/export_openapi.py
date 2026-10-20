"""Exporta el contrato OpenAPI de KAI Core a shared/openapi.json (lo usan los clientes desktop/Android).

Uso:  python -m app.export_openapi
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.core.config import REPO_ROOT, Settings
from app.main import create_app
from app.security.secrets import SecretStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(_env_file=None, KAI_DATA_DIR=tmp, KAI_USE_KEYRING=False)  # type: ignore[call-arg]
        app = create_app(settings, secrets=SecretStore(None, use_keyring=False), configure_logging=False)
        spec = app.openapi()
        app.state.ctx.db.engine.dispose()
    out = REPO_ROOT / "shared" / "openapi.json"
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI exportado en {Path(out).relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
