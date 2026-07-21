"""
Artefacto 5 · Fase 2 · LA BÁSCULA

Corre el eval-set contra una versión de los prompts y ESCRIBE el resultado en
historial.json. Es el único paso que cuesta dinero (llama a la API); todo lo
demás lee ese JSON. Patrón caro-una-vez / barato-mil-veces (ficha 04).

  evaluar_prompts.py  ──►  historial.json  ──►  render_historial.py
  ● CUESTA API             ▲ FUENTE DE VERDAD     ○ GRATIS, mil veces

Uso:
    python evaluacion/evaluar_prompts.py --nota "baseline v1, sin tocar nada"
    python evaluacion/evaluar_prompts.py --version match_cv=v2 --nota "CoT en el CEFR"
    python evaluacion/evaluar_prompts.py --seco     # no llama a la API, no escribe

Cada fila que se guarda lleva el HASH del prompt que se usó de verdad. Eso es lo
que hace que el historial no pueda mentir: si alguien edita la v1 en vez de crear
una v2, el hash cambia y las corridas viejas dejan de cuadrar. La regla "una
versión publicada no se edita" pasa de ser un comentario a ser comprobable.
"""

import argparse
import fcntl
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))

import prompts
from agente import DISPATCH          # reutilizamos el despachador del agente, no otro
from herramientas import MODELO, _cargar_cv

RUTA_CASOS = AQUI / "casos.json"
RUTA_HISTORIAL = AQUI / "historial.json"
RUTA_CERROJO = AQUI / "historial.json.lock"
RUTA_UMBRAL = AQUI / "umbral.json"


# ─────────────────────────────────────────────────────────────
# LAS COMPROBACIONES
# ─────────────────────────────────────────────────────────────
# Viven en Python, no en el JSON: son LÓGICA. Meterlas en el JSON obligaría a
# inventarse un mini-lenguaje de reglas, y acabaríamos manteniendo un intérprete
# en vez de un eval-set.
#
# Cada una recibe la salida de la herramienta y devuelve (pasa, motivo).
# El motivo se guarda SIEMPRE, también cuando pasa: dentro de un mes querrás
# saber por qué aquella fila estaba verde.

def _texto(lista) -> str:
    """Aplana una lista de strings a un texto en minúsculas, para buscar dentro."""
    return " | ".join(str(x) for x in lista).lower()


def check_of_bug_alternativa_o(salida) -> tuple[bool, str]:
    imprescindibles = salida.get("imprescindibles", [])
    juntos = [x for x in imprescindibles if "gcp" in x.lower() and "aws" in x.lower()]
    aws_solo = [x for x in imprescindibles if "aws" in x.lower() and "gcp" not in x.lower()]
    if aws_solo:
        return False, f"partió la alternativa: {aws_solo!r} salió como requisito aparte"
    if not juntos:
        return False, f"no aparece la alternativa GCP/AWS en imprescindibles: {imprescindibles!r}"
    return True, f"la alternativa quedó como un solo requisito: {juntos[0]!r}"


def check_of_control_compuesto_y(salida) -> tuple[bool, str]:
    imprescindibles = salida.get("imprescindibles", [])
    def menciona(x, *claves):
        return any(k in x.lower() for k in claves)

    juntos = [x for x in imprescindibles if menciona(x, "llm") and menciona(x, "rag")]
    if juntos:
        return False, f"NO separó el compuesto con 'y': {juntos[0]!r} quedó como un solo requisito"

    hay_llm = any(menciona(x, "llm") for x in imprescindibles)
    hay_rag = any(menciona(x, "rag") for x in imprescindibles)
    if not (hay_llm and hay_rag):
        return False, f"se perdió una de las dos competencias: {imprescindibles!r}"
    return True, "separó 'APIs de LLMs y RAG' en dos requisitos independientes"


def check_cv_bug_cefr_b2(salida) -> tuple[bool, str]:
    faltan = salida.get("imprescindibles_que_faltan", [])
    culpables = [x for x in faltan if re.search(r"ingl[eé]s|english|b2", x.lower())]
    if culpables:
        return False, f"marcó el inglés como faltante teniendo C1: {culpables!r}"
    return True, f"no marcó el inglés como faltante (faltantes: {faltan!r})"


def check_cv_control_bloqueante_real(salida) -> tuple[bool, str]:
    faltan = salida.get("imprescindibles_que_faltan", [])
    if not any("kubernetes" in x.lower() for x in faltan):
        return False, (
            "NO avisó de un bloqueante real (Kubernetes no está en el CV) "
            f"— faltantes: {faltan!r}"
        )
    return True, "avisó del bloqueante real de Kubernetes"


