"""
comparar.py — DETECCIÓN DE REGRESIONES del harness (Artefacto 3 · Fase 3)
========================================================================
Aquí el conjunto de scripts deja de ser "una evaluación suelta" y se convierte
en un HARNESS de verdad: algo que recuerda cómo iba antes y AVISA si una versión
nueva empeora. Esa memoria es la LÍNEA BASE (baseline.json), la foto buena que
congelamos como referencia.

Idea (igual que un test de regresión de software, pero para calidad de un RAG):
  · Congelas una versión que funciona  →  baseline.json
  · Cada vez que cambias algo (umbral, prompt, modelo…) vuelves a evaluar
  · El comparador mide candidato vs. base y dicta veredicto

Lo que vigila, de más grave a menos:

  🔴 REGRESIÓN DURA  (rompe el "build" → exit code 1, lo que la Fase 4 usará en CI)
     · un caso cuya DECISIÓN se rompe: lo peor es un NUEVO FALSO POSITIVO
       (responder algo ausente del corpus = alucinación que antes no pasaba).
       También un nuevo falso negativo (callarse teniendo recuerdo claro).
     · faithfulness media o relevancia media caen más que la tolerancia (0.3).

  🟡 AVISO  (no rompe el build, pero se reporta)
     · cae el % de respuestas con cita, o la banda exacta.
     · un caso suelto pierde ≥2 puntos de score aunque la media aguante.

  🟢 MEJORA  (informativo: también queremos saber qué subió)

Por qué "decisión rota" pesa más que las medias: en TU sistema lo distintivo es
que sabe callarse (banda ⚪ → no llama al LLM). Una media de faithfulness alta no
sirve de nada si de repente el motor empieza a inventarse recuerdos ausentes.
Por eso un falso positivo es regresión dura aunque las medias suban.

Modos de uso:
  python comparar.py fijar            → promueve resultados.json a baseline.json
  python comparar.py fijar <a.json>   → promueve ese archivo a baseline.json
  python comparar.py                  → compara resultados.json vs baseline.json
  python comparar.py <a.json>         → compara ese archivo vs baseline.json

Salidas (BLINDADAS en .gitignore, derivan del corpus):
  · comparacion.json   — el diff máquina (para la Fase 4 / CI)
  · comparacion.html   — el diff legible a nuestro estilo
Exit code: 0 si NO hay regresiones duras, 1 si las hay (la futura puerta CI/CD).

No gasta API: solo lee dos JSON ya producidos por evaluar.py.
"""

import json
import shutil
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
BASELINE = BASE / "baseline.json"
RESULTADOS = BASE / "resultados.json"
OUT_JSON = BASE / "comparacion.json"
OUT_HTML = BASE / "comparacion.html"

# ── Tolerancias (la "sensibilidad" del harness; explícitas para poder calibrarlas) ──
TOL_SCORE = 0.3      # caída admisible de faithfulness/relevancia media (sobre 5)
TOL_PCT = 0.15       # caída admisible de % citas / banda exacta antes de avisar
CAIDA_CASO = 2       # caída de score en UN caso que merece aviso (sobre 5)

EMOJI = {"claro": "🟢", "posible": "🟡", "lejano": "⚪"}


