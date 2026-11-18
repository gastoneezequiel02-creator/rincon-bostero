// Rincón Bostero: cuenta regresiva, horarios relativos, filtros e historial.
(function () {
  "use strict";

  // Cuenta regresiva al próximo partido
  function cuenta() {
    document.querySelectorAll("[data-cuenta]").forEach(function (el) {
      var falta = new Date(el.getAttribute("data-cuenta")) - new Date();
      var num = el.querySelector("[data-num]");
      var txt = el.querySelector("small");
      if (!num) return;
      if (falta <= 0) {
        num.textContent = falta > -2.5 * 3600e3 ? "¡Juega Boca!" : "Terminó";
        if (txt) txt.textContent = "";
        return;
      }
      var d = Math.floor(falta / 864e5), h = Math.floor(falta / 36e5) % 24, m = Math.floor(falta / 6e4) % 60;
      if (d >= 1) { num.textContent = d + (d === 1 ? " día" : " días"); if (txt) txt.textContent = "y " + h + " h para el partido"; }
      else { num.textContent = h + " h " + String(m).padStart(2, "0") + " min"; if (txt) txt.textContent = "para el partido"; }
    });
  }

  // "hace 5 min", "ayer", etc.
  var MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  function relativos() {
    document.querySelectorAll("time[data-rel]").forEach(function (el) {
      var d = new Date(el.getAttribute("datetime")), s = (new Date() - d) / 1000, t;
      if (s < 60) t = "recién";
      else if (s < 3600) t = "hace " + Math.floor(s / 60) + " min";
      else if (s < 86400) t = "hace " + Math.floor(s / 3600) + " h";
      else if (s < 172800) t = "ayer";
      else if (s < 604800) t = "hace " + Math.floor(s / 86400) + " días";
      else t = d.getDate() + " " + MESES[d.getMonth()];
      el.textContent = t;
    });
  }

  // Filtros por botón: <div class="filtros" data-filtra="#lista"> <button data-valor="x">
  document.querySelectorAll("[data-filtra]").forEach(function (grupo) {
    var objetivo = document.querySelector(grupo.getAttribute("data-filtra"));
    grupo.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-valor]");
      if (!b || !objetivo) return;
      grupo.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      var v = b.getAttribute("data-valor");
      objetivo.querySelectorAll("[data-grupo]").forEach(function (item) {
        item.hidden = !(v === "todos" || item.getAttribute("data-grupo").split(" ").indexOf(v) >= 0);
      });
      objetivo.querySelectorAll("[data-anio]").forEach(function (h) {
        var sig = h.nextElementSibling, visible = false;
        if (sig) sig.querySelectorAll("[data-grupo]").forEach(function (i) { if (!i.hidden) visible = true; });
        h.hidden = !visible; if (sig) sig.hidden = !visible;
      });
    });
  });

  // Fixture y posiciones: pestañas por competencia
  document.querySelectorAll("[data-pestanas]").forEach(function (grupo) {
    var botones = grupo.querySelectorAll("button[data-destino]");
    var secciones = document.querySelectorAll("[data-pestana-id]");
    function mostrar(id, cambiarHash) {
      var existe = false;
      secciones.forEach(function (s) { if (s.getAttribute("data-pestana-id") === id) existe = true; });
      if (!existe) return false;
      secciones.forEach(function (s) { s.hidden = s.getAttribute("data-pestana-id") !== id; });
      botones.forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-destino") === id ? "true" : "false"); });
      if (cambiarHash) history.replaceState(null, "", "#" + id);
      return true;
    }
    grupo.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-destino]");
      if (b) mostrar(b.getAttribute("data-destino"), true);
    });
    var inicial = grupo.querySelector("button[aria-pressed='true']");
    if (!(location.hash && mostrar(location.hash.slice(1), false)) && inicial) mostrar(inicial.getAttribute("data-destino"), false);
    window.addEventListener("hashchange", function () { mostrar(location.hash.slice(1), false); });
  });

  // Resultados: elegir temporada (dentro de cada competencia)
  document.querySelectorAll("select[data-temporadas]").forEach(function (sel) {
    sel.addEventListener("change", function () {
      var caja = sel.closest("section") || document;
      caja.querySelectorAll("[data-temporada]").forEach(function (b) {
        b.hidden = b.getAttribute("data-temporada") !== sel.value;
      });
    });
  });

  // Campañas: buscador + filtro por competencia + resumen
  var tablaCamp = document.getElementById("tabla-campanas");
  if (tablaCamp) {
    var buscador = document.getElementById("buscar-campana");
    var grupoComp = document.querySelector("[data-filtro-campanas]");
    var resumen = document.getElementById("resumen-campanas");
    var vacio = document.getElementById("sin-campanas");
    var compActual = "todas";
    var normal = function (t) { return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); };
    function filtrar() {
      var palabras = normal(buscador.value).split(/\s+/).filter(Boolean);
      var t = { n: 0, pj: 0, g: 0, e: 0, p: 0, gf: 0, gc: 0, campeon: 0 };
      tablaCamp.querySelectorAll("tbody tr").forEach(function (tr) {
        var texto = tr.getAttribute("data-texto");
        var comp = tr.getAttribute("data-comp");
        var ok = (compActual === "todas" ? comp !== "amistosos" : comp === compActual) &&
          palabras.every(function (w) { return texto.indexOf(w) >= 0; });
        tr.hidden = !ok;
        if (ok) {
          t.n++;
          ["pj", "g", "e", "p", "gf", "gc", "campeon"].forEach(function (k) { t[k] += +tr.getAttribute("data-" + k) || 0; });
        }
      });
      vacio.hidden = t.n > 0;
      resumen.innerHTML = t.n ? "<b>" + t.n + (t.n === 1 ? " campaña" : " campañas") + "</b>" +
        (t.campeon ? ", <b>" + t.campeon + (t.campeon === 1 ? " título" : " títulos") + "</b>" : "") +
        ". " + t.pj + " partidos: " + t.g + " ganados, " + t.e + " empatados y " + t.p + " perdidos. Goles: " + t.gf + " a favor y " + t.gc + " en contra." : "";
    }
    grupoComp.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-comp]");
      if (!b) return;
      compActual = b.getAttribute("data-comp");
      grupoComp.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      filtrar();
    });
    buscador.addEventListener("input", filtrar);
    filtrar();
  }

  // Historial: elegir rival (las cifras vienen en la página; la lista de partidos se carga aparte)
  var selector = document.getElementById("rival");
  if (selector) {
    var datos = JSON.parse(document.getElementById("datos-historial").textContent);
    var caja = document.getElementById("historial-resultado");
    var cache = {};
    var verAmistosos = false;
    function cifras(b, nombre, grande) {
      return "<div class='historial-cifras" + (grande ? "" : " chicas") + "'>" +
        "<div style='background:var(--verde)'><b>" + b.g + "</b>Ganó Boca</div>" +
        "<div style='background:#8a93a8'><b>" + b.e + "</b>Empates</div>" +
        "<div style='background:var(--rojo)'><b>" + b.p + "</b>Ganó " + nombre + "</div></div>" +
        "<p class='nota-dato'>" + b.pj + " partidos" + (b.gf != null ? ". Goles: Boca " + b.gf + ", " + nombre + " " + b.gc : "") +
        ". " + b.nota + "</p>";
    }
    function filas(lista, h) {
      return lista.filter(function (p) { return verAmistosos || !p.amistoso; }).map(function (p) {
        var f = p.fecha.split("-");
        var fecha = (+f[2]) + " " + MESES[+f[1] - 1] + " " + f[0];
        var pen = p.penales_boca != null ? " <small>(" + p.penales_boca + "-" + p.penales_rival + " pen.)</small>" : "";
        var cruce = p.condicion === "V"
          ? h.corto + " <span class='goles'>" + p.goles_rival + " - " + p.goles_boca + "</span> Boca"
          : "Boca <span class='goles'>" + p.goles_boca + " - " + p.goles_rival + "</span> " + h.corto;
        return "<li><span class='lp-fecha'>" + fecha + "</span><span><span class='lp-cruce'>" + cruce + pen +
          "</span><span class='lp-sub'>" + p.competencia + (p.condicion === "N" ? ". Cancha neutral" : "") +
          "</span></span><span class='lp-res r-" + p.resultado + "'>" + p.resultado + "</span></li>";
      }).join("");
    }
    function pintarLista(clave) {
      var h = datos[clave], lista = cache[clave], cont = document.getElementById("lista-historial");
      if (!cont || !lista) return;
      var hay = lista.some(function (p) { return p.amistoso; });
      cont.innerHTML = "<h3 class='titulo-seccion' style='font-size:22px'>Todos los partidos (" + lista.length + ")" +
        (hay ? " <label class='nota-dato' style='font-weight:500'><input type='checkbox' id='con-amistosos'" + (verAmistosos ? " checked" : "") + "> Incluir amistosos</label>" : "") +
        "</h3><ul class='lista-partidos'>" + filas(lista, h) + "</ul>";
      var chk = document.getElementById("con-amistosos");
      if (chk) chk.addEventListener("change", function () { verAmistosos = chk.checked; pintarLista(clave); });
    }
    function pintar() {
      var clave = selector.value, h = datos[clave];
      if (!h) { caja.innerHTML = ""; return; }
      var html = "";
      h.bloques.forEach(function (b, i) {
        html += (i === 0 ? "<h2 class='titulo-seccion'>" : "<h3 class='titulo-seccion' style='font-size:22px'>") + b.titulo +
          (i === 0 ? "</h2>" : "</h3>") + cifras(b, h.corto, i === 0);
      });
      caja.innerHTML = html + "<div id='lista-historial'><p class='nota-dato'>Cargando partidos…</p></div>";
      if (cache[clave]) return pintarLista(clave);
      fetch("historial/" + clave + ".json").then(function (r) { return r.json(); }).then(function (lista) {
        cache[clave] = lista;
        if (selector.value === clave) pintarLista(clave);
      }).catch(function () {
        var cont = document.getElementById("lista-historial");
        if (cont) cont.innerHTML = "<p class='nota-dato'>No se pudo cargar la lista de partidos.</p>";
      });
    }
    selector.addEventListener("change", function () { pintar(); history.replaceState(null, "", "#" + selector.value); });
    if (location.hash && datos[location.hash.slice(1)]) selector.value = location.hash.slice(1);
    pintar();
  }

  cuenta(); relativos();
  setInterval(cuenta, 30000); setInterval(relativos, 60000);
})();