# Un teléfono en la firma NO es numerología: el bug es usar cifras como ARGUMENTO
# ("más de dos años"), y una firma no argumenta nada. Los teléfonos se leen del CV
# en vez de copiarlos aquí: un dato personal vive en un sitio y solo uno.
_PATRON_TELEFONO = r"\+?\d[\d\s().\-]{7,}\d"


def _telefonos_del_cv() -> set[str]:
    """Los dígitos de los teléfonos que aparezcan en la cabecera del CV."""
    cabecera = _cargar_cv()[:600]
    return {re.sub(r"\D", "", t) for t in re.findall(_PATRON_TELEFONO, cabecera)}


TELEFONOS_CV = _telefonos_del_cv()


# Números escritos en letra. 'un'/'una' quedan fuera a propósito: son artículos
# ("un reporte"), no cifras. El bug real fue "más de dos años".
_NUMEROS_EN_LETRA = (
    r"\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|"
    r"quince|dieciséis|dieciseis|diecisiete|dieciocho|diecinueve|veinte|treinta|"
    r"cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|mil|millón|millones|"
    r"two|three|four|five|six|seven|eight|nine|ten)\b"
)


def check_carta_bug_numerologia(salida) -> tuple[bool, str]:
    cuerpo = salida.get("cuerpo", "")
    # Antes de barrer, quitamos lo que NO es numerología aunque lleve dígitos:
    #   1. el GPA, que es el único número permitido por el propio prompt;
    #   2. la firma (email y teléfono del CV), que no argumenta nada.
    limpio = cuerpo.replace("8.57", "").replace("8,57", "")
    limpio = re.sub(r"\S+@\S+\.\S+", " ", limpio)
    for trozo in re.findall(_PATRON_TELEFONO, limpio):
        if re.sub(r"\D", "", trozo) in TELEFONOS_CV:
            limpio = limpio.replace(trozo, " ")

    digitos = re.findall(r"\d+(?:[.,]\d+)?", limpio)
    letras = re.findall(_NUMEROS_EN_LETRA, limpio.lower())
    if digitos or letras:
        return False, f"se le colaron números — dígitos: {digitos!r} · en letra: {letras!r}"
    return True, "ni un número fuera del GPA"


def check_carta_control_sigue_siendo_carta(salida) -> tuple[bool, str]:
    asunto = (salida.get("asunto") or "").strip()
    cuerpo = (salida.get("cuerpo") or "").strip()
    notas = salida.get("notas") or []
    palabras = len(cuerpo.split())

    fallos = []
    if not asunto:
        fallos.append("asunto vacío")
    # DOS DIALES DISTINTOS (decisión de Denys, 21/07):
    #   · lo que PEDIMOS  → el prompt sigue exigiendo 130-180. No se toca: si le
    #     bajas la petición, el modelo recentra su puntería y aterriza más abajo.
    #   · lo que ACEPTAMOS → 125. Cerrar una frase con sentido no cuadra con un
    #     recuento exacto; forzar las últimas 5 palabras mete relleno y empeora la
    #     carta. Se perdona el roce gramatical, no el desmadre.
    # Verificado sobre las 13 corridas del historial (re-puntuadas sin llamar a la
    # API): con aceptación 125 la regresión de v2 marca 0.55/0.45 y sigue cayendo
    # muy por debajo de su listón 0.90. A partir de 115 sí quedaríamos ciegos.
    if not (125 <= palabras <= 180):
        fallos.append(f"{palabras} palabras (aceptamos 125-180; el prompt pide 130-180)")
    if not (2 <= len(notas) <= 3):
        fallos.append(f"{len(notas)} notas (el contrato dice 2-3)")

    if fallos:
        return False, "la carta se desvía: " + " · ".join(fallos)
    return True, f"carta íntegra: {palabras} palabras, {len(notas)} notas, asunto presente"


