"""
17_mapa_difusion.py — MAPA ESTELAR G1 RECOLOREADO POR DIFUSIÓN
==============================================================
Mismo layout UMAP que 15_mapa.py (random_state=42), pero el COLOR ya no es la
cronología: es la dispersion_interna calibrada contra el techo heterogéneo.

  · posición = cercanía semántica (UMAP, idéntica al mapa G1)
  · tamaño   = longitud de la respuesta (proxy de densidad)
  · color    = dispersión interna   azul=coherente (1 vector basta)
                                     rojo=ensalada de temas (subdividir)
  · borde    = ⬤ rojo grueso si disp ≥ 80% del techo → candidata clara multi-vector

Escala: 0 (coherente) … TECHO≈0.268 (mezcla aleatoria de temas distintos).

Uso:  ./.venv/bin/python 17_mapa_difusion.py
"""

import json
from pathlib import Path

import numpy as np
import umap

BASE = Path(__file__).parent
OUT = BASE / "embeddings"
VEC = OUT / "vectores_g1.npy"
META = OUT / "meta_g1.json"
CORPUS = BASE / "corpus_dobe_enriquecido.json"
HTML = OUT / "mapa_difusion.html"

W, H, PAD = 1100, 720, 60
TECHO = 0.268            # dispersión de una mezcla 100% heterogénea (referencia)
UMBRAL_SUB = 0.80        # ≥80% del techo → candidata clara a subdividir


