"""Integración con Historia de Boca (historiadeboca.com.ar), con permiso de sus autores.

- Historial total contra cada rival: datos/manual/historial_oficial.json, más los partidos de liga
  jugados después de la última actualización (así el total queda siempre al día).
- Historial partido a partido de cada clásico: se importa una vez por semana y se verifica contra los totales.
- Efemérides: una vez por día lee "Un día como hoy" y lo guarda (con los días se arma un almanaque propio).
  Todo se muestra dentro de la web, con el crédito "Datos históricos: Historia de Boca".
"""
from __future__ import annotations

import datetime as dt
import html as html_mod
import re
import time

from comun import DATOS, DATOS_MANUAL, ahora, config, guardar_json, http_get, leer_json, limpiar_html, log, normalizar, parsear_fecha

BASE = "https://historiadeboca.com.ar"


def opciones() -> dict:
    h = config().get("historia_de_boca") or {}
    return h if h.get("activado") else {}


# --------------------------------------------------------------- historial --
def historiales() -> dict:
    return leer_json(DATOS_MANUAL / "historial_oficial.json", {}) or {}


def buscar_historial(nombre_rival: str) -> dict | None:
    n = normalizar(nombre_rival)
    for r in historiales().get("rivales", []):
        if any(normalizar(x) == n for x in r.get("nombres", [])):
            return r
    return None


def total_actualizado(rival: dict, partidos: list[dict]) -> dict | None:
    """Suma al total de Historia de Boca los partidos de liga posteriores a su fecha de corte."""
    base = buscar_historial(rival["nombre"])
    if not base or not base.get("pj"):
        return None
    meta = historiales()
    imp = historial_importado(rival["nombre"])
    if imp and imp.get("totales", {}).get("pj"):
        base = {**base, **imp["totales"], "hasta": imp.get("hasta") or base.get("hasta")}
    corte = base.get("hasta", "")
    extra = {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0}
    for p in partidos:
        if (p["estado"] != "finalizado" or p.get("resultado") is None or p["rival"]["id"] != rival["id"]
                or p.get("competencia_slug") != "arg.1" or not p.get("fecha")):
            continue
        d = parsear_fecha(p["fecha"])
        if not d or d.date().isoformat() <= corte:
            continue
        extra["pj"] += 1
        extra[p["resultado"].lower()] += 1
        extra["gf"] += p["goles_boca"]
        extra["gc"] += p["goles_rival"]
    total = {k: (base.get(k) or 0) + extra[k] for k in extra}
    return {**total, "hasta": corte, "sumados": extra["pj"], "alcance": meta.get("alcance", ""),
            "fuente": meta.get("fuente", "Historia de Boca")}


