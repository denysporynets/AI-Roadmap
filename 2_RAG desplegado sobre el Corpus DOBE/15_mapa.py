"""
15_mapa.py — MAPA ESTELAR G1 (proyección 2D de los embeddings)
==============================================================
Reduce los vectores de 1536 dim a 2D con UMAP (métrica cosine) y genera un
HTML interactivo (fondo claro) con los 169 intercambios:
  · posición = cercanía semántica (UMAP)
  · tamaño   = longitud de la respuesta (proxy de densidad → candidatos a subdividir)
  · color    = cronología del viaje (orden del corpus)
  · hover    = num, página, tokens y la pregunta

Uso:  ./.venv/bin/python 15_mapa.py
"""

import json
from pathlib import Path

import numpy as np
import umap

BASE = Path(__file__).parent
OUT = BASE / "embeddings"
VEC = OUT / "vectores_g1.npy"
META = OUT / "meta_g1.json"
HTML = OUT / "mapa_g1.html"

W, H, PAD = 1100, 720, 60


def lerp_color(t: float) -> str:
    """Gradiente cronológico: teal (inicio) → ámbar (final)."""
    c0 = (0x0e, 0x7c, 0x86)   # teal
    c1 = (0xa8, 0x6a, 0x00)   # ámbar oscuro (coherente con paleta clara)
    r, g, b = (int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def main() -> None:
    arr = np.load(VEC)
    meta = json.loads(META.read_text(encoding="utf-8"))

    print(f"Proyectando {arr.shape[0]} vectores de dim {arr.shape[1]} con UMAP (cosine)…")
    reducer = umap.UMAP(n_components=2, metric="cosine", n_neighbors=15,
                        min_dist=0.12, random_state=42)
    xy = reducer.fit_transform(arr)

    # escalar a viewBox
    mn, mx = xy.min(0), xy.max(0)
    xy = (xy - mn) / (mx - mn)
    xs = PAD + xy[:, 0] * (W - 2 * PAD)
    ys = PAD + xy[:, 1] * (H - 2 * PAD)

    # tamaño por longitud de respuesta
    tok = np.array([m["n_tok_respuesta"] for m in meta], dtype=float)
    tnorm = (tok - tok.min()) / (tok.max() - tok.min() + 1e-9)
    radios = 4 + tnorm * 12

    n = len(meta)
    circles, puntos = "", []
    for i, m in enumerate(meta):
        color = lerp_color(i / (n - 1))
        circles += (f'<circle cx="{xs[i]:.1f}" cy="{ys[i]:.1f}" r="{radios[i]:.1f}" '
                    f'fill="{color}" fill-opacity="0.72" stroke="#fff" stroke-width="1" '
                    f'data-i="{i}" class="pt"/>')
        puntos.append({"num": m["num"], "pages": m["pages"],
                       "tokR": m["n_tok_respuesta"], "tokP": m["n_tok_pregunta"],
                       "preg": m["pregunta"]})

    doc = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa estelar G1 · Corpus DOBE</title>
<style>
  :root {{ --bg:#f5f3ee; --card:#fff; --amber:#a86a00; --txt:#24292f; --dim:#6b6b6b; --line:#e2e0d9; }}
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
  .legend {{ font-size:12.5px; color:var(--dim); margin-top:10px; line-height:1.7; }}
  .legend b {{ color:var(--txt); }}
  .foot {{ color:var(--dim); font-size:11.5px; margin-top:20px; font-family:'DM Mono',monospace; }}
</style></head><body>
  <h1>Mapa estelar — G1 (un vector por intercambio)</h1>
  <div class="sub">169 intercambios · UMAP sobre text-embedding-3-small (cosine) · pasa el ratón por una estrella</div>
  <div class="layout">
    <div class="mapbox">
      <svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">{circles}</svg>
    </div>
    <div class="panel">
      <h3>Detalle</h3>
      <div id="info"><span class="k">Pasa el ratón por una estrella…</span></div>
      <div class="legend">
        <b>Posición</b> = cercanía semántica (temas juntos = constelaciones)<br>
        <b>Tamaño</b> = longitud de la respuesta (grandes = densas → candidatas a subdividir)<br>
        <b>Color</b> = cronología del viaje (teal = inicio · ámbar = final)
      </div>
    </div>
  </div>
  <div class="foot">protocolo ds-nexus · artefacto 2 · mapa G1 · NOTA: el "difuso" real (dispersion_interna) se calculará embebiendo por párrafo; aquí el tamaño es un proxy por longitud</div>
<script>
  const P = {json.dumps(puntos, ensure_ascii=False)};
  const info = document.getElementById('info');
  document.querySelectorAll('.pt').forEach(c => {{
    c.addEventListener('mouseenter', e => {{
      const p = P[+e.target.dataset.i];
      info.innerHTML = `<div class="k">intercambio</div><div class="mono" style="font-size:18px;color:var(--amber)">#${{p.num}}</div>`
        + `<div class="k" style="margin-top:8px">página · tokens</div><div class="mono">${{p.pages}} · P:${{p.tokP}} / R:${{p.tokR}}</div>`
        + `<div class="k" style="margin-top:8px">pregunta</div><div>${{p.preg}}…</div>`;
    }});
  }});
</script>
</body></html>"""

    HTML.write_text(doc, encoding="utf-8")
    print(f"✅ Mapa generado → embeddings/{HTML.name}")


if __name__ == "__main__":
    main()
