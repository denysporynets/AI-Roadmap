/* ═══════════════════════════════════════════════════════════════════════════
   laton.js — comportamiento compartido del sistema "latón sobre papel"
   ═══════════════════════════════════════════════════════════════════════════
   Lo clonaban 7 páginas (ROADMAP + las 6 gemelas): el reveal "enfoque de
   instrumento", el mando día/noche, el fondo de carta náutica y su parallax.
   Aquí viven UNA sola vez; cada página lo enlaza y añade su pieza propia en un
   <script> inline que se carga DESPUÉS de este fichero.

   Se quedan inline en cada página A PROPÓSITO (no entran aquí):
   - el guardián del <head> (aplica el tema antes del primer pintado; un fichero
     externo llegaría tarde y se vería el destello blanco al cargar en noche);
   - el <symbol> del sello (es markup SVG, no JS; compartir HTML pediría un build).

   `reduce` se declara a nivel de script (fuera de todo IIFE) a posta: alguna
   pieza propia lo usa (la traza del artefacto 4, el extractor del 1, la bitácora
   del 6…), y en un script CLÁSICO ese binding queda visible para el <script>
   inline que va detrás en la misma página.

   Cada bloque va aislado en su try/catch: antes era un único <script> y una
   excepción temprana dejaba TODOS los .reveal en opacity:0 para siempre (el
   <noscript> no cubre errores de JS, solo la AUSENCIA de JS). Ahora el fallo de
   un bloque no arrastra a los demás, y si el reveal peta hay red de seguridad
   que destapa todo el contenido.
   ═══════════════════════════════════════════════════════════════════════════ */

const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ── reveal "enfoque de instrumento" ──
try {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) { e.target.classList.add("revealed"); io.unobserve(e.target); }
    }
  }, { threshold: 0.08 });
  document.querySelectorAll(".reveal").forEach((el) => { if (!el.closest(".hero")) io.observe(el); });
  requestAnimationFrame(() => {
    document.querySelectorAll(".hero .reveal").forEach((el, i) => {
      setTimeout(() => el.classList.add("revealed"), 90 * i);
    });
  });
} catch (e) {
  // Red de seguridad: si el reveal falla, que NADA quede invisible.
  document.querySelectorAll(".reveal").forEach((el) => el.classList.add("revealed"));
}

// ── modo noche / día (misma clave que la home: el tema viaja con el visitante) ──
try {
  (function tema() {
    const root = document.documentElement;
    const btn = document.getElementById("themeToggle");
    const CLAVE = "portfolio-tema";
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    function aplicar(t) {
      if (t === "dark") { root.setAttribute("data-theme", "dark"); btn.setAttribute("aria-label", "Cambiar a modo día"); }
      else { root.removeAttribute("data-theme"); btn.setAttribute("aria-label", "Cambiar a modo noche"); }
    }
    function guardado() { try { return localStorage.getItem(CLAVE); } catch (e) { return null; } }
    // El tema ya lo aplicó el script del <head>; aquí solo se pone al día la etiqueta del botón.
    aplicar(root.getAttribute("data-theme") === "dark" ? "dark" : "light");
    btn.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      aplicar(next);
      try { localStorage.setItem(CLAVE, next); } catch (e) {}
    });
    mq.addEventListener("change", (e) => { if (!guardado()) aplicar(e.matches ? "dark" : "light"); });
  })();
} catch (e) {}

// ── fondo: contornos tipo carta náutica ──
try {
  (function drawContours() {
    const svg = document.getElementById("contours");
    if (!svg || reduce) return;
    const W = 1200, H = 1200, lines = 26;
    let frag = "";
    for (let i = 0; i < lines; i++) {
      const baseY = (H / (lines - 1)) * i;
      const amp = 20 + (i % 5) * 5;
      const phase = i * 0.7;
      const freq = 0.0055 + (i % 3) * 0.0011;
      let d = "";
      for (let x = 0; x <= W; x += 40) {
        const y = baseY + Math.sin(x * freq + phase) * amp;
        d += (x === 0 ? "M" : "L") + x + " " + y.toFixed(1) + " ";
      }
      const index = (i % 5 === 0);
      frag += '<path d="' + d.trim() + '" stroke-width="' + (index ? 1.5 : 0.8) + '"/>';
    }
    svg.innerHTML = frag;
  })();
} catch (e) {}

// ── parallax del fondo ──
try {
  (function parallax() {
    const el = document.getElementById("contours");
    if (!el || reduce) return;
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        el.style.transform = "translateY(" + (window.scrollY * -0.07).toFixed(1) + "px)";
        ticking = false;
      });
    }, { passive: true });
  })();
} catch (e) {}
