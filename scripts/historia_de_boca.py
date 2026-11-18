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


def efemerides_del_dia(mes: int, dia: int) -> list[dict]:
    return leer_json(CARPETA_EFEMERIDES / f"{mes:02d}-{dia:02d}.json", {}).get("items", [])


def efemerides_guardadas() -> dict[str, list[dict]]:
    """Todas las efemérides juntadas hasta ahora, por día ("11-18": [...])."""
    return {f.stem: leer_json(f, {}).get("items", []) for f in sorted(CARPETA_EFEMERIDES.glob("*.json"))}


# ------------------------------------------------------ historial partido a partido --
CARPETA_HISTORIALES = DATOS / "hdb" / "historiales"
RE_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
EQUIPO = r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑÜáéíóúñü'´`’\.\(\) ]{0,40}?"
RE_MARCADOR = re.compile(rf"({EQUIPO})\s+(\d{{1,2}})\s*-\s*({EQUIPO})\s+(\d{{1,2}})(?!\d)")


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


def ejecutar() -> None:
    if not opciones():
        return
    ejecutar_efemerides()
    importar_historiales()


if __name__ == "__main__":
    import sys
    if "--historiales" in sys.argv:
        importar_historiales(forzar=True)
    else:
        ejecutar()
