"""
Artefacto 5 · Fase 2 · EL ESPEJO DEL HISTORIAL

Lee historial.json y pinta historial.html: la tabla de trazabilidad y la gráfica
de evolución. Es el paso barato del patrón (ficha 04):

  evaluar_prompts.py  ──►  historial.json  ──►  render_historial.py
  ● CUESTA API             ▲ FUENTE DE VERDAD     ○ GRATIS, no llama a nada

Regla de oro: aquí NO se escribe ningún dato a mano. Cada fila de la tabla y cada
punto de la gráfica sale de una corrida real del JSON. Si una fila no tiene una
corrida detrás, no existe. El informe no puede decir nada que la báscula no midiera.

Uso:
    python evaluacion/render_historial.py
    # abre evaluacion/historial.html
"""

import json
from pathlib import Path
from datetime import datetime

AQUI = Path(__file__).parent
RUTA_HISTORIAL = AQUI / "historial.json"
RUTA_SALIDA = AQUI / "historial.html"

# Suelo de ruido de la báscula. NO es un número inventado: sale del par de corridas
# #2/#3, que tenían configuración IDÉNTICA y aun así dieron 0.833 y 0.9. Ese 0.067
# es lo que se mueve la nota SIN que cambies nada. Una diferencia menor que esto no
# es una mejora ni un empeoramiento: es azar. El informe lo dice en voz alta.
RUIDO = 0.07

# (clave en el JSON, etiqueta, color validado para las 3 series — ver dataviz)
SERIES = [
    ("nota_bugs", "bugs", "#c2410c"),
    ("nota_controles", "controles", "#0369a1"),
    ("nota_global", "global", "#6d28d9"),
]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _fecha_corta(iso: str) -> str:
    """'2026-07-16T19:38:15+00:00' → '16 jul · 19:38'."""
    MESES = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]
    d = datetime.fromisoformat(iso)
    return f"{d.day} {MESES[d.month - 1]} · {d.hour:02d}:{d.minute:02d}"


def _esc(t) -> str:
    """Escapa lo mínimo para meter texto del JSON en HTML sin romperlo."""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _versiones_compactas(corrida: dict) -> str:
    """{'analizar_oferta':'v1',...} → 'v1' si todas coinciden, si no el detalle."""
    vs = corrida.get("versiones", {})
    if not vs:
        return "—"
    unicas = set(vs.values())
    if len(unicas) == 1:
        return f"todas {unicas.pop()}"
    return " · ".join(f"{k.split('_')[0]}={v}" for k, v in vs.items())