# --------------------------------------------------------------- efemérides --
RE_LINK = re.compile(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>')
RE_HREF_UTIL = re.compile(r"(^|/)(partido|jugadores|tecnicos|notas?)/|/[a-z0-9-]+\.html$")
RE_ANIO = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
VERBOS = [("naci", "Nació"), ("falleci", "Falleció"), ("debut", "Debutó"), ("muri", "Murió")]
CARPETA_EFEMERIDES = DATOS / "hdb" / "efemerides"


def parsear_efemerides(pagina: str) -> list[dict]:
    """Saca de la página de efemérides cada hecho: año, título y una descripción breve."""
    cuerpo = pagina
    m = re.search(r"(?is)efem[eé]rides.{0,200}?\d{1,2}\s+de\s+[a-z]+", pagina)
    if m:
        cuerpo = pagina[m.start():]
    links = [l for l in RE_LINK.finditer(cuerpo) if RE_HREF_UTIL.search(l.group(1))]
    items, vistos = [], set()
    for i, link in enumerate(links):
        href, interior = link.group(1), link.group(2)
        titulo = limpiar_html(interior)
        if len(titulo) < 6 or href in vistos:
            continue
        antes = limpiar_html(cuerpo[max(0, link.start() - 600):link.start()])
        anios = RE_ANIO.findall(antes[-160:]) or RE_ANIO.findall(titulo)
        if not anios:
            continue
        ruta = "/" + href.split("historiadeboca.com.ar")[-1].lstrip("/")
        tipo = "partido" if ruta.startswith("/partido/") else "persona" if ruta.startswith(("/jugadores/", "/tecnicos/")) else "nota"
        if tipo == "persona":
            previo = normalizar(antes[-60:])
            verbo = next((v for clave, v in VERBOS if clave in previo), "")
            if verbo and not normalizar(titulo).startswith(normalizar(verbo)):
                titulo = f"{verbo} {titulo}"
        # descripción: el texto entre este link y el link de la entrada siguiente
        fin = next((l.start() for l in links[i + 1:] if l.group(1) != href), min(len(cuerpo), link.end() + 800))
        desc = limpiar_html(cuerpo[link.end():fin]).strip(" .·-–|")
        desc = re.sub(r"\s*\b(1[89]\d{2}|20\d{2})\b[^.]{0,30}$", "", desc)  # encabezado de la entrada siguiente
        desc = re.sub(r"(?i)\s*(y además\.*|ver más|leer más)\s*$", "", desc).strip(" .·-–|")
        vistos.add(href)
        items.append({"anio": int(anios[-1]), "titulo": titulo[:140], "detalle": desc[:220], "tipo": tipo})
    return items[:15]


def ejecutar_efemerides() -> None:
    op = opciones()
    if not op.get("efemerides"):
        return
    hoy = ahora()
    archivo = CARPETA_EFEMERIDES / f"{hoy:%m-%d}.json"
    if leer_json(archivo, {}).get("consultado") == hoy.date().isoformat():
        return
    try:
        pagina = http_get(op["efemerides"]).decode("utf-8", "ignore")
    except Exception as e:
        log(f"Historia de Boca: no pude leer las efemérides ({e})")
        return
    items = parsear_efemerides(pagina)
    if items:
        guardar_json(archivo, {"consultado": hoy.date().isoformat(), "items": sorted(items, key=lambda x: x["anio"])})
    log(f"Historia de Boca: {len(items)} efemérides para hoy")


ARCHIVO_EFEMERIDES_ANIO = DATOS / "hdb" / "efemerides.json"  # los 366 días, importados desde el navegador


def efemerides_guardadas() -> dict[str, list[dict]]:
    """Todas las efemérides guardadas, por día ("11-18": [...]): el archivo con el año completo,
    más los días sueltos que haya leído el robot (si un día está en los dos, vale el del año completo)."""
    dias = {f.stem: leer_json(f, {}).get("items", []) for f in sorted(CARPETA_EFEMERIDES.glob("*.json"))}
    dias.update({k: v for k, v in ((leer_json(ARCHIVO_EFEMERIDES_ANIO, {}) or {}).get("dias") or {}).items() if v})
    return dict(sorted(dias.items()))


def efemerides_del_dia(mes: int, dia: int) -> list[dict]:
    return efemerides_guardadas().get(f"{mes:02d}-{dia:02d}", [])


def efemerides_destacadas(items: list[dict], n: int = 5) -> list[dict]:
    """Las n más llamativas de un día, en orden de año: la destacada por Historia de Boca, jugadores con títulos,
    partidos oficiales y después el resto (las más recientes primero)."""
    def peso(x):
        if x.get("destacado"):
            return 0
        if x.get("tipo") == "persona" and re.search(r"(?i)gan[óo] (un|dos|tres|\d+) t[íi]tulo", x.get("detalle", "")):
            return 1
        if x.get("tipo") == "partido" and "amistoso" not in normalizar(x.get("detalle", "")):
            return 2
        return 3
    elegidas = sorted(items, key=lambda x: (peso(x), -x["anio"]))[:n]
    return sorted(elegidas, key=lambda x: x["anio"])


# ------------------------------------------------------ historial partido a partido --
CARPETA_HISTORIALES = DATOS / "hdb" / "historiales"
RE_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
EQUIPO = r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑÜáéíóúñü'´`’\.\(\) ]{0,40}?"
# "Boca 1-River 2"; en desempates por penales: "Boca 0 (3)-River 0 (4)"
RE_MARCADOR = re.compile(rf"({EQUIPO})\s+(\d{{1,2}})(?:\s*\(\d{{1,2}}\))?\s*-\s*({EQUIPO})\s+(\d{{1,2}})(?:\s*\(\d{{1,2}}\))?(?![\d(])")


def _texto_con_filas(html: str) -> str:
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?i)</(tr|li|p|div|h\d)>|<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)<t[dh][^>]*>", " | ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    return re.sub(r"[ \t\r\f\v]+", " ", t)


