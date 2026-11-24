"""Integración con BocaStats (bocastats.com), con permiso de sus autores.

Qué trae (todo se muestra dentro de nuestra web, con el crédito "Datos históricos: BocaStats"):
- El historial contra los 240 rivales (totales, incluidos amistosos y era amateur).
- Partido por partido de cada rival: con eso se arman las campañas desde 1905, los récords y las efemérides.
- Récords históricos y goleadores de la temporada.

Cómo se protege la calidad: cada descarga se verifica (por ejemplo, que la cantidad de partidos leídos
coincida con la que informa la página). Si algo no cierra, no se usa y se mantiene la última versión buena.
En el repositorio hay una copia inicial (datos/bocastats/*.json) para que la web tenga datos desde el día uno.
"""
from __future__ import annotations

import datetime as dt
import html as html_mod
import re

from comun import DATOS, DATOS_ESPN, ahora, config, guardar_json, http_get, leer_json, log, normalizar
from historia_de_boca import _texto_con_filas

BASE = "https://bocastats.com"
CARPETA = DATOS / "bocastats"
CARPETA_PARTIDOS = CARPETA / "partidos"
RIVALES_POR_CORRIDA = 40  # para no cargar su servidor: se completa en varias corridas
DIAS_ENTRE_ACTUALIZACIONES = 7

# Nombres con tildes para mostrar (BocaStats los publica sin tildes)
NOMBRES = {
    "huracan": "Huracán", "velez": "Vélez", "newells": "Newell's", "lanus": "Lanús", "colon": "Colón",
    "union": "Unión", "penarol": "Peñarol", "atletico-tucuman": "Atlético Tucumán", "deportivo-espanol": "Deportivo Español",
    "san-martin-tuc": "San Martín de Tucumán", "san-martin-sj": "San Martín de San Juan", "porteno": "Porteño",
    "cerro-porteno": "Cerro Porteño", "bolivar": "Bolívar", "america-mex": "América de México",
    "u-catolica-chi": "Universidad Católica", "gremio": "Grêmio", "sao-caetano": "São Caetano",
    "nacional-uru": "Nacional (Uruguay)", "olimpia-paraguay": "Olimpia", "colo-colo": "Colo-Colo",
    "olimpo-b-blanca": "Olimpo", "gimnasia": "Gimnasia (LP)", "gimnasia-j": "Gimnasia (Jujuy)",
    "gimnasia-mendoza": "Gimnasia (Mendoza)", "estudiantes": "Estudiantes (LP)", "estudiantes-rio-iv": "Estudiantes (Río Cuarto)",
    "racing-cba": "Racing (Córdoba)", "atl-mineiro": "Atlético Mineiro", "atl-paranaense": "Athletico Paranaense",
    "atl-rafaela": "Atlético Rafaela", "atl-nacional": "Atlético Nacional", "dep-cali": "Deportivo Cali",
    "inter-brasil": "Internacional", "libertad-par": "Libertad", "sp-cristal": "Sporting Cristal",
    "universidad-chi": "Universidad de Chile", "liga-dep-univ-ecu": "Liga de Quito", "independiente-med": "Independiente Medellín",
    "independiente-ecu": "Independiente del Valle", "defensa": "Defensa y Justicia", "argentinos": "Argentinos Juniors",
    "ferro": "Ferro Carril Oeste", "dep-riestra": "Deportivo Riestra", "central-cordoba-santiago-del-estero": "Central Córdoba (SdE)",
    "junior-col": "Junior", "america-col": "América de Cali", "universitario-p": "Universitario", "dep-quito": "Deportivo Quito",
}