# ─────────────────────────────────────────────────────────────
# LA GRÁFICA (SVG a mano, sin librerías)
# ─────────────────────────────────────────────────────────────
def svg_evolucion(historial: list) -> str:
    W, H = 760, 340
    ML, MR, MT, MB = 46, 96, 34, 42           # márgenes
    pw, ph = W - ML - MR, H - MT - MB
    n = len(historial)

    def x(i):
        return ML + (pw * i / (n - 1) if n > 1 else pw / 2)

    def y(v):
        return MT + ph * (1 - v)              # 0 abajo, 1 arriba

    partes = [
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        f'aria-label="Evolución de las notas por corrida" font-family="system-ui,sans-serif">',
        # superficie clara fija: así la paleta validada vale aunque la página se oscurezca
        f'<rect x="{ML}" y="{MT}" width="{pw}" height="{ph}" fill="#fcfcfb" '
        f'stroke="#e7e2d8"/>',
    ]

    # rejilla horizontal + etiquetas del eje Y (recesiva)
    for g in (0, 0.25, 0.5, 0.75, 1.0):
        yy = y(g)
        partes.append(f'<line x1="{ML}" y1="{yy:.1f}" x2="{ML + pw}" y2="{yy:.1f}" '
                      f'stroke="#efeae0"/>')
        partes.append(f'<text x="{ML - 8}" y="{yy + 4:.1f}" text-anchor="end" '
                      f'font-size="11" fill="#9a9284">{g:.2f}</text>')

    # etiquetas del eje X (una por corrida)
    for i, c in enumerate(historial):
        partes.append(f'<text x="{x(i):.1f}" y="{MT + ph + 16:.1f}" text-anchor="middle" '
                      f'font-size="11" fill="#6b6357">#{i + 1}</text>')
        partes.append(f'<text x="{x(i):.1f}" y="{MT + ph + 30:.1f}" text-anchor="middle" '
                      f'font-size="9.5" fill="#a49b8c">{_fecha_corta(c["fecha"])}</text>')

    # una línea + puntos por serie
    for clave, etiqueta, color in SERIES:
        pts = [(x(i), y(c[clave])) for i, c in enumerate(historial) if c.get(clave) is not None]
        if not pts:
            continue
        if len(pts) > 1:
            d = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
            partes.append(f'<polyline points="{d}" fill="none" stroke="{color}" '
                          f'stroke-width="2" stroke-linejoin="round"/>')
        for i, (px, py) in enumerate(pts):
            v = historial[i][clave]
            # anillo de superficie de 2px donde los puntos se solapan (marks spec)
            partes.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{color}" '
                          f'stroke="#fcfcfb" stroke-width="2">'
                          f'<title>corrida #{i + 1} · {etiqueta} {v}</title></circle>')
        # etiqueta directa SOLO en el último punto (identidad = punto de color + texto en tinta)
        lx, ly = pts[-1]
        partes.append(f'<circle cx="{lx + 16:.1f}" cy="{ly:.1f}" r="4" fill="{color}"/>')
        partes.append(f'<text x="{lx + 24:.1f}" y="{ly + 4:.1f}" font-size="12" '
                      f'fill="#4a4438">{etiqueta} {historial[-1][clave]}</text>')

    partes.append("</svg>")
    return "\n".join(partes)


# ─────────────────────────────────────────────────────────────
# LA TABLA DE TRAZABILIDAD
# ─────────────────────────────────────────────────────────────
def _veredicto(actual: float, previa) -> str:
    """Compara con la corrida anterior, pero con el ruido puesto delante."""
    if previa is None:
        return '<span class="v-base">baseline</span>'
    d = actual - previa
    if abs(d) <= RUIDO:
        return f'<span class="v-ruido">≈ ruido ({d:+.3f})</span>'
    if d > 0:
        return f'<span class="v-sube">▲ mejora ({d:+.3f})</span>'
    return f'<span class="v-baja">▼ empeora ({d:+.3f})</span>'


def tabla_corridas(historial: list) -> str:
    filas = []
    prev_global = None
    for i, c in enumerate(historial):
        notas = "".join(
            f'<td class="num">{c.get(k):.3f}</td>' for k, _, _ in SERIES
        )
        rev = ""
        if c.get("nota_revision"):
            rev = (f'<tr class="rev"><td></td><td colspan="6">'
                   f'⚑ {_esc(c["nota_revision"])}</td></tr>')
        filas.append(
            f'<tr><td class="num">#{i + 1}</td>'
            f'<td class="fecha">{_fecha_corta(c["fecha"])}</td>'
            f'<td class="cambio">{_esc(c["cambio"])}<br>'
            f'<span class="vers">{_esc(_versiones_compactas(c))}</span></td>'
            f'{notas}'
            f'<td>{_veredicto(c.get("nota_global"), prev_global)}</td></tr>'
            + rev
        )
        prev_global = c.get("nota_global")
    cabecera = ("<tr><th>#</th><th>fecha</th><th>cambio aplicado</th>"
                "<th>bugs</th><th>controles</th><th>global</th>"
                "<th>vs. anterior</th></tr>")
    return f'<table class="corridas">{cabecera}{"".join(filas)}</table>'


