"""
test_calidad.py — LA PUERTA DE CALIDAD del harness (Artefacto 3 · Fase 4)
========================================================================
Convierte el harness en una RED DE SEGURIDAD automática: envuelve las
métricas de calidad del RAG como asserts de pytest. Si una versión nueva
alucina o baja de nota respecto a la línea base, `pytest` se pone ROJO.

Cómo encaja (separación caro / barato — el patrón de un quality gate):
  · evaluar.py   → interroga al RAG + jueces LLM   (CUESTA API)  → resultados.json
  · comparar.py  → diff resultados vs baseline      (gratis)      → veredicto + exit code
  · test_calidad → asserts sobre ESE diff           (gratis)      → verde / rojo

pytest NO gasta API: solo lee dos JSON ya producidos. Por eso el flujo es
"evalúa UNA vez (caro) → testea cuantas veces quieras (barato)". El paso caro
corre una vez; la puerta se ejecuta sola sobre su salida.

Reutiliza la lógica de comparar.py (MISMA definición de "regresión" y las
mismas tolerancias — una sola fuente de verdad, no dos criterios que se
puedan contradecir). Esto es lo mismo que el exit code 0/1 de comparar.py,
pero expresado como asserts legibles que un pipeline entiende.

Uso:
    python evaluar.py                              # produce resultados.json (una vez, cuesta API)
    pytest -v                                      # corre la puerta de calidad (gratis)
    HARNESS_CAND=resultados_u040.json pytest -v    # testea OTRO candidato (p. ej. la regresión del umbral 0.40)
"""

import os
from pathlib import Path

import pytest

import comparar   # reutilizamos su lógica de comparación y sus tolerancias

BASE = Path(__file__).parent
BASELINE = BASE / "baseline.json"
# el candidato por defecto es resultados.json; HARNESS_CAND permite apuntar a otro
# sin tocar nada (útil para demostrar que la puerta SÍ se pone roja con una regresión).
RESULTADOS = BASE / os.environ.get("HARNESS_CAND", "resultados.json")


# ── fixtures: cargan los dos JSON una sola vez por sesión ────────────────────
@pytest.fixture(scope="session")
def base():
    if not BASELINE.exists():
        pytest.skip("No hay baseline.json — fíjala con:  python comparar.py fijar")
    return comparar.cargar(BASELINE)


@pytest.fixture(scope="session")
def cand():
    if not RESULTADOS.exists():
        pytest.skip(f"No existe {RESULTADOS.name} — evalúa antes con:  python evaluar.py")
    return comparar.cargar(RESULTADOS)


@pytest.fixture(scope="session")
def diff(base, cand):
    """El diff candidato vs línea base, calculado una sola vez y compartido."""
    return comparar.comparar(base, cand)


# ── LA PUERTA: ninguna regresión dura ────────────────────────────────────────
def test_sin_regresiones_duras(diff):
    """El corazón del gate: si comparar.py marca una regresión dura, esto es ROJO."""
    assert diff["regresiones"] == [], (
        "Regresiones detectadas respecto a la línea base:\n  · "
        + "\n  · ".join(diff["regresiones"])
    )


# ── desgloses explícitos (mismo criterio, legibles uno a uno) ────────────────
def test_ninguna_alucinacion_nueva(diff):
    """Ningún NUEVO falso positivo: responder algo ausente del corpus = alucinación.
    Es la métrica que distingue a este RAG (sabe callarse); por eso tiene su propio test."""
    alucinaciones = [r for r in diff["regresiones"] if "FALSO POSITIVO" in r]
    assert not alucinaciones, "Alucinación nueva:\n  · " + "\n  · ".join(alucinaciones)


def test_decision_no_empeora(diff):
    """La decisión (responder cuando toca / callarse cuando toca) no baja vs la base."""
    d = diff["deltas"]["decision_acierto"]
    assert d["cand"] >= d["base"], f"decisión {d['base']} → {d['cand']} (no debería bajar)"


@pytest.mark.parametrize("metrica", ["faithfulness_media", "relevancia_media"])
def test_calidad_media_no_cae(diff, metrica):
    """Faithfulness / relevancia media no caen más que la tolerancia (TOL_SCORE=0.3)."""
    d = diff["deltas"][metrica]
    if d["base"] is None or d["cand"] is None:
        pytest.skip(f"{metrica} sin dato en base o candidato")
    assert d["cand"] >= d["base"] - comparar.TOL_SCORE, (
        f"{metrica} {d['base']} → {d['cand']} (tolerancia {comparar.TOL_SCORE})"
    )


def test_citas_no_caen(diff):
    """El % de respuestas con cita no baja más que la tolerancia de porcentaje (TOL_PCT=0.15)."""
    d = diff["deltas"]["citas_pct"]
    if d["base"] is None or d["cand"] is None:
        pytest.skip("citas_pct sin dato")
    assert d["cand"] >= d["base"] - comparar.TOL_PCT, (
        f"% citas {d['base']} → {d['cand']} (tolerancia {comparar.TOL_PCT})"
    )