# Cómo puede llamar ESPN a cada rival → slug de BocaStats (cuando no alcanza con comparar nombres)
ALIAS = {
    "river plate": "river", "racing club": "racing", "estudiantes de la plata": "estudiantes",
    "estudiantes de rio cuarto": "estudiantes-rio-iv", "velez sarsfield": "velez", "newell's old boys": "newells",
    "newells old boys": "newells", "gimnasia la plata": "gimnasia", "gimnasia y esgrima la plata": "gimnasia",
    "gimnasia mendoza": "gimnasia-mendoza", "gimnasia y esgrima de mendoza": "gimnasia-mendoza",
    "argentinos juniors": "argentinos", "ferro carril oeste": "ferro", "defensa y justicia": "defensa",
    "atletico tucuman": "atletico-tucuman", "san martin de san juan": "san-martin-sj", "san martin de tucuman": "san-martin-tuc",
    "central cordoba": "central-cordoba-santiago-del-estero", "central cordoba (sde)": "central-cordoba-santiago-del-estero",
    "deportivo riestra": "dep-riestra", "independiente rivadavia": "independiente-rivadavia",
    "union de santa fe": "union", "sarmiento": "sarmiento",
    "nacional": "nacional-uru", "penarol": "penarol", "universidad catolica": "u-catolica-chi",
    "olimpia": "olimpia-paraguay", "cerro porteno": "cerro-porteno", "palmeiras": "palmeiras",
    "independiente del valle": "independiente-ecu", "ldu quito": "liga-dep-univ-ecu", "liga de quito": "liga-dep-univ-ecu",
    "atletico mineiro": "atl-mineiro", "athletico paranaense": "atl-paranaense", "internacional": "inter-brasil",
    "sporting cristal": "sp-cristal", "deportivo cali": "dep-cali", "atletico nacional": "atl-nacional",
}

RE_RIVAL = re.compile(r'href=["\'](?:https?://bocastats\.com)?/historial/boca-vs-([a-z0-9-]+)/?["\']')
RE_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
RE_TORNEO = re.compile(
    r"((?:Amistos|Campeonato|Torneo|Copa|Supercopa|Recopa|Superliga|Liga|Argentine|Trofeo|Intercontinental|Mundial|"
    r"Primera|Conmebol|Desempate|Liguilla|Reducido|Octogonal|Cuadrangular|Hexagonal|Tira|Petrobras|Sudamericana|Libertadores)"
    r"[^|\n]{0,70}?)(?=\s*(?:\||\bLocal\b|\bVisitante\b|\bNeutral\b|\bVictoria\b|\bEmpate\b|\bDerrota\b|$))", re.M)


def opciones() -> dict:
    o = config().get("bocastats") or {}
    return o if o.get("activado") else {}


def nombre_lindo(slug: str, nombre: str) -> str:
    # el índice a veces trae la sigla delante ("TI\n Tigre"): queda solo el nombre
    limpio = re.sub(r"^\s*[A-Z0-9]{2,4}\s*\n\s*", "", nombre or "").strip()
    return NOMBRES.get(slug, limpio or nombre)


# ------------------------------------------------------------ índice de rivales --
def rivales() -> list[dict]:
    return (leer_json(CARPETA / "rivales.json", {}) or {}).get("rivales", [])


def slug_de(nombre: str) -> str | None:
    """Encuentra el slug de BocaStats para un nombre de equipo (de ESPN o de otra fuente)."""
    n = normalizar(nombre).replace(".", "")
    if n in ALIAS:
        return ALIAS[n]
    lista = rivales()
    for r in lista:
        if normalizar(r["nombre"]) == n or normalizar(NOMBRES.get(r["slug"], "")) == n:
            return r["slug"]
    # el nombre de BocaStats más largo que sea el comienzo del otro ("racing" → "racing club")
    candidatos = [r for r in lista if n.startswith(normalizar(r["nombre"]) + " ")]
    if candidatos:
        return max(candidatos, key=lambda r: len(r["nombre"]))["slug"]
    return None


