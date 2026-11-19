"""Jugadores de Boca y los otros clubes en los que jugaron, desde Wikidata (datos libres, CC0).

Se usa para la «Grilla bostera». Se baja una vez por semana a datos/wikidata/jugadores_boca.json.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse

from comun import DATOS, ahora, config, guardar_json, http_get, leer_json, log

ARCHIVO = DATOS / "wikidata" / "jugadores_boca.json"
BOCA = "Q170703"
DIAS = 7
MIN_JUGADORES_CLUB = 8   # clubes con menos jugadores compartidos no sirven para la grilla

CONSULTA = """SELECT ?p ?pLabel (GROUP_CONCAT(DISTINCT STRAFTER(STR(?c), "entity/"); separator="|") AS ?clubes) WHERE {
  ?p wdt:P54 wd:%s ; wdt:P106 wd:Q937857 .
  OPTIONAL { ?p wdt:P54 ?c }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
} GROUP BY ?p ?pLabel""" % BOCA


def _ua() -> str:
    return f"RinconBosteroBot/1.0 ({config().get('sitio', {}).get('url', '')}; grilla de jugadores) python-urllib"


def nombre_corto(etiqueta: str) -> str:
    """'Club Atlético River Plate' → 'River Plate'; 'selección de fútbol de Argentina' → 'Selección Argentina'."""
    t = etiqueta.strip()
    m = re.match(r"(?i)selecci[oó]n de f[uú]tbol de (.+)$", t)
    if m:
        pais = m.group(1)
        gent = {"Argentina": "Argentina", "Uruguay": "uruguaya", "Paraguay": "paraguaya", "Colombia": "colombiana",
                "Brasil": "brasileña", "Chile": "chilena", "Perú": "peruana", "Bolivia": "boliviana",
                "Ecuador": "ecuatoriana", "Venezuela": "venezolana", "México": "mexicana"}.get(pais)
        return f"Selección {gent}" if gent else f"Selección de {pais}"
    for pref in ("Club Atlético ", "Club Deportivo ", "Club Social y Deportivo ", "Club de Fútbol ", "Asociación Atlética ",
                 "Club de Gimnasia y Esgrima ", "Club Ferro Carril ", "Club "):
        if t.startswith(pref) and len(t) > len(pref) + 3:
            t = t[len(pref):]
            break
    t = re.sub(r"\s+(Fútbol Club|Football Club|Futebol Clube|F\.C\.|FC|Club de Fútbol)$", "", t)
    arreglos = {"Gimnasia y Esgrima La Plata": "Gimnasia (LP)", "La Plata": "Gimnasia (LP)",
                "Estudiantes de La Plata": "Estudiantes (LP)", "San Lorenzo de Almagro": "San Lorenzo",
                "Newell’s Old Boys": "Newell's", "Newell's Old Boys": "Newell's", "Oeste": "Ferro",
                "Clube de Regatas do Flamengo": "Flamengo", "Sport Club Corinthians Paulista": "Corinthians",
                "Inter de Milán": "Inter", "A.S. Roma": "Roma", "A.C. Milan": "Milan", "Real Zaragoza": "Zaragoza",
                "Villarreal": "Villarreal", "Atlético de Madrid": "Atlético Madrid", "Colo-Colo": "Colo Colo",
                "Universidad Católica": "U. Católica (Chile)", "Quilmes Atlético": "Quilmes",
                "Talleres de Córdoba": "Talleres", "Genoa Cricket & Football": "Genoa"}
    return arreglos.get(t, t)


def actualizar(forzar: bool = False) -> bool:
    previo = leer_json(ARCHIVO, {}) or {}
    if not forzar and previo.get("consultado", "") > (ahora() - dt.timedelta(days=DIAS)).isoformat():
        return False
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(CONSULTA)
    try:
        datos = json.loads(http_get(url, intentos=2, timeout=90, headers={
            "User-Agent": _ua(), "Accept": "application/sparql-results+json"}).decode("utf-8"))
    except Exception as e:
        log(f"Wikidata: no pude bajar los jugadores ({e}). Queda la copia anterior.")
        return False
    filas = datos.get("results", {}).get("bindings", [])
    jugadores, cuenta = [], {}
    for b in filas:
        nombre = (b.get("pLabel") or {}).get("value", "").strip()
        if not nombre or re.fullmatch(r"Q\d+", nombre):
            continue
        clubes = sorted({c for c in (b.get("clubes") or {}).get("value", "").split("|") if c and c != BOCA})
        jugadores.append([nombre, clubes])
        for c in clubes:
            cuenta[c] = cuenta.get(c, 0) + 1
    if len(jugadores) < 300:  # algo salió mal: no piso una copia buena con una chica
        log(f"Wikidata: vinieron solo {len(jugadores)} jugadores. Queda la copia anterior.")
        return False
    utiles = [c for c, n in cuenta.items() if n >= MIN_JUGADORES_CLUB]
    etiquetas = {}
    for i in range(0, len(utiles), 50):
        u = ("https://www.wikidata.org/w/api.php?action=wbgetentities&props=labels&languages=es|en&format=json&ids="
             + "|".join(utiles[i:i + 50]))
        try:
            ents = json.loads(http_get(u, intentos=2, timeout=30, headers={"User-Agent": _ua()}).decode()).get("entities", {})
        except Exception as e:
            log(f"Wikidata: no pude leer los nombres de los clubes ({e}).")
            return False
        for q, ent in ents.items():
            lab = (ent.get("labels") or {})
            etiquetas[q] = (lab.get("es") or lab.get("en") or {}).get("value", "")
    clubes = {}
    for q in utiles:
        et = etiquetas.get(q, "")
        if not et or re.search(r"(?i)sub-?\d|olímpic|juvenil|reserva|femenin|B$", et):
            continue
        clubes[q] = {"nombre": nombre_corto(et), "jugadores": cuenta[q]}
    salida = {"_fuente": "Wikidata (CC0). Jugadores con «miembro del equipo deportivo: Club Atlético Boca Juniors».",
              "consultado": ahora().isoformat(), "clubes": clubes,
              "jugadores": [[n, [c for c in cs if c in clubes]] for n, cs in sorted(jugadores)]}
    guardar_json(ARCHIVO, salida)
    log(f"Wikidata: {len(jugadores)} jugadores de Boca, {len(clubes)} clubes para la grilla")
    return True


def ejecutar() -> None:
    actualizar()


if __name__ == "__main__":
    actualizar(forzar=True)