def cargar(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def por_id(salida: dict) -> dict:
    return {c["id"]: c for c in salida["casos"]}


def _score(caso: dict, metrica: str):
    """Saca el score 1-5 de un caso para 'faithfulness'/'relevancia' (o None si se calló)."""
    v = caso.get(metrica)
    return v["score"] if v else None


# ── EL COMPARADOR ───────────────────────────────────────────────────────────────
def comparar(base: dict, cand: dict) -> dict:
    bidx, cidx = por_id(base), por_id(cand)
    comunes = [i for i in cidx if i in bidx]
    nuevos = [i for i in cidx if i not in bidx]
    perdidos = [i for i in bidx if i not in cidx]

    regresiones: list[str] = []
    avisos: list[str] = []
    mejoras: list[str] = []

    # 1) DECISIÓN por caso (lo más crítico): ¿se rompió responder/callarse?
    for i in comunes:
        b, c = bidx[i], cidx[i]
        if b["decision_ok"] and not c["decision_ok"]:
            if not c["debe_responder"] and c["respondio"]:
                regresiones.append(
                    f"{i} ({c['tipo']}) · FALSO POSITIVO nuevo: respondió a algo "
                    f"que NO debía (posible alucinación). banda {EMOJI.get(c['banda_real'],'?')} "
                    f"{c['banda_real']} sim {c['sim_top']}")
            else:
                regresiones.append(
                    f"{i} ({c['tipo']}) · FALSO NEGATIVO nuevo: se calló teniendo "
                    f"que responder. banda {EMOJI.get(c['banda_real'],'?')} {c['banda_real']} "
                    f"sim {c['sim_top']}")
        elif not b["decision_ok"] and c["decision_ok"]:
            mejoras.append(f"{i} ({c['tipo']}) · decisión ARREGLADA (antes fallaba)")

    # 2) MEDIAS de calidad (agregado): caída más allá de la tolerancia = regresión dura
    ab, ac = base["agregados"], cand["agregados"]
    for clave, etiq in [("faithfulness_media", "faithfulness media"),
                        ("relevancia_media", "relevancia media")]:
        vb, vc = ab.get(clave), ac.get(clave)
        if vb is not None and vc is not None:
            d = round(vc - vb, 2)
            if d <= -TOL_SCORE:
                regresiones.append(f"{etiq} cayó {vb} → {vc} (Δ{d:+}, tolerancia {TOL_SCORE})")
            elif d >= TOL_SCORE:
                mejoras.append(f"{etiq} subió {vb} → {vc} (Δ{d:+})")

    # 3) % CITAS y BANDA EXACTA (agregado): caída = aviso (no rompe el build)
    for clave, etiq in [("citas_pct", "% respuestas con cita"),
                        ("banda_exacta_acierto", "banda exacta")]:
        vb, vc = ab.get(clave), ac.get(clave)
        if vb is not None and vc is not None:
            d = round(vc - vb, 3)
            if d <= -TOL_PCT:
                avisos.append(f"{etiq} bajó {vb} → {vc} (Δ{d:+}, aviso desde {TOL_PCT})")
            elif d > 0:
                mejoras.append(f"{etiq} subió {vb} → {vc} (Δ{d:+})")

    # 4) SCORE por caso (fino): un caso suelto que pierde ≥2 puntos aunque la media aguante
    for i in comunes:
        for metrica in ("faithfulness", "relevancia"):
            sb, sc = _score(bidx[i], metrica), _score(cidx[i], metrica)
            if sb is not None and sc is not None and sc - sb <= -CAIDA_CASO:
                avisos.append(f"{i} · {metrica} cayó {sb} → {sc} en este caso (Δ{sc-sb:+})")

    # 5) cambios de tamaño del dataset (info)
    for i in nuevos:
        avisos.append(f"{i} · caso NUEVO en el dataset (no estaba en la base)")
    for i in perdidos:
        avisos.append(f"{i} · caso DESAPARECIDO respecto a la base")

    veredicto = ("REGRESION" if regresiones
                 else "ESTABLE_CON_AVISOS" if avisos
                 else "OK")

    # deltas de agregados para la tabla del informe
    deltas = {}
    for clave in ("decision_acierto", "banda_exacta_acierto", "faithfulness_media",
                  "relevancia_media", "citas_pct"):
        vb, vc = ab.get(clave), ac.get(clave)
        deltas[clave] = {"base": vb, "cand": vc,
                         "delta": (round(vc - vb, 3) if vb is not None and vc is not None else None)}

    return {
        "meta": {
            "fecha": str(date.today()),
            "base": {"fecha": base["meta"]["fecha"], "umbral_posible": base["meta"].get("umbral_posible")},
            "cand": {"fecha": cand["meta"]["fecha"], "umbral_posible": cand["meta"].get("umbral_posible")},
            "tolerancias": {"score": TOL_SCORE, "pct": TOL_PCT, "caida_caso": CAIDA_CASO},
        },
        "veredicto": veredicto,
        "regresiones": regresiones,
        "avisos": avisos,
        "mejoras": mejoras,
        "deltas": deltas,
    }


def fijar_baseline(origen: Path) -> None:
    if not origen.exists():
        sys.exit(f"✗ No existe {origen.name}. Corre antes:  python evaluar.py")
    shutil.copyfile(origen, BASELINE)
    s = cargar(BASELINE)
    print(f"✓ Línea base fijada desde {origen.name} → baseline.json")
    print(f"  ({s['meta']['n_casos']} casos · umbral_posible={s['meta'].get('umbral_posible')} "
          f"· decisión {s['agregados']['decision_acierto']*100:.0f}% · {s['meta']['fecha']})")
    print("  baseline.json está BLINDADO en .gitignore (deriva del corpus).")


# ── informe HTML (a nuestro estilo: claro, brillo, scroll-reveal) ────────────────
def escribir_informe(d: dict) -> None:
    v = d["veredicto"]
    banner = {
        "OK": ("✅", "#3a7d44", "#eef5ee", "Sin regresiones",
               "El candidato mantiene o mejora la calidad de la línea base."),
        "ESTABLE_CON_AVISOS": ("🟡", "#b07d2b", "#fbf3e3", "Estable, con avisos",
               "Ninguna regresión dura, pero hay detalles a vigilar (no rompen el build)."),
        "REGRESION": ("❌", "#b0392b", "#fbf1ee", "Regresión detectada",
               "El candidato empeora respecto a la base. En CI esto bloquearía el deploy."),
    }[v]

    def lista(items, css):
        if not items:
            return '<div class="vacio">— ninguno —</div>'
        return "".join(f'<li class="{css}">{x}</li>' for x in items)

    def fmt(x, clave):
        if x is None:
            return "—"
        return f"{x*100:.0f}%" if clave != "faithfulness_media" and clave != "relevancia_media" else f"{x}"

    fdeltas = []
    nombres = {"decision_acierto": "decisión correcta", "banda_exacta_acierto": "banda exacta",
               "faithfulness_media": "faithfulness media", "relevancia_media": "relevancia media",
               "citas_pct": "% con cita"}
    for clave, nom in nombres.items():
        dd = d["deltas"].get(clave, {})
        b, c, delta = dd.get("base"), dd.get("cand"), dd.get("delta")
        if delta is None:
            flecha, color = "—", "#6b6b6b"
        elif delta > 0:
            flecha, color = f"▲ {delta:+}", "#3a7d44"
        elif delta < 0:
            flecha, color = f"▼ {delta:+}", "#b0392b"
        else:
            flecha, color = "= 0", "#6b6b6b"
        fdeltas.append(f"""<tr><td>{nom}</td><td>{fmt(b,clave)}</td><td>{fmt(c,clave)}</td>
          <td style="color:{color};font-weight:600">{flecha}</td></tr>""")

    m = d["meta"]
    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparación · línea base vs candidato · {m['fecha']}</title>
<style>
  :root {{ --bg:#f5f3ee; --card:#fff; --txt:#24292f; --dim:#6b6b6b; --line:#e2e0d9;
          --azul:#2c6eb5; --verde:#3a7d44; --ambar:#b07d2b; --rojo:#b0392b; }}
  html {{ transition:filter .35s ease; }}
  body {{ background:var(--bg); color:var(--txt); margin:0 auto; padding:32px; max-width:820px;
         font-family:'DM Sans',-apple-system,system-ui,sans-serif; line-height:1.6; }}
  .kicker {{ font-family:'DM Mono',monospace; font-size:12px; color:var(--azul); text-transform:uppercase; letter-spacing:.08em; }}
  h1 {{ font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:28px; margin:2px 0 4px; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:18px; }}
  h2 {{ font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:20px; margin:28px 0 8px;
        padding-top:14px; border-top:2px solid var(--line); }}
  .banner {{ border-radius:14px; padding:18px 22px; margin:14px 0; border:1px solid var(--line);
             display:flex; align-items:center; gap:16px; }}
  .banner .ico {{ font-size:38px; }}
  .banner .t {{ font-family:'Fraunces',serif; font-weight:600; font-size:22px; }}
  .banner .d {{ font-size:13.5px; color:#444; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; margin:8px 0; }}
  th,td {{ border:1px solid var(--line); padding:9px 12px; text-align:left; }}
  th {{ background:#ece9e1; font-weight:600; font-family:'DM Mono',monospace; font-size:12px; text-transform:uppercase; }}
  ul {{ list-style:none; padding:0; margin:6px 0; }}
  li {{ border-radius:9px; padding:10px 14px; margin:7px 0; font-size:13.5px; border:1px solid var(--line); }}
  li.reg {{ background:#fbf1ee; border-left:4px solid var(--rojo); }}
  li.avi {{ background:#fbf3e3; border-left:4px solid var(--ambar); }}
  li.mej {{ background:#f3f8f3; border-left:4px solid var(--verde); }}
  .vacio {{ color:var(--dim); font-size:13px; font-style:italic; padding:4px 0; }}
  .reveal {{ opacity:0; transform:translateY(18px); transition:opacity .6s ease, transform .6s ease; }}
  .reveal.visible {{ opacity:1; transform:none; }}
  .foot {{ color:var(--dim); font-size:11.5px; margin-top:30px; font-family:'DM Mono',monospace;
           border-top:1px solid var(--line); padding-top:12px; }}
  #brillo {{ position:fixed; top:14px; right:14px; display:flex; align-items:center; gap:7px;
            background:rgba(255,255,255,.82); border:1px solid var(--line); border-radius:20px;
            padding:6px 12px; font-size:13px; box-shadow:0 1px 4px rgba(0,0,0,.08); z-index:50; }}
  #brillo input {{ width:90px; accent-color:var(--ambar); }}
  @media (prefers-reduced-motion: reduce) {{ .reveal{{opacity:1;transform:none}} }}
</style></head><body>
<div id="brillo" title="Brillo: día → noche cálida (filtra luz azul)">☀️<input id="lux" type="range" min="0" max="100" value="0">🌙</div>

<div class="kicker">Harness · detección de regresiones · fase 3</div>
<h1>Línea base vs. candidato</h1>
<div class="sub">base: umbral={m['base']['umbral_posible']} ({m['base']['fecha']}) ·
  candidato: umbral={m['cand']['umbral_posible']} ({m['cand']['fecha']}) ·
  tolerancias: score ±{m['tolerancias']['score']}, pct ±{m['tolerancias']['pct']} · BLINDADO (no se publica)</div>

<div class="banner reveal" style="background:{banner[2]};border-color:{banner[1]}">
  <div class="ico">{banner[0]}</div>
  <div><div class="t" style="color:{banner[1]}">{banner[3]}</div><div class="d">{banner[4]}</div></div>
</div>

<h2>Métricas: base → candidato</h2>
<table class="reveal">
  <tr><th>métrica</th><th>base</th><th>candidato</th><th>Δ</th></tr>
  {''.join(fdeltas)}
</table>

<h2>🔴 Regresiones duras <span style="font-weight:400;font-size:13px;color:#6b6b6b">(rompen el build)</span></h2>
<ul class="reveal">{lista(d['regresiones'],'reg')}</ul>

<h2>🟡 Avisos <span style="font-weight:400;font-size:13px;color:#6b6b6b">(no rompen el build)</span></h2>
<ul class="reveal">{lista(d['avisos'],'avi')}</ul>

<h2>🟢 Mejoras</h2>
<ul class="reveal">{lista(d['mejoras'],'mej')}</ul>

<div class="foot">comparacion.html · harness de evaluación (artefacto 3, fase 3) · fichero blindado ·
  veredicto={v} · exit code {'1' if d['regresiones'] else '0'} → la Fase 4 (pytest/CI) usará este código
  como puerta de calidad · técnicas: scroll-reveal</div>

<script>
  (function(){{var l=document.getElementById('lux');function a(v){{document.documentElement.style.filter='brightness('+(1-v*0.0028)+') sepia('+(v*0.0055)+')';}}
    var g=localStorage.getItem('ficha-brillo'); if(g!==null)l.value=g; a(+l.value);
    l.addEventListener('input',function(){{a(+l.value);localStorage.setItem('ficha-brillo',l.value);}});}})();
  (function(){{var io=new IntersectionObserver(function(es){{es.forEach(function(e){{if(e.isIntersecting){{e.target.classList.add('visible');io.unobserve(e.target);}}}});}},{{threshold:0.12}});
    document.querySelectorAll('.reveal').forEach(function(el){{io.observe(el);}});}})();
</script>
</body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")


def main() -> None:
    args = sys.argv[1:]

    # modo FIJAR
    if args and args[0] == "fijar":
        origen = Path(args[1]) if len(args) > 1 else RESULTADOS
        if not origen.is_absolute():
            origen = BASE / origen
        fijar_baseline(origen)
        return

    # modo COMPARAR
    if not BASELINE.exists():
        sys.exit("✗ No hay línea base todavía. Crea una con:\n"
                 "    python comparar.py fijar\n"
                 "  (promueve resultados.json a baseline.json)")

    cand_path = Path(args[0]) if args else RESULTADOS
    if not cand_path.is_absolute():
        cand_path = BASE / cand_path
    if not cand_path.exists():
        sys.exit(f"✗ No existe el candidato {cand_path.name}. Corre antes:  python evaluar.py")

    base, cand = cargar(BASELINE), cargar(cand_path)
    d = comparar(base, cand)
    OUT_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_informe(d)

    # informe en consola
    print(f"== COMPARACIÓN  base(umbral={d['meta']['base']['umbral_posible']}) "
          f"vs candidato(umbral={d['meta']['cand']['umbral_posible']}) ==\n")
    for clave, nom in [("decision_acierto", "decisión"), ("faithfulness_media", "faithfulness"),
                       ("relevancia_media", "relevancia"), ("citas_pct", "citas")]:
        dd = d["deltas"][clave]
        if dd["delta"] is not None:
            print(f"  {nom:12} {dd['base']} → {dd['cand']}  (Δ{dd['delta']:+})")
    print()
    if d["regresiones"]:
        print("  🔴 REGRESIONES:")
        for x in d["regresiones"]:
            print(f"     · {x}")
    if d["avisos"]:
        print("  🟡 AVISOS:")
        for x in d["avisos"]:
            print(f"     · {x}")
    if d["mejoras"]:
        print("  🟢 MEJORAS:")
        for x in d["mejoras"]:
            print(f"     · {x}")

    print(f"\n  VEREDICTO: {d['veredicto']}")
    print("  → comparacion.json y comparacion.html escritos (blindados).")
    sys.exit(1 if d["regresiones"] else 0)


if __name__ == "__main__":
    main()