def importar_indice() -> None:
    try:
        html = http_get(f"{BASE}/historial/", timeout=40).decode("utf-8", "ignore")
    except Exception as e:
        log(f"BocaStats: no pude leer el historial ({e})")
        return
    enlaces = list(RE_RIVAL.finditer(html))
    filas, vistos = [], set()
    for i, m in enumerate(enlaces):
        slug = m.group(1)
        if slug in vistos:
            continue
        fin = enlaces[i + 1].start() if i + 1 < len(enlaces) else m.end() + 1500
        tramo = _texto_con_filas(html[m.start():fin])
        tramo = re.sub(r"^[^>]*>", "", tramo)
        nums = re.findall(r"[+-]?\d+", re.sub(r"\d+[.,]\d+\s*%", " ", tramo))
        nombre = re.split(r"\d", tramo.strip(" |\n"), maxsplit=1)[0].strip(" |\n") or slug
        if len(nums) < 4:
            continue
        pj, g, e, p = (int(x) for x in nums[:4])
        if g + e + p != pj:
            continue
        vistos.add(slug)
        filas.append({"slug": slug, "nombre": nombre[:40], "pj": pj, "g": g, "e": e, "p": p,
                      "dg": int(nums[4]) if len(nums) > 4 else None})
    total = sum(f["pj"] for f in filas)
    anterior = leer_json(CARPETA / "rivales.json", {})
    if len(filas) < 150 or total < 0.95 * (anterior.get("totales", {}).get("pj") or 5000):
        log(f"BocaStats: el índice de rivales no cerró ({len(filas)} rivales, {total} partidos). Uso la copia anterior.")
        return
    guardar_json(CARPETA / "rivales.json", {**anterior, "consultado": ahora().date().isoformat(), "rivales": filas})
    log(f"BocaStats: índice actualizado ({len(filas)} rivales, {total} partidos)")


# ---------------------------------------------------------- partido por partido --
def _torneo_normalizado(torneo: str, anio: int, mes: int) -> str:
    torneo = re.sub(r"\s+", " ", html_mod.unescape(torneo)).strip(" |,.")
    if re.search(r"(?i)argentine liga profesional", torneo):
        # desde 2025 la liga se juega en Apertura (primer semestre) y Clausura (segundo)
        torneo = (f"Torneo {'Apertura' if mes <= 6 else 'Clausura'} {anio}" if anio >= 2025 else f"Liga Profesional {anio}")
    return torneo


def _parsear_filas_con_datos(html: str) -> list[dict]:
    """Filas de la tabla «Todos los partidos»: <tr data-res data-cond data-fecha data-gf data-gc> + competencia."""
    partidos = []
    for etiqueta, cuerpo in re.findall(r'(?is)<tr\b([^>]*\bdata-fecha="\d{8}"[^>]*)>(.*?)</tr>', html):
        attrs = dict(re.findall(r'data-([a-z]+)="([^"]*)"', etiqueta))
        try:
            fecha, gb, gr = attrs["fecha"], int(attrs["gf"]), int(attrs["gc"])
        except (KeyError, ValueError):
            continue
        comp = re.search(r'(?is)<td[^>]*class="[^"]*td-comp[^"]*"[^>]*>(.*?)</td>', cuerpo)
        torneo = _torneo_normalizado(re.sub(r"<[^>]+>", " ", comp.group(1)) if comp else "", int(fecha[:4]), int(fecha[4:6]))
        condicion = {"local": "L", "visitante": "V", "neutral": "N"}.get(attrs.get("cond", "").lower(), "N")
        partidos.append({"fecha": f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}", "torneo": torneo, "condicion": condicion,
                         "goles_boca": gb, "goles_rival": gr, "resultado": "G" if gb > gr else "P" if gb < gr else "E",
                         "amistoso": torneo.lower().startswith("amistos")})
    return partidos