# ─────────────────────────────────────────────────────────────
# LA TABLA POR HERRAMIENTA (el detalle: qué caso movió la nota)
# ─────────────────────────────────────────────────────────────
def tabla_por_herramienta(historial: list) -> str:
    # ids de caso en el orden en que aparecen, con su tipo
    orden, tipos = [], {}
    for c in historial:
        for r in c.get("resultados", []):
            if r["id"] not in tipos:
                orden.append(r["id"])
                tipos[r["id"]] = r["tipo"]

    cols = "".join(f"<th>#{i + 1}</th>" for i in range(len(historial)))
    filas = []
    for cid in orden:
        celdas = []
        for c in historial:
            r = next((x for x in c.get("resultados", []) if x["id"] == cid), None)
            if r is None:
                celdas.append('<td class="num">·</td>')
                continue
            clase = "cel-ok" if r["nota"] == 1 else ("cel-mal" if r["nota"] == 0 else "cel-medio")
            celdas.append(f'<td class="num {clase}" title="{r["pasadas"]}/{r["repeticiones"]} pasadas">'
                          f'{r["nota"]:.2f}</td>')
        etiqueta_tipo = "bug" if tipos[cid] == "bug" else "ctrl"
        filas.append(f'<tr><td class="caso"><span class="tipo tipo-{tipos[cid]}">'
                     f'{etiqueta_tipo}</span> {_esc(cid)}</td>{"".join(celdas)}</tr>')
    return (f'<table class="porherr"><tr><th>caso</th>{cols}</tr>{"".join(filas)}</table>')