def parsear_historial(html: str) -> dict:
    """Lista de partidos y totales de una página de historial. Devuelve {"partidos": [...], "totales": {...}}."""
    texto = _texto_con_filas(html)
    totales = {}
    for clave, patron in (("g", r"Victorias de Boca:\s*(\d+)"), ("e", r"Empates:\s*(\d+)"),
                          ("p", r"Triunfos de [^:\n]{1,40}:\s*(\d+)"), ("gf", r"Goles de Boca:\s*(\d+)"),
                          ("gc", r"Goles de (?!Boca)[^:\n]{1,40}:\s*(\d+)"), ("pj", r"Total Partidos:\s*(\d+)")):
        m = re.findall(patron, texto)
        if m:
            totales[clave] = int(m[-1])
    fechas = list(RE_FECHA.finditer(texto))
    partidos, vistos = [], set()
    for i, f in enumerate(fechas):
        fin = fechas[i + 1].start() if i + 1 < len(fechas) else min(len(texto), f.end() + 400)
        tramo = texto[f.end():min(fin, f.end() + 400)]
        marcador = None
        for m in RE_MARCADOR.finditer(tramo):
            if "boca" in normalizar(m.group(1)) or "boca" in normalizar(m.group(3)):
                marcador = m
                break
        if not marcador:
            continue
        local, gl, visit, gv = (marcador.group(1).strip(" |"), int(marcador.group(2)),
                                marcador.group(3).strip(" |"), int(marcador.group(4)))
        boca_local = "boca" in normalizar(local)
        gb, gr = (gl, gv) if boca_local else (gv, gl)
        limpiar = lambda t: re.sub(r"\s+", " ", re.sub(r"\s*\|\s*", " ", t)).strip(" ,.-–·()")
        torneo = limpiar(tramo[:marcador.start()]) or limpiar(tramo[marcador.end():])[:60]
        fecha = f"{f.group(3)}-{f.group(2)}-{f.group(1)}"
        clave = (fecha, gb, gr)
        if clave in vistos:
            continue
        vistos.add(clave)
        partidos.append({"fecha": fecha, "torneo": torneo[:70], "condicion": "L" if boca_local else "V",
                         "local": local, "visitante": visit, "goles_boca": gb, "goles_rival": gr,
                         "resultado": "G" if gb > gr else "P" if gb < gr else "E"})
    partidos.sort(key=lambda x: x["fecha"])
    return {"partidos": partidos, "totales": totales}


def importar_historiales(forzar: bool = False) -> None:
    """Una vez por semana baja el historial partido a partido de cada rival y lo verifica contra los totales."""
    meta = historiales()
    for r in meta.get("rivales", []):
        if not r.get("url"):
            continue
        clave = normalizar(r["nombres"][0]).replace(" ", "-").replace("'", "")
        archivo = CARPETA_HISTORIALES / f"{clave}.json"
        previo = leer_json(archivo, {})
        if not forzar and previo.get("importado", "") > (ahora() - dt.timedelta(days=7)).isoformat():
            continue
        try:
            html = http_get(r["url"], timeout=40).decode("utf-8", "ignore")
        except Exception as e:
            log(f"Historia de Boca: no pude leer el historial de {r['nombres'][0]} ({e})")
            continue
        datos = parsear_historial(html)
        ps, tot = datos["partidos"], datos["totales"]
        cuenta = {k: sum(1 for p in ps if p["resultado"] == k.upper()) for k in ("g", "e", "p")}
        ok = tot.get("g") is not None and all(cuenta[k] == tot.get(k) for k in ("g", "e", "p"))
        if not ok:
            log(f"Historia de Boca: el historial de {r['nombres'][0]} no cerró "
                f"(leí {len(ps)} partidos {cuenta}, la página dice {tot}). Me quedo con la versión anterior.")
            continue
        guardar_json(archivo, {"rival": r["nombres"][0], "importado": ahora().isoformat(timespec="seconds"),
                               "totales": tot, "hasta": ps[-1]["fecha"] if ps else r.get("hasta"), "partidos": ps})
        log(f"Historia de Boca: historial con {r['nombres'][0]} importado ({len(ps)} partidos, verificado)")


def historial_importado(nombre_rival: str) -> dict | None:
    base = buscar_historial(nombre_rival)
    if not base:
        return None
    clave = normalizar(base["nombres"][0]).replace(" ", "-").replace("'", "")
    return leer_json(CARPETA_HISTORIALES / f"{clave}.json")