def parsear_rival(html: str) -> dict:
    texto = _texto_con_filas(html)
    info = {}
    if m := re.search(r"(?i)(\d+)\s+partidos oficiales", texto):
        info["oficiales"] = int(m.group(1))
    if m := re.search(r"(?i)(\d+)\s+totales", texto) or re.search(r"(?i)Mostrando\s+(\d+)\s+de\s+(\d+)", texto):
        info["totales"] = int(m.groups()[-1])
    con_datos = _parsear_filas_con_datos(html)
    if con_datos:
        vistos, unicos = set(), []
        for x in con_datos:  # la tabla de «últimos antecedentes» repite los más recientes
            k = (x["fecha"], x["goles_boca"], x["goles_rival"])
            if k not in vistos:
                vistos.add(k)
                unicos.append(x)
        con_datos = sorted(unicos, key=lambda p: p["fecha"])
        return {"partidos": con_datos, **info}
    partidos = []
    lineas = [l for l in texto.split("\n") if RE_FECHA.search(l)]
    for linea in lineas:
        f = RE_FECHA.search(linea)
        resto = linea[f.end():]
        marcador = re.search(r"(?<![\d/])(\d{1,2})\s*-\s*(\d{1,2})(?![\d/])", resto)
        if not marcador:
            continue
        a, b = int(marcador.group(1)), int(marcador.group(2))
        cond = re.search(r"\b(Local|Visitante|Neutral)\b", resto)
        condicion = {"Local": "L", "Visitante": "V", "Neutral": "N"}.get(cond.group(1) if cond else "", "N")
        res = re.search(r"\b(Victoria|Empate|Derrota)\b", resto)
        gb, gr = (b, a) if condicion == "V" else (a, b)
        if res:  # si la página dice el resultado, se usa para ordenar el marcador
            palabra = res.group(1)
            if palabra == "Victoria" and gb < gr or palabra == "Derrota" and gb > gr:
                gb, gr = gr, gb
        t = RE_TORNEO.search(resto)
        torneo = re.sub(r"\s+", " ", t.group(1)).strip(" |,.") if t else ""
        if re.search(r"(?i)argentine liga profesional", torneo):
            anio, mes = int(f.group(3)), int(f.group(2))
            # desde 2025 la liga se juega en Apertura (primer semestre) y Clausura (segundo)
            torneo = (f"Torneo {'Apertura' if mes <= 6 else 'Clausura'} {anio}" if anio >= 2025 else f"Liga Profesional {anio}")
        partidos.append({
            "fecha": f"{f.group(3)}-{f.group(2)}-{f.group(1)}", "torneo": torneo, "condicion": condicion,
            "goles_boca": gb, "goles_rival": gr, "resultado": "G" if gb > gr else "P" if gb < gr else "E",
            "amistoso": torneo.lower().startswith("amistos"),
        })
    vistos, unicos = set(), []
    for p in partidos:
        clave = (p["fecha"], p["goles_boca"], p["goles_rival"])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(p)
    unicos.sort(key=lambda p: p["fecha"])
    return {"partidos": unicos, **info}


def importar_rivales() -> None:
    lista = rivales()
    if not lista:
        return
    CARPETA_PARTIDOS.mkdir(parents=True, exist_ok=True)
    limite = (ahora() - dt.timedelta(days=DIAS_ENTRE_ACTUALIZACIONES)).isoformat()
    pendientes = sorted(lista, key=lambda r: leer_json(CARPETA_PARTIDOS / f"{r['slug']}.json", {}).get("importado", ""))
    hechos = 0
    for r in pendientes:
        archivo = CARPETA_PARTIDOS / f"{r['slug']}.json"
        if leer_json(archivo, {}).get("importado", "") > limite:
            continue
        if hechos >= RIVALES_POR_CORRIDA:
            break
        hechos += 1
        try:
            html = http_get(f"{BASE}/historial/boca-vs-{r['slug']}/", timeout=40).decode("utf-8", "ignore")
        except Exception as e:
            log(f"BocaStats: no pude leer el historial con {r['nombre']} ({e})")
            continue
        datos = parsear_rival(html)
        ps = datos["partidos"]
        esperado = datos.get("totales") or r["pj"]
        if len(ps) != esperado:
            log(f"BocaStats: {r['nombre']}: leí {len(ps)} partidos y la página dice {esperado}. No lo uso.")
            guardar_json(archivo, {**leer_json(archivo, {}), "intento": ahora().isoformat(timespec="seconds")})
            continue
        guardar_json(archivo, {"slug": r["slug"], "nombre": nombre_lindo(r["slug"], r["nombre"]),
                               "importado": ahora().isoformat(timespec="seconds"),
                               "oficiales_segun_pagina": datos.get("oficiales"), "partidos": ps})
    if hechos:
        listos = sum(1 for r in lista if (CARPETA_PARTIDOS / f"{r['slug']}.json").exists()
                     and leer_json(CARPETA_PARTIDOS / f"{r['slug']}.json", {}).get("partidos"))
        log(f"BocaStats: historial partido a partido de {listos} de {len(lista)} rivales")


# Partidos que BocaStats no marca como amistosos pero que no cuentan como oficiales:
# los anulados ("Campeonato (Anulado) 1919") y las giras ("Gira por Europa 1925").
RE_NO_COMPUTABLE = re.compile(r"(?i)\b(anulad[oa]|gira)\b")


def _computable(p: dict) -> dict:
    if not p.get("amistoso") and RE_NO_COMPUTABLE.search(p.get("torneo") or ""):
        return {**p, "amistoso": True, "no_computable": True}
    return p


