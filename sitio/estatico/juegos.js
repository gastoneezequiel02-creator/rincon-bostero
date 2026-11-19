// Rincón Bostero: juegos.
//   Portada con una tarjeta por juego; cada juego se abre en su propia pantalla (#del-dia, #idolo, ...).
//   Pregunta del día y trivia: con cuentas (Supabase) se corrigen en la base de datos y suman al ranking.
//   El resto corre en el navegador. Al terminar cada juego se arma una imagen para compartir.
(function () {
  "use strict";
  var nodo = document.getElementById("datos-juegos");
  if (!nodo) return;
  var D = JSON.parse(nodo.textContent);
  var URL_JUEGOS = nodo.getAttribute("data-url") || location.href.split("#")[0];
  var SB_URL = nodo.getAttribute("data-supabase-url"), SB_KEY = nodo.getAttribute("data-supabase-key");
  var CON_GOOGLE = nodo.getAttribute("data-google") === "1";
  var sb = null, usuario = null, perfil = null;
  var INICIO = new Date(2026, 10, 18); // día 1 de la pregunta del día
  var REDUCIR = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------- utilidades --
  function guardar(k, v) { try { localStorage.setItem("rb-" + k, JSON.stringify(v)); } catch (e) {} }
  function leer(k, def) { try { var v = localStorage.getItem("rb-" + k); return v ? JSON.parse(v) : def; } catch (e) { return def; } }
  function hoyTxt(d) { d = d || new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function ayerTxt() { var d = new Date(); d.setDate(d.getDate() - 1); return hoyTxt(d); }
  function numeroDelDia() { var h = new Date(); h.setHours(0, 0, 0, 0); return Math.round((h - INICIO) / 864e5) + 1; }
  function semilla(txt) { var h = 1779033703 ^ txt.length; for (var i = 0; i < txt.length; i++) { h = Math.imul(h ^ txt.charCodeAt(i), 3432918353); h = h << 13 | h >>> 19; } return h >>> 0; }
  function azar(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function mezclar(lista, r) { var a = lista.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function normal(t) { return (t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/\s+/g, " ").trim(); }
  function iniciales(n) { var p = String(n).split(/\s+/).filter(function (x) { return x.length > 2 || /^[A-ZÁÉÍÓÚ]/.test(x); }); return ((p[0] || "")[0] || "") + ((p[p.length - 1] || "")[0] || ""); }
  function rpc(nombre, args) { return sb.rpc(nombre, args || {}).then(function (r) { if (r.error) throw r.error; return r.data; }); }
  function errorConexion(caja) { caja.innerHTML = "<p class='vacio'>No pudimos conectarnos con el servidor de los juegos. Probá de nuevo en un rato.</p>"; }
  function firma() { return perfil && perfil.apodo ? perfil.apodo + " en " : ""; }
  function plural(n, uno, varios) { return n + " " + (n === 1 ? uno : varios); }
  function contar(el, hasta, sufijo) {
    if (REDUCIR || !el) { if (el) el.textContent = hasta + (sufijo || ""); return; }
    var t0 = null, dur = 650;
    function paso(t) { if (!t0) t0 = t; var k = Math.min(1, (t - t0) / dur); el.textContent = Math.round(hasta * (1 - Math.pow(1 - k, 3))) + (sufijo || ""); if (k < 1) requestAnimationFrame(paso); }
    requestAnimationFrame(paso);
  }
  function aviso(texto) {
    var t = document.createElement("div");
    t.className = "aviso-juego"; t.setAttribute("role", "status"); t.innerHTML = texto;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add("sale"); }, 3200);
    setTimeout(function () { t.remove(); }, 3800);
  }

  // ---------------------------------------------------------------- logros --
  var INSIGNIAS = [
    { id: "debut", nombre: "Debut", glifo: "1", desc: "Jugaste tu primera Pregunta del día.", cuenta: true, ok: function (p) { return p.dias_total >= 1; } },
    { id: "racha3", nombre: "Tres al hilo", glifo: "3", desc: "3 días seguidos con la Pregunta del día.", cuenta: true, ok: function (p) { return p.mejor_racha >= 3; } },
    { id: "racha7", nombre: "Semana completa", glifo: "7", desc: "7 días seguidos con la Pregunta del día.", cuenta: true, ok: function (p) { return p.mejor_racha >= 7; } },
    { id: "racha30", nombre: "Abonado", glifo: "30", desc: "30 días seguidos con la Pregunta del día.", cuenta: true, ok: function (p) { return p.mejor_racha >= 30; } },
    { id: "perfecto", nombre: "Partido perfecto", glifo: "10", desc: "10 de 10 en la Pregunta del día.", cuenta: true, ok: function (p) { return p.perfectos >= 1; } },
    { id: "cien", nombre: "Centenario", glifo: "100", desc: "100 respuestas correctas con tu cuenta.", cuenta: true, ok: function (p) { return p.aciertos_total >= 100; } },
    { id: "quinientos", nombre: "Quinientos", glifo: "500", desc: "500 respuestas correctas con tu cuenta.", cuenta: true, ok: function (p) { return p.aciertos_total >= 500; } },
    { id: "enciclopedia", nombre: "Enciclopedia", glifo: "A–Z", desc: "Jugaste la trivia de todos los temas.", cuenta: true, ok: function (p) { return p.temas_trivia >= Object.keys(D.temas).length; } },
    { id: "hincha", nombre: "Hincha de la semana", glifo: "1°", desc: "Terminaste primero en el ranking de una semana.", cuenta: true, ok: function (p) { return p.semanas_primero >= 1; } },
    { id: "mom10", nombre: "Diez al hilo", glifo: "+10", desc: "Racha de 10 en ¿Más o menos?" },
    { id: "scout", nombre: "Ojo de scout", glifo: "2", desc: "Adivinaste el ídolo del día en 2 intentos o menos." },
    { id: "archivo", nombre: "Memoria de archivo", glifo: "±0", desc: "Clavaste el año exacto en ¿En qué año fue?" },
    { id: "historiador", nombre: "Historiador", glifo: "400", desc: "400 puntos o más en ¿En qué año fue?" },
    { id: "grilla9", nombre: "Grilla llena", glifo: "9", desc: "Completaste los 9 casilleros de la Grilla bostera." },
    { id: "grilla-experto", nombre: "Enciclopedia", glifo: "E", desc: "Llenaste una Grilla bostera en Experto." },
    { id: "detective", nombre: "Detective", glifo: "?", desc: "Adivinaste un jugador de ¿Quién soy? con la primera pista." }
  ];
  function logrosLocales() { return leer("logros", {}); }
  function ganar(id) {
    var l = logrosLocales();
    if (l[id]) return;
    l[id] = hoyTxt(); guardar("logros", l);
    var ins = INSIGNIAS.filter(function (x) { return x.id === id; })[0];
    if (ins) aviso("<b>Nueva insignia:</b> " + esc(ins.nombre));
    pintarEstados();
  }
  function ganadas() {
    var l = logrosLocales();
    return INSIGNIAS.filter(function (i) { return i.cuenta ? !!(perfil && perfil.apodo && i.ok(perfil)) : !!l[i.id]; });
  }
  function revisarInsigniasCuenta() {
    if (!(perfil && perfil.apodo)) return;
    var vistas = leer("insignias-vistas", null), ahora = ganadas().filter(function (i) { return i.cuenta; }).map(function (i) { return i.id; });
    if (vistas) ahora.forEach(function (id) { if (vistas.indexOf(id) < 0) { var i = INSIGNIAS.filter(function (x) { return x.id === id; })[0]; aviso("<b>Nueva insignia:</b> " + esc(i.nombre)); } });
    guardar("insignias-vistas", ahora);
  }
  function medalla(i, ok) {
    var largo = i.glifo.length, tam = largo >= 3 ? 30 : largo === 2 ? 38 : 46;
    return "<svg viewBox='0 0 100 100' class='medalla" + (ok ? " ganada" : "") + "' aria-hidden='true'>" +
      "<circle cx='50' cy='50' r='46' class='m-borde'/><circle cx='50' cy='50' r='38' class='m-centro'/>" +
      "<text x='50' y='51' text-anchor='middle' dominant-baseline='central' style='font-size:" + tam + "px'>" + esc(i.glifo) + "</text></svg>";
  }

  // ----------------------------------------------------------- compartir --
  // cfg: {juego, puntaje, total, linea, celdas: [[estado, ...], ...], texto}
  //   estado: "ok" | "cerca" | "mal" | "vacio"
  var LOGO = new Image(); LOGO.src = "img/logo.webp";
  function dibujarResultado(cfg) {
    var W = 1080, H = 1350, c = document.createElement("canvas");
    c.width = W; c.height = H;
    var g = c.getContext("2d");
    g.fillStyle = "#071d4f"; g.fillRect(0, 0, W, H);
    g.fillStyle = "#f5b700"; g.fillRect(0, 300, W, 16);  // la franja
    try { if (LOGO.complete && LOGO.naturalWidth) g.drawImage(LOGO, 80, 90, 150, 150); } catch (e) {}
    g.fillStyle = "#ffffff"; g.font = "800 70px 'Barlow Condensed', 'Arial Narrow', sans-serif"; g.textBaseline = "alphabetic";
    g.fillText("Rincón Bostero", 260, 170);
    g.fillStyle = "#c5d0ea"; g.font = "600 40px 'Barlow', system-ui, sans-serif";
    g.fillText(cfg.juego, 262, 228);
    g.fillStyle = "#f5b700"; g.font = "800 300px 'Barlow Condensed', 'Arial Narrow', sans-serif";
    var p = String(cfg.puntaje), wP = g.measureText(p).width;
    g.font = "700 110px 'Barlow Condensed', 'Arial Narrow', sans-serif";
    var tot = cfg.total ? "/" + cfg.total : "", wT = g.measureText(tot).width;
    var x0 = (W - wP - wT) / 2;
    g.font = "800 300px 'Barlow Condensed', 'Arial Narrow', sans-serif"; g.fillText(p, x0, 640);
    g.fillStyle = "#8fa0c9"; g.font = "700 110px 'Barlow Condensed', 'Arial Narrow', sans-serif"; g.fillText(tot, x0 + wP + 6, 640);
    g.fillStyle = "#ffffff"; g.font = "600 44px 'Barlow', system-ui, sans-serif"; g.textAlign = "center";
    g.fillText(cfg.linea || "", W / 2, 730); g.textAlign = "left";
    var filas = cfg.celdas || [], maxCols = Math.max.apply(null, filas.map(function (f) { return f.length; }).concat([1]));
    var lado = Math.min(84, Math.floor(860 / maxCols) - 12), sep = 12, alto = filas.length * (lado + sep);
    var y = 790 + Math.max(0, (400 - alto) / 2);
    var colores = { ok: "#f5b700", cerca: "#8fa0c9", mal: "#3a5394", vacio: "#10275f" };
    filas.forEach(function (f) {
      var x = (W - (f.length * (lado + sep) - sep)) / 2;
      f.forEach(function (est) { g.fillStyle = colores[est] || colores.vacio; g.beginPath(); if (g.roundRect) g.roundRect(x, y, lado, lado, 10); else g.rect(x, y, lado, lado); g.fill(); x += lado + sep; });
      y += lado + sep;
    });
    g.fillStyle = "#c5d0ea"; g.font = "500 34px 'Barlow', system-ui, sans-serif"; g.textAlign = "center";
    g.fillText("Jugá en Rincón Bostero · " + hoyTxt().split("-").reverse().join("/"), W / 2, H - 70);
    return c;
  }
  function bloqueCompartir(cfg) {
    return "<div class='compartir-caja' data-compartir><div class='compartir-img'><img alt='Imagen con tu resultado para compartir'></div>" +
      "<div class='compartir'><button type='button' class='boton' data-accion='imagen'>Compartir imagen</button>" +
      "<a class='boton secundario' target='_blank' rel='noopener' href='https://wa.me/?text=" + encodeURIComponent(cfg.texto) + "'>Mandar por WhatsApp</a>" +
      "<button type='button' class='boton secundario' data-copiar='" + esc(cfg.texto) + "'>Copiar resultado</button></div></div>";
  }
  function activarCompartir(caja, cfg) {
    var el = caja.querySelector("[data-compartir]");
    if (!el) return;
    var listo = (document.fonts && document.fonts.load) ? Promise.all([
      document.fonts.load("800 100px 'Barlow Condensed'"), document.fonts.load("600 40px 'Barlow'")]).catch(function () {}) : Promise.resolve();
    var esperarLogo = new Promise(function (r) { if (LOGO.complete) r(); else { LOGO.onload = r; LOGO.onerror = r; } });
    Promise.all([listo, esperarLogo]).then(function () {
      var canvas = dibujarResultado(cfg);
      el.querySelector("img").src = canvas.toDataURL("image/png");
      el.querySelector("[data-accion='imagen']").addEventListener("click", function () {
        canvas.toBlob(function (blob) {
          var archivo = new File([blob], "rincon-bostero-" + hoyTxt() + ".png", { type: "image/png" });
          if (navigator.canShare && navigator.canShare({ files: [archivo] })) {
            navigator.share({ files: [archivo], text: cfg.texto }).catch(function () {});
          } else {
            var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = archivo.name; a.click();
            setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
          }
        }, "image/png");
      });
    });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copiar]");
    if (!b) return;
    var original = b.textContent;
    var listo = function () { b.textContent = "Copiado"; setTimeout(function () { b.textContent = original; }, 2000); };
    try { navigator.clipboard.writeText(b.getAttribute("data-copiar")).then(listo, function () { b.textContent = "No se pudo copiar"; }); }
    catch (err) { b.textContent = "No se pudo copiar"; }
  });

  function pantallaFinal(caja, o) {
    // o: {etiqueta, puntaje, total, frase, extra, botones, compartir}
    caja.innerHTML = "<div class='marcador final'><p class='m-etiqueta'>" + esc(o.etiqueta) + "</p>" +
      "<p class='m-puntaje'><b data-contar>" + o.puntaje + "</b>" + (o.total ? "<small>/" + o.total + "</small>" : "") + "</p>" +
      "<p class='m-frase'>" + esc(o.frase) + "</p>" + (o.extra || "") + "</div>" +
      (o.botones ? "<div class='compartir acciones-final'>" + o.botones + "</div>" : "") +
      (o.compartir ? bloqueCompartir(o.compartir) : "");
    contar(caja.querySelector("[data-contar]"), Number(o.puntaje) || 0);
    if (o.compartir) activarCompartir(caja, o.compartir);
  }

  // ------------------------------------------------------ motor de preguntas --
  var LETRAS = "ABCD";
  function jugarPreguntas(caja, preguntas, corregir, alTerminar, previas, alResponder) {
    var hechas = (previas || []).slice();
    function puntos() {
      return "<ol class='m-puntos' aria-hidden='true'>" + preguntas.map(function (_, i) {
        var h = hechas[i]; return "<li class='" + (h ? (h.opcion === h.correcta ? "ok" : "mal") : i === hechas.length ? "actual" : "") + "'></li>";
      }).join("") + "</ol>";
    }
    function pintar() {
      if (hechas.length >= preguntas.length) return alTerminar(hechas);
      var i = hechas.length, q = preguntas[i];
      caja.innerHTML = "<div class='marcador'><div class='m-arriba'><span class='m-tema'>" + esc(D.temas[q.tema] || "") + "</span>" +
        "<span class='m-cuenta'>" + (i + 1) + "<small>/" + preguntas.length + "</small></span></div>" + puntos() +
        "<h3 class='m-pregunta'>" + esc(q.texto) + "</h3><div class='opciones'>" + q.opciones.map(function (o, k) {
          return "<button type='button' class='opcion' data-k='" + k + "'><span class='op-letra'>" + LETRAS[k] + "</span><span class='op-texto'>" + esc(o) + "</span></button>";
        }).join("") + "</div><div class='juego-dato' aria-live='polite'></div></div>";
      caja.querySelectorAll(".opcion").forEach(function (b) { b.addEventListener("click", function () { responder(+b.getAttribute("data-k")); }); });
    }
    function responder(k) {
      var q = preguntas[hechas.length];
      caja.querySelectorAll(".opcion").forEach(function (b) { b.disabled = true; });
      caja.querySelector(".juego-dato").innerHTML = "<p class='m-nota'>Corrigiendo…</p>";
      corregir(q, k).then(function (r) {
        var elegida = r.opcion_valida != null ? r.opcion_valida : k;
        hechas.push({ opcion: elegida, correcta: r.correcta });
        caja.querySelectorAll(".opcion").forEach(function (b, j) { if (j === r.correcta) b.classList.add("ok"); else if (j === elegida) b.classList.add("mal"); });
        var bien = elegida === r.correcta;
        caja.querySelector(".m-puntos").outerHTML = puntos();
        caja.querySelector(".juego-dato").innerHTML = "<p class='m-veredicto " + (bien ? "bien" : "mal") + "'><b>" + (bien ? "¡Bien ahí!" : "No era esa.") + "</b> " +
          esc(r.dato || ("La respuesta es " + q.opciones[r.correcta] + ".")) + "</p>" +
          "<button type='button' class='boton siguiente'>" + (hechas.length === preguntas.length ? "Ver resultado" : "Siguiente") + "</button>";
        caja.querySelector(".siguiente").addEventListener("click", pintar);
        caja.querySelector(".siguiente").focus({ preventScroll: true });
        if (alResponder) alResponder(hechas);
      }).catch(function () {
        caja.querySelectorAll(".opcion").forEach(function (b) { b.disabled = false; });
        caja.querySelector(".juego-dato").innerHTML = "<p class='m-nota'>No se pudo corregir. Revisá la conexión y tocá de nuevo una opción.</p>";
      });
    }
    pintar();
  }
  function aciertos(h) { return h.filter(function (x) { return x.opcion === x.correcta; }).length; }
  function fila(h) { return h.map(function (x) { return x.opcion === x.correcta ? "🟨" : "⬛"; }).join(""); }
  function celdasDe(h) { return [h.map(function (x) { return x.opcion === x.correcta ? "ok" : "mal"; })]; }
  function corregirLocal(q) { return Promise.resolve({ correcta: q.correcta, dato: q.dato }); }

  // ---------------------------------------------------- 1. Pregunta del día --
  function preguntasDelDiaLocal() {
    var n = numeroDelDia(), cupos = { titulos: 2, superclasico: 1, rivales: 2, historia: 2, idolos: 2, temporada: 1 };
    var elegidas = [], usadas = {};
    Object.keys(cupos).forEach(function (t) {
      var lista = mezclar(D.preguntas.filter(function (q) { return q.tema === t; }).sort(function (a, b) { return a.id < b.id ? -1 : 1; }), azar(semilla("rotacion-" + t)));
      for (var i = 0; i < cupos[t] && lista.length; i++) { var q = lista[((n - 1) * cupos[t] + i) % lista.length]; if (!usadas[q.id]) { elegidas.push(q); usadas[q.id] = 1; } }
    });
    var resto = mezclar(D.preguntas.filter(function (q) { return !usadas[q.id]; }), azar(semilla("dia" + hoyTxt())));
    return mezclar(elegidas.concat(resto.slice(0, 10 - elegidas.length)), azar(semilla("orden" + hoyTxt())));
  }
  function finDelDia(caja, hechas, rachaServidor) {
    var hoy = hoyTxt(), racha = leer("racha", { ultimo: "", dias: 0 });
    if (racha.ultimo !== hoy) { racha = { ultimo: hoy, dias: racha.ultimo === ayerTxt() ? racha.dias + 1 : 1 }; guardar("racha", racha); }
    var dias = rachaServidor != null ? rachaServidor : racha.dias, n = aciertos(hechas);
    guardar("res-dia-" + hoy, n);
    pintarEstados();
    var frase = n === 10 ? "¡Perfecto! Sabés todo de Boca." : n >= 8 ? "¡Muy bien! Bostero de ley." : n >= 5 ? "Bien, pero se puede mejorar." : "Hay que repasar la historia.";
    var extra = "<p class='m-nota'>Racha: " + plural(dias, "día seguido", "días seguidos") + ". Mañana hay 10 preguntas nuevas.</p>" +
      (sb ? (perfil && perfil.apodo ? "<p class='m-nota'>Sumaste " + n + " puntos al ranking. <a href='#ranking'>Ver ranking</a></p>"
        : "<p class='m-nota'>Entrá con tu cuenta (arriba) para que tus aciertos sumen en el ranking.</p>") : "");
    pantallaFinal(caja, { etiqueta: "Pregunta del día #" + numeroDelDia(), puntaje: n, total: 10, frase: frase, extra: extra,
      compartir: { juego: "Pregunta del día #" + numeroDelDia(), puntaje: n, total: 10, linea: "Racha: " + plural(dias, "día", "días"), celdas: celdasDe(hechas),
        texto: firma() + "Pregunta xeneize del día #" + numeroDelDia() + "\n" + n + "/10 " + fila(hechas) + "\nRacha: " + plural(dias, "día", "días") + "\n" + URL_JUEGOS } });
  }
  function iniciarDia() {
    var caja = document.getElementById("juego-dia");
    if (!caja) return;
    var clave = "dia-" + hoyTxt();
    if (!sb) {
      var preguntas = preguntasDelDiaLocal();
      if (preguntas.length < 10) { caja.innerHTML = "<p class='vacio'>Las preguntas aparecen cuando se cargan los datos.</p>"; return; }
      jugarPreguntas(caja, preguntas, corregirLocal, function (h) { finDelDia(caja, h); }, leer(clave, { hechas: [] }).hechas || [],
        function (h) { guardar(clave, { hechas: h }); pintarEstados(); });
      return;
    }
    caja.innerHTML = "<p class='nota-dato'>Cargando las preguntas de hoy…</p>";
    rpc("desafio_hoy").then(function (filas) {
      var preguntas = filas.map(function (f) { return { id: f.id, tema: f.tema, texto: f.texto, opciones: f.opciones }; });
      var previas = [];
      if (perfil && perfil.apodo) filas.every(function (f) { if (f.respondida == null) return false; previas.push({ opcion: f.respondida, correcta: f.era_correcta }); return true; });
      else previas = leer(clave, { hechas: [] }).hechas || [];
      jugarPreguntas(caja, preguntas, function (q, k) { return rpc("responder_dia", { p_pregunta: q.id, p_opcion: k }); },
        function (h) {
          if (perfil && perfil.apodo) rpc("mi_resumen").then(function (r) { perfil = r; pintarCuenta(); revisarInsigniasCuenta(); finDelDia(caja, h, r.racha); }).catch(function () { finDelDia(caja, h); });
          else finDelDia(caja, h);
        }, previas, function (h) { guardar(clave, { hechas: h }); pintarEstados(); });
    }).catch(function () { errorConexion(caja); });
  }

  // ------------------------------------------------------- 2. ¿Más o menos? --
  function caraHTML(x, g, k) {
    var foto = x.foto ? "<img src='" + esc(x.foto) + "' alt='' loading='lazy'>" : "<span class='cara-iniciales'>" + esc(iniciales(x.nombre)) + "</span>";
    return "<button type='button' class='cara' data-k='" + k + "'><span class='cara-foto'>" + foto + "</span>" +
      "<span class='cara-nombre'>" + esc(x.nombre) + "</span><span class='cara-valor' aria-live='polite'><b>?</b>" +
      (g.unidad ? "<small>" + esc(g.unidad) + "</small>" : "") + "</span>" +
      (x.credito ? "<span class='cara-credito'>Foto: " + esc(x.credito) + "</span>" : "") + "</button>";
  }
  function iniciarMasOMenos() {
    var caja = document.getElementById("juego-mom");
    if (!caja) return;
    if (!D.mas_o_menos.length) { caja.innerHTML = "<p class='vacio'>Este juego aparece cuando se cargan los datos.</p>"; return; }
    var racha = 0, record = leer("mom-record", 0), ultimo = null;
    var celdas = [];
    function ronda() {
      // Más seguido los duelos de personas (con foto), que son los más lindos de jugar
      var personas = D.mas_o_menos.filter(function (g) { return g.personas; });
      var pool = personas.length && Math.random() < 0.6 ? personas : D.mas_o_menos;
      var g = pool[Math.floor(Math.random() * pool.length)];
      if (g === ultimo && D.mas_o_menos.length > 1 && Math.random() < 0.7) g = D.mas_o_menos[Math.floor(Math.random() * D.mas_o_menos.length)];
      ultimo = g;
      var a, b, n = 0;
      do { a = g.items[Math.floor(Math.random() * g.items.length)]; b = g.items[Math.floor(Math.random() * g.items.length)]; } while ((a === b || a.valor === b.valor) && ++n < 60);
      if (a.valor === b.valor) return ronda();
      var gana = g.menor ? (a.valor < b.valor ? 0 : 1) : (a.valor > b.valor ? 0 : 1);
      caja.innerHTML = "<div class='marcador'><div class='m-arriba'><span class='m-tema'>Racha " + racha + "</span><span class='m-tema'>Récord " + record + "</span></div>" +
        "<h3 class='m-pregunta'>" + esc(g.pregunta) + "</h3><div class='duelo-caras'>" + caraHTML(a, g, 0) + "<span class='vs-caras'>o</span>" + caraHTML(b, g, 1) + "</div>" +
        (g.fuente ? "<p class='m-fuente'>Datos: " + esc(g.fuente) + ".</p>" : "") + "<div class='juego-dato' aria-live='polite'></div></div>";
      caja.querySelectorAll(".cara").forEach(function (bt) {
        bt.addEventListener("click", function () {
          var k = +bt.getAttribute("data-k");
          caja.querySelectorAll(".cara").forEach(function (x, j) {
            x.disabled = true; x.classList.add(j === gana ? "gana" : "pierde");
            contar(x.querySelector(".cara-valor b"), [a, b][j].valor);
          });
          bt.classList.add("elegida");
          var dato = caja.querySelector(".juego-dato");
          if (k === gana) {
            racha++; celdas.push("ok");
            if (racha > record) { record = racha; guardar("mom-record", record); pintarEstados(); }
            if (racha >= 10) ganar("mom10");
            dato.innerHTML = "<p class='m-veredicto bien'><b>¡Bien!</b> Racha de " + racha + ".</p><button type='button' class='boton siguiente'>Seguir</button>";
            dato.querySelector(".siguiente").addEventListener("click", ronda);
            dato.querySelector(".siguiente").focus({ preventScroll: true });
          } else {
            var final = racha; racha = 0;
            setTimeout(function () {
              var c = celdas.concat(["mal"]); celdas = [];
              var filas = []; for (var i = 0; i < c.length; i += 10) filas.push(c.slice(i, i + 10));
              pantallaFinal(caja, { etiqueta: "¿Más o menos?", puntaje: final, frase: final >= 10 ? "¡Tremenda racha!" : final >= 5 ? "Buena racha." : "Se cortó rápido. ¡Otra!",
                extra: "<p class='m-nota'>Tu récord: " + record + ".</p>",
                botones: "<button type='button' class='boton' data-otra>Jugar de nuevo</button>",
                compartir: { juego: "¿Más o menos?", puntaje: final, linea: final === 1 ? "1 acierto seguido" : final + " aciertos seguidos", celdas: filas.slice(-4),
                  texto: firma() + "Hice una racha de " + final + " en ¿Más o menos? de Rincón Bostero. Mi récord: " + record + ".\n" + URL_JUEGOS + "#mas-o-menos" } });
              caja.querySelector("[data-otra]").addEventListener("click", ronda);
            }, REDUCIR ? 300 : 1400);
            dato.innerHTML = "<p class='m-veredicto mal'><b>Uh, no.</b> Se cortó la racha.</p>";
          }
        });
      });
    }
    ronda();
  }

  // -------------------------------------------------------- 3. Trivia por temas --
  function iniciarTrivia() {
    var caja = document.getElementById("juego-trivia");
    if (!caja) return;
    function menu() {
      caja.innerHTML = (sb ? "<p class='nota-dato'>La primera partida de cada tema del día suma al ranking.</p>" : "") +
        "<div class='temas'>" + Object.keys(D.temas).map(function (t) {
          var cant = Math.min(10, D.cantidades[t] || 0), mejor = leer("trivia-" + t, null);
          return "<button type='button' class='tema' data-t='" + t + "'><b>" + esc(D.temas[t]) + "</b><span>" + cant + " preguntas" +
            (mejor !== null ? " · tu mejor: " + mejor + "/" + cant : "") + "</span></button>";
        }).join("") + "</div>";
      caja.querySelectorAll(".tema").forEach(function (b) { b.addEventListener("click", function () { jugar(b.getAttribute("data-t")); }); });
    }
    function terminar(t, h, sumo) {
      var n = aciertos(h), mejor = leer("trivia-" + t, -1);
      if (n > mejor) guardar("trivia-" + t, n);
      pintarEstados();
      var extra = sb ? "<p class='m-nota'>" + (sumo ? "Sumaste " + n + " puntos al ranking." : perfil && perfil.apodo ?
        "Esta partida no suma: solo cuenta la primera de cada tema por día." : "Entrá con tu cuenta para sumar al ranking.") + "</p>" : "";
      pantallaFinal(caja, { etiqueta: D.temas[t], puntaje: n, total: h.length, frase: n >= 8 ? "¡Sabés mucho!" : n >= 5 ? "Bien." : "A repasar.", extra: extra,
        botones: "<button type='button' class='boton' data-otra>Jugar otra vez</button><button type='button' class='boton secundario' data-menu>Elegir otro tema</button>",
        compartir: { juego: "Trivia: " + D.temas[t], puntaje: n, total: h.length, linea: D.temas[t], celdas: celdasDe(h),
          texto: firma() + "Trivia de Rincón Bostero: " + D.temas[t] + "\n" + n + "/" + h.length + " " + fila(h) + "\n" + URL_JUEGOS + "#trivia" } });
      caja.querySelector("[data-otra]").addEventListener("click", function () { jugar(t); });
      caja.querySelector("[data-menu]").addEventListener("click", menu);
    }
    function jugar(t) {
      if (!sb) {
        var lista = mezclar(D.preguntas.filter(function (q) { return q.tema === t; }), Math.random).slice(0, 10);
        return jugarPreguntas(caja, lista, corregirLocal, function (h) { terminar(t, h, false); });
      }
      caja.innerHTML = "<p class='nota-dato'>Armando la partida…</p>";
      rpc("trivia_iniciar", { p_tema: t }).then(function (r) {
        jugarPreguntas(caja, r.preguntas, function (q, k) { return rpc("responder_trivia", { p_sesion: r.sesion, p_pregunta: q.id, p_opcion: k }); },
          function (h) { terminar(t, h, r.suma); if (perfil && perfil.apodo) rpc("mi_resumen").then(function (x) { perfil = x; revisarInsigniasCuenta(); pintarEstados(); }); });
      }).catch(function () { errorConexion(caja); });
    }
    menu();
  }

  // ------------------------------------------------------ 4. Adiviná el ídolo --
  var BLUR = [26, 19, 13, 8, 5, 3];
  function idoloDelDia() { return D.idolos[Math.floor(azar(semilla("idolo" + hoyTxt()))() * D.idolos.length)]; }
  function iniciarIdolo() {
    var caja = document.getElementById("juego-idolo");
    if (!caja) return;
    if (D.idolos.length < 5) { caja.innerHTML = "<p class='vacio'>Este juego aparece cuando se cargan los datos.</p>"; return; }
    var MAX = 6, hoy = hoyTxt();
    var opciones = D.idolos.map(function (i) { return "<option value='" + esc(i.nombre) + "'>"; }).join("");
    function partida(secreto, claveGuardado) {
      var intentos = (claveGuardado ? leer(claveGuardado, []) : []).map(function (n) { return D.idolos.filter(function (i) { return i.nombre === n; })[0]; }).filter(Boolean);
      function celda(ok, texto, cerca) { return "<td class='" + (ok ? "c-ok" : cerca ? "c-cerca" : "c-no") + "'>" + texto + "</td>"; }
      function filaIntento(g) {
        var dif = secreto.debut - g.debut;
        return "<tr><th scope='row'>" + esc(g.nombre) + "</th>" + celda(g.posicion === secreto.posicion, esc(g.posicion)) + celda(g.pais === secreto.pais, esc(g.pais)) +
          celda(dif === 0, g.debut + (dif === 0 ? "" : dif > 0 ? " ↑" : " ↓"), Math.abs(dif) <= 5) +
          celda(g.libertadores === secreto.libertadores, g.libertadores ? "Sí" : "No") + celda(g.intercontinental === secreto.intercontinental, g.intercontinental ? "Sí" : "No") + "</tr>";
      }
      function estados(g) {
        return [g.posicion === secreto.posicion, g.pais === secreto.pais, g.debut === secreto.debut, g.libertadores === secreto.libertadores, g.intercontinental === secreto.intercontinental]
          .map(function (ok, i) { return ok ? "ok" : (i === 2 && Math.abs(g.debut - secreto.debut) <= 5 ? "cerca" : "mal"); });
      }
      function pintar() {
        var gano = intentos.some(function (g) { return g.nombre === secreto.nombre; });
        var termino = gano || intentos.length >= MAX;
        var blur = termino ? 0 : BLUR[Math.min(intentos.length, BLUR.length - 1)];
        var foto = secreto.foto ? "<div class='idolo-foto" + (termino ? " revelada" : "") + "'><img src='" + esc(secreto.foto) + "' alt='" + (termino ? esc(secreto.nombre) : "Foto borrosa del ídolo") +
          "' style='filter: blur(" + blur + "px)" + (termino ? "" : " grayscale(1)") + "'>" + (termino && secreto.credito ? "<span class='cara-credito'>Foto: " + esc(secreto.credito) + "</span>" : "") + "</div>"
          : "<div class='idolo-foto sin-foto'><svg viewBox='0 0 80 80' aria-hidden='true'><circle cx='40' cy='28' r='15'/><path d='M12 78c2-18 14-28 28-28s26 10 28 28z'/></svg></div>";
        var pista = !termino && intentos.length >= 3 && secreto.apodo ? "<p class='pista'>Pista: le dicen <b>" + esc(secreto.apodo) + "</b>.</p>" : "";
        var tabla = intentos.length ? "<div class='tabla-scroll'><table class='tabla-idolo'><thead><tr><th class='izq'>Jugador</th><th>Posición</th><th>País</th>" +
          "<th title='Año en que llegó a Boca'>Llegó</th><th title='Ganó la Libertadores con Boca'>Libert.</th><th title='Ganó la Intercontinental con Boca'>Interc.</th></tr></thead><tbody>" +
          intentos.map(filaIntento).join("") + "</tbody></table></div>" : "";
        var abajo, cfg = null;
        if (termino) {
          if (claveGuardado) { guardar("res-idolo-" + hoy, gano ? intentos.length : 0); if (gano && intentos.length <= 2) ganar("scout"); pintarEstados(); }
          var res = gano ? intentos.length + "/" + MAX : "X/" + MAX;
          cfg = { juego: "Adiviná el ídolo" + (claveGuardado ? " #" + numeroDelDia() : ""), puntaje: gano ? intentos.length : "X", total: MAX,
            linea: gano ? "Lo saqué en " + plural(intentos.length, "intento", "intentos") : "Esta vez no salió", celdas: intentos.map(estados),
            texto: firma() + "Adiviná el ídolo de Rincón Bostero" + (claveGuardado ? " #" + numeroDelDia() : "") + "\n" + res + "\n" +
              intentos.map(function (g) { return estados(g).map(function (x) { return x === "ok" ? "🟩" : x === "cerca" ? "🟨" : "⬜"; }).join(""); }).join("\n") + "\n" + URL_JUEGOS + "#idolo" };
          abajo = "<div class='idolo-final'><p>" + (gano ? "<b>¡Lo sacaste!</b> Era " : "<b>Se terminaron los intentos.</b> Era ") + "<b>" + esc(secreto.nombre) + "</b>" +
            (secreto.apodo ? " (" + esc(secreto.apodo) + ")" : "") + ": " + esc(secreto.posicion.toLowerCase()) + ", " + esc(secreto.pais) + ", llegó a Boca en " + secreto.debut + ".</p>" +
            bloqueCompartir(cfg) + "<button type='button' class='boton secundario' id='idolo-practica'>Jugar con otro ídolo</button></div>";
        } else {
          abajo = "<form class='idolo-form' autocomplete='off'><label for='idolo-input' class='oculto'>Jugador</label>" +
            "<input id='idolo-input' list='lista-idolos' placeholder='Escribí un jugador…'><datalist id='lista-idolos'>" + opciones + "</datalist>" +
            "<button class='boton' type='submit'>Probar</button></form><p class='nota-dato' id='idolo-msg'>Intento " + (intentos.length + 1) + " de " + MAX + "." + (secreto.foto ? " La foto se aclara con cada intento." : "") + "</p>" + pista;
        }
        caja.innerHTML = "<div class='idolo'><div>" + foto + "</div><div class='idolo-juego'><h3 class='juego-pregunta'>" +
          (claveGuardado ? "¿Quién es el ídolo de hoy?" : "Modo práctica: ¿quién es?") + "</h3>" +
          "<p class='nota-dato'>Verde: coincide. Amarillo: llegó con menos de 5 años de diferencia. La flecha dice si llegó antes o después.</p>" + tabla + abajo + "</div></div>";
        if (cfg) activarCompartir(caja, cfg);
        var form = caja.querySelector(".idolo-form");
        if (form) form.addEventListener("submit", function (e) {
          e.preventDefault();
          var v = normal(caja.querySelector("#idolo-input").value);
          var g = D.idolos.filter(function (i) { return normal(i.nombre) === v || normal(i.apodo) === v; })[0] ||
            D.idolos.filter(function (i) { return normal(i.nombre).indexOf(v) >= 0 && v.length >= 4; })[0];
          if (!g) { caja.querySelector("#idolo-msg").textContent = "No está en la lista. Elegí uno de los que aparecen al escribir."; return; }
          if (intentos.some(function (x) { return x.nombre === g.nombre; })) return;
          intentos.push(g);
          if (claveGuardado) guardar(claveGuardado, intentos.map(function (x) { return x.nombre; }));
          pintar();
          var inp = caja.querySelector("#idolo-input"); if (inp) inp.focus({ preventScroll: true });
        });
        var prac = caja.querySelector("#idolo-practica");
        if (prac) prac.addEventListener("click", function () { partida(D.idolos[Math.floor(Math.random() * D.idolos.length)], null); });
      }
      pintar();
    }
    partida(idoloDelDia(), "idolo-" + hoy);
  }

  // ------------------------------------------------------ 5. ¿En qué año fue? --
  var ANIO_MIN = 1905, ANIO_MAX = new Date().getFullYear();
  function puntosAnio(dif) { return Math.max(0, 100 - 10 * Math.abs(dif)); }
  function eventosDelDia(r) {
    var cupo = { "Título": 3, "Superclásico": 2, "Récord": 1 }, usados = {}, out = [];
    mezclar(D.anio, r).forEach(function (e) {
      if (out.length >= 5) return;
      usados[e.tipo] = (usados[e.tipo] || 0) + 1;
      if (usados[e.tipo] <= (cupo[e.tipo] || 2)) out.push(e);
    });
    return out;
  }
  function iniciarAnio() {
    var caja = document.getElementById("juego-anio");
    if (!caja) return;
    if (!D.anio || D.anio.length < 10) { caja.innerHTML = "<p class='vacio'>Este juego aparece cuando se cargan los datos.</p>"; return; }
    function partida(eventos, clave) {
      var rondas = clave ? (leer(clave, { rondas: [] }).rondas || []) : [];
      function pintar() {
        if (rondas.length >= eventos.length) return final();
        var ev = eventos[rondas.length], valor = 1960;
        caja.innerHTML = "<div class='marcador'><div class='m-arriba'><span class='m-tema'>" + esc(ev.tipo) + "</span><span class='m-cuenta'>" + (rondas.length + 1) + "<small>/" + eventos.length + "</small></span></div>" +
          "<ol class='m-puntos' aria-hidden='true'>" + eventos.map(function (_, i) { var x = rondas[i]; return "<li class='" + (x ? (x.puntos >= 90 ? "ok" : x.puntos >= 50 ? "cerca" : "mal") : i === rondas.length ? "actual" : "") + "'></li>"; }).join("") + "</ol>" +
          "<h3 class='m-pregunta'>" + esc(ev.texto) + "</h3>" +
          "<div class='anio-elegir'><output class='anio-valor' id='anio-valor'>" + valor + "</output>" +
          "<input type='range' id='anio-rango' min='" + ANIO_MIN + "' max='" + ANIO_MAX + "' value='" + valor + "' aria-label='Año'>" +
          "<div class='anio-botones'>" + [-10, -1, 1, 10].map(function (d) { return "<button type='button' class='boton secundario' data-d='" + d + "'>" + (d > 0 ? "+" : "−") + Math.abs(d) + "</button>"; }).join("") + "</div>" +
          "<button type='button' class='boton' id='anio-ok'>Confirmar " + valor + "</button></div><div class='juego-dato' aria-live='polite'></div></div>";
        var rango = caja.querySelector("#anio-rango"), sal = caja.querySelector("#anio-valor"), ok = caja.querySelector("#anio-ok");
        function poner(v) { valor = Math.max(ANIO_MIN, Math.min(ANIO_MAX, v)); rango.value = valor; sal.textContent = valor; ok.textContent = "Confirmar " + valor; }
        rango.addEventListener("input", function () { poner(+rango.value); });
        caja.querySelectorAll("[data-d]").forEach(function (b) { b.addEventListener("click", function () { poner(valor + +b.getAttribute("data-d")); }); });
        ok.addEventListener("click", function () {
          var dif = valor - ev.anio, pts = puntosAnio(dif);
          rondas.push({ id: ev.id, eleccion: valor, puntos: pts });
          if (clave) guardar(clave, { rondas: rondas });
          if (dif === 0) ganar("archivo");
          caja.querySelectorAll(".anio-elegir button, .anio-elegir input").forEach(function (x) { x.disabled = true; });
          sal.textContent = ev.anio; sal.classList.add(pts >= 90 ? "bien" : pts >= 50 ? "cerca" : "lejos");
          ok.textContent = dif === 0 ? "Elegiste " + valor + ": ¡justo!" : "Elegiste " + valor; ok.classList.add("elegido");
          caja.querySelector(".juego-dato").innerHTML = "<p class='m-veredicto " + (pts >= 50 ? "bien" : "mal") + "'><b>" +
            (dif === 0 ? "¡Exacto!" : "Era " + ev.anio + ". Te fuiste por " + plural(Math.abs(dif), "año", "años") + ".") + "</b> +" + pts + " puntos. " + esc(ev.dato || "") + "</p>" +
            "<button type='button' class='boton siguiente'>" + (rondas.length === eventos.length ? "Ver resultado" : "Siguiente") + "</button>";
          caja.querySelector(".siguiente").addEventListener("click", pintar);
          caja.querySelector(".siguiente").focus({ preventScroll: true });
          pintarEstados();
        });
      }
      function final() {
        var total = rondas.reduce(function (s, x) { return s + x.puntos; }, 0);
        if (clave) { guardar("res-anio-" + hoyTxt(), total); pintarEstados(); }
        if (total >= 400) ganar("historiador");
        var est = rondas.map(function (x) { return x.puntos >= 90 ? "ok" : x.puntos >= 50 ? "cerca" : "mal"; });
        pantallaFinal(caja, { etiqueta: "¿En qué año fue?" + (clave ? " #" + numeroDelDia() : " · práctica"), puntaje: total, total: 500,
          frase: total >= 400 ? "Memoria de historiador." : total >= 250 ? "Muy bien." : "La historia es larga: ¡a seguir!",
          botones: "<button type='button' class='boton secundario' data-mas>Jugar 5 más (práctica)</button>",
          compartir: clave ? { juego: "¿En qué año fue? #" + numeroDelDia(), puntaje: total, total: 500, linea: rondas.map(function (x) { return "+" + x.puntos; }).join("  "), celdas: [est],
            texto: firma() + "¿En qué año fue? #" + numeroDelDia() + " de Rincón Bostero\n" + total + "/500 " + est.map(function (s) { return s === "ok" ? "🟨" : s === "cerca" ? "🟦" : "⬛"; }).join("") + "\n" + URL_JUEGOS + "#anio" } : null });
        caja.querySelector("[data-mas]").addEventListener("click", function () { partida(eventosDelDia(Math.random), null); });
      }
      pintar();
    }
    partida(eventosDelDia(azar(semilla("anio" + hoyTxt()))), "anio-" + hoyTxt());
  }

  // -------------------------------------------------------- 6. Grilla bostera --
  var GRILLA = null;
  var NIVELES_GRILLA = ["facil", "intermedio", "dificil", "experto"];
  function nivelesGrilla(G) { return G.niveles && G.pj ? NIVELES_GRILLA.filter(function (k) { return G.niveles[k]; }) : []; }
  function armarGrilla(G, r, nivel, evitar) {
    var n = G.clubes.length, miembros = G.clubes.map(function () { return []; });
    G.jugadores.forEach(function (j, idx) { for (var k = 1; k < j.length; k++) miembros[j[k]].push(idx); });
    var conjuntos = miembros.map(function (l) { var s = {}; l.forEach(function (x) { s[x] = 1; }); return s; });
    function cruce(a, b) { var m = miembros[a].length < miembros[b].length ? [a, b] : [b, a]; return miembros[m[0]].filter(function (x) { return conjuntos[m[1]][x]; }); }
    function esSel(i) { return /^Selección/.test(G.clubes[i]); }
    // fama de un casillero: partidos en Boca del jugador más conocido que lo resuelve (tope 300)
    function fama(x) { var m = 0; x.forEach(function (i) { var p = G.pj[i] || 0; if (p > m) m = p; }); return Math.min(m, 300); }
    var cfg = nivel && G.niveles && G.pj ? G.niveles[nivel] : null;
    var tope = cfg ? Math.min(cfg.clubes, n) : Math.min(24, n);
    var todos = G.clubes.map(function (_, i) { return i; }).slice(0, tope);
    function probar(pool, aceptar, intentos) {
      if (pool.length < 6) return null;
      for (var intento = 0; intento < intentos; intento++) {
        var elegidos = mezclar(pool, r).slice(0, 6);
        var filas = elegidos.slice(0, 3), cols = elegidos.slice(3);
        if (filas.filter(esSel).length > 1 || cols.filter(esSel).length > 1) continue;
        var resp = [], ok = true;
        for (var f = 0; f < 3 && ok; f++) for (var c = 0; c < 3; c++) { var x = cruce(filas[f], cols[c]); if (!aceptar.celda(x)) { ok = false; break; } resp.push(x); }
        if (ok && (!aceptar.total || aceptar.total(resp))) return { filas: filas, cols: cols, resp: resp, nivel: nivel || null };
      }
      return null;
    }
    var g = null;
    if (cfg) {
      var conNivel = {
        celda: function (x) { return x.length >= (cfg.resp || 1) && fama(x) >= (cfg.piso || 0); },
        total: function (resp) { var m = resp.reduce(function (s, x) { return s + fama(x); }, 0) / 9; return m >= cfg.media[0] && m < cfg.media[1]; }
      };
      // Primero sin los clubes de la grilla de ayer del mismo nivel, para que no se repitan siempre los mismos.
      var sinAyer = evitar ? todos.filter(function (i) { return evitar.indexOf(i) < 0; }) : null;
      if (sinAyer) g = probar(sinAyer, conNivel, 4000);
      if (!g) g = probar(todos, conNivel, 6000);
    }
    for (var minimo = 3; !g && minimo >= 1; minimo--) g = probar(todos, { celda: function (x) { return x.length >= minimo; } }, 3000);
    if (g && nivel) g.nivel = nivel;
    return g;
  }
  function iniciarGrilla() {
    var caja = document.getElementById("juego-grilla");
    if (!caja || caja.getAttribute("data-listo")) return;
    caja.setAttribute("data-listo", "1");
    caja.innerHTML = "<p class='nota-dato'>Armando la grilla…</p>";
    fetch("grilla.json").then(function (r) { if (!r.ok) throw r; return r.json(); }).then(function (G) {
      GRILLA = G;
      var marco = caja, niveles = nivelesGrilla(G), nivel = null;
      if (niveles.length) {
        nivel = leer("grilla-nivel", "intermedio");
        if (niveles.indexOf(nivel) < 0) nivel = niveles[0];
        marco.innerHTML = "<div class='g-niveles' role='group' aria-label='Dificultad'></div><p class='nota-dato g-nivel-info'></p><div class='g-juego'></div>";
        caja = marco.querySelector(".g-juego");
      }
      function nombreNivel(k) { return G.niveles && G.niveles[k] ? G.niveles[k].nombre || k : ""; }
      function claveNivel(k) { return k ? k + "-" : ""; }
      function pintarNiveles() {
        if (!niveles.length) return;
        var hoy = hoyTxt(), st = leer("grilla-stats", {});
        marco.querySelector(".g-niveles").innerHTML = niveles.map(function (k) {
          var res = leer("res-grilla-" + k + "-" + hoy, null);
          return "<button type='button' class='g-nivel n-" + k + (k === nivel ? " activo" : "") + "' data-nivel='" + k + "' aria-pressed='" + (k === nivel) + "'>" +
            esc(nombreNivel(k)) + "<small>" + (res != null ? "Hoy " + res + "/9" : "Sin jugar") + "</small></button>";
        }).join("");
        var e = st[nivel];
        marco.querySelector(".g-nivel-info").innerHTML = (nivel === "facil" ? "Casilleros con jugadores de muchos partidos en Boca." :
          nivel === "intermedio" ? "Jugadores conocidos, no siempre los primeros que se te vienen a la cabeza." :
          nivel === "dificil" ? "Menos partidos, etapas menos recordadas." : "Pasos cortos y otras épocas: para los que saben de verdad.") +
          (e && e.jugadas ? " Tus números en " + esc(nombreNivel(nivel)) + ": " + plural(e.jugadas, "grilla", "grillas") + ", promedio " +
            (e.casilleros / e.jugadas).toFixed(1).replace(".", ",") + "/9" + (e.llenas ? ", " + plural(e.llenas, "llena", "llenas") : "") + "." : "");
        marco.querySelectorAll(".g-nivel").forEach(function (b) {
          b.addEventListener("click", function () { var k = b.getAttribute("data-nivel"); if (k === nivel) return; nivel = k; guardar("grilla-nivel", k); delDia(); });
        });
      }
      function grillaDelDia(k, fecha) {
        var semillaTxt = k ? "grilla-" + k + fecha : "grilla" + fecha;
        var ayer = null;
        if (k) { var d = new Date(); d.setDate(d.getDate() - 1); var ga = armarGrilla(G, azar(semilla("grilla-" + k + hoyTxt(d))), k, null); if (ga) ayer = ga.filas.concat(ga.cols); }
        return armarGrilla(G, azar(semilla(semillaTxt)), k, ayer);
      }
      function delDia() {
        pintarNiveles();
        var g = grillaDelDia(nivel, hoyTxt());
        if (!g) { caja.innerHTML = "<p class='vacio'>Hoy no se pudo armar la grilla. Probá mañana.</p>"; return; }
        partida(g, "grilla-" + claveNivel(nivel) + hoyTxt());
      }
      var nombres = {}; G.jugadores.forEach(function (j, i) { nombres[normal(j[0])] = i; });
      var lista = "<datalist id='lista-grilla'>" + G.jugadores.map(function (j) { return "<option value='" + esc(j[0]) + "'>"; }).join("") + "</datalist>";
      function partida(grilla, clave) {
        var est = clave ? leer(clave, null) : null;
        est = est && est.celdas ? est : { celdas: {}, intentos: 9 };
        var activa = null;
        function lleno() { return Object.keys(est.celdas).length; }
        function guardarEst() { if (clave) guardar(clave, est); }
        function pintar() {
          var termino = est.intentos <= 0 || lleno() === 9;
          var html = (clave ? "" : "<p class='nota-dato g-practica'>Grilla de práctica" + (grilla.nivel ? " en " + esc(nombreNivel(grilla.nivel)) : "") + ": no cuenta para tus números.</p>") +
            "<div class='grilla' role='grid' aria-label='Grilla bostera'><div class='g-esquina'>Boca y…</div>" +
            grilla.cols.map(function (c) { return "<div class='g-cab' role='columnheader'>" + esc(G.clubes[c]) + "</div>"; }).join("");
          for (var f = 0; f < 3; f++) {
            html += "<div class='g-cab g-fila' role='rowheader'>" + esc(G.clubes[grilla.filas[f]]) + "</div>";
            for (var c = 0; c < 3; c++) {
              var k = f * 3 + c, v = est.celdas[k];
              html += v != null ? "<div class='g-celda llena' role='gridcell'><span>" + esc(G.jugadores[v][0]) + "</span></div>"
                : "<button type='button' class='g-celda" + (activa === k ? " activa" : "") + "' data-k='" + k + "' " + (termino ? "disabled" : "") + " aria-label='" +
                  esc(G.clubes[grilla.filas[f]] + " y " + G.clubes[grilla.cols[c]]) + "'>" + (termino ? "<small>" + grilla.resp[k].length + " posibles</small>" : "+") + "</button>";
            }
          }
          html += "</div>";
          var abajo = "";
          if (!termino) {
            abajo = "<p class='nota-dato'>Te quedan <b id='grilla-intentos'>" + plural(est.intentos, "intento", "intentos") + "</b>. Tocá un casillero y escribí un jugador que haya pasado por Boca y por los dos clubes.</p>" +
              (activa != null ? "<form class='idolo-form' autocomplete='off' id='grilla-form'><label class='oculto' for='grilla-input'>Jugador</label><input id='grilla-input' list='lista-grilla' placeholder='" +
                esc(G.clubes[grilla.filas[Math.floor(activa / 3)]] + " y " + G.clubes[grilla.cols[activa % 3]]) + "…'>" + lista + "<button class='boton' type='submit'>Probar</button></form><p class='nota-dato' id='grilla-msg'></p>" : "");
          }
          caja.innerHTML = html + abajo + (termino ? "<div id='grilla-final'></div>" : "") +
            "<p class='m-fuente'>Datos de Wikidata" + (G.consultado ? " (" + G.consultado.split("-").reverse().join("/") + ")" : "") + ". Si un jugador que sabés que pasó por los dos clubes no aparece, puede que falte en Wikidata.</p>";
          caja.querySelectorAll("button.g-celda").forEach(function (b) { b.addEventListener("click", function () { activa = +b.getAttribute("data-k"); pintar(); var i = caja.querySelector("#grilla-input"); if (i) i.focus(); }); });
          var form = caja.querySelector("#grilla-form");
          if (form) form.addEventListener("submit", function (e) {
            e.preventDefault();
            var v = normal(caja.querySelector("#grilla-input").value), msg = caja.querySelector("#grilla-msg");
            var idx = nombres[v];
            if (idx == null) {
              var parecidos = v.length >= 4 ? G.jugadores.map(function (j, i) { return [normal(j[0]), i]; }).filter(function (x) { return x[0].indexOf(v) >= 0; }) : [];
              if (parecidos.length === 1) idx = parecidos[0][1];
              else { msg.textContent = parecidos.length > 1 ? "Hay varios con ese nombre: elegí uno de la lista." : "No lo encuentro entre los jugadores de Boca. Elegí uno de la lista."; return; }
            }
            if (Object.keys(est.celdas).some(function (k) { return est.celdas[k] === idx; })) { msg.textContent = "Ya lo usaste en otro casillero."; return; }
            est.intentos--;
            if (grilla.resp[activa].indexOf(idx) >= 0) { est.celdas[activa] = idx; activa = null; }
            else {
              msg.textContent = G.jugadores[idx][0] + " no cumple las dos condiciones.";
              var ci = caja.querySelector("#grilla-intentos"); if (ci) ci.textContent = plural(est.intentos, "intento", "intentos");
            }
            guardarEst();
            if (est.intentos <= 0 || lleno() === 9) { activa = null; pintar(); return final(); }
            if (activa == null) pintar(); else { var i2 = caja.querySelector("#grilla-input"); i2.value = ""; i2.focus(); }
          });
        }
        function final() {
          var n = lleno(), nv = grilla.nivel, etiquetaNivel = nv ? " (" + nombreNivel(nv) + ")" : "";
          if (clave) {
            var claveRes = "res-grilla-" + claveNivel(nv) + hoyTxt(), nueva = leer(claveRes, null) == null;
            guardar(claveRes, n);
            if (nv && nueva) {
              var st = leer("grilla-stats", {}), e = st[nv] || { jugadas: 0, casilleros: 0, llenas: 0 };
              e.jugadas++; e.casilleros += n; if (n === 9) e.llenas++; st[nv] = e; guardar("grilla-stats", st);
            }
            pintarEstados(); pintarNiveles();
          }
          if (n === 9) ganar("grilla9");
          if (n === 9 && nv === "experto") ganar("grilla-experto");
          var celdas = [0, 1, 2].map(function (f) { return [0, 1, 2].map(function (c) { return est.celdas[f * 3 + c] != null ? "ok" : "mal"; }); });
          var ejemplos = grilla.resp.map(function (r, k) {
            if (est.celdas[k] != null) return "";
            var orden = G.pj ? r.slice().sort(function (a, b) { return (G.pj[b] || 0) - (G.pj[a] || 0); }) : r;
            return "<li><b>" + esc(G.clubes[grilla.filas[Math.floor(k / 3)]] + " y " + G.clubes[grilla.cols[k % 3]]) + ":</b> " +
              esc(orden.slice(0, 3).map(function (i) { return G.jugadores[i][0]; }).join(", ")) + (r.length > 3 ? " y " + (r.length - 3) + " más" : "") + "</li>"; }).join("");
          var cont = caja.querySelector("#grilla-final");
          var textoG = firma() + "Grilla bostera #" + numeroDelDia() + etiquetaNivel + " de Rincón Bostero: " + n + "/9\n" +
            celdas.map(function (f) { return f.map(function (x) { return x === "ok" ? "🟨" : "⬛"; }).join(""); }).join("\n") + "\n" + URL_JUEGOS + "#grilla";
          cont.innerHTML = "<div class='marcador final chico'><p class='m-etiqueta'>Grilla bostera" + (clave ? " #" + numeroDelDia() : "") + esc(etiquetaNivel) + "</p><p class='m-puntaje'><b>" + n + "</b><small>/9</small></p></div>" +
            (ejemplos ? "<details class='grilla-resp'><summary>Ver algunos que servían</summary><ul>" + ejemplos + "</ul></details>" : "") +
            (clave ? bloqueCompartir({ texto: textoG }) : "") +
            "<button type='button' class='boton secundario' id='grilla-otra'>Jugar otra grilla (práctica)</button>";
          if (clave) activarCompartir(cont, { juego: "Grilla bostera #" + numeroDelDia() + etiquetaNivel, puntaje: n, total: 9, linea: n === 9 ? "¡Grilla llena!" : plural(n, "casillero", "casilleros"), celdas: celdas, texto: textoG });
          cont.querySelector("#grilla-otra").addEventListener("click", function () { var g2 = armarGrilla(G, Math.random, nv, null); if (g2) partida(g2, null); });
        }
        pintar();
        if (est.intentos <= 0 || lleno() === 9) final();
      }
      delDia();
    }).catch(function (e) { if (window.console) console.error(e); var m = document.getElementById("juego-grilla"); m.innerHTML = "<p class='vacio'>No se pudo cargar la grilla. Probá de nuevo en un rato.</p>"; m.removeAttribute("data-listo"); });
  }

  // ----------------------------------------------------------------- Ranking --
  var ESTADO_RANKING = { ambito: "general", periodo: "semana", ligas: [] };
  function linkLiga(cod) { return URL_JUEGOS + "#liga-" + cod; }
  function tablaRanking(filas, general) {
    if (!filas.length) return "<p class='vacio'>Todavía nadie sumó puntos en este período. ¡Podés ser el primero!</p>";
    var podio = filas.slice(0, 3).map(function (f, i) {
      return "<li class='podio-" + (i + 1) + (f.soy_yo ? " soy-yo" : "") + "'><span class='p-pos'>" + f.posicion + "°</span><b>" + esc(f.apodo) + "</b><span class='p-pts'>" + f.puntos + " pts</span></li>";
    }).join("");
    return "<ol class='podio'>" + podio + "</ol><div class='tabla-scroll'><table class='tabla-ranking'><thead><tr><th>#</th><th class='izq'>Apodo</th><th>Puntos</th>" +
      "<th title='Aciertos en la pregunta del día'>Del día</th><th title='Aciertos en la trivia que suman'>Trivia</th><th title='Días que jugó la pregunta del día'>Días</th></tr></thead><tbody>" +
      filas.map(function (f) {
        return "<tr class='" + (f.soy_yo ? "fila-boca" : "") + "'><td>" + f.posicion + "</td><td class='izq'>" + esc(f.apodo) + (f.soy_yo ? " (vos)" : "") +
          "</td><td class='pts'>" + f.puntos + "</td><td>" + f.aciertos_dia + "</td><td>" + f.aciertos_trivia + "</td><td>" + f.dias_jugados + "</td></tr>";
      }).join("") + "</tbody></table></div><p class='nota-dato'>1 punto por cada acierto en la pregunta del día y en la primera partida de cada tema de la trivia por día. " +
      "Solo cuenta la primera respuesta de cada pregunta." + (general ? " El primero de cada semana es el Hincha de la semana y aparece en el inicio." : "") + "</p>";
  }
  function iniciarRanking() {
    var caja = document.getElementById("juego-ranking");
    if (!caja) return;
    if (!sb) { caja.innerHTML = "<p class='vacio'>El ranking se activa cuando se configuren las cuentas de usuario.</p>"; return; }
    var conCuenta = !!(perfil && perfil.apodo);
    (conCuenta ? rpc("mis_ligas") : Promise.resolve([])).then(function (ligas) {
      ESTADO_RANKING.ligas = ligas || [];
      if (ESTADO_RANKING.ambito !== "general" && !ESTADO_RANKING.ligas.some(function (l) { return l.codigo === ESTADO_RANKING.ambito; })) ESTADO_RANKING.ambito = "general";
      pintarRanking();
    }).catch(function () { ESTADO_RANKING.ligas = []; pintarRanking(); });
  }
  function pintarRanking() {
    var caja = document.getElementById("juego-ranking"), E = ESTADO_RANKING, conCuenta = !!(perfil && perfil.apodo);
    var pendiente = leer("liga-pendiente", null);
    var invitacion = pendiente && !E.ligas.some(function (l) { return l.codigo === pendiente; }) ? "<div class='invitacion-liga' id='invitacion-liga'><p class='nota-dato'>Buscando la liga…</p></div>" : "";
    var ambitos = [["general", "General"]].concat(E.ligas.map(function (l) { return [l.codigo, l.nombre]; }));
    caja.innerHTML = invitacion +
      "<div class='filtros' role='group' aria-label='Ranking'>" + ambitos.map(function (a) {
        return "<button type='button' data-ambito='" + a[0] + "' aria-pressed='" + (a[0] === E.ambito) + "'>" + esc(a[1]) + "</button>";
      }).join("") + "</div>" +
      "<div class='filtros filtros-chicos' role='group' aria-label='Período'>" + [["semana", "Esta semana"], ["mes", "Este mes"], ["total", "Histórico"]].map(function (p) {
        return "<button type='button' data-p='" + p[0] + "' aria-pressed='" + (p[0] === E.periodo) + "'>" + p[1] + "</button>";
      }).join("") + "</div><div id='tabla-ranking'><p class='nota-dato'>Cargando…</p></div>" +
      "<section class='ligas'><h3 class='insignias-titulo'>Ligas con amigos</h3>" +
      (conCuenta ? "<p class='nota-dato'>Armá una liga con tu grupo y compartí el link: cada liga tiene su propio ranking, con los mismos puntos que el general.</p>" +
        (E.ligas.length ? "<ul class='mis-ligas'>" + E.ligas.map(function (l) {
          return "<li><div><b>" + esc(l.nombre) + "</b><span>Código <code>" + esc(l.codigo) + "</code> · " + plural(l.miembros, "miembro", "miembros") + "</span></div>" +
            "<div class='mis-ligas-acciones'><a class='boton secundario' target='_blank' rel='noopener' href='https://wa.me/?text=" +
            encodeURIComponent("Sumate a mi liga «" + l.nombre + "» en los juegos de Rincón Bostero: " + linkLiga(l.codigo)) + "'>Invitar por WhatsApp</a>" +
            "<button type='button' class='boton secundario' data-copiar='" + esc(linkLiga(l.codigo)) + "'>Copiar link</button>" +
            "<button type='button' class='enlace-peligro' data-salir='" + esc(l.codigo) + "'>Salir</button></div></li>";
        }).join("") + "</ul>" : "") +
        "<div class='ligas-forms'><form class='idolo-form' id='liga-crear'><label class='oculto' for='liga-nombre'>Nombre de la liga</label>" +
        "<input id='liga-nombre' maxlength='30' required placeholder='Nombre de la liga (ej.: Los del laburo)'><button class='boton' type='submit'>Crear liga</button></form>" +
        "<form class='idolo-form' id='liga-unir'><label class='oculto' for='liga-codigo'>Código</label>" +
        "<input id='liga-codigo' maxlength='6' required placeholder='Código de 6 letras' autocapitalize='characters'><button class='boton secundario' type='submit'>Unirme</button></form></div>" +
        "<p class='nota-dato' id='liga-msg'></p>"
        : "<p class='nota-dato'>Entrá con tu cuenta (arriba) para crear una liga o sumarte a la de tus amigos.</p>") + "</section>";
    caja.querySelectorAll("[data-ambito]").forEach(function (b) { b.addEventListener("click", function () { E.ambito = b.getAttribute("data-ambito"); pintarRanking(); }); });
    caja.querySelectorAll("[data-p]").forEach(function (b) { b.addEventListener("click", function () { E.periodo = b.getAttribute("data-p"); pintarRanking(); }); });
    var msg = caja.querySelector("#liga-msg");
    function errorLiga(err) { if (msg) msg.textContent = (err && err.message) || "No se pudo. Probá de nuevo."; }
    var fc = caja.querySelector("#liga-crear");
    if (fc) fc.addEventListener("submit", function (e) {
      e.preventDefault();
      rpc("liga_crear", { p_nombre: caja.querySelector("#liga-nombre").value }).then(function (l) { E.ambito = l.codigo; iniciarRanking(); }).catch(errorLiga);
    });
    var fu = caja.querySelector("#liga-unir");
    if (fu) fu.addEventListener("submit", function (e) {
      e.preventDefault();
      rpc("liga_unirse", { p_codigo: caja.querySelector("#liga-codigo").value }).then(function (l) { E.ambito = l.codigo; iniciarRanking(); }).catch(errorLiga);
    });
    caja.querySelectorAll("[data-salir]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!b.getAttribute("data-confirmar")) { b.setAttribute("data-confirmar", "1"); b.textContent = "Tocá de nuevo para salir"; return; }
        rpc("liga_salir", { p_codigo: b.getAttribute("data-salir") }).then(function () { E.ambito = "general"; iniciarRanking(); }).catch(errorLiga);
      });
    });
    if (invitacion) mostrarInvitacion(pendiente);
    var t = caja.querySelector("#tabla-ranking");
    var pedido = E.ambito === "general" ? rpc("ranking", { p_periodo: E.periodo }) : rpc("ranking_liga", { p_codigo: E.ambito, p_periodo: E.periodo });
    pedido.then(function (filas) { t.innerHTML = tablaRanking(filas, E.ambito === "general"); }).catch(function () { errorConexion(t); });
  }
  function mostrarInvitacion(cod) {
    var box = document.getElementById("invitacion-liga");
    if (!box) return;
    rpc("liga_ver", { p_codigo: cod }).then(function (l) {
      if (!l) { box.innerHTML = "<p>No encontramos una liga con el código <b>" + esc(cod) + "</b>.</p>"; guardar("liga-pendiente", null); return; }
      if (l.soy_miembro) { guardar("liga-pendiente", null); box.remove(); return; }
      var conCuenta = !!(perfil && perfil.apodo);
      box.innerHTML = "<p><b>Te invitaron a la liga «" + esc(l.nombre) + "»</b> (" + plural(l.miembros, "miembro", "miembros") + ").</p>" +
        (conCuenta ? "<div class='compartir'><button type='button' class='boton' id='liga-aceptar'>Unirme</button><button type='button' class='boton secundario' id='liga-ignorar'>Ahora no</button></div>"
          : "<p class='nota-dato'>Entrá con tu cuenta (arriba) y te sumamos a la liga.</p>");
      var ok = box.querySelector("#liga-aceptar");
      if (ok) ok.addEventListener("click", function () {
        rpc("liga_unirse", { p_codigo: cod }).then(function (x) { guardar("liga-pendiente", null); ESTADO_RANKING.ambito = x.codigo; iniciarRanking(); aviso("Te sumaste a <b>" + esc(x.nombre) + "</b>"); })
          .catch(function (err) { box.querySelector("p").textContent = (err && err.message) || "No se pudo."; });
      });
      var no = box.querySelector("#liga-ignorar");
      if (no) no.addEventListener("click", function () { guardar("liga-pendiente", null); box.remove(); });
    }).catch(function () { box.remove(); });
  }

  // ---------------------------------------------------- Desafío a un amigo --
  function linkReto(cod) { return URL_JUEGOS + "#desafio-" + cod; }
  function misRetos() { return leer("retos", []); }
  function guardarReto(cod, datos) { var l = misRetos().filter(function (x) { return x.codigo !== cod; }); l.unshift(Object.assign({ codigo: cod }, datos)); guardar("retos", l.slice(0, 20)); }
  function nombreJugador() { return perfil && perfil.apodo ? perfil.apodo : leer("nombre-desafio", ""); }
  function campoNombre() {
    if (perfil && perfil.apodo) return "<p class='nota-dato'>Jugás como <b>" + esc(perfil.apodo) + "</b>.</p>";
    return "<label class='oculto' for='reto-nombre'>Tu nombre</label><input id='reto-nombre' class='campo' maxlength='20' placeholder='Tu nombre (lo ven tus amigos)' value='" + esc(nombreJugador()) + "'>";
  }
  function leerNombre(caja) {
    if (perfil && perfil.apodo) return perfil.apodo;
    var v = (caja.querySelector("#reto-nombre") || {}).value || "";
    v = v.trim();
    if (v) guardar("nombre-desafio", v);
    return v;
  }
  function iniciarDesafio() {
    var caja = document.getElementById("juego-desafio");
    if (!caja) return;
    if (!sb) { caja.innerHTML = "<p class='vacio'>El desafío se activa cuando se configuren las cuentas de usuario.</p>"; return; }
    var lista = misRetos();
    caja.innerHTML = "<div class='marcador reto-crear'><h3 class='m-pregunta'>Armá un desafío de 10 preguntas</h3>" +
      "<p class='m-nota'>Te tocan 10 preguntas al azar de todos los temas. Las jugás vos primero y después le mandás el link a quien quieras: juegan las mismas y se ve quién sabe más. No hace falta cuenta.</p>" +
      "<form class='idolo-form' id='reto-form'>" + campoNombre() + "<button class='boton' type='submit'>Crear desafío</button></form><p class='m-nota' id='reto-msg'></p></div>" +
      (lista.length ? "<h3 class='insignias-titulo'>Tus desafíos</h3><ul class='mis-ligas'>" + lista.map(function (r) {
        return "<li><div><b>" + (r.creado ? "Creado por vos" : "De " + esc(r.creador || "un amigo")) + "</b><span>Código <code>" + esc(r.codigo) + "</code>" +
          (r.aciertos != null ? " · hiciste " + r.aciertos + "/10" : "") + "</span></div><div class='mis-ligas-acciones'><a class='boton secundario' href='#desafio-" + esc(r.codigo) + "'>Ver tabla</a></div></li>";
      }).join("") + "</ul>" : "");
    caja.querySelector("#reto-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var nombre = leerNombre(caja), msg = caja.querySelector("#reto-msg");
      if (nombre.length < 2) { msg.textContent = "Poné tu nombre (al menos 2 letras)."; return; }
      msg.textContent = "Armando el desafío…";
      rpc("reto_crear", { p_nombre: nombre }).then(function (r) {
        guardarReto(r.codigo, { creado: true, creador: r.creador });
        history.replaceState(null, "", "#desafio-" + r.codigo);
        jugarReto(caja, r, nombre);
      }).catch(function (err) { msg.textContent = (err && err.message) || "No se pudo crear el desafío. Probá de nuevo."; });
    });
  }
  function abrirReto(cod) {
    var caja = document.getElementById("juego-desafio");
    if (!caja) return;
    if (!sb) { caja.innerHTML = "<p class='vacio'>El desafío se activa cuando se configuren las cuentas de usuario.</p>"; return; }
    caja.innerHTML = "<p class='nota-dato'>Cargando el desafío…</p>";
    rpc("reto_ver", { p_codigo: cod }).then(function (r) {
      if (!r) { caja.innerHTML = "<p class='vacio'>No encontramos ese desafío. Revisá el link.</p><p><a class='boton' href='#desafio'>Crear uno nuevo</a></p>"; return; }
      var mio = misRetos().filter(function (x) { return x.codigo === r.codigo; })[0];
      if (mio && mio.aciertos != null) return tablaReto(caja, r, mio);
      caja.innerHTML = "<div class='marcador reto-crear'><p class='m-etiqueta'>Desafío " + esc(r.codigo) + "</p><h3 class='m-pregunta'>" + esc(r.creador) + " te desafía: 10 preguntas sobre Boca</h3>" +
        "<p class='m-nota'>" + (r.resultados.length ? plural(r.resultados.length, "persona ya lo jugó", "personas ya lo jugaron") + ". " : "") + "Jugá y fijate si le ganás.</p>" +
        "<form class='idolo-form' id='reto-form'>" + campoNombre() + "<button class='boton' type='submit'>Jugar</button></form><p class='m-nota' id='reto-msg'></p></div>";
      caja.querySelector("#reto-form").addEventListener("submit", function (e) {
        e.preventDefault();
        var nombre = leerNombre(caja);
        if (nombre.length < 2) { caja.querySelector("#reto-msg").textContent = "Poné tu nombre (al menos 2 letras)."; return; }
        guardarReto(r.codigo, { creador: r.creador });
        jugarReto(caja, r, nombre);
      });
    }).catch(function () { errorConexion(caja); });
  }
  function jugarReto(caja, r, nombre) {
    jugarPreguntas(caja, r.preguntas, function (q, k) { return rpc("reto_responder", { p_codigo: r.codigo, p_pregunta: q.id, p_opcion: k }); },
      function (h) { terminarReto(caja, r, nombre, h.map(function (x) { return x.opcion; })); });
  }
  function terminarReto(caja, r, nombre, opciones) {
    caja.innerHTML = "<p class='nota-dato'>Guardando tu resultado…</p>";
    rpc("reto_terminar", { p_codigo: r.codigo, p_nombre: nombre, p_opciones: opciones }).then(function (r2) {
      var yo = r2.resultados.filter(function (x) { return x.nombre.toLowerCase() === nombre.toLowerCase(); })[0];
      var dato = { creador: r2.creador, nombre: nombre, aciertos: yo ? yo.aciertos : null, detalle: yo ? yo.detalle : null };
      var previo = misRetos().filter(function (x) { return x.codigo === r.codigo; })[0];
      if (previo && previo.creado) dato.creado = true;
      guardarReto(r.codigo, dato);
      tablaReto(caja, r2, dato);
    }).catch(function (err) {
      // Si el nombre ya estaba usado, se puede elegir otro sin volver a jugar
      caja.innerHTML = "<div class='marcador'><p class='m-veredicto mal'><b>No se guardó.</b> " + esc((err && err.message) || "Probá de nuevo.") + "</p>" +
        "<form class='idolo-form' id='reto-form2'>" + (perfil && perfil.apodo ? "" : "<label class='oculto' for='reto-nombre'>Tu nombre</label><input id='reto-nombre' class='campo' maxlength='20' value='" + esc(nombre) + "'>") +
        "<button class='boton' type='submit'>Guardar resultado</button></form></div>";
      caja.querySelector("#reto-form2").addEventListener("submit", function (e) { e.preventDefault(); terminarReto(caja, r, leerNombre(caja) || nombre, opciones); });
    });
  }
  function tablaReto(caja, r, yo) {
    var esCreador = !!(yo && yo.creado);
    var filas = r.resultados.map(function (x, i) {
      var soy = yo && yo.nombre && x.nombre.toLowerCase() === yo.nombre.toLowerCase();
      return "<tr class='" + (soy ? "fila-boca" : "") + "'><td>" + (i + 1) + "</td><td class='izq'>" + esc(x.nombre) + (soy ? " (vos)" : "") + (x.creador ? " <small class='nota-dato'>creó el desafío</small>" : "") + "</td>" +
        "<td class='pts'>" + x.aciertos + "<small>/10</small></td><td><span class='mini-fila'>" + (x.detalle || []).map(function (ok) { return "<i class='" + (ok ? "ok" : "") + "'></i>"; }).join("") + "</span></td></tr>";
    }).join("");
    var mis = yo && yo.aciertos != null ? yo.aciertos : null;
    var texto = (mis != null ? (esCreador ? "Te desafío en Rincón Bostero: hice " + mis + "/10 en 10 preguntas sobre Boca. ¿Me ganás?" : "Hice " + mis + "/10 en el desafío de " + r.creador + " en Rincón Bostero. ¿Me ganás?")
      : r.creador + " te desafía en Rincón Bostero: 10 preguntas sobre Boca.") + "\n" + linkReto(r.codigo);
    caja.innerHTML = (mis != null ? "<div class='marcador final'><p class='m-etiqueta'>Desafío " + esc(r.codigo) + " de " + esc(r.creador) + "</p><p class='m-puntaje'><b data-contar>" + mis + "</b><small>/10</small></p>" +
      "<p class='m-frase'>" + (r.resultados.length > 1 ? "Vas " + (r.resultados.findIndex(function (x) { return x.nombre.toLowerCase() === (yo.nombre || "").toLowerCase(); }) + 1) + "° de " + r.resultados.length + "." : "Ahora mandale el link a tus amigos.") + "</p></div>" : "") +
      "<div class='compartir acciones-final'><a class='boton' target='_blank' rel='noopener' href='https://wa.me/?text=" + encodeURIComponent(texto) + "'>Mandar el desafío por WhatsApp</a>" +
      "<button type='button' class='boton secundario' data-copiar='" + esc(linkReto(r.codigo)) + "'>Copiar link</button><button type='button' class='boton secundario' id='reto-actualizar'>Actualizar tabla</button>" +
      "<a class='boton secundario' href='#desafio'>Crear otro</a></div>" +
      "<h3 class='insignias-titulo'>Tabla del desafío</h3><div class='tabla-scroll'><table class='tabla-ranking'><thead><tr><th>#</th><th class='izq'>Nombre</th><th>Aciertos</th><th>Pregunta por pregunta</th></tr></thead><tbody>" +
      (filas || "<tr><td colspan='4'>Todavía nadie lo jugó.</td></tr>") + "</tbody></table></div>" +
      (mis != null ? bloqueCompartir({ texto: texto }) : "");
    contar(caja.querySelector("[data-contar]"), mis || 0);
    if (mis != null) activarCompartir(caja, { juego: "Desafío de " + r.creador, puntaje: mis, total: 10, linea: "¿Me ganás? Código " + r.codigo,
      celdas: [(yo.detalle || []).map(function (ok) { return ok ? "ok" : "mal"; })], texto: texto });
    caja.querySelector("#reto-actualizar").addEventListener("click", function () { abrirRetoTabla(r.codigo, yo); });
  }
  function abrirRetoTabla(cod, yo) {
    var caja = document.getElementById("juego-desafio");
    rpc("reto_ver", { p_codigo: cod }).then(function (r) { if (r) tablaReto(caja, r, yo); }).catch(function () { errorConexion(caja); });
  }

  // --------------------------------------------------------------- Insignias --
  function pintarInsignias() {
    var caja = document.getElementById("juego-insignias");
    if (!caja) return;
    var ids = ganadas().map(function (i) { return i.id; }), conCuenta = !!(perfil && perfil.apodo);
    function grupo(titulo, items, nota) {
      return "<h3 class='insignias-titulo'>" + titulo + "</h3>" + (nota ? "<p class='nota-dato'>" + nota + "</p>" : "") + "<ul class='insignias'>" + items.map(function (i) {
        var ok = ids.indexOf(i.id) >= 0;
        return "<li class='" + (ok ? "ganada" : "") + "'>" + medalla(i, ok) + "<b>" + esc(i.nombre) + "</b><span>" + esc(i.desc) + "</span>" + (ok ? "" : "<span class='bloqueada'>Todavía no</span>") + "</li>";
      }).join("") + "</ul>";
    }
    caja.innerHTML = "<p class='insignias-cuenta'><b>" + ids.length + "</b> de " + INSIGNIAS.length + " ganadas</p>" +
      grupo("Con tu cuenta", INSIGNIAS.filter(function (i) { return i.cuenta; }), sb ? (conCuenta ? "" : "Entrá con tu cuenta (arriba) para ganarlas: quedan guardadas aunque cambies de celular.") : "Se activan cuando estén las cuentas de usuario.") +
      grupo("En este dispositivo", INSIGNIAS.filter(function (i) { return !i.cuenta; }), "Se guardan en este navegador.");
  }

  // ----------------------------------------------------------- Cuenta --
  function pintarCuenta() {
    var caja = document.getElementById("cuenta");
    if (!caja || !sb) return;
    caja.hidden = false;
    if (!usuario) {
      caja.innerHTML = "<div class='cuenta-fila'><p><b>Entrá para sumar puntos en el ranking y ganar insignias.</b> También podés jugar sin cuenta.</p>" +
        "<div class='cuenta-acciones'>" + (CON_GOOGLE ? "<button type='button' class='boton' id='entrar-google'>Entrar con Google</button>" : "") +
        "<details class='cuenta-mail'><summary>" + (CON_GOOGLE ? "O entrar con tu mail" : "Entrar con tu mail") + "</summary><form id='entrar-mail' class='idolo-form'>" +
        "<label for='mail' class='oculto'>Tu mail</label><input id='mail' type='email' required placeholder='Tu mail'>" +
        "<button class='boton secundario' type='submit'>Mandame el link</button></form><p class='nota-dato' id='cuenta-msg'></p></details></div></div>";
      if (CON_GOOGLE) caja.querySelector("#entrar-google").addEventListener("click", function () { sb.auth.signInWithOAuth({ provider: "google", options: { redirectTo: URL_JUEGOS } }); });
      caja.querySelector("#entrar-mail").addEventListener("submit", function (e) {
        e.preventDefault();
        sb.auth.signInWithOtp({ email: caja.querySelector("#mail").value.trim(), options: { emailRedirectTo: URL_JUEGOS } }).then(function (r) {
          caja.querySelector("#cuenta-msg").textContent = r.error ? "No se pudo mandar el mail. Probá de nuevo en unos minutos." : "Listo. Revisá tu mail (y la carpeta de spam) y tocá el link para entrar.";
        });
      });
      return;
    }
    if (!perfil || !perfil.apodo) {
      caja.innerHTML = "<form id='form-apodo' class='idolo-form'><label for='apodo'><b>Elegí tu apodo para el ranking</b></label>" +
        "<input id='apodo' maxlength='20' required placeholder='Ej.: Juancito_xeneize'><button class='boton' type='submit'>Guardar</button></form>" +
        "<p class='nota-dato' id='cuenta-msg'>De 3 a 20 letras, números, espacios o guiones. Es lo que van a ver los demás.</p>";
      caja.querySelector("#form-apodo").addEventListener("submit", function (e) {
        e.preventDefault();
        sb.from("perfiles").insert({ id: usuario.id, apodo: caja.querySelector("#apodo").value.trim() }).then(function (r) {
          if (r.error) { caja.querySelector("#cuenta-msg").textContent = r.error.code === "23505" ? "Ese apodo ya lo usa otra persona. Probá con otro." : "Ese apodo no vale: usá de 3 a 20 letras, números, espacios o guiones."; return; }
          cargarPerfil().then(reiniciarJuegos);
        });
      });
      return;
    }
    caja.innerHTML = "<div class='cuenta-fila cuenta-ok'><span class='avatar' aria-hidden='true'>" + esc(iniciales(perfil.apodo).toUpperCase() || perfil.apodo[0]) + "</span>" +
      "<p><b>" + esc(perfil.apodo) + "</b><span>Racha: " + plural(perfil.racha || 0, "día", "días") + " · Esta semana: " + (perfil.puntos_semana || 0) + " pts" +
      (perfil.posicion_semana ? " (puesto " + perfil.posicion_semana + ")" : "") + " · <a href='#insignias'>" + ganadas().length + " insignias</a></span></p>" +
      "<div class='cuenta-acciones'><button type='button' class='boton secundario' id='salir'>Salir</button><button type='button' class='enlace-peligro' id='borrar'>Borrar mi cuenta</button></div></div>";
    caja.querySelector("#salir").addEventListener("click", function () { sb.auth.signOut(); });
    var borrar = caja.querySelector("#borrar");
    borrar.addEventListener("click", function () {
      if (borrar.getAttribute("data-confirmar")) rpc("borrar_mi_cuenta").then(function () { return sb.auth.signOut(); });
      else { borrar.setAttribute("data-confirmar", "1"); borrar.textContent = "Se borran tu cuenta y tus puntos. Tocá de nuevo para confirmar"; }
    });
  }
  function cargarPerfil() {
    if (!usuario) { perfil = null; return Promise.resolve(); }
    return rpc("mi_resumen").then(function (r) { perfil = r; revisarInsigniasCuenta(); }).catch(function () { perfil = null; });
  }
  function reiniciarJuegos() {
    pintarCuenta(); iniciarDia(); iniciarTrivia(); iniciarRanking(); pintarInsignias(); pintarEstados();
    var secDesafio = document.querySelector("[data-juego='desafio']");
    if (PENDIENTE && PENDIENTE.tipo === "desafio") { var pend = PENDIENTE; PENDIENTE = null; abrirReto(pend.codigo); }
    else if (secDesafio && !secDesafio.hidden && !document.querySelector("#juego-desafio .marcador:not(.reto-crear)")) iniciarDesafio();
    else if (PENDIENTE) PENDIENTE = null;
  }

  // ------------------------------------------------- Portada y navegación --
  function pintarEstados() {
    var hoy = hoyTxt();
    function poner(id, txt, hecho) { document.querySelectorAll("[data-estado='" + id + "']").forEach(function (el) { el.textContent = txt; el.classList.toggle("hecho", !!hecho); }); }
    var rd = leer("res-dia-" + hoy, null), parcial = (leer("dia-" + hoy, { hechas: [] }).hechas || []).length;
    poner("del-dia", rd != null ? "Hoy: " + rd + "/10. Mañana hay más." : parcial ? "Vas " + parcial + " de 10" : "Todavía no jugaste hoy", rd != null);
    var ri = leer("res-idolo-" + hoy, null);
    poner("idolo", ri != null ? (ri ? "Hoy: lo sacaste en " + plural(ri, "intento", "intentos") : "Hoy no salió. Mañana, otro ídolo.") : "Ídolo nuevo todos los días", ri != null);
    poner("mas-o-menos", "Tu récord: " + leer("mom-record", 0), false);
    var ra = leer("res-anio-" + hoy, null);
    poner("anio", ra != null ? "Hoy: " + ra + "/500" : "5 momentos nuevos por día", ra != null);
    var rq = leer("res-quien-" + hoy, null);
    poner("quien", rq != null ? "Hoy: " + rq + "/300" : "Tres jugadores nuevos por día", rq != null);
    var rg = leer("res-grilla-" + hoy, null), NG = { facil: "Fácil", intermedio: "Intermedio", dificil: "Difícil", experto: "Experto" };
    var porNivel = NIVELES_GRILLA.map(function (k) { var v = leer("res-grilla-" + k + "-" + hoy, null); return v != null ? NG[k] + " " + v + "/9" : null; }).filter(Boolean);
    if (rg != null) porNivel.unshift(rg + "/9");
    poner("grilla", porNivel.length ? "Hoy: " + porNivel.join(", ") : "Cuatro dificultades, grilla nueva cada día", porNivel.length > 0);
    var mejor = Object.keys(D.temas).map(function (t) { return leer("trivia-" + t, null); }).filter(function (x) { return x != null; });
    poner("trivia", mejor.length ? "Jugaste " + plural(mejor.length, "tema", "temas") + " de " + Object.keys(D.temas).length : Object.keys(D.temas).length + " temas", false);
    if (perfil && perfil.posicion_semana) poner("ranking", "Vas " + perfil.posicion_semana + "° esta semana", false);
    poner("insignias", ganadas().length + " de " + INSIGNIAS.length + " ganadas", false);
    var retos = misRetos();
    poner("desafio", retos.length ? "Jugaste " + plural(retos.length, "desafío", "desafíos") : "Sin cuenta: solo el link", false);
    if (document.getElementById("juego-insignias") && !document.querySelector("[data-juego='insignias']").hidden) pintarInsignias();
  }
  // ------------------------------------------------------------ ¿Quién soy? --
  var QS_PUNTOS = [100, 80, 60, 40, 20], QS_ERRORES = 3, QS_DIF = { 1: "Fácil", 2: "Intermedio", 3: "Difícil" };
  function iniciarQuienSoy() {
    var caja = document.getElementById("juego-quien");
    if (!caja || caja.getAttribute("data-listo")) return;
    caja.setAttribute("data-listo", "1");
    caja.innerHTML = "<p class='nota-dato'>Buscando jugadores…</p>";
    fetch("quiensoy.json").then(function (r) { if (!r.ok) throw r; return r.json(); }).then(function (Q) {
      var J = Q.jugadores;
      var lista = "<datalist id='lista-quien'>" + J.map(function (j) { return "<option value='" + esc(j.n) + "'>"; }).join("") + "</datalist>";
      function buscar(txt) {
        var v = normal(txt); if (v.length < 3) return null;
        var exacto = J.filter(function (j) { return normal(j.n) === v; });
        if (exacto.length) return exacto[0];
        var ap = J.filter(function (j) { var p = normal(j.n).split(" "); return p[p.length - 1] === v || normal(j.n).slice(-v.length - 1) === " " + v; });
        if (ap.length === 1) return ap[0];
        var parte = J.filter(function (j) { return v.length >= 5 && normal(j.n).indexOf(v) >= 0; });
        return parte.length === 1 ? parte[0] : (ap.length > 1 || parte.length > 1 ? "varios" : null);
      }
      function delDia() {
        var r = azar(semilla("quien" + hoyTxt()));
        return [1, 2, 3].map(function (d) { var p = J.filter(function (j) { return j.dif === d; }); return p[Math.floor(r() * p.length)]; }).filter(Boolean);
      }
      function partida(secretos, clave) {
        var est = clave ? leer(clave, null) : null;
        est = est && est.r ? est : { r: [], vistas: 1, errores: [], revelado: false };
        function guardarEst() { if (clave) guardar(clave, est); }
        function total() { return est.r.reduce(function (a, x) { return a + x.p; }, 0); }
        function pintar() {
          var termino = est.r.length >= secretos.length && !est.revelado, html = "", cfg = null;
          if (est.revelado) {
            var ult = est.r[est.r.length - 1], s0 = secretos[est.r.length - 1];
            html = "<div class='qs-revela" + (ult.p ? " ok" : "") + "'><p class='qs-res'>" + (ult.p ? "¡Bien! <b>+" + ult.p + "</b>" : "Esta vez no.") + "</p>" +
              "<h3>" + esc(s0.n) + "</h3><p class='qs-datos'>" + s0.pj + " partidos oficiales · " + plural(s0.goles, "gol", "goles") + " · " + esc(s0.etapa) + "</p>" +
              (s0.bio ? "<p class='qs-bio'>" + esc(s0.bio) + "</p>" : "") +
              "<button type='button' class='boton' id='qs-seguir'>" + (est.r.length >= secretos.length ? "Ver resultado" : "Siguiente jugador") + "</button></div>";
          } else if (termino) {
            var t = total(), max = secretos.length * 100;
            if (clave) { guardar("res-quien-" + hoyTxt(), t); pintarEstados(); }
            var celdas = est.r.map(function (x) { var f = []; for (var i = 0; i < x.v; i++) f.push(i === x.v - 1 && x.p ? "ok" : "mal"); return f; });
            cfg = { juego: "¿Quién soy?" + (clave ? " #" + numeroDelDia() : ""), puntaje: t, total: max,
              linea: est.r.filter(function (x) { return x.p; }).length + " de " + secretos.length + " adivinados", celdas: celdas,
              texto: firma() + "¿Quién soy? de Rincón Bostero" + (clave ? " #" + numeroDelDia() : "") + "\n" + t + "/" + max + "\n" +
                celdas.map(function (f) { return f.map(function (x) { return x === "ok" ? "🟨" : "⬜"; }).join(""); }).join("\n") + "\n" + URL_JUEGOS + "#quien" };
            html = "<div class='qs-final'><p class='qs-total'><b>" + t + "</b><small>/" + max + "</small></p><ol class='qs-lista'>" +
              secretos.map(function (s, i) { var x = est.r[i]; return "<li><span>" + esc(s.n) + "</span><b>" + (x && x.p ? "+" + x.p : "—") + "</b></li>"; }).join("") + "</ol>" +
              bloqueCompartir(cfg) + "<button type='button' class='boton secundario' id='qs-practica'>Jugar con otros jugadores</button></div>";
          } else {
            var s = secretos[est.r.length], vale = QS_PUNTOS[est.vistas - 1];
            html = "<div class='qs-cabeza'><span>Jugador " + (est.r.length + 1) + " de " + secretos.length + "</span><span class='qs-dif d" + s.dif + "'>" + QS_DIF[s.dif] + "</span>" +
              "<span>Vale <b>" + vale + "</b></span></div><ol class='qs-pistas'>" +
              s.pistas.slice(0, est.vistas).map(function (p, i) { return "<li" + (i === est.vistas - 1 ? " class='nueva'" : "") + ">" + esc(p) + "</li>"; }).join("") + "</ol>" +
              (est.errores.length ? "<p class='qs-errores'>No es: " + est.errores.map(esc).join(", ") + "</p>" : "") +
              "<form class='idolo-form' id='qs-form' autocomplete='off'><label class='oculto' for='qs-input'>¿Quién es?</label>" +
              "<input id='qs-input' list='lista-quien' placeholder='¿Quién es?'>" + lista + "<button class='boton' type='submit'>Arriesgar</button></form>" +
              "<p class='nota-dato' id='qs-msg'>Te quedan " + plural(QS_ERRORES - est.errores.length, "intento", "intentos") + ". Cada error destapa otra pista.</p>" +
              "<div class='qs-acciones'>" + (est.vistas < s.pistas.length ? "<button type='button' class='boton secundario' id='qs-pista'>Otra pista (vale " + QS_PUNTOS[est.vistas] + ")</button>" : "") +
              "<button type='button' class='boton secundario' id='qs-rendir'>Me rindo</button></div>";
          }
          caja.innerHTML = "<div class='quien'><h3 class='juego-pregunta'>" + (clave ? "¿Quién soy? Los tres de hoy" : "Modo práctica") + "</h3>" + html + "</div>";
          if (cfg) activarCompartir(caja, cfg);
          function cerrar(puntos) {
            est.r.push({ p: puntos, v: est.vistas }); est.vistas = 1; est.errores = []; est.revelado = true; guardarEst();
            if (puntos === 100) ganar("detective");
            pintar();
          }
          var f = caja.querySelector("#qs-form");
          if (f) f.addEventListener("submit", function (e) {
            e.preventDefault();
            var s = secretos[est.r.length], g = buscar(caja.querySelector("#qs-input").value), msg = caja.querySelector("#qs-msg");
            if (g === "varios") { msg.textContent = "Hay varios con ese nombre: elegí uno de la lista."; return; }
            if (!g) { msg.textContent = "No está en la lista: solo entran jugadores con más de " + (Q.minimo - 1) + " partidos oficiales."; return; }
            if (g.n === s.n) { cerrar(QS_PUNTOS[est.vistas - 1]); return; }
            if (est.errores.indexOf(g.n) >= 0) { msg.textContent = "Ya lo probaste."; return; }
            est.errores.push(g.n);
            if (est.errores.length >= QS_ERRORES) { cerrar(0); return; }
            if (est.vistas < s.pistas.length) est.vistas++;
            guardarEst(); pintar();
            var inp = caja.querySelector("#qs-input"); if (inp) inp.focus({ preventScroll: true });
          });
          var bp = caja.querySelector("#qs-pista");
          if (bp) bp.addEventListener("click", function () { est.vistas++; guardarEst(); pintar(); });
          var br = caja.querySelector("#qs-rendir");
          if (br) br.addEventListener("click", function () { cerrar(0); });
          var bs = caja.querySelector("#qs-seguir");
          if (bs) bs.addEventListener("click", function () { est.revelado = false; guardarEst(); pintar(); });
          var bpr = caja.querySelector("#qs-practica");
          if (bpr) bpr.addEventListener("click", function () {
            var r = Math.random, al = [1, 2, 3].map(function (d) { var p = J.filter(function (j) { return j.dif === d; }); return p[Math.floor(r() * p.length)]; });
            partida(al, null);
          });
        }
        pintar();
      }
      partida(delDia(), "quien-" + hoyTxt());
    }).catch(function () { caja.innerHTML = "<p class='vacio'>No pude cargar el juego. Probá de nuevo en un rato.</p>"; caja.removeAttribute("data-listo"); });
  }

  var INICIAR_AL_ABRIR = { grilla: iniciarGrilla, quien: iniciarQuienSoy, insignias: pintarInsignias, desafio: function () { if (sb) iniciarDesafio(); } };
  var PENDIENTE = null;  // link a un desafío o liga que llegó antes de conectar con el servidor
  function mostrar() {
    var id = (location.hash || "").slice(1), m = /^(desafio|liga)-([A-Za-z0-9]{6})$/.exec(id);
    if (m) {
      var cod = m[2].toUpperCase();
      if (m[1] === "liga") { guardar("liga-pendiente", cod); id = "ranking"; }
      else { id = "desafio"; }
      PENDIENTE = { tipo: m[1], codigo: cod };
    } else if (/^[a-z-]+$/.test(id)) { PENDIENTE = null; }
    var sec = id && /^[a-z-]+$/.test(id) && document.querySelector("[data-juego='" + id + "']");
    var portada = document.getElementById("portada-juegos");
    document.querySelectorAll("[data-juego]").forEach(function (s) { s.hidden = s !== sec; });
    portada.hidden = !!sec;
    if (sec && PENDIENTE && sb) {
      var pend = PENDIENTE; PENDIENTE = null;
      if (pend.tipo === "desafio") abrirReto(pend.codigo); else iniciarRanking();
    } else if (sec && INICIAR_AL_ABRIR[id]) INICIAR_AL_ABRIR[id]();
    if (sec) { var top = document.querySelector(".juegos").getBoundingClientRect().top + window.scrollY - 8; if (window.scrollY > top) window.scrollTo(0, top); }
  }
  window.addEventListener("hashchange", mostrar);
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a.volver");
    if (a) { e.preventDefault(); history.pushState(null, "", location.pathname + location.search); mostrar(); }
  });
  window.addEventListener("popstate", mostrar);

  // ---------------------------------------------------------------- arranque --
  mostrar();
  pintarEstados();
  iniciarMasOMenos();
  iniciarIdolo();
  iniciarAnio();
  pintarInsignias();
  if (SB_URL && SB_KEY && window.supabase) {
    sb = window.supabase.createClient(SB_URL, SB_KEY);
    var primera = true;
    sb.auth.onAuthStateChange(function (_evento, sesion) {
      var nuevo = sesion ? sesion.user : null;
      if (!primera && (nuevo && usuario && nuevo.id === usuario.id)) return;
      primera = false;
      usuario = nuevo;
      cargarPerfil().then(reiniciarJuegos);
    });
  } else if (SB_URL) {
    ["juego-dia", "juego-trivia", "juego-ranking"].forEach(function (id) { var c = document.getElementById(id); if (c) errorConexion(c); });
  } else { iniciarDia(); iniciarTrivia(); iniciarRanking(); }
})();
