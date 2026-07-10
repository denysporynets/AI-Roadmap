"""
evaluar.py — EL BUCLE DE EVALUACIÓN del harness (Artefacto 3 · Fase 2)
======================================================================
Recorre el golden set (dataset_eval.json), interroga al RAG DOBE real
(MotorRAG.preguntar, del Artefacto 2, SIN tocarlo) y mide cuatro cosas:

  1. DECISIÓN DEL UMBRAL  ¿respondió cuando debía / se calló cuando debía?
                          (lo más importante: respondio  <=>  debe_responder)
  2. BANDA EXACTA         ¿la banda (claro/posible/lejano) coincide con la esperada?
                          (más fino; en los casos 'frontera' sirve para CALIBRAR)
  3. FAITHFULNESS         juez-LLM sobre las respuestas (¿inventa recuerdos?)
  4. RELEVANCIA           juez-LLM sobre las respuestas (¿responde a lo pedido?)
     + CITA               check barato: ¿la respuesta trae [#num ...] como exige el sistema?

Las trampas (T1, T2) deberían dar banda 'lejano' → el motor se calla → NI generan
NI gastan juez (gratis). Si una trampa responde, es un FALSO POSITIVO (alucinación).

Salidas (ambas BLINDADAS en .gitignore, derivan del corpus personal):
  · resultados.json     — datos por caso + agregados (para la Fase 3, comparar)
  · informe_eval.html   — informe legible a nuestro estilo

Coste: ~6 generaciones + ~12 llamadas de juez = céntimos. Las trampas no cuestan.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
A2 = BASE.parent / "2_RAG desplegado sobre el Corpus DOBE"   # donde vive el motor
sys.path.insert(0, str(A2))

from rag_core import MotorRAG                                  # noqa: E402
from eval_jueces import juez_faithfulness, juez_relevancia, _cliente  # noqa: E402

DATASET = BASE / "dataset_eval.json"

CITA_RE = re.compile(r"\[#\s*\d+")      # detecta citas tipo [#121 · pág]


def construir_contexto(motor: MotorRAG, fuentes: list[dict]) -> str:
    """Reconstruye el texto de los momentos citados (para el juez de faithfulness)."""
    bloques = []
    for f in fuentes:
        x = motor.corpus[f["num"]]
        bloques.append(
            f"--- MOMENTO #{f['num']} · {x['pages']} ---\n"
            f"DENYS PREGUNTÓ: {x['denys_texto']}\n"
            f"DEEP RESPONDIÓ: {x['ia_texto']}"
        )
    return "\n\n".join(bloques)


def evaluar(umbral_posible: float | None = None, sufijo: str = "") -> dict:
    """Evalúa el golden set. `umbral_posible` permite EXPERIMENTAR con otro corte
    sin tocar rag_core.py (override en memoria, reversible: solo este proceso).
    `sufijo` cambia el nombre de salida para no pisar la línea base."""
    import rag_core
    umbral_usado = rag_core.UMBRAL_POSIBLE
    if umbral_posible is not None:
        rag_core.UMBRAL_POSIBLE = umbral_posible      # override SOLO en este proceso
        umbral_usado = umbral_posible

    out_json = BASE / f"resultados{sufijo}.json"
    out_html = BASE / f"informe_eval{sufijo}.html"

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    casos = data["casos"]
    motor = MotorRAG()
    client = _cliente()

    resultados = []
    for c in casos:
        r = motor.preguntar(c["pregunta"])
        respondio = r["respuesta"] is not None
        debe = c["debe_responder"]
        calibrar = c.get("calibrar", False)

        fila = {
            "id": c["id"],
            "tipo": c["tipo"],
            "pregunta": c["pregunta"],
            "banda_esperada": c["banda_esperada"],
            "banda_real": r["banda"],
            "sim_top": r["sim_top"],
            "debe_responder": debe,
            "respondio": respondio,
            # decisión: ¿respondió/se calló como tocaba?  (el criterio que de verdad importa)
            "decision_ok": (respondio == debe),
            # banda exacta: fino; en 'frontera' es info de calibración, no un fallo
            "banda_exacta_ok": (r["banda"] == c["banda_esperada"]),
            "calibrar": calibrar,
            "respuesta": r["respuesta"],
            "fuentes": r["fuentes"],
        }

        if respondio:
            contexto = construir_contexto(motor, r["fuentes"])
            fila["faithfulness"] = juez_faithfulness(c["pregunta"], contexto, r["respuesta"], client)
            fila["relevancia"] = juez_relevancia(c["pregunta"], r["respuesta"], client)
            fila["cita_ok"] = bool(CITA_RE.search(r["respuesta"]))
        else:
            # se calló: el "acierto" es haberse callado cuando debía
            fila["faithfulness"] = None
            fila["relevancia"] = None
            fila["cita_ok"] = None

        resultados.append(fila)
        print(f"  {c['id']:3} {c['tipo']:9} banda={r['banda']:8} "
              f"{'respondió' if respondio else 'se calló':10} "
              f"decisión={'OK' if fila['decision_ok'] else 'FALLO'}")

    agg = agregar(resultados)
    salida = {
        "meta": {"fecha": str(date.today()), "n_casos": len(resultados),
                 "motor": "MotorRAG (gpt-4o-mini)", "juez": "gpt-4o",
                 "umbral_posible": umbral_usado},
        "agregados": agg,
        "casos": resultados,
    }
    out_json.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_informe(salida, out_html)
    return salida


def agregar(res: list[dict]) -> dict:
    respondidos = [r for r in res if r["respondio"]]
    faiths = [r["faithfulness"]["score"] for r in respondidos]
    relevs = [r["relevancia"]["score"] for r in respondidos]
    citas = [r["cita_ok"] for r in respondidos]
    # banda exacta solo cuenta en los casos NO marcados para calibrar
    fijos = [r for r in res if not r["calibrar"]]
    return {
        "decision_acierto": round(sum(r["decision_ok"] for r in res) / len(res), 3),
        "banda_exacta_acierto": round(sum(r["banda_exacta_ok"] for r in fijos) / len(fijos), 3) if fijos else None,
        "faithfulness_media": round(sum(faiths) / len(faiths), 2) if faiths else None,
        "relevancia_media": round(sum(relevs) / len(relevs), 2) if relevs else None,
        "citas_pct": round(sum(citas) / len(citas), 2) if citas else None,
        "n_respondidos": len(respondidos),
        "n_callados": len(res) - len(respondidos),
    }


# ── informe HTML (a nuestro estilo: fondo claro, brillo, scroll-reveal, barras) ──
def escribir_informe(s: dict, out_html: Path) -> None:
    a = s["agregados"]

    def banda_emoji(b):
        return {"claro": "🟢", "posible": "🟡", "lejano": "⚪"}.get(b, "?")

    def barra(score):
        if score is None:
            return '<span style="color:#7a766c">—</span>'
        cls = "hi" if score >= 4 else ("mid" if score == 3 else "lo")
        return (f'<span class="num {cls}">{score}/5</span>'
                f'<div class="bar"><i class="{cls}" style="--w:{score/5*100:.0f}%"></i></div>')

    filas = []
    for r in s["casos"]:
        f = r["faithfulness"]["score"] if r["faithfulness"] else None
        rel = r["relevancia"]["score"] if r["relevancia"] else None
        fr = r["faithfulness"]["reason"] if r["faithfulness"] else ""
        rr = r["relevancia"]["reason"] if r["relevancia"] else ""
        deco = "ok" if r["decision_ok"] else "no"
        cal = ' <span class="cal">calibrar</span>' if r["calibrar"] else ""
        resp = r["respuesta"] or "<i>(se calló — sin recuerdo claro)</i>"
        cita = "✓" if r["cita_ok"] else ("—" if r["cita_ok"] is None else "✗")
        filas.append(f"""