def partidos_de(slug: str) -> list[dict]:
    return [_computable(p) for p in (leer_json(CARPETA_PARTIDOS / f"{slug}.json", {}) or {}).get("partidos", [])]


def todos_los_partidos() -> list[dict]:
    """Todos los partidos importados, con el rival incluido. Los anulados y las giras quedan como no oficiales."""
    salida = []
    for f in sorted(CARPETA_PARTIDOS.glob("*.json")):
        d = leer_json(f, {})
        for p in d.get("partidos", []):
            salida.append({**_computable(p), "rival_slug": d.get("slug", f.stem),
                           "rival": nombre_lindo(d.get("slug", f.stem), d.get("nombre", f.stem))})
    salida.sort(key=lambda p: p["fecha"])
    return salida


def mejores_rachas(partidos: list[dict]) -> dict[str, list[list[dict]]]:
    """Las rachas más largas de victorias y de partidos sin perder, en orden de fecha. Se cuentan solo los oficiales;
    un partido anulado o de gira no suma, pero si no fue triunfo (o fue derrota) corta la racha igual.
    Devuelve todas las que empatan en el primer puesto."""
    partidos = [p for p in partidos if not p["amistoso"] or p.get("no_computable")]
    res = {}
    for clave, sirve in (("victorias", lambda p: p["resultado"] == "G"), ("invicto", lambda p: p["resultado"] != "P")):
        rachas, actual = [], []
        for p in partidos + [None]:
            if p is not None and p.get("no_computable") and sirve(p):
                continue
            if p is not None and sirve(p) and not p.get("no_computable"):
                actual.append(p)
            else:
                if actual:
                    rachas.append(actual)
                actual = []
        largo = max((len(r) for r in rachas), default=0)
        res[clave] = [r for r in rachas if len(r) == largo]
    return res


# ---------------------------------------------------------- récords y goleadores --
def importar_records() -> None:
    try:
        texto = _texto_con_filas(http_get(f"{BASE}/records/", timeout=40).decode("utf-8", "ignore"))
    except Exception as e:
        log(f"BocaStats: no pude leer los récords ({e})")
        return
    def numero(etiqueta):
        for patron in (rf"(?i){etiqueta}\s*[:|]?\s*(\d[\d.]*)", rf"(?i)(\d[\d.]*)\s*[|]?\s*{etiqueta}"):
            m = re.search(patron, texto)
            if m and m.group(1).replace(".", "").isdigit():
                return int(m.group(1).replace(".", ""))
        return None
    balance = {"pj": numero("Partidos"), "g": numero("Victorias"), "e": numero("Empates"), "p": numero("Derrotas"),
               "gf": numero("Goles a favor"), "gc": numero("Goles en contra")}
    if None in balance.values() or balance["g"] + balance["e"] + balance["p"] != balance["pj"]:
        log("BocaStats: no pude verificar el balance de récords. Uso la copia anterior.")
        return
    anterior = leer_json(CARPETA / "records.json", {})
    guardar_json(CARPETA / "records.json", {**anterior, "consultado": ahora().date().isoformat(), "balance": balance})
    log(f"BocaStats: récords actualizados ({balance['pj']} partidos)")


def parsear_goleadores(html: str) -> list[dict]:
    """Tabla de artilleros de bocastats.com/goleadores/ (filas <a class="gol-row">: nombre, "Puesto · 10 Liga (5 Clausura)
    · 1 Libertadores", goles, asistencias y partidos de Liga)."""
    filas = []
    for bloque in re.findall(r'(?s)<a[^>]*class="gol-row[^"]*"[^>]*>(.*?)</a>', html):
        nombre = re.search(r'(?s)class="gol-player-name"[^>]*>(.*?)<', bloque)
        pos = re.search(r'(?s)class="gol-player-pos"[^>]*>(.*?)<', bloque)
        goles = re.search(r'class="gol-stat gol-stat-goles"[^>]*>\s*(\d+)', bloque)
        if not (nombre and goles):
            continue
        partes = [x.strip() for x in html_mod.unescape(pos.group(1) if pos else "").split("·")]
        desglose = {}
        for x in partes[1:]:
            m = re.match(r"(\d+)\s+([^(]+?)\s*(\(.*\))?$", x)
            if m:
                desglose[m.group(2).strip()] = int(m.group(1))
        fila = {"nombre": html_mod.unescape(nombre.group(1)).strip(), "posicion": partes[0] if partes else "",
                "goles": int(goles.group(1)), "desglose": desglose}
        ast = re.search(r'gol-col-ast"[^>]*>\s*(\d+)', bloque)
        pj = re.search(r'gol-col-pj"[^>]*>\s*(\d+)', bloque)
        if ast:
            fila["asistencias_liga"] = int(ast.group(1))
        if pj:
            fila["pj_liga"] = int(pj.group(1))
        filas.append(fila)
    return filas


