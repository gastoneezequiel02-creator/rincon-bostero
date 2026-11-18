// Rincón Bostero: juegos (pregunta del día, ¿más o menos?, trivia por temas, adiviná el ídolo) y ranking.
//
// Dos modos:
// - Sin cuentas (config.json > cuentas > activado: false): todo corre en el navegador.
// - Con cuentas (Supabase): las preguntas del día y de la trivia vienen SIN la respuesta y se corrigen
//   en la base de datos; así el ranking es justo. Se puede jugar igual sin entrar (no suma al ranking).
(function () {
  "use strict";
  var nodo = document.getElementById("datos-juegos");
  if (!nodo) return;
  var D = JSON.parse(nodo.textContent);
  var URL_JUEGOS = nodo.getAttribute("data-url") || location.href.split("#")[0];
  var SB_URL = nodo.getAttribute("data-supabase-url"), SB_KEY = nodo.getAttribute("data-supabase-key");
  var CON_GOOGLE = nodo.getAttribute("data-google") === "1";
  var sb = null;          // cliente de Supabase (si hay cuentas)
  var usuario = null;     // sesión actual
  var perfil = null;      // {apodo, racha, posicion_semana, puntos_semana}
  var INICIO = new Date(2026, 10, 18); // día 1 de la pregunta del día

  // ---------- utilidades ----------
  function guardar(k, v) { try { localStorage.setItem("rb-" + k, JSON.stringify(v)); } catch (e) {} }
  function leer(k, def) { try { var v = localStorage.getItem("rb-" + k); return v ? JSON.parse(v) : def; } catch (e) { return def; } }
  function hoyTxt(d) { d = d || new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function ayerTxt() { var d = new Date(); d.setDate(d.getDate() - 1); return hoyTxt(d); }
  function numeroDelDia() { var h = new Date(); h.setHours(0, 0, 0, 0); return Math.round((h - INICIO) / 864e5) + 1; }
  function semilla(txt) { var h = 1779033703 ^ txt.length; for (var i = 0; i < txt.length; i++) { h = Math.imul(h ^ txt.charCodeAt(i), 3432918353); h = h << 13 | h >>> 19; } return h >>> 0; }
  function azar(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function mezclar(lista, r) { var a = lista.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function normal(t) { return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim(); }
  function rpc(nombre, args) {
    return sb.rpc(nombre, args || {}).then(function (r) { if (r.error) throw r.error; return r.data; });
  }
  function errorConexion(caja) {
    caja.innerHTML = "<p class='vacio'>No pudimos conectarnos con el servidor de los juegos. Probá de nuevo en un rato.</p>";
  }

  function botonesCompartir(texto) {
    var wa = "https://wa.me/?text=" + encodeURIComponent(texto);
    return "<div class='compartir'><a class='boton' href='" + wa + "' target='_blank' rel='noopener'>Compartir por WhatsApp</a>" +
      "<button type='button' class='boton secundario' data-copiar='" + esc(texto) + "'>Copiar resultado</button></div>";
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copiar]");
    if (!b) return;
    var txt = b.getAttribute("data-copiar");
    var listo = function () { b.textContent = "Copiado"; setTimeout(function () { b.textContent = "Copiar resultado"; }, 2000); };
    try { navigator.clipboard.writeText(txt).then(listo, function () { b.textContent = "No se pudo copiar"; }); }
    catch (err) { b.textContent = "No se pudo copiar"; }
  });
  function firma() { return perfil && perfil.apodo ? perfil.apodo + " en " : ""; }

  // ---------- motor de preguntas ----------
  // corregir(q, opcion) devuelve una promesa con {correcta, dato}. previas: [{opcion, correcta}] ya respondidas.
  function jugarPreguntas(caja, preguntas, corregir, alTerminar, previas, alResponder) {
    var hechas = (previas || []).slice();
    function pintar() {
      if (hechas.length >= preguntas.length) return alTerminar(hechas);
      var i = hechas.length, q = preguntas[i];
      caja.innerHTML =
        "<div class='juego-progreso'><span>Pregunta " + (i + 1) + " de " + preguntas.length + "</span><span>" + esc(D.temas[q.tema] || "") + "</span></div>" +
        "<div class='barra-progreso'><i style='width:" + (100 * i / preguntas.length) + "%'></i></div>" +
        "<h3 class='juego-pregunta'>" + esc(q.texto) + "</h3>" +
        "<div class='opciones'>" + q.opciones.map(function (o, k) {
          return "<button type='button' class='opcion' data-k='" + k + "'>" + esc(o) + "</button>";
        }).join("") + "</div><div class='juego-dato' aria-live='polite'></div>";
      caja.querySelectorAll(".opcion").forEach(function (b) {
        b.addEventListener("click", function () { responder(+b.getAttribute("data-k")); });
      });
    }
    function responder(k) {
      var q = preguntas[hechas.length];
      caja.querySelectorAll(".opcion").forEach(function (b) { b.disabled = true; });
      caja.querySelector(".juego-dato").innerHTML = "<p class='nota-dato'>Corrigiendo…</p>";
      corregir(q, k).then(function (r) {
        var elegida = r.opcion_valida != null ? r.opcion_valida : k;
        hechas.push({ opcion: elegida, correcta: r.correcta });
        caja.querySelectorAll(".opcion").forEach(function (b, j) {
          if (j === r.correcta) b.classList.add("ok"); else if (j === elegida) b.classList.add("mal");
        });
        var bien = elegida === r.correcta;
        caja.querySelector(".juego-dato").innerHTML =
          "<p><b>" + (bien ? "¡Bien ahí!" : "No era esa.") + "</b> " + esc(r.dato || ("La respuesta es " + q.opciones[r.correcta] + ".")) + "</p>" +
          "<button type='button' class='boton siguiente'>" + (hechas.length === preguntas.length ? "Ver resultado" : "Siguiente") + "</button>";
        caja.querySelector(".siguiente").addEventListener("click", pintar);
        caja.querySelector(".siguiente").focus();
        if (alResponder) alResponder(hechas);
      }).catch(function () {
        caja.querySelectorAll(".opcion").forEach(function (b) { b.disabled = false; });
        caja.querySelector(".juego-dato").innerHTML = "<p class='nota-dato'>No se pudo corregir. Revisá la conexión y tocá de nuevo una opción.</p>";
      });
    }
    pintar();
  }
  function aciertos(h) { return h.filter(function (x) { return x.opcion === x.correcta; }).length; }
  function fila(h) { return h.map(function (x) { return x.opcion === x.correcta ? "💙" : "⬜"; }).join(""); }
  function corregirLocal(q, k) { return Promise.resolve({ correcta: q.correcta, dato: q.dato }); }

  // ---------- 1. La pregunta del día ----------
  function preguntasDelDiaLocal() {
    // Rotación: cada tema se recorre en un orden fijo y cada día avanza, así no se repiten hasta agotar el banco.
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
    var hoy = hoyTxt();
    var racha = leer("racha", { ultimo: "", dias: 0 });
    if (racha.ultimo !== hoy) { racha = { ultimo: hoy, dias: racha.ultimo === ayerTxt() ? racha.dias + 1 : 1 }; guardar("racha", racha); }
    var dias = rachaServidor != null ? rachaServidor : racha.dias;
    var n = aciertos(hechas);
    var texto = firma() + "La pregunta xeneize del día #" + numeroDelDia() + "\n" + n + "/10 " + fila(hechas) +
      "\nRacha: " + dias + (dias === 1 ? " día" : " días") + "\n" + URL_JUEGOS;
    var frase = n === 10 ? "¡Perfecto! Sabés todo de Boca." : n >= 8 ? "¡Muy bien! Bostero de ley." : n >= 5 ? "Bien, pero se puede mejorar." : "Hay que repasar la historia.";
    var extra = sb ? (perfil && perfil.apodo ? "<p class='nota-dato'>Sumaste " + n + " puntos al ranking. <a href='#ranking' data-ir='ranking'>Ver ranking</a></p>"
      : "<p class='nota-dato'>Entrá con tu cuenta para que tus aciertos sumen en el ranking.</p>") : "";
    caja.innerHTML = "<div class='juego-final'><p class='nota-dato'>Pregunta del día #" + numeroDelDia() + "</p>" +
      "<b class='puntaje'>" + n + "<small>/10</small></b><p>" + frase + "</p><p class='fila-resultado'>" + fila(hechas) + "</p>" +
      "<p class='nota-dato'>Racha: " + dias + (dias === 1 ? " día seguido" : " días seguidos") + ". Mañana hay 10 preguntas nuevas.</p>" +
      extra + botonesCompartir(texto) + "</div>";
  }
  function iniciarDia() {
    var caja = document.getElementById("juego-dia");
    if (!caja) return;
    var clave = "dia-" + hoyTxt();
    if (!sb) {
      var preguntas = preguntasDelDiaLocal();
      if (preguntas.length < 10) { caja.innerHTML = "<p class='vacio'>Las preguntas aparecen cuando se cargan los datos.</p>"; return; }
      var guardado = leer(clave, { hechas: [] }).hechas || [];
      jugarPreguntas(caja, preguntas, corregirLocal, function (h) { finDelDia(caja, h); }, guardado,
        function (h) { guardar(clave, { hechas: h }); });
      return;
    }
    caja.innerHTML = "<p class='nota-dato'>Cargando las preguntas de hoy…</p>";
    rpc("desafio_hoy").then(function (filas) {
      var preguntas = filas.map(function (f) { return { id: f.id, tema: f.tema, texto: f.texto, opciones: f.opciones }; });
      var previas = [];
      if (perfil && perfil.apodo) {
        filas.every(function (f) { if (f.respondida == null) return false; previas.push({ opcion: f.respondida, correcta: f.era_correcta }); return true; });
      } else {
        previas = leer(clave, { hechas: [] }).hechas || [];
      }
      jugarPreguntas(caja, preguntas, function (q, k) { return rpc("responder_dia", { p_pregunta: q.id, p_opcion: k }); },
        function (h) {
          if (perfil && perfil.apodo) rpc("mi_resumen").then(function (r) { perfil = r; pintarCuenta(); finDelDia(caja, h, r.racha); }).catch(function () { finDelDia(caja, h); });
          else finDelDia(caja, h);
        }, previas, function (h) { if (!(perfil && perfil.apodo)) guardar(clave, { hechas: h }); });
    }).catch(function () { errorConexion(caja); });
  }

  // ---------- 2. ¿Más o menos? (siempre en el navegador; no suma al ranking) ----------
  function iniciarMasOMenos() {
    var caja = document.getElementById("juego-mom");
    if (!caja || !D.mas_o_menos.length) return;
    var racha = 0, record = leer("mom-record", 0);
    function ronda() {
      var g = D.mas_o_menos[Math.floor(Math.random() * D.mas_o_menos.length)];
      var a, b, intentos = 0;
      do {
        a = g.items[Math.floor(Math.random() * g.items.length)];
        b = g.items[Math.floor(Math.random() * g.items.length)];
      } while ((a === b || a.valor === b.valor) && ++intentos < 50);
      if (a.valor === b.valor) return ronda();
      var gana = g.menor ? (a.valor < b.valor ? 0 : 1) : (a.valor > b.valor ? 0 : 1);
      caja.innerHTML =
        "<div class='juego-progreso'><span>Racha: <b>" + racha + "</b></span><span>Récord: <b>" + record + "</b></span></div>" +
        "<h3 class='juego-pregunta'>" + esc(g.pregunta) + "</h3>" +
        "<div class='duelo'>" + [a, b].map(function (x, k) {
          return "<button type='button' class='lado' data-k='" + k + "'><span class='lado-nombre'>" + esc(x.nombre) + "</span><span class='lado-valor' hidden>" +
            x.valor + (g.unidad ? " " + esc(g.unidad) : "") + "</span></button>";
        }).join("<span class='vs-duelo'>o</span>") + "</div><div class='juego-dato' aria-live='polite'></div>";
      caja.querySelectorAll(".lado").forEach(function (bt) {
        bt.addEventListener("click", function () {
          var k = +bt.getAttribute("data-k");
          caja.querySelectorAll(".lado").forEach(function (x, j) {
            x.disabled = true;
            x.querySelector(".lado-valor").hidden = false;
            x.classList.add(j === gana ? "ok" : "mal-suave");
          });
          var dato = caja.querySelector(".juego-dato");
          if (k === gana) {
            racha++;
            if (racha > record) { record = racha; guardar("mom-record", record); }
            dato.innerHTML = "<p><b>¡Bien!</b> Racha de " + racha + ".</p><button type='button' class='boton siguiente'>Seguir</button>";
            dato.querySelector(".siguiente").addEventListener("click", ronda);
          } else {
            var texto = firma() + "Hice una racha de " + racha + " en ¿Más o menos? de Rincón Bostero. Mi récord: " + record + ".\n" + URL_JUEGOS + "#mas-o-menos";
            dato.innerHTML = "<p><b>Uh, no.</b> Terminaste con una racha de " + racha + ". Tu récord es " + record + ".</p>" +
              "<button type='button' class='boton siguiente'>Jugar de nuevo</button>" + botonesCompartir(texto);
            racha = 0;
            dato.querySelector(".siguiente").addEventListener("click", ronda);
          }
          dato.querySelector(".siguiente").focus();
        });
      });
    }
    ronda();
  }

  // ---------- 3. Trivia por temas ----------
  function iniciarTrivia() {
    var caja = document.getElementById("juego-trivia");
    if (!caja) return;
    function menu() {
      caja.innerHTML = "<h3 class='juego-pregunta'>Elegí un tema</h3>" +
        (sb ? "<p class='nota-dato'>La primera partida de cada tema del día suma al ranking.</p>" : "") +
        "<div class='temas'>" + Object.keys(D.temas).map(function (t) {
          var cant = Math.min(10, D.cantidades[t] || 0), mejor = leer("trivia-" + t, null);
          return "<button type='button' class='tema' data-t='" + t + "'><b>" + esc(D.temas[t]) + "</b><span>" + cant + " preguntas" +
            (mejor !== null ? ". Tu mejor: " + mejor + "/" + cant : "") + "</span></button>";
        }).join("") + "</div>";
      caja.querySelectorAll(".tema").forEach(function (b) { b.addEventListener("click", function () { jugar(b.getAttribute("data-t")); }); });
    }
    function terminar(t, h, sumo) {
      var n = aciertos(h), mejor = leer("trivia-" + t, -1);
      if (n > mejor) guardar("trivia-" + t, n);
      var texto = firma() + "Trivia de Rincón Bostero: " + D.temas[t] + "\n" + n + "/" + h.length + " " + fila(h) + "\n" + URL_JUEGOS + "#trivia";
      caja.innerHTML = "<div class='juego-final'><p class='nota-dato'>" + esc(D.temas[t]) + "</p><b class='puntaje'>" + n + "<small>/" + h.length + "</small></b>" +
        "<p class='fila-resultado'>" + fila(h) + "</p>" +
        (sb ? "<p class='nota-dato'>" + (sumo ? "Sumaste " + n + " puntos al ranking." : perfil && perfil.apodo ?
          "Esta partida no suma: solo cuenta la primera de cada tema por día." : "Entrá con tu cuenta para sumar al ranking.") + "</p>" : "") +
        "<div class='compartir'><button type='button' class='boton' id='otra-vez'>Jugar otra vez</button><button type='button' class='boton secundario' id='otro-tema'>Elegir otro tema</button></div>" +
        botonesCompartir(texto) + "</div>";
      caja.querySelector("#otra-vez").addEventListener("click", function () { jugar(t); });
      caja.querySelector("#otro-tema").addEventListener("click", menu);
    }
    function jugar(t) {
      if (!sb) {
        var lista = mezclar(D.preguntas.filter(function (q) { return q.tema === t; }), Math.random).slice(0, 10);
        return jugarPreguntas(caja, lista, corregirLocal, function (h) { terminar(t, h, false); });
      }
      caja.innerHTML = "<p class='nota-dato'>Armando la partida…</p>";
      rpc("trivia_iniciar", { p_tema: t }).then(function (r) {
        jugarPreguntas(caja, r.preguntas, function (q, k) { return rpc("responder_trivia", { p_sesion: r.sesion, p_pregunta: q.id, p_opcion: k }); },
          function (h) { terminar(t, h, r.suma); });
      }).catch(function () { errorConexion(caja); });
    }
    menu();
  }

  // ---------- 4. Adiviná el ídolo (en el navegador) ----------
  function iniciarIdolo() {
    var caja = document.getElementById("juego-idolo");
    if (!caja || D.idolos.length < 5) return;
    var MAX = 6, hoy = hoyTxt();
    var diario = D.idolos[Math.floor(azar(semilla("idolo" + hoy))() * D.idolos.length)];
    var opciones = D.idolos.map(function (i) { return "<option value='" + esc(i.nombre) + "'>"; }).join("");
    function partida(secreto, claveGuardado) {
      var intentos = (claveGuardado ? leer(claveGuardado, []) : []).map(function (n) {
        return D.idolos.filter(function (i) { return i.nombre === n; })[0];
      }).filter(Boolean);
      function celda(ok, texto, cerca) { return "<td class='" + (ok ? "c-ok" : cerca ? "c-cerca" : "c-no") + "'>" + texto + "</td>"; }
      function filaIntento(g) {
        var dif = secreto.debut - g.debut;
        return "<tr><th scope='row'>" + esc(g.nombre) + "</th>" +
          celda(g.posicion === secreto.posicion, esc(g.posicion)) + celda(g.pais === secreto.pais, esc(g.pais)) +
          celda(dif === 0, g.debut + (dif === 0 ? "" : dif > 0 ? " ↑" : " ↓"), Math.abs(dif) <= 5) +
          celda(g.libertadores === secreto.libertadores, g.libertadores ? "Sí" : "No") +
          celda(g.intercontinental === secreto.intercontinental, g.intercontinental ? "Sí" : "No") + "</tr>";
      }
      function cuadros(g) {
        return [g.posicion === secreto.posicion, g.pais === secreto.pais, g.debut === secreto.debut,
          g.libertadores === secreto.libertadores, g.intercontinental === secreto.intercontinental]
          .map(function (ok, i) { return ok ? "🟩" : (i === 2 && Math.abs(g.debut - secreto.debut) <= 5 ? "🟨" : "⬜"); }).join("");
      }
      function pintar() {
        var gano = intentos.some(function (g) { return g.nombre === secreto.nombre; });
        var termino = gano || intentos.length >= MAX;
        var pista = !termino && intentos.length >= 3 && secreto.apodo ? "<p class='pista'>Pista: le dicen <b>" + esc(secreto.apodo) + "</b>.</p>" : "";
        var tabla = intentos.length ? "<div class='tabla-scroll'><table class='tabla-idolo'><thead><tr><th class='izq'>Jugador</th><th>Posición</th><th>País</th>" +
          "<th title='Año en que llegó a Boca'>Llegó</th><th title='Ganó la Libertadores con Boca'>Libert.</th><th title='Ganó la Intercontinental con Boca'>Interc.</th></tr></thead><tbody>" +
          intentos.map(filaIntento).join("") + "</tbody></table></div>" : "";
        var abajo;
        if (termino) {
          var texto = firma() + "Adiviná el ídolo de Rincón Bostero" + (claveGuardado ? " #" + numeroDelDia() : "") + "\n" +
            (gano ? intentos.length + "/" + MAX : "X/" + MAX) + "\n" + intentos.map(cuadros).join("\n") + "\n" + URL_JUEGOS + "#idolo";
          abajo = "<div class='juego-final'><p>" + (gano ? "<b>¡Lo sacaste!</b> Era " : "<b>Se terminaron los intentos.</b> Era ") +
            "<b>" + esc(secreto.nombre) + "</b>" + (secreto.apodo ? " (" + esc(secreto.apodo) + ")" : "") + ": " + esc(secreto.posicion.toLowerCase()) +
            ", " + esc(secreto.pais) + ", llegó a Boca en " + secreto.debut + ".</p>" + botonesCompartir(texto) +
            "<button type='button' class='boton secundario' id='idolo-practica'>Jugar con otro ídolo</button></div>";
        } else {
          abajo = "<form class='idolo-form' autocomplete='off'><label for='idolo-input' class='oculto'>Jugador</label>" +
            "<input id='idolo-input' list='lista-idolos' placeholder='Escribí un jugador…'><datalist id='lista-idolos'>" + opciones + "</datalist>" +
            "<button class='boton' type='submit'>Probar</button></form><p class='nota-dato' id='idolo-msg'>Intento " + (intentos.length + 1) + " de " + MAX + ".</p>" + pista;
        }
        caja.innerHTML = "<h3 class='juego-pregunta'>" + (claveGuardado ? "¿Quién es el ídolo de hoy?" : "Modo práctica: ¿quién es?") + "</h3>" +
          "<p class='nota-dato'>Verde: coincide. Amarillo: llegó a Boca con menos de 5 años de diferencia. Las flechas indican si llegó antes o después.</p>" + tabla + abajo;
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
          var inp = caja.querySelector("#idolo-input"); if (inp) inp.focus();
        });
        var prac = caja.querySelector("#idolo-practica");
        if (prac) prac.addEventListener("click", function () { partida(D.idolos[Math.floor(Math.random() * D.idolos.length)], null); });
      }
      pintar();
    }
    partida(diario, "idolo-" + hoy);
  }

  // ---------- Ranking ----------
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
        t.innerHTML = "<div class='tabla-scroll'><table class='tabla-ranking'><thead><tr><th>#</th><th class='izq'>Apodo</th><th>Puntos</th>" +
          "<th title='Aciertos en la pregunta del día'>Del día</th><th title='Aciertos en la trivia que suman'>Trivia</th><th title='Días que jugó la pregunta del día'>Días</th></tr></thead><tbody>" +
          filas.map(function (f) {
            return "<tr class='" + (f.soy_yo ? "fila-boca" : "") + "'><td>" + f.posicion + "</td><td class='izq'>" + esc(f.apodo) + (f.soy_yo ? " (vos)" : "") +
              "</td><td class='pts'>" + f.puntos + "</td><td>" + f.aciertos_dia + "</td><td>" + f.aciertos_trivia + "</td><td>" + f.dias_jugados + "</td></tr>";
          }).join("") + "</tbody></table></div><p class='nota-dato'>1 punto por cada acierto en la pregunta del día y en la primera partida de cada tema de la trivia por día. " +
          "Solo cuenta la primera respuesta de cada pregunta.</p>";
      }).catch(function () { errorConexion(document.getElementById("tabla-ranking")); });
    }
    cargar();
  }

  // ---------- Cuenta: entrar, apodo, salir, borrar ----------
  function pintarCuenta() {
    var caja = document.getElementById("cuenta");
    if (!caja || !sb) return;
    caja.hidden = false;
    if (!usuario) {
      caja.innerHTML = "<p><b>Entrá para sumar puntos en el ranking.</b> También podés jugar sin cuenta.</p>" +
        "<div class='cuenta-acciones'>" + (CON_GOOGLE ? "<button type='button' class='boton' id='entrar-google'>Entrar con Google</button>" : "") +
        "<form id='entrar-mail' class='idolo-form'><label for='mail' class='oculto'>Tu mail</label><input id='mail' type='email' required placeholder='" +
        (CON_GOOGLE ? "O dejá tu mail y te mandamos un link" : "Dejá tu mail y te mandamos un link para entrar") + "'>" +
        "<button class='boton secundario' type='submit'>Mandame el link</button></form></div><p class='nota-dato' id='cuenta-msg'></p>";
      if (CON_GOOGLE) caja.querySelector("#entrar-google").addEventListener("click", function () {
        sb.auth.signInWithOAuth({ provider: "google", options: { redirectTo: URL_JUEGOS } });
      });
      caja.querySelector("#entrar-mail").addEventListener("submit", function (e) {
        e.preventDefault();
        var mail = caja.querySelector("#mail").value.trim();
        sb.auth.signInWithOtp({ email: mail, options: { emailRedirectTo: URL_JUEGOS } }).then(function (r) {
          caja.querySelector("#cuenta-msg").textContent = r.error ? "No se pudo mandar el mail. Probá de nuevo en unos minutos." :
            "Listo. Revisá tu mail (y la carpeta de spam) y tocá el link para entrar.";
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
        var apodo = caja.querySelector("#apodo").value.trim();
        sb.from("perfiles").insert({ id: usuario.id, apodo: apodo }).then(function (r) {
          if (r.error) {
            caja.querySelector("#cuenta-msg").textContent = r.error.code === "23505" ? "Ese apodo ya lo usa otra persona. Probá con otro." :
              "Ese apodo no vale: usá de 3 a 20 letras, números, espacios o guiones.";
            return;
          }
          cargarPerfil().then(reiniciarJuegos);
        });
      });
      return;
    }
    caja.innerHTML = "<p>Hola, <b>" + esc(perfil.apodo) + "</b>. Racha: " + (perfil.racha || 0) + (perfil.racha === 1 ? " día" : " días") +
      ". Esta semana: " + (perfil.puntos_semana || 0) + " puntos" + (perfil.posicion_semana ? " (puesto " + perfil.posicion_semana + ")" : "") + ".</p>" +
      "<div class='cuenta-acciones'><button type='button' class='boton secundario' id='salir'>Salir</button>" +
      "<button type='button' class='enlace-peligro' id='borrar'>Borrar mi cuenta</button></div>";
    caja.querySelector("#salir").addEventListener("click", function () { sb.auth.signOut(); });
    var borrar = caja.querySelector("#borrar");
    borrar.addEventListener("click", function () {
      if (borrar.getAttribute("data-confirmar")) {
        rpc("borrar_mi_cuenta").then(function () { return sb.auth.signOut(); });
      } else {
        borrar.setAttribute("data-confirmar", "1");
        borrar.textContent = "Se borran tu cuenta y tus puntos. Tocá de nuevo para confirmar";
      }
    });
  }
  function cargarPerfil() {
    if (!usuario) { perfil = null; return Promise.resolve(); }
    return rpc("mi_resumen").then(function (r) { perfil = r; }).catch(function () { perfil = null; });
  }
  function reiniciarJuegos() { pintarCuenta(); iniciarDia(); iniciarTrivia(); iniciarRanking(); }

  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-ir]");
    if (a) { var b = document.querySelector("button[data-destino='" + a.getAttribute("data-ir") + "']"); if (b) { e.preventDefault(); b.click(); } }
  });

  // ---------- arranque ----------
  iniciarMasOMenos();
  iniciarIdolo();
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
  } else {
    if (SB_URL) { // había cuentas configuradas pero no cargó la librería
      ["juego-dia", "juego-trivia", "juego-ranking"].forEach(function (id) { var c = document.getElementById(id); if (c) errorConexion(c); });
    } else { iniciarDia(); iniciarTrivia(); iniciarRanking(); }
  }
})();
