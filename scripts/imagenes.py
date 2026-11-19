"""Fotos para las notas, siempre con licencia libre y con el crédito del autor.

Las fotos de los diarios tienen dueño (el medio o la agencia), así que no las copiamos. En su lugar:
  1. Si alguien del equipo mandó una foto por Telegram, se usa esa (eso lo hace bot_telegram.py).
  2. Si no, se busca en Wikidata al protagonista de la nota (jugador, DT o dirigente vinculado a Boca)
     y se usa su foto de Wikimedia Commons.
  3. Si no hay protagonista con foto, va una foto de la Bombonera, también de Wikimedia Commons.

Las fotos se bajan una sola vez por persona a sitio/estatico/img/archivo/ y se reutilizan.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.parse

from comun import (ESTADO, NOTAS, SITIO, ahora, config, guardar_json, http_get, leer_json, limpiar_html, log,
                   normalizar)

WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
CACHE = ESTADO / "imagenes_wikimedia.json"
CARPETA = SITIO / "estatico" / "img" / "archivo"
ANCHO = 960            # ancho estándar de miniatura de Wikimedia
DIAS_REINTENTO = 21    # si una persona no tenía foto, se vuelve a buscar después de estos días
DIAS_POOL = 30         # cada cuánto se renueva la lista de fotos de la Bombonera
MAX_POR_CORRIDA = 25

PALABRAS_PERSONA = ("futbol", "football", "entrenador", "director tecnico", "dirigente", "presidente", "arquero",
                    "delantero", "defensor", "mediocampista", "centrocampista", "portero")
NO_PERSONAS = {"boca juniors", "boca", "xeneize", "la bombonera", "bombonera", "river plate", "river", "superclasico",
               "copa sudamericana", "copa libertadores", "copa argentina", "liga profesional", "afa", "conmebol",
               "seleccion argentina", "reserva", "plantel", "mercado de pases", "barranquilla", "hinchas"}


class SinRed(Exception):
    """Wikimedia no responde: se corta para no demorar la corrida."""


# ---------------------------------------------------------------- pedidos --
def _ua() -> str:
    url = config().get("sitio", {}).get("url", "https://github.com")
    return f"RinconBosteroBot/1.0 ({url}; fotos de archivo con credito) python-urllib"


def _api(base: str, **params) -> dict:
    params.setdefault("format", "json")
    url = base + "?" + urllib.parse.urlencode(params)
    try:
        return json.loads(http_get(url, intentos=2, timeout=20, headers={"User-Agent": _ua()}).decode("utf-8"))
    except Exception as e:
        raise SinRed(str(e)) from None


def _cache() -> dict:
    c = leer_json(CACHE, {}) or {}
    c.setdefault("personas", {})
    c.setdefault("archivos", {})
    return c


# ------------------------------------------------------------- licencias --
def _licencia_ok(nombre: str) -> bool:
    n = normalizar(nombre)
    if "nc" in re.split(r"[\s\-]", n) or "nd" in re.split(r"[\s\-]", n):
        return False
    return n.startswith(("cc0", "cc by", "cc-by", "public domain", "dominio publico", "pd")) or n == "pd"


def _info_archivos(titulos: list[str]) -> dict[str, dict]:
    """Datos de hasta 50 archivos de Commons: miniatura, tamaño, autor y licencia (solo los de licencia libre)."""
    salida = {}
    for i in range(0, len(titulos), 50):
        tanda = [t if t.startswith("File:") else "File:" + t for t in titulos[i:i + 50]]
        r = _api(COMMONS, action="query", prop="imageinfo", titles="|".join(tanda),
                 iiprop="url|size|mime|extmetadata", iiurlwidth=ANCHO, iiextmetadatafilter="Artist|LicenseShortName")
        for pag in (r.get("query", {}).get("pages") or {}).values():
            ii = (pag.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata") or {}
            licencia = (meta.get("LicenseShortName") or {}).get("value", "")
            if not ii.get("thumburl") or not _licencia_ok(licencia):
                continue
            if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                continue
            autor = limpiar_html((meta.get("Artist") or {}).get("value", "")) or "Autor desconocido"
            autor = re.sub(r"\s+", " ", autor).strip()[:80]
            salida[pag.get("title", "").removeprefix("File:")] = {
                "thumb": ii["thumburl"], "ancho": ii.get("width", 0), "alto": ii.get("height", 0),
                "autor": autor, "licencia": licencia,
            }
    return salida


def _bajar(archivo: str, info: dict, cache: dict) -> dict | None:
    """Baja la miniatura (una sola vez por archivo) y devuelve {imagen, credito}."""
    if archivo in cache["archivos"] and (SITIO / "estatico" / cache["archivos"][archivo]["imagen"]).exists():
        return cache["archivos"][archivo]
    ext = ".png" if info["thumb"].split("?")[0].lower().endswith(".png") else ".jpg"
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(archivo.rsplit(".", 1)[0]))[:50].strip("-") or "foto"
    nombre = f"{base}-{hashlib.sha1(archivo.encode()).hexdigest()[:6]}{ext}"
    try:
        datos = http_get(info["thumb"], intentos=2, timeout=30, headers={"User-Agent": _ua()})
    except Exception as e:
        raise SinRed(str(e)) from None
    if len(datos) < 5000:
        return None
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / nombre).write_bytes(datos)
    res = {"imagen": f"img/archivo/{nombre}",
           "credito": f"Foto de archivo: {info['autor']} / Wikimedia Commons ({info['licencia']})"}
    cache["archivos"][archivo] = res
    return res


# --------------------------------------------------------------- personas --
# Boca en Wikidata: club (Q170703), femenino (Q20983574) y reserva (Q4936095). Van fijos porque la búsqueda
# por nombre también trae a Boca Juniors de Cali, de Gibraltar, de Belice, etc.
IDS_BOCA = {"Q170703", "Q20983574", "Q4936095"}


def _vinculos(claims: dict, prop: str) -> set[str]:
    out = set()
    for c in claims.get(prop, []) or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.add(v["id"])
    return out


def _foto_wikidata(nombre: str, cache: dict) -> str | None:
    """Nombre del archivo de Commons con la foto de esa persona, solo si Wikidata la vincula con Boca."""
    r = _api(WIKIDATA, action="wbsearchentities", search=nombre, language="es", uselang="es", type="item", limit=7)
    candidatos = [x["id"] for x in r.get("search", [])
                  if any(p in normalizar(x.get("description", "")) for p in PALABRAS_PERSONA)]
    if not candidatos:
        return None
    boca = IDS_BOCA
    ents = _api(WIKIDATA, action="wbgetentities", ids="|".join(candidatos[:5]), props="claims").get("entities", {})
    for qid in candidatos[:5]:
        claims = (ents.get(qid) or {}).get("claims") or {}
        fotos = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") for c in claims.get("P18", [])]
        fotos = [f for f in fotos if isinstance(f, str)]
        # P54 = jugó en ese club, P6087 = lo dirigió como DT
        if fotos and boca & (_vinculos(claims, "P54") | _vinculos(claims, "P6087")):
            return fotos[0]
    return None


def foto_de_persona(nombre: str, cache: dict) -> dict | None:
    clave = normalizar(nombre)
    guardado = cache["personas"].get(clave)
    if guardado:
        if guardado.get("archivo"):
            info_bajada = cache["archivos"].get(guardado["archivo"])
            if info_bajada and (SITIO / "estatico" / info_bajada["imagen"]).exists():
                return info_bajada
        elif guardado.get("buscado", "") > (ahora() - dt.timedelta(days=DIAS_REINTENTO)).isoformat():
            return None
    archivo = _foto_wikidata(nombre, cache)
    res = None
    if archivo:
        infos = _info_archivos([archivo])
        info = infos.get(archivo.replace("_", " ")) or next(iter(infos.values()), None)
        if info:
            res = _bajar(archivo, info, cache)
    cache["personas"][clave] = {"archivo": archivo if res else None, "buscado": ahora().isoformat()}
    return res


def _nombres_posibles(nota: dict) -> list[str]:
    nombres = list(nota.get("protagonistas") or [])
    for e in nota.get("etiquetas") or []:
        # Las etiquetas que parecen nombre y apellido (dos o más palabras con mayúscula)
        palabras = e.split()
        if len(palabras) >= 2 and all(p[:1].isupper() for p in palabras if len(p) > 3) \
                and normalizar(e) not in NO_PERSONAS and not any(c.isdigit() for c in e):
            nombres.append(e)
    vistos, salida = set(), []
    for n in nombres:
        k = normalizar(n)
        if k and k not in vistos and k not in NO_PERSONAS:
            vistos.add(k)
            salida.append(n)
    return salida[:4]


# ------------------------------------------------------------- Bombonera --
def _pool_bombonera(cache: dict) -> list[str]:
    pool = cache.get("bombonera") or {}
    if pool.get("archivos") and pool.get("fecha", "") > (ahora() - dt.timedelta(days=DIAS_POOL)).isoformat():
        return pool["archivos"]
    r = _api(COMMONS, action="query", generator="search", gsrsearch="Bombonera estadio Boca Juniors filetype:bitmap",
             gsrnamespace=6, gsrlimit=50, prop="imageinfo", iiprop="size|mime")
    titulos = [pag["title"].removeprefix("File:") for pag in (r.get("query", {}).get("pages") or {}).values()
               if not re.search(r"logo|escudo|crest|entrada|ticket", pag.get("title", ""), re.I)]
    infos = _info_archivos(titulos)
    # Solo fotos apaisadas y de buen tamaño (las verticales y los planos quedan mal como portada)
    buenas = sorted(t for t, i in infos.items() if i["ancho"] >= 1000 and i["ancho"] >= i["alto"] * 1.2)
    if not buenas:
        return pool.get("archivos", [])
    cache["bombonera"] = {"fecha": ahora().isoformat(), "archivos": buenas, "info": {t: infos[t] for t in buenas}}
    return buenas


def foto_de_la_bombonera(semilla: str, cache: dict) -> dict | None:
    pool = _pool_bombonera(cache)
    if not pool:
        return None
    i = int(hashlib.sha1(semilla.encode()).hexdigest(), 16) % len(pool)
    archivo = pool[i]
    info = (cache.get("bombonera", {}).get("info") or {}).get(archivo)
    if not info:
        info = _info_archivos([archivo]).get(archivo)
    return _bajar(archivo, info, cache) if info else None


# ----------------------------------------------------------------- notas --
def elegir_foto(nota: dict, cache: dict) -> dict | None:
    for nombre in _nombres_posibles(nota):
        res = foto_de_persona(nombre, cache)
        if res:
            return res
    return foto_de_la_bombonera(nota.get("id") or nota.get("titulo", ""), cache)


def ejecutar(dias: int = 10) -> int:
    """Le pone foto a las notas recientes que no tienen. Devuelve cuántas completó."""
    if not config().get("imagenes", {}).get("activado", True):
        return 0
    corte = (ahora() - dt.timedelta(days=dias)).isoformat()
    pendientes = []
    for ruta in NOTAS.glob("*.json"):
        n = leer_json(ruta)
        if n and not n.get("imagen") and n.get("fecha", "") >= corte:
            pendientes.append((ruta, n))
    if not pendientes:
        return 0
    pendientes.sort(key=lambda x: x[1].get("fecha", ""), reverse=True)
    cache = _cache()
    hechas = 0
    try:
        for ruta, n in pendientes[:MAX_POR_CORRIDA]:
            res = elegir_foto(n, cache)
            if res:
                n["imagen"] = res["imagen"]
                n["imagen_credito"] = res["credito"]
                guardar_json(ruta, n)
                hechas += 1
    except SinRed as e:
        log(f"Imágenes: Wikimedia no respondió ({e}). Se reintenta en la próxima corrida.")
    finally:
        guardar_json(CACHE, cache)
    log(f"Imágenes: {hechas} notas con foto nueva")
    return hechas


if __name__ == "__main__":
    ejecutar()