def importar_goleadores() -> bool:
    """Devuelve True si pudo actualizar la tabla (si no, queda la copia anterior y se reintenta en la próxima corrida)."""
    try:
        html = http_get(f"{BASE}/goleadores/", timeout=40).decode("utf-8", "ignore")
    except Exception as e:
        log(f"BocaStats: no pude leer los goleadores ({e})")
        return False
    filas = parsear_goleadores(html)
    if len(filas) < 5:  # por si cambian el diseño otra vez: el formato viejo, en texto
        texto = _texto_con_filas(html)
        filas = [{"nombre": m.group(1).strip(), "posicion": m.group(2), "goles": int(m.group(3))} for m in re.finditer(
            r"([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñü'´\. ]{3,40}?)\s*\|?\s*(Arquero|Defensor|Mediocampista|Delantero)\s*\|?\s*(\d{1,3})\b", texto)]
    goles = [f["goles"] for f in filas]
    if len(filas) < 5 or goles != sorted(goles, reverse=True) or any(f.get("desglose") and sum(f["desglose"].values()) != f["goles"] for f in filas):
        log("BocaStats: no pude verificar la tabla de goleadores. Uso la copia anterior.")
        return False
    anterior = {j["nombre"]: j for j in leer_json(CARPETA / "goleadores.json", {}).get("jugadores", [])}
    for f in filas:  # si el formato viejo no trae el desglose, conserva el anterior cuando los goles no cambiaron
        viejo = anterior.get(f["nombre"])
        if viejo and viejo.get("goles") == f["goles"] and not f.get("desglose"):
            f.update({k: viejo[k] for k in ("desglose", "asistencias_liga", "pj_liga") if k in viejo})
    m = re.search(r"(?i)Actualizado el (\d{1,2}) de (\w+) de (\d{4})", html)
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    extra = {}
    if m and m.group(2).lower() in meses:
        extra["actualizado_fuente"] = f"{m.group(3)}-{meses.index(m.group(2).lower()) + 1:02d}-{int(m.group(1)):02d}"
    guardar_json(CARPETA / "goleadores.json", {**leer_json(CARPETA / "goleadores.json", {}), **extra,
                                               "consultado": ahora().date().isoformat(), "jugadores": filas})
    log(f"BocaStats: goleadores actualizados ({len(filas)} jugadores, {sum(goles)} goles)")
    return True


# ------------------------------------------- goles recientes que BocaStats no cargó --
# BocaStats a veces tarda días en sumar los goles de un partido. Para que la tabla de goleadores no quede atrasada,
# se leen de ESPN los goles de Boca de los partidos de los últimos días y se suman mientras BocaStats no los cargue.
# Para saber si ya los cargó, cuando se ve el partido por primera vez se anota cuántos goles le contaba BocaStats
# a cada goleador en esa competencia ("antes"): en cuanto ese número sube, el gol de ESPN deja de sumarse.
ARCHIVO_RECIENTES = CARPETA / "goles_recientes.json"
DIAS_RECIENTES = 12
COMP_BS = {"arg.1": "Liga", "conmebol.libertadores": "Libertadores", "conmebol.sudamericana": "Sudamericana",
           "arg.copa": "Copa Argentina"}


def _buscar_goleador(tabla: list[dict], nombre: str) -> dict | None:
    n = normalizar(nombre)
    for j in tabla:
        if normalizar(j["nombre"]) == n:
            return j
    ap = n.split()[-1] if n else ""
    candidatos = [j for j in tabla if normalizar(j["nombre"]).split()[-1:] == [ap]]
    return candidatos[0] if len(candidatos) == 1 else None