def check_of_bug_rango_python_o(salida) -> tuple[bool, str]:
    """'2 o 3 años o más' es redundante: equivale a '2 o más años'. ¿Lo ve?

    PASA si el analizador colapsa la redundancia (deja un mínimo de 2, SIN el '3'
    superfluo). FALLA si mantiene el '3' (no la vio) o si colapsa de más y pierde
    el mínimo de años (se le va la información).
    """
    imprescindibles = salida.get("imprescindibles", [])
    python_items = [x for x in imprescindibles if "python" in x.lower()]
    if len(python_items) != 1:
        return False, (
            f"esperaba UN requisito de Python; hay {len(python_items)}: "
            f"{python_items!r} (imprescindibles: {imprescindibles!r})"
        )
    item = python_items[0].lower()
    tiene_3 = bool(re.search(r"\b3\b|\btres\b", item))
    tiene_minimo = bool(re.search(r"\b2\b|\bdos\b|\+|m[aá]s|al menos|m[ií]nimo|mayor", item))
    if tiene_3:
        return False, f"NO vio la redundancia: mantuvo el '3' superfluo → {python_items[0]!r}"
    if not tiene_minimo:
        return False, f"colapsó de más y perdió el mínimo de años → {python_items[0]!r}"
    return True, f"vio la redundancia: quedó como mínimo de 2 sin el '3' → {python_items[0]!r}"


COMPROBACIONES = {
    "of_bug_alternativa_o": check_of_bug_alternativa_o,
    "of_control_compuesto_y": check_of_control_compuesto_y,
    "cv_bug_cefr_b2": check_cv_bug_cefr_b2,
    "cv_control_bloqueante_real": check_cv_control_bloqueante_real,
    "carta_bug_numerologia": check_carta_bug_numerologia,
    "carta_control_sigue_siendo_carta": check_carta_control_sigue_siendo_carta,
    # Corrida #12 · la prueba de la redundancia '2 o 3 años o más', dos bloques:
    "of_bug_rango_python_o": check_of_bug_rango_python_o,          # bloque analizar_oferta
    "carta_bug_rango_numerologia": check_carta_bug_numerologia,    # bloque redactar_borrador (check REUTILIZADO)
}


# ─────────────────────────────────────────────────────────────
# EL MOTOR
# ─────────────────────────────────────────────────────────────
def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def correr_caso(caso: dict, version: str, juez: bool = False) -> dict:
    """Corre UN caso N veces y devuelve su fila de resultado.

    Si `juez` está activo y la herramienta es redactar_borrador, cada carta pasa
    ADEMÁS por el juez de estilo (gpt-4o): puntúa lo cualitativo que los asserts
    no ven (arranque/voz/enganche). Cuesta una llamada extra por carta, por eso
    es opt-in: los asserts corren siempre, el juez solo cuando se pide.
    """
    herramienta = caso["herramienta"]
    funcion = DISPATCH[herramienta]
    comprobar = COMPROBACIONES[caso["id"]]
    repeticiones = caso.get("repeticiones", 1)

    juzgar_estilo = None
    if juez and herramienta == "redactar_borrador":
        from juez_estilo import juzgar_estilo  # perezoso: solo carga el juez si se pide

    intentos = []
    for _ in range(repeticiones):
        salida = funcion(**caso["entrada"])
        pasa, motivo = comprobar(salida)
        # La salida entera se guarda SIEMPRE, pase o falle: es la columna
        # "respuesta obtenida" de la tabla. Un veredicto sin la respuesta que
        # lo provocó no es trazabilidad, es una nota al pie.
        intento = {"pasa": pasa, "motivo": motivo, "salida": salida}
        if juzgar_estilo is not None:
            intento["juez"] = juzgar_estilo(salida.get("asunto", ""), salida.get("cuerpo", ""))
        intentos.append(intento)

    pasadas = sum(i["pasa"] for i in intentos)
    fila = {
        "id": caso["id"],
        "herramienta": herramienta,
        "tipo": caso["tipo"],
        "version_prompt": version,
        "hash_prompt": _huella(prompts.obtener(herramienta, version))[:12],
        "repeticiones": repeticiones,
        "pasadas": pasadas,
        "nota": round(pasadas / repeticiones, 3),
        "intentos": intentos,
    }
    # El juez es un EJE SEPARADO de pasa/falla: son notas 1-5, no un booleano.
    # Se guardan aparte para no mezclar dos escalas distintas en la misma columna.
    con_juez = [i["juez"] for i in intentos if "juez" in i]
    if con_juez:
        from juez_estilo import CRITERIOS
        fila["juez_medias"] = {
            c: round(sum(j[c]["score"] for j in con_juez) / len(con_juez), 2)
            for c in CRITERIOS
        }
    return fila


