"""Datos de Boca: fixture, resultados, posiciones, campañas anteriores y plantel.

Fuente: los datos públicos que usa la web de ESPN (gratis, sin clave). No es una API oficial
documentada: si algún día cambia, este es el único archivo que hay que tocar.
"""
from __future__ import annotations

import datetime as dt

from comun import DATOS_ESPN, ESTADO, ahora, config, guardar_json, http_get_json, leer_json, log, normalizar, parsear_fecha

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer"
MAX_PEDIDOS_HISTORICOS_POR_CORRIDA = 12


# ---------------------------------------------------------------- equipo --
def equipo_id() -> str:
    cfg = config()["datos_futbol"]
    if cfg.get("equipo_id_espn"):
        return str(cfg["equipo_id_espn"])
    guardado = leer_json(DATOS_ESPN / "equipo.json", {})
    if guardado.get("id"):
        return guardado["id"]
    buscado = normalizar(cfg["equipo_nombre"])
    datos = http_get_json(f"{SITE}/arg.1/teams")
    for liga in datos.get("sports", [{}])[0].get("leagues", []):
        for t in liga.get("teams", []):
            team = t.get("team", t)
            if normalizar(team.get("displayName", "")) == buscado or buscado in normalizar(team.get("displayName", "")):
                info = {"id": str(team["id"]), "nombre": team.get("displayName"), "escudo": _logo(team)}
                guardar_json(DATOS_ESPN / "equipo.json", info)
                log(f"Datos: {info['nombre']} tiene ID {info['id']} en ESPN")
                return info["id"]
    raise RuntimeError(f"No encontré a «{cfg['equipo_nombre']}» en ESPN")


def _logo(team: dict) -> str:
    if team.get("logo"):
        return team["logo"]
    logos = team.get("logos") or []
    return logos[0].get("href", "") if logos else ""


# --------------------------------------------------------------- partidos --
TRADUCCIONES = [
    (r"(?i)\bround of 64\b", "32avos de final"), (r"(?i)\bround of 32\b", "16avos de final"),
    (r"(?i)\bround of 16\b", "Octavos de final"), (r"(?i)\bquarter-?finals?\b", "Cuartos de final"),
    (r"(?i)\bsemi-?finals?\b", "Semifinal"), (r"(?i)\bthird place\b", "Tercer puesto"),
    (r"(?i)\bgroup stage\b", "Fase de grupos"), (r"(?i)\bgroup ([A-Z])\b", r"Grupo \1"),
    (r"(?i)\bknockout round play-?offs?\b", "Repechaje"), (r"(?i)\bplay-?offs?\b", "Repechaje"),
    (r"(?i)\bpreliminary round\b", "Fase previa"), (r"(?i)\bqualifying\b", "Fase previa"),
    (r"(?i)\b(1st|first) leg\b", "ida"), (r"(?i)\b(2nd|second) leg\b", "vuelta"),
    (r"(?i)\bmatchday\b", "Fecha"), (r"(?i)(?<!de )\bfinal\b", "Final"), (r"(?i)\bleg\b", "partido"),
]


def traducir(texto: str) -> str:
    import re
    for patron, reemplazo in TRADUCCIONES:
        texto = re.sub(patron, reemplazo, texto or "")
    return texto.replace(" - ida", ", ida").replace(" - vuelta", ", vuelta").strip()