# ------------------------------------------------------------ campañas --
ARCHIVO_CAMPANIAS = DATOS / "hdb" / "campanias.json"
CARPETA_POSICIONES = DATOS.parent / "sitio" / "estatico" / "img" / "posiciones"
CAMPANIAS_POR_CORRIDA = 40
PAUSA = 1.5  # segundos entre pedidos, para no cargar el sitio
EXCLUIR_TORNEOS = ("amistoso", "anulado", "gira")


def _post_form(url: str, campos: dict, timeout: int = 40) -> tuple[str, str]:
    """POST de formulario; devuelve (url final, html). Sigue la redirección a la página de la campaña."""
    import urllib.parse
    import urllib.request
    from comun import USER_AGENT
    req = urllib.request.Request(url, data=urllib.parse.urlencode(campos).encode(),
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read().decode("utf-8", "ignore")


def parsear_campania(html: str) -> list[dict]:
    """Partidos de una página de campaña: fecha, fase, local, visitante y goles."""
    partidos = []
    for fila in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", html):
        celdas = [re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"(?s)<div class=\"tooltip_templates\">.*?</div>\s*</div>\s*</div>", "", c)))
                  for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", fila)]
        celdas = [re.sub(r"<[^>]+>", " ", c).strip() for c in celdas]
        if len(celdas) < 3 or not RE_FECHA.fullmatch(celdas[0]):
            continue
        m = RE_MARCADOR.search(celdas[2])
        if not m:
            continue
        local, gl, visit, gv = m.group(1).strip(), int(m.group(2)), m.group(3).strip(), int(m.group(4))
        boca_local = normalizar(local) == "boca"
        if not boca_local and normalizar(visit) != "boca":
            continue
        gb, gr = (gl, gv) if boca_local else (gv, gl)
        d, me, a = celdas[0].split("/")
        partidos.append({"fecha": f"{a}-{me}-{d}", "fase": celdas[1], "rival": visit if boca_local else local,
                         "condicion": celdas[4] if len(celdas) > 4 and celdas[4] in ("L", "V", "N") else ("L" if boca_local else "V"),
                         "goles_boca": gb, "goles_rival": gr, "resultado": "G" if gb > gr else "P" if gb < gr else "E"})
    vistos, unicos = set(), []
    for x in partidos:
        k = (x["fecha"], x["rival"], x["goles_boca"], x["goles_rival"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(x)
    return unicos


def importar_campanias() -> None:
    """Catálogo de campañas oficiales (1905 en adelante) y, de a poco, el detalle de cada una con su tabla."""
    datos = leer_json(ARCHIVO_CAMPANIAS, {}) or {}
    catalogo = datos.get("catalogo") or {}
    hoy = ahora()
    # 1) catálogo: una vez por semana se recorren todos los años
    if datos.get("catalogo_actualizado", "") < (hoy - dt.timedelta(days=7)).date().isoformat():
        nuevo = {}
        for anio in range(1905, hoy.year + 1):
            time.sleep(PAUSA)
            try:
                html = http_get(f"{BASE}/anios-campeonatos.php?anios={anio}", timeout=25).decode("utf-8", "ignore")
            except Exception as e:
                log(f"Historia de Boca: no pude leer el catálogo de campañas de {anio} ({e})")
                nuevo = None
                break
            for cod, nombre in re.findall(r"value='(\d+)'>([^<]+)<", html):
                nombre = html_mod.unescape(nombre).strip()
                if any(x in normalizar(nombre) for x in EXCLUIR_TORNEOS):
                    continue
                nuevo[f"{anio}-{cod}"] = {"anio": anio, "codigo": cod, "nombre": nombre}
        if nuevo and len(nuevo) >= 0.9 * len(catalogo):  # si el sitio no respondió bien, queda el catálogo anterior
            catalogo = nuevo
            datos["catalogo"] = catalogo
            datos["catalogo_actualizado"] = hoy.date().isoformat()
            log(f"Historia de Boca: catálogo con {len(catalogo)} campañas oficiales")
    detalle = datos.get("detalle") or {}
    # 2) detalle: primero las que faltan; las del año en curso se renuevan cada día
    pendientes = [k for k in catalogo if k not in detalle]
    pendientes += [k for k in catalogo if k in detalle and catalogo[k]["anio"] >= hoy.year - (1 if hoy.month <= 2 else 0)
                   and detalle[k].get("consultado") != hoy.date().isoformat()]
    hechas = 0
    for k in pendientes[:CAMPANIAS_POR_CORRIDA]:
        c = catalogo[k]
        time.sleep(PAUSA)
        try:
            url, html = _post_form(f"{BASE}/validarcamp.php", {"anios": c["anio"], "comboCampeonato": c["codigo"]})
        except Exception as e:
            log(f"Historia de Boca: no pude leer la campaña {c['nombre']} {c['anio']} ({e}). Sigo en la próxima corrida.")
            break
        ps = parsear_campania(html)
        if not ps:
            detalle[k] = {"consultado": hoy.date().isoformat(), "partidos": [], "sin_datos": True}
            continue
        m = re.search(r'(?i)src="(/Fotos/Posiciones/[^"]+\.(?:gif|png|jpe?g))"', html)
        tabla = BASE + m.group(1) if m else None
        detalle[k] = {"consultado": hoy.date().isoformat(), "partidos": ps, "tabla": tabla}
        hechas += 1
    datos["detalle"] = detalle
    guardar_json(ARCHIVO_CAMPANIAS, datos)
    if hechas:
        faltan = len([k for k in catalogo if k not in detalle])
        log(f"Historia de Boca: {hechas} campañas importadas" + (f" (faltan {faltan})" if faltan else " (catálogo completo)"))


def campanias() -> list[dict]:
    """Campañas ya importadas, con totales: [{anio, nombre, pj, g, e, p, gf, gc, tabla}]."""
    datos = leer_json(ARCHIVO_CAMPANIAS, {}) or {}
    salida = []
    for k, c in (datos.get("catalogo") or {}).items():
        if any(x in normalizar(c["nombre"]) for x in EXCLUIR_TORNEOS):
            continue
        d = (datos.get("detalle") or {}).get(k)
        if d and d.get("totales") and not d.get("partidos"):  # copia cargada con los totales de cada campaña
            if d["totales"].get("pj"):
                salida.append({**c, **{x: d["totales"][x] for x in ("pj", "g", "e", "p", "gf", "gc")}, "tabla": d.get("tabla")})
            continue
        if not d or not d.get("partidos"):
            continue
        ps = d["partidos"]
        salida.append({**c, "pj": len(ps), "g": sum(p["resultado"] == "G" for p in ps), "e": sum(p["resultado"] == "E" for p in ps),
                       "p": sum(p["resultado"] == "P" for p in ps), "gf": sum(p["goles_boca"] for p in ps),
                       "gc": sum(p["goles_rival"] for p in ps), "tabla": d.get("tabla")})
    return salida


def catalogo_completo() -> bool:
    datos = leer_json(ARCHIVO_CAMPANIAS, {}) or {}
    cat = datos.get("catalogo") or {}
    return bool(cat) and all(k in (datos.get("detalle") or {}) for k in cat)


# ------------------------------------------------------- rankings de jugadores y DT --
ARCHIVO_RANKINGS = DATOS / "hdb" / "rankings.json"
RANKINGS_JUGADORES = {  # código de Historia de Boca → (clave, título)
    0: ("partidos", "Los que más partidos jugaron"),
    1: ("goles", "Máximos goleadores"),
    3: ("penales", "Más goles de penal"),
    16: ("cabeza", "Más goles de cabeza"),
    6: ("expulsiones", "Los más expulsados"),
    27: ("amonestaciones", "Los más amonestados"),
}


def _filas_ranking(html: str) -> list[list[str]]:
    filas = []
    for fila in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", html):
        fila = re.sub(r'(?is)<div class="tooltip_templates">.*?</div>\s*</div>\s*</div>', "", fila)
        celdas = [re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                  for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", fila)]
        if celdas and re.fullmatch(r"\d+º", celdas[0]):
            filas.append(celdas)
    return filas


def importar_rankings(forzar: bool = False) -> None:
    """Una vez por semana: rankings históricos (partidos oficiales) de jugadores y técnicos."""
    previo = leer_json(ARCHIVO_RANKINGS, {}) or {}
    if not forzar and previo.get("importado", "") > (ahora() - dt.timedelta(days=7)).isoformat():
        return
    hasta = ahora().year
    salida = {"importado": ahora().isoformat(timespec="seconds"), "alcance": "partidos oficiales", "jugadores": {}}
    for cod, (clave, titulo) in RANKINGS_JUGADORES.items():
        time.sleep(PAUSA)
        try:
            html = http_get(f"{BASE}/records-jugadores/20/{cod}/0/1905/{hasta}/6/0/0.html", timeout=40).decode("utf-8", "ignore")
        except Exception as e:
            log(f"Historia de Boca: no pude leer el ranking «{titulo}» ({e})")
            if clave in (previo.get("jugadores") or {}):
                salida["jugadores"][clave] = previo["jugadores"][clave]
            continue
        filas = []
        for c in _filas_ranking(html):
            nums = [int(x) for x in c[2:] if x.isdigit()]
            if not nums:
                continue
            fila = {"nombre": c[1], "valor": nums[0]}
            if clave == "goles" and len(nums) > 1:
                fila["partidos"] = nums[1]
            if clave == "partidos" and len(nums) > 1:
                fila["goles"] = nums[1]
            filas.append(fila)
        valores = [f["valor"] for f in filas]
        if len(filas) >= 5 and valores == sorted(valores, reverse=True):
            salida["jugadores"][clave] = {"titulo": titulo, "filas": filas}
        else:
            log(f"Historia de Boca: el ranking «{titulo}» no se pudo verificar; queda el anterior")
            if clave in (previo.get("jugadores") or {}):
                salida["jugadores"][clave] = previo["jugadores"][clave]
    # técnicos: partidos dirigidos y, de cada uno, ganados/empatados/perdidos sumando su tabla por campeonato
    tecnicos = []
    try:
        html = http_get(f"{BASE}/tecnicos-records/20/0/0/1930/{hasta}/6/0/0.html", timeout=40).decode("utf-8", "ignore")
        enlaces = dict(re.findall(r'href="(/tecnicos/[^"]+\.html)"[^>]*>([^<]+)</a>', html))
        por_nombre = {html_mod.unescape(v).strip(): k for k, v in enlaces.items()}
        for c in _filas_ranking(html):
            nombre, pj = c[1], int(c[2]) if c[2].isdigit() else None
            if not pj:
                continue
            t = {"nombre": nombre, "pj": pj, "nacimiento": c[3] if len(c) > 3 else ""}
            url = por_nombre.get(nombre)
            if url:
                time.sleep(PAUSA)
                try:
                    pag = http_get(BASE + url, timeout=40).decode("utf-8", "ignore")
                    ini = pag.find("Por campeonato")
                    bloque = pag[ini:pag.find("</table>", ini)] if ini >= 0 else ""
                    tot = [0, 0, 0, 0, 0, 0]
                    for fila in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", bloque):
                        nums = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"(?is)<td[^>]*>(.*?)</td>", fila)]
                        nums = [int(x) for x in nums[1:7] if x.isdigit()]
                        if len(nums) == 6:
                            tot = [a + b for a, b in zip(tot, nums)]
                    if tot[0] == pj and tot[1] + tot[2] + tot[3] == pj:
                        t.update(g=tot[1], e=tot[2], p=tot[3], gf=tot[4], gc=tot[5])
                except Exception as e:
                    log(f"Historia de Boca: no pude leer la ficha de {nombre} ({e})")
            tecnicos.append(t)
    except Exception as e:
        log(f"Historia de Boca: no pude leer el ranking de técnicos ({e})")
    if len(tecnicos) >= 5 and sum("g" in t for t in tecnicos) >= sum("g" in t for t in previo.get("tecnicos", [])):
        salida["tecnicos"] = tecnicos
    elif previo.get("tecnicos"):
        salida["tecnicos"] = previo["tecnicos"]
    guardar_json(ARCHIVO_RANKINGS, salida)
    log(f"Historia de Boca: rankings actualizados ({len(salida['jugadores'])} de jugadores, "
        f"{sum(1 for t in salida.get('tecnicos', []) if 'g' in t)} técnicos con balance verificado)")


def rankings() -> dict:
    return leer_json(ARCHIVO_RANKINGS, {}) or {}


def ejecutar() -> None:
    if not opciones():
        return
    if not opciones().get("actualizar_automaticamente", True):
        return  # Historia de Boca no habilitó la lectura automática: se usan las copias guardadas
    ejecutar_efemerides()
    importar_historiales()
    for paso in (importar_rankings, importar_campanias):
        try:
            paso()
        except Exception as e:  # un paso que falla no frena a los demás
            log(f"Historia de Boca: falló {paso.__name__} ({e})")


if __name__ == "__main__":
    import sys
    if "--historiales" in sys.argv:
        importar_historiales(forzar=True)
    else:
        ejecutar()