def actualizar_goles_recientes() -> None:
    from datos_futbol import resumen_partido
    rec = leer_json(ARCHIVO_RECIENTES, {}) or {}
    tabla = leer_json(CARPETA / "goleadores.json", {}).get("jugadores", [])
    desde = (ahora() - dt.timedelta(days=DIAS_RECIENTES)).date().isoformat()
    for p in leer_json(DATOS_ESPN / "partidos.json", []) or []:
        comp = COMP_BS.get(p.get("competencia_slug"))
        if not comp or p.get("estado") != "finalizado" or (p.get("fecha") or "")[:10] < desde or p["id"] in rec:
            continue
        try:
            hechos = resumen_partido(p["id"], p["competencia_slug"])["hechos"]
        except Exception as e:
            log(f"BocaStats: no pude leer los goles de {p['id']} en ESPN ({e})")
            continue
        goles = {}
        for h in hechos:
            if h["tipo"] == "gol" and "boca" in normalizar(h["equipo"]) and h["jugador"] and "own goal" not in h["detalle"].lower():
                goles[h["jugador"]] = goles.get(h["jugador"], 0) + 1
        base = {}
        for nombre in goles:
            j = _buscar_goleador(tabla, nombre)
            base[nombre] = {"bs": j["nombre"] if j else None, "antes": ((j or {}).get("desglose") or {}).get(comp, 0)}
        rec[p["id"]] = {"fecha": p["fecha"][:10], "competencia": comp, "rival": (p.get("rival") or {}).get("nombre", ""),
                        "goles": goles, "base": base}
        log(f"BocaStats: goles de ESPN vs {rec[p['id']]['rival']}: {goles}")
    rec = {k: v for k, v in rec.items() if v["fecha"] >= desde}
    guardar_json(ARCHIVO_RECIENTES, rec)


def goleadores() -> dict:
    """La tabla de BocaStats más los goles recientes que todavía no cargó (ver arriba)."""
    gol = leer_json(CARPETA / "goleadores.json", {}) or {}
    tabla = [dict(j, desglose=dict(j.get("desglose") or {})) for j in gol.get("jugadores", [])]
    originales = {j["nombre"]: dict(j.get("desglose") or {}) for j in gol.get("jugadores", [])}
    sumados = 0
    for m in sorted((leer_json(ARCHIVO_RECIENTES, {}) or {}).values(), key=lambda x: x["fecha"]):
        for nombre, g in m["goles"].items():
            b = m["base"].get(nombre, {})
            j = next((x for x in tabla if x["nombre"] == b.get("bs")), None) if b.get("bs") else _buscar_goleador(tabla, nombre)
            if j and (originales.get(j["nombre"], {}).get(m["competencia"], 0) != b.get("antes", 0)):
                continue  # BocaStats ya lo cargó
            if not j:
                j = {"nombre": nombre, "posicion": "", "goles": 0, "desglose": {}}
                tabla.append(j)
            j["goles"] += g
            j["desglose"][m["competencia"]] = j["desglose"].get(m["competencia"], 0) + g
            j["recientes"] = j.get("recientes", 0) + g
            sumados += g
    tabla.sort(key=lambda j: -j["goles"])
    return {**gol, "jugadores": tabla, "goles_recientes": sumados}


def ejecutar() -> None:
    if not opciones():
        return
    estado = leer_json(CARPETA / "estado.json", {})
    hoy = ahora().date().isoformat()
    semana = (ahora() - dt.timedelta(days=DIAS_ENTRE_ACTUALIZACIONES)).date().isoformat()
    if estado.get("indice", "") <= semana:
        importar_indice()
        importar_records()
        estado["indice"] = hoy
    # Los goleadores cambian seguido: se revisan cada 3 horas, y si falla se reintenta en la corrida siguiente
    hace_3h = (ahora() - dt.timedelta(hours=3)).isoformat(timespec="minutes")
    if estado.get("goleadores", "") < hace_3h and importar_goleadores():
        estado["goleadores"] = ahora().isoformat(timespec="minutes")
    guardar_json(CARPETA / "estado.json", estado)
    try:
        actualizar_goles_recientes()
    except Exception as e:
        log(f"BocaStats: no pude revisar los goles recientes ({e})")
    importar_rivales()


if __name__ == "__main__":
    ejecutar()