def _goles(comp: dict):
    s = comp.get("score")
    if isinstance(s, dict):
        s = s.get("displayValue", s.get("value"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _estado(status: dict) -> str:
    tipo = (status or {}).get("type", {})
    nombre = (tipo.get("name") or "").upper()
    if "POSTPONED" in nombre or "CANCELED" in nombre or "SUSPENDED" in nombre:
        return "postergado"
    if tipo.get("completed") or tipo.get("state") == "post":
        return "finalizado"
    if tipo.get("state") == "in":
        return "en_juego"
    return "programado"


def convertir_evento(ev: dict, slug: str, nombre_comp: str, boca_id: str) -> dict | None:
    comps = ev.get("competitions") or []
    if not comps:
        return None
    c = comps[0]
    equipos = {}
    for comp in c.get("competitors", []):
        team = comp.get("team", {})
        lado = comp.get("homeAway", "home")
        shoot = comp.get("shootoutScore")
        equipos[lado] = {
            "id": str(team.get("id", comp.get("id", ""))),
            "nombre": team.get("displayName") or team.get("name", "?"),
            "corto": team.get("shortDisplayName") or team.get("abbreviation") or team.get("displayName", "?"),
            "escudo": _logo(team),
            "goles": _goles(comp),
            "penales": int(shoot) if isinstance(shoot, (int, float)) else None,
        }
    if "home" not in equipos or "away" not in equipos:
        return None
    local, visit = equipos["home"], equipos["away"]
    es_local = local["id"] == boca_id
    if not es_local and visit["id"] != boca_id:
        return None
    status = c.get("status") or ev.get("status") or {}
    estado = _estado(status)
    boca, rival = (local, visit) if es_local else (visit, local)

    resultado = None
    if estado == "finalizado" and boca["goles"] is not None and rival["goles"] is not None:
        if boca["goles"] > rival["goles"]:
            resultado = "G"
        elif boca["goles"] < rival["goles"]:
            resultado = "P"
        else:
            resultado = "E"
    fecha = parsear_fecha(ev.get("date") or c.get("date"))
    temporada = (ev.get("season") or {}).get("year") or (fecha.year if fecha else None)
    venue = c.get("venue") or {}
    detalle = (status.get("type") or {}).get("shortDetail", "")
    # ESPN marca "TBD" cuando el horario no está confirmado
    hora_a_confirmar = bool(c.get("timeValid") is False or "TBD" in detalle.upper())
    return {
        "id": str(ev.get("id")),
        "fecha": fecha.isoformat() if fecha else None,
        "hora_a_confirmar": hora_a_confirmar,
        "competencia": nombre_comp,
        "competencia_slug": slug,
        "instancia": traducir((c.get("notes") or [{}])[0].get("headline", "")) if c.get("notes") else "",
        "temporada": temporada,
        "estado": estado,
        "detalle": detalle,
        "estadio": venue.get("fullName", ""),
        "ciudad": (venue.get("address") or {}).get("city", ""),
        "condicion": "L" if es_local else "V",
        "local": local,
        "visitante": visit,
        "rival": {k: rival[k] for k in ("id", "nombre", "corto", "escudo")},
        "goles_boca": boca["goles"],
        "goles_rival": rival["goles"],
        "penales_boca": boca["penales"],
        "penales_rival": rival["penales"],
        "resultado": resultado,
    }


def bajar_calendario(slug: str, nombre: str, boca_id: str, temporada: int | None = None) -> list[dict]:
    urls = []
    base = f"{SITE}/{slug}/teams/{boca_id}/schedule"
    if temporada:
        urls.append(f"{base}?season={temporada}")
    else:
        urls += [base, f"{base}?fixture=true"]
    partidos = []
    for url in urls:
        try:
            datos = http_get_json(url)
        except Exception as e:
            log(f"Datos: {slug} {temporada or ''} sin datos ({e})")
            continue
        for ev in datos.get("events", []):
            p = convertir_evento(ev, slug, nombre, boca_id)
            if p:
                partidos.append(p)
    return partidos


# ------------------------------------------------------------- posiciones --
MAPA_STATS = {
    "gamesPlayed": "pj", "wins": "g", "ties": "e", "losses": "p", "pointsFor": "gf",
    "pointsAgainst": "gc", "pointDifferential": "dg", "points": "pts", "rank": "pos",
}
MAPA_ABREV = {"GP": "pj", "W": "g", "D": "e", "L": "p", "F": "gf", "A": "gc", "GD": "dg", "P": "pts"}


def _fila(entry: dict, boca_id: str) -> dict:
    team = entry.get("team", {})
    fila = {"equipo": team.get("displayName", "?"), "corto": team.get("shortDisplayName") or team.get("abbreviation", ""),
            "id": str(team.get("id", "")), "escudo": _logo(team)}
    for st in entry.get("stats", []):
        clave = MAPA_STATS.get(st.get("name")) or MAPA_ABREV.get(st.get("abbreviation"))
        if clave and clave not in fila:
            try:
                fila[clave] = int(float(st.get("value", st.get("displayValue", 0))))
            except (TypeError, ValueError):
                pass
    fila["es_boca"] = fila["id"] == boca_id
    nota = entry.get("note") or {}
    if nota.get("description"):
        fila["nota"] = nota["description"]
        fila["color"] = nota.get("color", "")
    return fila


def bajar_posiciones(slug: str, nombre: str, boca_id: str, temporada: int | None = None) -> dict | None:
    url = f"{STANDINGS}/{slug}/standings" + (f"?season={temporada}" if temporada else "")
    try:
        datos = http_get_json(url)
    except Exception as e:
        log(f"Datos: tabla {slug} {temporada or ''} no disponible ({e})")
        return None
    grupos = []
    bloques = datos.get("children") or ([datos] if datos.get("standings") else [])
    for b in bloques:
        entries = (b.get("standings") or {}).get("entries", [])
        if not entries:
            continue
        filas = [_fila(e, boca_id) for e in entries]
        filas.sort(key=lambda f: (f.get("pos") or 999, -(f.get("pts") or 0)))
        for i, f in enumerate(filas, 1):
            f["pos"] = i  # posición dentro de su grupo o zona
        grupos.append({"nombre": traducir(b.get("name") or b.get("abbreviation") or nombre), "filas": filas})
    if not grupos:
        return None
    temporada_txt = (datos.get("seasons") or [{}])[0].get("displayName") if datos.get("seasons") else None
    return {"slug": slug, "nombre": nombre, "temporada": temporada or temporada_txt or ahora().year,
            "grupos": grupos, "actualizado": ahora().isoformat(timespec="minutes")}


def campaña_de_boca(tabla: dict) -> dict | None:
    for g in tabla.get("grupos", []):
        for f in g["filas"]:
            if f.get("es_boca"):
                return {"grupo": g["nombre"], "equipos": len(g["filas"]),
                        **{k: f.get(k) for k in ("pos", "pj", "g", "e", "p", "gf", "gc", "pts")}}
    return None


# ----------------------------------------------------------------- plantel --
def bajar_plantel(boca_id: str) -> list[dict]:
    datos = http_get_json(f"{SITE}/arg.1/teams/{boca_id}/roster")
    atletas = datos.get("athletes", [])
    if atletas and "items" in atletas[0]:  # algunos deportes los agrupan por posición
        atletas = [a for grupo in atletas for a in grupo.get("items", [])]
    jugadores = []
    for a in atletas:
        pos = a.get("position") or {}
        jugadores.append({
            "nombre": a.get("displayName") or a.get("fullName", "?"),
            "numero": a.get("jersey", ""),
            "posicion": pos.get("displayName") or pos.get("name", ""),
            "pos_abrev": pos.get("abbreviation", ""),
            "edad": a.get("age"),
            "nacionalidad": a.get("citizenship", ""),
            "foto": (a.get("headshot") or {}).get("href", ""),
        })
    return jugadores


# --------------------------------------------------------------- historial --
def calcular_historial(partidos: list[dict]) -> dict:
    """Historial contra cada rival a partir de los partidos guardados."""
    por_rival: dict[str, dict] = {}
    for p in partidos:
        if p["estado"] != "finalizado" or p["resultado"] is None:
            continue
        r = p["rival"]
        h = por_rival.setdefault(r["id"], {"rival": r, "pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0,
                                           "partidos": [], "desde": None})
        h["pj"] += 1
        h[{"G": "g", "E": "e", "P": "p"}[p["resultado"]]] += 1
        h["gf"] += p["goles_boca"]
        h["gc"] += p["goles_rival"]
        h["partidos"].append({k: p[k] for k in ("id", "fecha", "competencia", "condicion", "goles_boca", "goles_rival",
                                                "penales_boca", "penales_rival", "resultado", "temporada")})
    for h in por_rival.values():
        h["partidos"].sort(key=lambda x: x["fecha"] or "", reverse=True)
        h["desde"] = h["partidos"][-1]["temporada"] if h["partidos"] else None
    return por_rival


# ---------------------------------------------------------------- ejecutar --
def ejecutar() -> None:
    cfg = config()["datos_futbol"]
    if not cfg.get("activado"):
        return
    boca_id = equipo_id()
    año = ahora().year
    estado = leer_json(ESTADO / "espn.json", {"historico_listo": []})
    guardados = {p["id"]: p for p in leer_json(DATOS_ESPN / "partidos.json", [])}

    # 1) Temporada actual (siempre) – fixture y resultados
    for comp in cfg["competencias"]:
        for p in bajar_calendario(comp["slug"], comp["nombre"], boca_id):
            guardados[p["id"]] = p

    # 2) Temporadas anteriores (de a poco, una sola vez cada una)
    pedidos = 0
    temporadas = leer_json(DATOS_ESPN / "temporadas.json", {})
    for anio in range(año - 1, cfg.get("temporada_desde", 2010) - 1, -1):
        for comp in cfg["competencias"]:
            clave = f"{anio}:{comp['slug']}"
            if clave in estado["historico_listo"]:
                continue
            if pedidos >= MAX_PEDIDOS_HISTORICOS_POR_CORRIDA:
                break
            for p in bajar_calendario(comp["slug"], comp["nombre"], boca_id, anio):
                guardados[p["id"]] = p
            if comp.get("tabla"):
                tabla = bajar_posiciones(comp["slug"], comp["nombre"], boca_id, anio)
                if tabla and (c := campaña_de_boca(tabla)):
                    temporadas.setdefault(str(anio), {})[comp["slug"]] = {"competencia": comp["nombre"], **c}
            estado["historico_listo"].append(clave)
            pedidos += 2
    if pedidos:
        log(f"Datos: historial ampliado ({len(estado['historico_listo'])} temporadas-torneo bajadas)")

    # 3) Tablas actuales
    tablas = {}
    for comp in cfg["competencias"]:
        if comp.get("tabla"):
            t = bajar_posiciones(comp["slug"], comp["nombre"], boca_id)
            if t and campaña_de_boca(t):
                tablas[comp["slug"]] = t
                temporadas.setdefault(str(año), {})[comp["slug"]] = {"competencia": comp["nombre"], **campaña_de_boca(t)}

    # 4) Plantel
    try:
        plantel = bajar_plantel(boca_id)
        if plantel:
            guardar_json(DATOS_ESPN / "plantel.json", {"actualizado": ahora().isoformat(timespec="minutes"),
                                                       "jugadores": plantel})
    except Exception as e:
        log(f"Datos: plantel no disponible ({e})")

    partidos = sorted(guardados.values(), key=lambda p: p["fecha"] or "")
    guardar_json(DATOS_ESPN / "partidos.json", partidos)
    if tablas:
        guardar_json(DATOS_ESPN / "posiciones.json", tablas)
    guardar_json(DATOS_ESPN / "temporadas.json", temporadas)
    guardar_json(DATOS_ESPN / "historial.json", calcular_historial(partidos))
    guardar_json(ESTADO / "espn.json", estado)
    proximos = [p for p in partidos if p["estado"] == "programado"]
    log(f"Datos: {len(partidos)} partidos guardados, {len(proximos)} por jugar, {len(tablas)} tablas")


# --------------------------------------------------------------- consultas --
def resumen_partido(evento_id: str, slug: str) -> dict:
    """Goles y expulsiones de un partido (para las crónicas automáticas)."""
    datos = http_get_json(f"{SITE}/{slug}/summary?event={evento_id}")
    hechos = []
    for k in datos.get("keyEvents", []) or []:
        tipo = ((k.get("type") or {}).get("type") or (k.get("type") or {}).get("text") or "").lower()
        es_gol = k.get("scoringPlay") or "goal" in tipo
        es_roja = "red" in tipo
        if not (es_gol or es_roja):
            continue
        jugador = ""
        for part in k.get("participants", []) or []:
            jugador = (part.get("athlete") or {}).get("displayName", "")
            if jugador:
                break
        hechos.append({
            "tipo": "gol" if es_gol else "expulsión",
            "minuto": (k.get("clock") or {}).get("displayValue", ""),
            "equipo": (k.get("team") or {}).get("displayName", ""),
            "jugador": jugador,
            "detalle": k.get("text", "")[:160],
        })
    return {"hechos": hechos}


def proximos_y_ultimos(partidos: list[dict] | None = None):
    if partidos is None:
        partidos = leer_json(DATOS_ESPN / "partidos.json", [])
    limite = ahora() - dt.timedelta(hours=3)
    proximos = [p for p in partidos if p["estado"] in ("programado", "en_juego") and p["fecha"]
                and parsear_fecha(p["fecha"]) >= limite]
    jugados = [p for p in partidos if p["estado"] == "finalizado"]
    proximos.sort(key=lambda p: p["fecha"])
    jugados.sort(key=lambda p: p["fecha"] or "", reverse=True)
    return proximos, jugados


if __name__ == "__main__":
    ejecutar()