<div class="pcard reveal">
  <div class="head">
    <span>{r['id']} · {r['tipo']}{cal}</span>
    <span class="dec {deco}">{'decisión OK' if r['decision_ok'] else 'decisión FALLO'}</span>
  </div>
  <div class="body">
    <div class="row"><span class="lab2">pregunta</span> {r['pregunta']}</div>
    <div class="row"><span class="lab2">banda</span> {banda_emoji(r['banda_real'])} {r['banda_real']}
      (sim {r['sim_top']}) · esperada: {banda_emoji(r['banda_esperada'])} {r['banda_esperada']}</div>
    <div class="row"><span class="lab2">respuesta</span> {resp}</div>
    <div class="row"><span class="lab2">cita fuentes</span> {cita}</div>
    <div class="score">{barra(f)}<span class="lab2">faithfulness</span></div>
    {f'<div class="quote">{fr}</div>' if fr else ''}
    <div class="score">{barra(rel)}<span class="lab2">relevancia</span></div>
    {f'<div class="quote">{rr}</div>' if rr else ''}
  </div>
</div>""")

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informe de evaluación · RAG DOBE · {s['meta']['fecha']}</title>
<style>
  :root {{ --bg:#f5f3ee; --card:#fff; --txt:#24292f; --dim:#6b6b6b; --line:#e2e0d9;
          --azul:#2c6eb5; --verde:#3a7d44; --ambar:#b07d2b; --rojo:#b0392b; }}
  html {{ transition:filter .35s ease; }}
  body {{ background:var(--bg); color:var(--txt); margin:0 auto; padding:32px; max-width:880px;
         font-family:'DM Sans',-apple-system,system-ui,sans-serif; line-height:1.6; }}
  .kicker {{ font-family:'DM Mono',monospace; font-size:12px; color:var(--azul); text-transform:uppercase; letter-spacing:.08em; }}
  h1 {{ font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:28px; margin:2px 0 4px; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:18px; }}
  h2 {{ font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:20px; margin:30px 0 8px;
        padding-top:14px; border-top:2px solid var(--line); }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:14px 0; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
  .kpi .v {{ font-family:'Fraunces',serif; font-weight:600; font-size:26px; color:var(--verde); }}
  .kpi .k {{ font-family:'DM Mono',monospace; font-size:11px; color:var(--dim); text-transform:uppercase; }}
  .pcard {{ background:var(--card); border:1px solid var(--line); border-radius:13px; overflow:hidden;
            margin:13px 0; transition:transform .25s ease, box-shadow .25s ease; }}
  .pcard:hover {{ transform:translateY(-3px); box-shadow:0 8px 22px rgba(0,0,0,.09); }}
  .head {{ padding:10px 16px; background:#2b2f37; color:#fff; font-family:'DM Mono',monospace; font-size:12px;
           display:flex; justify-content:space-between; align-items:center; }}
  .dec.ok {{ color:#9fe0a8; }} .dec.no {{ color:#f0a89c; }}
  .cal {{ font-size:10px; background:#fbf3e3; color:#b07d2b; padding:1px 7px; border-radius:20px; }}
  .body {{ padding:13px 16px; }}
  .row {{ font-size:13.5px; margin:5px 0; }}
  .lab2 {{ font-family:'DM Mono',monospace; font-size:11px; color:var(--dim); text-transform:uppercase; margin-right:6px; }}
  .quote {{ background:#f7f5f0; border-left:3px solid var(--line); border-radius:0 6px 6px 0; padding:7px 12px;
            font-size:13px; margin:3px 0 8px; font-style:italic; color:#444; }}
  .score {{ display:flex; align-items:center; gap:10px; margin:8px 0 1px; }}
  .num {{ font-family:'Fraunces',serif; font-weight:600; font-size:17px; width:40px; }}
  .num.hi {{ color:var(--verde); }} .num.mid {{ color:var(--ambar); }} .num.lo {{ color:var(--rojo); }}
  .bar {{ flex:1; height:9px; background:#ece9e1; border-radius:6px; overflow:hidden; }}
  .bar i {{ display:block; height:100%; width:0; border-radius:6px; transition:width 1.1s cubic-bezier(.2,.8,.2,1); }}
  .bar i.hi {{ background:linear-gradient(90deg,#5aa86a,var(--verde)); }}
  .bar i.mid {{ background:linear-gradient(90deg,#d8a657,var(--ambar)); }}
  .bar i.lo {{ background:linear-gradient(90deg,#cf6a5c,var(--rojo)); }}
  .visible .bar i {{ width:var(--w); }}
  .reveal {{ opacity:0; transform:translateY(20px); transition:opacity .6s ease, transform .6s ease; }}
  .reveal.visible {{ opacity:1; transform:none; }}
  .foot {{ color:var(--dim); font-size:11.5px; margin-top:30px; font-family:'DM Mono',monospace;
           border-top:1px solid var(--line); padding-top:12px; }}
  #brillo {{ position:fixed; top:14px; right:14px; display:flex; align-items:center; gap:7px;
            background:rgba(255,255,255,.82); border:1px solid var(--line); border-radius:20px;
            padding:6px 12px; font-size:13px; box-shadow:0 1px 4px rgba(0,0,0,.08); z-index:50; }}
  #brillo input {{ width:90px; accent-color:var(--ambar); }}
  @media (prefers-reduced-motion: reduce) {{ .reveal{{opacity:1;transform:none}} .bar i{{transition:none}} }}
</style></head><body>
<div id="brillo" title="Brillo: día → noche cálida (filtra luz azul)">☀️<input id="lux" type="range" min="0" max="100" value="0">🌙</div>

<div class="kicker">Informe de evaluación · harness</div>
<h1>Cómo respondió el RAG DOBE</h1>
<div class="sub mono">{s['meta']['n_casos']} casos · motor {s['meta']['motor']} · juez {s['meta']['juez']} · umbral_posible={s['meta']['umbral_posible']} · {s['meta']['fecha']} · BLINDADO (no se publica)</div>

<h2>Resumen</h2>
<div class="kpis reveal">
  <div class="kpi"><div class="v">{a['decision_acierto']*100:.0f}%</div><div class="k">decisión correcta<br>(responder/callarse)</div></div>
  <div class="kpi"><div class="v">{a['faithfulness_media'] if a['faithfulness_media'] is not None else '—'}</div><div class="k">faithfulness media<br>(sobre 5)</div></div>
  <div class="kpi"><div class="v">{a['relevancia_media'] if a['relevancia_media'] is not None else '—'}</div><div class="k">relevancia media<br>(sobre 5)</div></div>
  <div class="kpi"><div class="v">{int(a['citas_pct']*100) if a['citas_pct'] is not None else '—'}%</div><div class="k">respuestas<br>con cita</div></div>
  <div class="kpi"><div class="v">{a['n_callados']}</div><div class="k">se calló<br>(de {s['meta']['n_casos']})</div></div>
</div>

<h2>Caso por caso</h2>
{''.join(filas)}

<div class="foot">informe generado por evaluar.py · harness de evaluación (artefacto 3, fase 2) · fichero blindado en .gitignore ·
agregados → línea base de la fase 3 (detección de regresiones) · técnicas: scroll-reveal · barras animadas</div>

<script>
  (function(){{var l=document.getElementById('lux');function a(v){{document.documentElement.style.filter='brightness('+(1-v*0.0028)+') sepia('+(v*0.0055)+')';}}
    var g=localStorage.getItem('ficha-brillo'); if(g!==null)l.value=g; a(+l.value);
    l.addEventListener('input',function(){{a(+l.value);localStorage.setItem('ficha-brillo',l.value);}});}})();
  (function(){{var io=new IntersectionObserver(function(es){{es.forEach(function(e){{if(e.isIntersecting){{e.target.classList.add('visible');io.unobserve(e.target);}}}});}},{{threshold:0.12}});
    document.querySelectorAll('.reveal').forEach(function(el){{io.observe(el);}});}})();
</script>
</body></html>"""
    out_html.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    # Uso:  python evaluar.py                  → corte por defecto (rag_core)
    #       python evaluar.py 0.43 _u043       → experimento con corte 0.43, salida con sufijo
    umbral = float(sys.argv[1]) if len(sys.argv) > 1 else None
    sufijo = sys.argv[2] if len(sys.argv) > 2 else ""
    cabecera = f" (umbral_posible={umbral})" if umbral else ""
    print(f"== Evaluando el RAG DOBE sobre el golden set{cabecera} ==")
    s = evaluar(umbral_posible=umbral, sufijo=sufijo)
    a = s["agregados"]
    print("\n== AGREGADOS ==")
    print(f"  decisión correcta (responder/callarse): {a['decision_acierto']*100:.0f}%")
    print(f"  banda exacta (casos no-calibrar):       {a['banda_exacta_acierto']}")
    print(f"  faithfulness media: {a['faithfulness_media']}   relevancia media: {a['relevancia_media']}")
    print(f"  citas: {a['citas_pct']}   respondidos: {a['n_respondidos']}   callados: {a['n_callados']}")
    print(f"\n  → resultados{sufijo}.json e informe_eval{sufijo}.html escritos (blindados).")