# ─────────────────────────────────────────────────────────────
# EL MONTAJE
# ─────────────────────────────────────────────────────────────
PLANTILLA = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Historial de la báscula · Artefacto 5</title>
<style>
  :root{{
    --warmth: 0;
    --h-bg: 40; --s-bg: 30%; --s-panel: 33%; --h-ink: 30; --s-ink: 15%; --h-acc: 38; --s-acc: 92%;
    --bg: hsl(var(--h-bg) var(--s-bg) calc(98% - var(--warmth) * 12%));
    --panel: hsl(var(--h-bg) var(--s-panel) calc(100% - var(--warmth) * 14%));
    --ink: hsl(var(--h-ink) var(--s-ink) calc(18% + var(--warmth) * 4%));
    --soft: hsl(var(--h-ink) 10% calc(42% + var(--warmth) * 6%));
    --amber: hsl(var(--h-acc) var(--s-acc) calc(45% - var(--warmth) * 6%));
    --line: hsl(var(--h-acc) 25% calc(86% - var(--warmth) * 12%));
    --code-bg: hsl(var(--h-bg) 25% calc(95% - var(--warmth) * 13%));
    --blue-filter: sepia(calc(var(--warmth) * 0.35)) brightness(calc(1 - var(--warmth) * 0.04));
  }}
  :root[data-paleta="azul"]{{ --h-bg:208; --s-bg:26%; --s-panel:30%; --h-ink:215; --s-ink:16%; --h-acc:205; --s-acc:72%; }}
  :root[data-paleta="neutra"]{{ --h-bg:220; --s-bg:6%; --s-panel:7%; --h-ink:220; --s-ink:9%; --h-acc:250; --s-acc:38%; }}
  *{{box-sizing:border-box}}
  html{{filter:var(--blue-filter);transition:filter .3s}}
  body{{margin:0;background:var(--bg);color:var(--ink);
    font-family:"Iowan Old Style","Palatino Linotype",Georgia,serif;
    line-height:1.6;font-size:17px;padding:0 20px 100px;transition:background .3s,color .3s}}
  .wrap{{max-width:900px;margin:0 auto}}
  header{{padding:50px 0 18px;border-bottom:2px solid var(--line);margin-bottom:30px}}
  .kicker{{font-family:"DM Mono",ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--amber);font-weight:600}}
  h1{{font-size:32px;line-height:1.15;margin:.35em 0 .15em;font-weight:600}}
  .sub{{color:var(--soft);font-size:15px;font-style:italic}}
  h2{{font-size:22px;margin:1.9em 0 .5em;font-weight:600}}
  p{{font-size:17px}}
  .card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:18px 0}}
  .leyenda{{display:flex;gap:20px;flex-wrap:wrap;font-family:system-ui,sans-serif;font-size:13px;
    color:var(--soft);margin:2px 0 14px}}
  .leyenda span{{display:inline-flex;align-items:center;gap:7px}}
  .sw{{width:22px;height:3px;border-radius:2px;display:inline-block}}
  .tabla-wrap{{overflow-x:auto;margin:6px 0}}
  table{{border-collapse:collapse;font-family:system-ui,sans-serif;font-size:14px;width:100%}}
  th,td{{text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top}}
  th{{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--soft);font-weight:600}}
  td.num{{font-family:"DM Mono",ui-monospace,monospace;text-align:right;white-space:nowrap}}
  td.fecha{{font-family:"DM Mono",monospace;font-size:12px;color:var(--soft);white-space:nowrap}}
  td.cambio{{max-width:360px}}
  .vers{{font-family:"DM Mono",monospace;font-size:11px;color:var(--amber)}}
  tr.rev td{{border-bottom:1px solid var(--line);background:hsl(var(--h-acc) 55% 94% / .5);
    font-size:13px;color:var(--soft);font-style:italic;padding-top:2px}}
  .v-base{{color:var(--soft)}}
  .v-sube{{color:hsl(150 45% 34%);font-weight:600}}
  .v-baja{{color:hsl(5 60% 46%);font-weight:600}}
  .v-ruido{{color:var(--soft);font-weight:600}}
  .porherr td.caso{{font-family:"DM Mono",monospace;font-size:12.5px}}
  .tipo{{font-size:10px;padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:.05em}}
  .tipo-bug{{background:hsl(15 70% 90%);color:hsl(15 65% 34%)}}
  .tipo-control{{background:hsl(205 55% 90%);color:hsl(205 60% 32%)}}
  .cel-ok{{color:hsl(150 45% 34%)}}
  .cel-mal{{color:hsl(5 60% 46%);font-weight:600}}
  .cel-medio{{color:hsl(35 80% 38%)}}
  footer{{margin-top:50px;padding-top:18px;border-top:1px solid var(--line);
    color:var(--soft);font-size:13px;font-family:"DM Mono",monospace}}
  .dial{{position:fixed;top:14px;right:14px;z-index:99;background:var(--panel);border:1px solid var(--line);
    border-radius:30px;padding:8px 14px;display:flex;align-items:center;gap:10px;
    box-shadow:0 2px 14px hsl(30 20% 20% / .12);font-family:system-ui,sans-serif;font-size:13px;color:var(--soft)}}
  .dial input[type=range]{{width:100px;accent-color:var(--amber)}}
  .sep{{width:1px;height:18px;background:var(--line)}}
  .pal{{width:15px;height:15px;border-radius:50%;border:1px solid hsl(30 15% 45% / .5);padding:0;cursor:pointer;transition:transform .15s}}
  .pal:hover{{transform:scale(1.18)}}
  .pal[data-p="calida"]{{background:hsl(38 92% 52%)}}
  .pal[data-p="azul"]{{background:hsl(205 72% 52%)}}
  .pal[data-p="neutra"]{{background:hsl(250 38% 58%)}}
  .pal[aria-pressed="true"]{{outline:2px solid var(--ink);outline-offset:2px}}
  @media print{{.dial{{display:none}}}}
</style>
</head>
<body>
<div class="dial">
  <span>☀️</span>
  <input type="range" id="warmth" min="0" max="100" value="0" aria-label="Hora: día a noche">
  <span>🌙</span><span class="sep"></span>
  <button class="pal" data-p="calida" aria-pressed="true" title="Paleta cálida"></button>
  <button class="pal" data-p="azul" aria-pressed="false" title="Paleta azul"></button>
  <button class="pal" data-p="neutra" aria-pressed="false" title="Paleta neutra"></button>