# ─────────────────────────────────────────────────────────────
# GUARDAR SIN PISARSE (el cerrojo)
# ─────────────────────────────────────────────────────────────
# Escribir en el historial son tres pasos —leer, añadir, escribir— y si dos
# evaluaciones corren a la vez, la segunda en escribir pisa la fila de la primera
# sin que salte ningún error. Es una carrera de datos. El cerrojo la cierra:
# mientras un proceso lo tiene, los demás esperan en flock().

@contextmanager
def _cerrojo(ruta: Path):
    """Exclusión mutua entre procesos sobre un fichero-candado aparte.

    flock() es consultivo: solo se respetan quienes lo piden, por eso TODO el que
    escriba el historial pasa por aquí. LOCK_EX bloquea hasta conseguirlo; al salir
    del `with` el fichero se cierra y el sistema suelta el cerrojo pase lo que pase.
    """
    with open(ruta, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _anadir_al_historial(corrida: dict) -> int:
    """Añade una corrida al historial de forma segura y devuelve el total.

    Dentro del cerrojo el leer-añadir-escribir es indivisible: ningún otro proceso
    puede colarse en medio. La escritura es atómica —a un .tmp y luego renombrado—
    para que un corte a media escritura no deje el JSON partido: o está la corrida
    entera o no está, nunca medio fichero.
    """
    with _cerrojo(RUTA_CERROJO):
        historial = []
        if RUTA_HISTORIAL.exists():
            historial = json.loads(RUTA_HISTORIAL.read_text(encoding="utf-8"))
        historial.append(corrida)                # SOLO se añade: nada se reescribe
        tmp = RUTA_HISTORIAL.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(historial, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        tmp.replace(RUTA_HISTORIAL)              # renombrado atómico
        return len(historial)


# ─────────────────────────────────────────────────────────────
# LA PUERTA (solo en --ci)
# ─────────────────────────────────────────────────────────────
# Un CI no lee tablas: lee el código de salida. 0 = pasa, ≠0 = bloquea.
# La puerta compara la corrida contra los listones de umbral.json.
#
# Por qué NO se exige igualdad exacta con el baseline: dos corridas de
# configuración IDÉNTICA ya dieron 0.833 y 0.9 (corridas #2 y #3). Ese hueco
# es RUIDO del modelo, no una regresión. Un listón exacto haría fallar el CI
# por azar, y un CI que falla por azar se acaba ignorando — que es la única
# forma de que un quality gate no sirva para nada.

def _puerta(corrida: dict) -> tuple[bool, list[str]]:
    """Devuelve (pasa, motivos). Los motivos explican SIEMPRE, pase o falle.

    Un listón POR CASO, no una media global: promediar casos deterministas con uno
    estocástico difumina la señal. Ver el razonamiento completo en umbral.json.
    """
    listones = json.loads(RUTA_UMBRAL.read_text(encoding="utf-8"))["listones"]
    motivos, pasa = [], True

    for f in corrida["resultados"]:
        if f["id"] not in listones:
            # Fail-closed: un caso nuevo no entra de tapadillo sin listón declarado.
            pasa = False
            motivos.append(f"✗ {f['id']}: sin listón en umbral.json — decláralo")
            continue
        liston = listones[f["id"]]
        if f["nota"] < liston:
            pasa = False
            motivos.append(f"✗ {f['id']}: {f['nota']} < {liston}  ({f['pasadas']}/{f['repeticiones']})")
        else:
            marca = "·" if liston == 0.0 else "✓"      # 0.0 = fuera de la puerta
            motivos.append(f"{marca} {f['id']}: {f['nota']} ≥ {liston}")

    return pasa, motivos


def main() -> None:
    p = argparse.ArgumentParser(description="Corre el eval-set y lo añade al historial.")
    p.add_argument("--nota",
                   help="QUÉ cambió respecto a la corrida anterior. Es la columna "
                        "'cambio aplicado' de la tabla: sin ella la fila no se explica. "
                        "Obligatoria salvo en --ci (una máquina no tiene nada que contar).")
    p.add_argument("--ci", action="store_true",
                   help="Modo máquina: NO escribe en el historial y sale con código 1 "
                        "si la corrida no pasa la puerta de umbral.json. El historial es "
                        "tu bitácora, escrita a mano; el CI no la ensucia.")
    p.add_argument("--version", action="append", default=[], metavar="HERR=vN",
                   help="Fuerza una versión (repetible). Por defecto, la activa.")
    p.add_argument("--seco", action="store_true",
                   help="No llama a la API ni escribe: solo enseña qué correría.")
    p.add_argument("--juez", action="store_true",
                   help="Además de los asserts, pasa cada carta por el juez de estilo "
                        "(gpt-4o): arranque/voz/enganche, 1-5. Cuesta una llamada extra "
                        "por carta; opt-in a propósito (asserts siempre, juez a demanda).")
    args = p.parse_args()
    # --nota justifica una FILA DEL HISTORIAL: es la columna "cambio aplicado".
    # Así que se exige exactamente cuando va a escribirse una fila, y no antes.
    # No la escriben: --ci (una máquina no cambió nada, solo vigila) ni --seco
    # (no llega a correr nada). Pedirla ahí es pedir que justifiques algo que no
    # va a pasar — y te obliga a colar un --ci que no viene a cuento.
    if not args.ci and not args.seco and not args.nota:
        p.error("--nota es obligatoria cuando la corrida va a escribir en el historial "
                "(no hace falta con --ci ni con --seco)")

    casos = json.loads(RUTA_CASOS.read_text(encoding="utf-8"))["casos"]

    # Qué versión usa cada herramienta en esta corrida.
    versiones = dict(prompts.VERSIONES_ACTIVAS)
    for par in args.version:
        herr, _, ver = par.partition("=")
        prompts.obtener(herr, ver)              # falla ya si no existe
        versiones[herr] = ver
        prompts.VERSIONES_ACTIVAS[herr] = ver   # para que herramientas.py la use

    llamadas = sum(c.get("repeticiones", 1) for c in casos)
    llamadas_juez = (sum(c.get("repeticiones", 1) for c in casos
                         if c["herramienta"] == "redactar_borrador") if args.juez else 0)
    print(f"modelo {MODELO} · {len(casos)} casos · {llamadas} llamadas a la API"
          + (f" + {llamadas_juez} al juez (gpt-4o)" if args.juez else ""))
    print("versiones: " + " · ".join(f"{k}={v}" for k, v in versiones.items()))
    if args.seco:
        for c in casos:
            print(f"  [{c['tipo']:7}] {c['id']:34} {c['herramienta']}")
        print("\n(corrida en seco: no se ha llamado a nada ni se ha escrito nada)")
        return

    filas = [correr_caso(c, versiones[c["herramienta"]], juez=args.juez) for c in casos]

    print()
    for f in filas:
        estado = "OK  " if f["nota"] == 1 else "FALLA"
        print(f"{estado} [{f['tipo']:7}] {f['id']:34} {f['pasadas']}/{f['repeticiones']}")
        # El motivo de cada intento cita la salida del modelo, y esa salida lleva
        # dentro el CV (la firma de una carta trae teléfono y email). En tu Mac eso
        # es diagnóstico; en un runner de GitHub es un log PÚBLICO. En modo máquina
        # se calla: la puerta ya imprime "caso: nota ≥ listón", que es lo único que
        # un CI necesita para decidir. Si una fila cae, la reproduces aquí sin --ci.
        if not args.ci:
            for i in f["intentos"]:
                print(f"        {'✓' if i['pasa'] else '✗'} {i['motivo']}")
        if "juez_medias" in f:
            jm = " · ".join(f"{c.split('_')[0]}={v}" for c, v in f["juez_medias"].items())
            print(f"        JUEZ (gpt-4o, 1-5): {jm}")

    bugs = [f for f in filas if f["tipo"] == "bug"]
    controles = [f for f in filas if f["tipo"] == "control"]
    def media(xs):
        return round(sum(x["nota"] for x in xs) / len(xs), 3) if xs else None

    corrida = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cambio": args.nota,
        "modelo": MODELO,
        "juez": args.juez,
        "versiones": versiones,
        "nota_bugs": media(bugs),
        "nota_controles": media(controles),
        "nota_global": media(filas),
        "resultados": filas,
    }

    print(f"\nbugs {corrida['nota_bugs']} · controles {corrida['nota_controles']} "
          f"· global {corrida['nota_global']}")

    if args.ci:
        # El historial es la bitácora de Denys: una fila por decisión suya, con su
        # nota. El CI corre en cada push y no decide nada, así que NO escribe.
        pasa, motivos = _puerta(corrida)
        print("\n── puerta de regresión ──")
        for m in motivos:
            print("  " + m)
        print("PASA ✅" if pasa else "BLOQUEA ❌")
        sys.exit(0 if pasa else 1)

    total = _anadir_al_historial(corrida)
    print(f"corrida #{total} añadida a {RUTA_HISTORIAL.name}")


if __name__ == "__main__":
    main()
