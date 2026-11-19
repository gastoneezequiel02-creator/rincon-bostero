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
    { id: "grilla9", nombre: "Grilla llena", glifo: "9", desc: "Completaste los 9 casilleros de la Grilla bostera." }
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
  function armarGrilla(G, r) {
    var n = G.clubes.length, miembros = G.clubes.map(function () { return []; });
    G.jugadores.forEach(function (j, idx) { for (var k = 1; k < j.length; k++) miembros[j[k]].push(idx); });
    var conjuntos = miembros.map(function (l) { var s = {}; l.forEach(function (x) { s[x] = 1; }); return s; });
    function cruce(a, b) { var m = miembros[a].length < miembros[b].length ? [a, b] : [b, a]; return miembros[m[0]].filter(function (x) { return conjuntos[m[1]][x]; }); }
    function esSel(i) { return /^Selección/.test(G.clubes[i]); }
    for (var minimo = 3; minimo >= 1; minimo--) {
      for (var intento = 0; intento < 3000; intento++) {
        var elegidos = mezclar(G.clubes.map(function (_, i) { return i; }), r).slice(0, 6);
        var filas = elegidos.slice(0, 3), cols = elegidos.slice(3);
        if (filas.filter(esSel).length > 1 || cols.filter(esSel).length > 1) continue;
        var resp = [], ok = true;
        for (var f = 0; f < 3 && ok; f++) for (var c = 0; c < 3; c++) { var x = cruce(filas[f], cols[c]); if (x.length < minimo) { ok = false; break; } resp.push(x); }
        if (ok) return { filas: filas, cols: cols, resp: resp };
      }
    }
    return null;
  }
  function iniciarGrilla() {
    var caja = document.getElementById("juego-grilla");
    if (!caja || caja.getAttribute("data-listo")) return;
    caja.setAttribute("data-listo", "1");
    caja.innerHTML = "<p class='nota-dato'>Armando la grilla…</p>";
    fetch("grilla.json").then(function (r) { if (!r.ok) throw r; return r.json(); }).then(function (G) {
      GRILLA = G;
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
          var html = "<div class='grilla' role='grid' aria-label='Grilla bostera'><div class='g-esquina'>Boca y…</div>" +
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
          var n = lleno();
          if (clave) { guardar("res-grilla-" + hoyTxt(), n); pintarEstados(); }
          if (n === 9) ganar("grilla9");
          var celdas = [0, 1, 2].map(function (f) { return [0, 1, 2].map(function (c) { return est.celdas[f * 3 + c] != null ? "ok" : "mal"; }); });
          var ejemplos = grilla.resp.map(function (r, k) { return est.celdas[k] != null ? "" : "<li><b>" + esc(G.clubes[grilla.filas[Math.floor(k / 3)]] + " y " + G.clubes[grilla.cols[k % 3]]) + ":</b> " +
            esc(r.slice(0, 3).map(function (i) { return G.jugadores[i][0]; }).join(", ")) + (r.length > 3 ? " y " + (r.length - 3) + " más" : "") + "</li>"; }).join("");
          var cont = caja.querySelector("#grilla-final");
          var textoG = firma() + "Grilla bostera #" + numeroDelDia() + " de Rincón Bostero: " + n + "/9\n" +
            celdas.map(function (f) { return f.map(function (x) { return x === "ok" ? "🟨" : "⬛"; }).join(""); }).join("\n") + "\n" + URL_JUEGOS + "#grilla";
          cont.innerHTML = "<div class='marcador final chico'><p class='m-etiqueta'>Grilla bostera" + (clave ? " #" + numeroDelDia() : "") + "</p><p class='m-puntaje'><b>" + n + "</b><small>/9</small></p></div>" +
            (ejemplos ? "<details class='grilla-resp'><summary>Ver algunos que servían</summary><ul>" + ejemplos + "</ul></details>" : "") +
            (clave ? bloqueCompartir({ texto: textoG }) : "") +
            "<button type='button' class='boton secundario' id='grilla-otra'>Jugar otra grilla (práctica)</button>";
          if (clave) activarCompartir(cont, { juego: "Grilla bostera #" + numeroDelDia(), puntaje: n, total: 9, linea: n === 9 ? "¡Grilla llena!" : plural(n, "casillero", "casilleros"), celdas: celdas, texto: textoG });
          cont.querySelector("#grilla-otra").addEventListener("click", function () { partida(armarGrilla(G, Math.random), null); });
        }
        pintar();
        if (est.intentos <= 0 || lleno() === 9) final();
      }
      var g = armarGrilla(G, azar(semilla("grilla" + hoyTxt())));
      if (!g) { caja.innerHTML = "<p class='vacio'>Hoy no se pudo armar la grilla. Probá mañana.</p>"; return; }
      partida(g, "grilla-" + hoyTxt());
    }).catch(function () { caja.innerHTML = "<p class='vacio'>No se pudo cargar la grilla. Probá de nuevo en un rato.</p>"; caja.removeAttribute("data-listo"); });
  }

  // ----------------------------------------------------------------- Ranking --
  function iniciarRanking() {
    var caja = document.getElementById("juego-ranking");
    if (!caja) return;
    if (!sb) { caja.innerHTML = "<p class='vacio'>El ranking se activa cuando se configuren las cuentas de usuario.</p>"; return; }
    var periodo = "semana";
    function cargar() {
      caja.innerHTML = "<div class='filtros' role='group' aria-label='Período'>" + [["semana", "Esta semana"], ["mes", "Este mes"], ["total", "Histórico"]].map(function (p) {
        return "<button type='button' data-p='" + p[0] + "' aria-pressed='" + (p[0] === periodo) + "'>" + p[1] + "</button>";
      }).join("") + "</div><div id='tabla-ranking'><p class='nota-dato'>Cargando…</p></div>";
      caja.querySelectorAll("[data-p]").forEach(function (b) { b.addEventListener("click", function () { periodo = b.getAttribute("data-p"); cargar(); }); });
      rpc("ranking", { p_periodo: periodo }).then(function (filas) {
        var t = document.getElementById("tabla-ranking");
        if (!filas.length) { t.innerHTML = "<p class='vacio'>Todavía nadie sumó puntos en este período. ¡Podés ser el primero!</p>"; return; }
        var podio = filas.slice(0, 3).map(function (f, i) {
          return "<li class='podio-" + (i + 1) + (f.soy_yo ? " soy-yo" : "") + "'><span class='p-pos'>" + f.posicion + "°</span><b>" + esc(f.apodo) + "</b><span class='p-pts'>" + f.puntos + " pts</span></li>";
        }).join("");
        t.innerHTML = "<ol class='podio'>" + podio + "</ol><div class='tabla-scroll'><table class='tabla-ranking'><thead><tr><th>#</th><th class='izq'>Apodo</th><th>Puntos</th>" +
          "<th title='Aciertos en la pregunta del día'>Del día</th><th title='Aciertos en la trivia que suman'>Trivia</th><th title='Días que jugó la pregunta del día'>Días</th></tr></thead><tbody>" +
          filas.map(function (f) {
            return "<tr class='" + (f.soy_yo ? "fila-boca" : "") + "'><td>" + f.posicion + "</td><td class='izq'>" + esc(f.apodo) + (f.soy_yo ? " (vos)" : "") +
              "</td><td class='pts'>" + f.puntos + "</td><td>" + f.aciertos_dia + "</td><td>" + f.aciertos_trivia + "</td><td>" + f.dias_jugados + "</td></tr>";
          }).join("") + "</tbody></table></div><p class='nota-dato'>1 punto por cada acierto en la pregunta del día y en la primera partida de cada tema de la trivia por día. " +
          "Solo cuenta la primera respuesta de cada pregunta. El primero de cada semana es el Hincha de la semana y aparece en el inicio.</p>";
      }).catch(function () { errorConexion(document.getElementById("tabla-ranking")); });
    }
    cargar();
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
  function reiniciarJuegos() { pintarCuenta(); iniciarDia(); iniciarTrivia(); iniciarRanking(); pintarInsignias(); pintarEstados(); }

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
    var rg = leer("res-grilla-" + hoy, null);
    poner("grilla", rg != null ? "Hoy: " + rg + "/9" : "Grilla nueva todos los días", rg != null);
    var mejor = Object.keys(D.temas).map(function (t) { return leer("trivia-" + t, null); }).filter(function (x) { return x != null; });
    poner("trivia", mejor.length ? "Jugaste " + plural(mejor.length, "tema", "temas") + " de " + Object.keys(D.temas).length : Object.keys(D.temas).length + " temas", false);
    if (perfil && perfil.posicion_semana) poner("ranking", "Vas " + perfil.posicion_semana + "° esta semana", false);
    poner("insignias", ganadas().length + " de " + INSIGNIAS.length + " ganadas", false);
    if (document.getElementById("juego-insignias") && !document.querySelector("[data-juego='insignias']").hidden) pintarInsignias();
  }
  var INICIAR_AL_ABRIR = { grilla: iniciarGrilla, insignias: pintarInsignias };
  function mostrar() {
    var id = (location.hash || "").slice(1), sec = id && document.querySelector("[data-juego='" + id + "']");
    var portada = document.getElementById("portada-juegos");
    document.querySelectorAll("[data-juego]").forEach(function (s) { s.hidden = s !== sec; });
    portada.hidden = !!sec;
    if (sec && INICIAR_AL_ABRIR[id]) INICIAR_AL_ABRIR[id]();
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