def color_disp(t: float) -> str:
    """Azul frío (coherente) → rojo cálido (disperso). t en 0..1."""
    c0 = (0x2c, 0x6e, 0xb5)   # azul
    c1 = (0xc0, 0x39, 0x2b)   # rojo ladrillo
    r, g, b = (int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def main() -> None:
    arr = np.load(VEC)
    meta = json.loads(META.read_text(encoding="utf-8"))
    corpus = {x["num"]: x for x in json.loads(CORPUS.read_text(encoding="utf-8"))}

    reducer = umap.UMAP(n_components=2, metric="cosine", n_neighbors=15,
                        min_dist=0.12, random_state=42)
    xy = reducer.fit_transform(arr)
    mn, mx = xy.min(0), xy.max(0)
    xy = (xy - mn) / (mx - mn)
    xs = PAD + xy[:, 0] * (W - 2 * PAD)
    ys = PAD + xy[:, 1] * (H - 2 * PAD)

    tok = np.array([m["n_tok_respuesta"] for m in meta], dtype=float)
    tnorm = (tok - tok.min()) / (tok.max() - tok.min() + 1e-9)
    radios = 4 + tnorm * 12

    circles, puntos = "", []
    n_sub = 0
    for i, m in enumerate(meta):
        x = corpus[m["num"]]
        disp = x.get("dispersion_interna") or 0.0
        nseg = x.get("n_segmentos", 1)
        t = min(disp / TECHO, 1.0)
        es_sub = t >= UMBRAL_SUB
        n_sub += es_sub
        stroke = "#7a1f17" if es_sub else "#fff"
        sw = 2.4 if es_sub else 1
        circles += (f'<circle cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="{radios[i]:.1f}" '
                    f'fill="{color_disp(t)}" fill-opacity="0.78" stroke="{stroke}" '
                    f'stroke-width="{sw}" data-i="{i}" class="pt"/>')
        puntos.append({"num": m["num"], "pages": m["pages"],
                       "tokR": m["n_tok_respuesta"], "tokP": m["n_tok_pregunta"],
                       "disp": round(disp, 3), "pct": round(100 * t),
                       "nseg": nseg, "preg": m["pregunta"]})

    doc = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa de difusión · Corpus DOBE</title>
<style>
  :root {{ --bg:#f5f3ee; --card:#fff; --accent:#c0392b; --txt:#24292f; --dim:#6b6b6b; --line:#e2e0d9; }}
  body {{ background:var(--bg); color:var(--txt); margin:0; padding:28px;
         font-family:'DM Sans',-apple-system,system-ui,sans-serif; }}
  h1 {{ font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:26px; margin:0 0 2px; }}
  .sub {{ color:var(--dim); font-size:13px; margin-bottom:14px; }}
  .layout {{ display:flex; gap:20px; align-items:flex-start; flex-wrap:wrap; }}
  .mapbox {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:8px; }}
  svg {{ display:block; }}
  .pt {{ cursor:pointer; transition:fill-opacity .1s; }}
  .pt:hover {{ fill-opacity:1; stroke:#24292f; stroke-width:1.5; }}
  .panel {{ flex:1; min-width:260px; background:var(--card); border:1px solid var(--line);
            border-radius:12px; padding:18px; font-size:14px; }}
  .panel h3 {{ margin:0 0 10px; font-family:'Fraunces',serif; }}
  .k {{ color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  .mono {{ font-family:'DM Mono',ui-monospace,monospace; }}
  .bar {{ height:8px; border-radius:4px; background:linear-gradient(90deg,#2c6eb5,#c0392b); margin:6px 0 2px; }}
  .legend {{ font-size:12.5px; color:var(--dim); margin-top:14px; line-height:1.7; }}
  .legend b {{ color:var(--txt); }}
  .foot {{ color:var(--dim); font-size:11.5px; margin-top:20px; font-family:'DM Mono',monospace; }}
</style></head><body>
  <h1>Mapa de difusión — dispersión interna real</h1>
  <div class="sub">169 intercambios · color = cuánto se dispersa la respuesta (segmentos ~250 tok) · {n_sub} candidatas claras a subdividir (borde rojo)</div>
  <div class="layout">
    <div class="mapbox">
      <svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">{circles}</svg>
    </div>
    <div class="panel">
      <h3>Detalle</h3>
      <div id="info"><span class="k">Pasa el ratón por una estrella…</span></div>
      <div class="legend">
        <div class="bar"></div>
        <b>Color</b> azul = coherente (1 vector) · rojo = ensalada de temas (subdividir)<br>
        <b>Escala</b> 0 → techo 0.268 (mezcla aleatoria de temas distintos)<br>
        <b>Borde rojo</b> = dispersión ≥ 80% del techo → multi-vector recomendado<br>
        <b>Tamaño</b> = longitud de la respuesta
      </div>
    </div>
  </div>
  <div class="foot">protocolo ds-nexus · artefacto 2 · mapa de difusión · dispersion_interna = dist. coseno media al centroide · techo calibrado con 500 mezclas heterogéneas</div>
<script>
  const P = {json.dumps(puntos, ensure_ascii=False)};
  const info = document.getElementById('info');
  document.querySelectorAll('.pt').forEach(c => {{
    c.addEventListener('mouseenter', e => {{
      const p = P[+e.target.dataset.i];
      info.innerHTML = `<div class="k">intercambio</div><div class="mono" style="font-size:18px;color:var(--accent)">#${{p.num}}</div>`
        + `<div class="k" style="margin-top:8px">dispersión</div><div class="mono">${{p.disp}} · ${{p.pct}}% del techo · ${{p.nseg}} segmentos</div>`
        + `<div class="k" style="margin-top:8px">página · tokens</div><div class="mono">${{p.pages}} · P:${{p.tokP}} / R:${{p.tokR}}</div>`
        + `<div class="k" style="margin-top:8px">pregunta</div><div>${{p.preg}}…</div>`;
    }});
  }});
</script>
</body></html>"""

    HTML.write_text(doc, encoding="utf-8")
    print(f"✅ Mapa de difusión → embeddings/{HTML.name}")
    print(f"   {n_sub} intercambios con dispersión ≥ {UMBRAL_SUB:.0%} del techo (borde rojo)")


if __name__ == "__main__":
    main()