</div>
<div class="wrap">
<header>
  <div class="kicker">Artefacto 5 · AI Engineering · Fase 2</div>
  <h1>Historial de la báscula</h1>
  <div class="sub">Generado de historial.json el {generado}. Ninguna fila se escribe a mano: si no hay corrida detrás, no aparece.</div>
</header>

<h2>Evolución</h2>
<div class="card">
  <div class="leyenda">
    <span><i class="sw" style="background:#c2410c"></i> bugs — ¿los arreglos funcionan?</span>
    <span><i class="sw" style="background:#0369a1"></i> controles — ¿algo se rompió?</span>
    <span><i class="sw" style="background:#6d28d9"></i> global — la media</span>
  </div>
  {grafica}
  <p style="font-size:13px;color:var(--soft);margin:14px 0 0;font-family:system-ui,sans-serif">
    Banda de ruido ≈ ±{ruido}: sale del par de corridas #2/#3, de configuración idéntica y notas distintas.
    Un salto menor que eso no es señal, es azar.</p>
</div>

<h2>Trazabilidad · una fila por corrida</h2>
<div class="tabla-wrap card">{tabla_corridas}</div>

<h2>El detalle · caso a caso</h2>
<p style="font-size:14.5px;color:var(--soft)">Cada celda es la nota de ese caso en esa corrida (pasa el ratón: pasadas/repeticiones). Aquí se ve <em>qué</em> caso movió la media, no solo que se movió.</p>
<div class="tabla-wrap card">{tabla_porherr}</div>

<footer>
  Artefacto 5 · Endurecimiento · render_historial.py — {n} corrida(s) · generado {generado}.<br>
  Paso gratis del patrón caro-una-vez / barato-mil-veces: no llama a ninguna API.
</footer>
</div>
<script>
  const dial=document.getElementById('warmth'),CLAVE='a4-warmth';
  const aplicarHora=v=>document.documentElement.style.setProperty('--warmth',v/100);
  const g=localStorage.getItem(CLAVE); if(g!==null)dial.value=g; aplicarHora(dial.value);
  dial.addEventListener('input',()=>{{aplicarHora(dial.value);localStorage.setItem(CLAVE,dial.value)}});
  const CLAVE_PAL='a4-paleta',botones=document.querySelectorAll('.pal');
  const aplicarPaleta=p=>{{document.documentElement.setAttribute('data-paleta',p);
    botones.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.p===p)))}};
  aplicarPaleta(localStorage.getItem(CLAVE_PAL)||'calida');
  botones.forEach(b=>b.addEventListener('click',()=>{{aplicarPaleta(b.dataset.p);localStorage.setItem(CLAVE_PAL,b.dataset.p)}}));
</script>
</body>
</html>
"""


def main() -> None:
    if not RUTA_HISTORIAL.exists():
        raise SystemExit(f"no encuentro {RUTA_HISTORIAL.name}: corre antes evaluar_prompts.py")
    historial = json.loads(RUTA_HISTORIAL.read_text(encoding="utf-8"))
    if not historial:
        raise SystemExit("historial.json está vacío: no hay nada que pintar")

    html = PLANTILLA.format(
        generado=datetime.now().strftime("%d/%m/%Y %H:%M"),
        grafica=svg_evolucion(historial),
        tabla_corridas=tabla_corridas(historial),
        tabla_porherr=tabla_por_herramienta(historial),
        ruido=RUIDO,
        n=len(historial),
    )
    RUTA_SALIDA.write_text(html, encoding="utf-8")
    print(f"escrito {RUTA_SALIDA.name} · {len(historial)} corrida(s) · no se ha llamado a ninguna API")


if __name__ == "__main__":
    main()
