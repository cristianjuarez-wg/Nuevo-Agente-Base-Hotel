"""
Fase 2.1 — CHECK DE ARQUITECTURA (permanente).

Regla: el FRAMEWORK (app/core/) no conoce el DOMINIO. No puede importar de
app.domains, app.services ni app.prompts ni app.routers. Este test lo hace cumplir
para siempre: si alguien reintroduce una dependencia core→dominio, falla en CI.

Excepción tolerada: imports de app.models.database / app.models.schemas / app.models.conversation*
(infra de persistencia y contratos de API genéricos, no lógica de hotel).
"""
import os
import re

_CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "core")

# Imports de dominio prohibidos dentro de app/core/.
_FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+app\.(domains|services|prompts|routers)\b",
    re.MULTILINE,
)
# Módulos de app.models tolerados en core (infra/contratos genéricos, no dominio hotel):
# database (engine/session), schemas (contratos API), conversation* (historial genérico),
# admin_user (auth del backoffice — infra de core/security, Fase 2.5).
_MODELS_OK = ("app.models.database", "app.models.schemas", "app.models.conversation",
              "app.models.admin_user")
_MODELS_IMPORT = re.compile(r"^\s*(?:from|import)\s+(app\.models\.[a-zA-Z_]+)", re.MULTILINE)


def _py_files(root):
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def test_core_no_importa_dominio():
    """app/core/ no importa de domains/services/prompts/routers."""
    violations = []
    for path in _py_files(_CORE_DIR):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for m in _FORBIDDEN.finditer(src):
            line = src[: m.start()].count("\n") + 1
            violations.append(f"{os.path.relpath(path)}:{line} → {m.group(0).strip()}")
    assert not violations, "core/ importa dominio:\n" + "\n".join(violations)


def test_core_solo_importa_models_de_infra():
    """Si core/ importa de app.models, debe ser solo infra genérica (database/schemas/conversation)."""
    violations = []
    for path in _py_files(_CORE_DIR):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for m in _MODELS_IMPORT.finditer(src):
            mod = m.group(1)
            if not mod.startswith(_MODELS_OK):
                line = src[: m.start()].count("\n") + 1
                violations.append(f"{os.path.relpath(path)}:{line} → {mod}")
    assert not violations, "core/ importa modelos de dominio:\n" + "\n".join(violations)
