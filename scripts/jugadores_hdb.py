"""Base de jugadores de Boca, importada de Historia de Boca (con permiso).

datos/hdb/jugadores.json se baja desde el navegador del dueño (Historia de Boca bloquea a GitHub), igual que
las efemérides. Por cada jugador trae: partidos oficiales, goles, titularidades, minutos, debut y despedida,
nacimiento, lugar de nacimiento, biografía, partidos y goles por torneo, dorsales y con quién jugó
(compañeros en al menos un partido oficial).

De acá salen "¿Quién soy?", las dificultades de la Grilla y "¿Quién jugó con quién?".

Los partidos que Boca juega después de la descarga se suman solos con los datos de ESPN (formación, cambios y
goles): datos/hdb/partidos_nuevos.json. Cuando se vuelva a bajar la base, esos partidos dejan de sumarse.
"""
from __future__ import annotations

import hashlib
import re

from comun import DATOS, ahora, guardar_json, leer_json, log, normalizar

ARCHIVO = DATOS / "hdb" / "jugadores.json"
MIN_PJ_QUIEN_SOY = 50  # "50 partidos oficiales o más"

PUESTOS = ["arquero", "marcador central", "marcador de punta derecho", "marcador de punta izquierdo",
           "lateral derecho", "lateral izquierdo", "defensor", "zaguero", "back", "medio derecho", "medio izquierdo",
           "centrohalf", "centro half", "volante central", "volante", "mediocampista", "enganche", "insider",
           "puntero derecho", "puntero izquierdo", "puntero", "wing", "centrodelantero", "delantero", "polifuncional"]
NUMEROS = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
           "nueve": 9, "diez": 10}
INTERNACIONALES = ("libertadores", "intercontinental", "sudamericana", "recopa", "supercopa", "mundial de clubes",
                   "copa de oro", "master")


def _cargar() -> dict:
    return (leer_json(ARCHIVO, {}) or {}).get("jugadores", {})


def jugadores() -> dict[str, dict]:
    """Los jugadores de Historia de Boca, con los partidos jugados después de la descarga ya sumados."""
    todos = _cargar()
    try:
        sumar_partidos_nuevos(todos)
    except Exception as e:  # si algo sale mal, quedan las cifras de la descarga
        log(f"Historia de Boca: no pude sumar los partidos nuevos ({e})")
    return todos


def credito() -> str:
    return "Historia de Boca"


def limpiar_bio(bio: str) -> str:
    bio = re.split(r"\(adsbygoogle|window\.adsbygoogle", bio or "")[0]
    return re.sub(r"\s+", " ", bio).strip()


def puesto(j: dict) -> str:
    """El puesto: la primera frase de la biografía de Historia de Boca ("Enganche.", "Marcador de Punta.")."""
    bio = limpiar_bio(j.get("bio", ""))
    primera = bio.split(".")[0].strip()
    if primera and len(primera) <= 45 and not re.match(r"(?i)(gan|jug|lleg|surg|naci|fue|debut|capit)", primera):
        return primera.lower()
    bio_n = normalizar(bio)[:160]
    for p in PUESTOS:
        if re.search(rf"\b{p}\b", bio_n):
            return p
    return ""


def titulos(j: dict) -> tuple[int, bool]:
    """Cantidad de títulos que dice la biografía y si alguno fue internacional."""
    bio = limpiar_bio(j.get("bio", ""))
    m = re.search(r"(?i)gan[óo] (\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez) t[íi]tulos?", bio)
    n = 0
    if m:
        x = m.group(1).lower()
        n = int(x) if x.isdigit() else NUMEROS.get(x, 0)
    detalle = normalizar(bio[m.end():m.end() + 260]) if m else ""
    return n, any(t in detalle for t in INTERNACIONALES)


def anio(fecha: str) -> int | None:
    m = re.search(r"(\d{4})$", fecha or "")
    return int(m.group(1)) if m else None


def es_argentino(j: dict) -> bool | None:
    lugar = normalizar(j.get("lugar") or "")
    if not lugar:
        return None
    paises = ("uruguay", "paraguay", "chile", "peru", "colombia", "brasil", "bolivia", "ecuador", "venezuela",
              "espana", "italia", "mexico", "japon", "hungria", "francia", "alemania", "estados unidos")
    return not any(p in lugar for p in paises)


def nombre_corto(nombre: str) -> str:
    """'Juan Román Riquelme' → 'Riquelme' (apellido final), para mostrar compañeros."""
    partes = nombre.split()
    return partes[-1] if partes else nombre


# ------------------------------------------------------------- ¿Quién soy? --
def _decada(a: int | None) -> str:
    if not a:
        return ""
    if a >= 2000:
        return f"los años {a // 10 * 10}"
    return f"los años {str(a)[2]}0" if a >= 1910 else "los primeros años del club"


def _companero_famoso(j: dict, todos: dict) -> str:
    comp = [todos[c] for c in j.get("comp", []) if c in todos and c != j["id"]]
    comp.sort(key=lambda x: -(x.get("pj") or 0))
    return comp[0]["n"] if comp else ""


def pistas(j: dict, todos: dict) -> list[str]:
    """Cinco pistas, de la más difícil a la más fácil."""
    p = []
    pu, d = puesto(j), anio(j.get("debut"))
    if pu and d:
        p.append(f"Fui {pu} y debuté en Boca en {_decada(d)}.")
    elif d:
        p.append(f"Debuté en Boca en {_decada(d)}.")
    lugar = j.get("lugar") or ""
    if lugar:
        if es_argentino(j) is False:
            p.append(f"No nací en la Argentina: soy de {lugar}.")
        elif normalizar(lugar) == "capital federal":
            p.append("Nací en la Capital Federal.")
        else:
            p.append(f"Nací en la provincia de {lugar}.")
    n, inter = titulos(j)
    if n:
        p.append(f"Gané {n} {'título' if n == 1 else 'títulos'} con Boca" + (", alguno internacional." if inter else "."))
    else:
        p.append("No gané ningún título con Boca.")
    goles = j.get("gol") or 0
    p.append(f"Jugué {j['pj']} partidos oficiales en Boca y convertí {goles} {'gol' if goles == 1 else 'goles'}.")
    dor = [x for x in j.get("dor", []) if x[1] >= max(10, (j.get("pj") or 0) // 3)]
    socio = _companero_famoso(j, todos)
    extras = []
    if dor:
        extras.append(f"usé la camiseta {dor[0][0]}")
    if socio:
        extras.append(f"compartí cancha con {socio}")
    if extras:
        p.append("Entre otras cosas, " + " y ".join(extras) + ".")
    desp = anio(j.get("desp"))
    if d and desp and len(p) < 5:
        p.append(f"Mi etapa en Boca fue de {d} a {desp}.")
    return p[:5]


def datos_quien_soy() -> dict | None:
    todos = jugadores()
    if not todos:
        return None
    for i, j in todos.items():
        j["id"] = i
    candidatos = [j for j in todos.values() if (j.get("pj") or 0) >= MIN_PJ_QUIEN_SOY and j.get("n")]
    if len(candidatos) < 30:
        return None
    salida = []
    for j in sorted(candidatos, key=lambda x: -x["pj"]):
        p = pistas(j, todos)
        if len(p) < 4:
            continue
        dif = 1 if j["pj"] >= 250 else 2 if j["pj"] >= 130 else 3
        bio = limpiar_bio(j.get("bio", ""))
        salida.append({"n": j["n"], "pistas": p, "dif": dif, "pj": j["pj"], "goles": j.get("gol") or 0,
                       "etapa": f"{anio(j.get('debut')) or '?'}-{anio(j.get('desp')) or '?'}",
                       "bio": (bio[:260].rsplit(" ", 1)[0] + "…") if len(bio) > 260 else bio})
    return {"jugadores": salida, "fuente": credito(), "minimo": MIN_PJ_QUIEN_SOY}


# -------------------------------------------------------- para otros juegos --
def _tokens(texto: str) -> list[str]:
    return re.sub(r"[^a-z ]", " ", normalizar(texto or "")).split()


def _indice_nombres() -> list[tuple[list[str], list[str], int]]:
    """(apellido, nombres, partidos) de cada jugador. "an" viene como "Apellido, Nombres"."""
    salida = []
    for j in jugadores().values():
        an = j.get("an") or j.get("n") or ""
        ap, _, no = an.partition(",") if "," in an else (an, "", "")
        if _tokens(ap):
            salida.append((_tokens(ap), _tokens(no), j.get("pj") or 0))
    return salida


def partidos_por_nombre(nombres: list[str]) -> dict[str, int]:
    """Cruza nombres de otra fuente (como Wikidata: "Juan Román Riquelme") con la base y devuelve los partidos
    oficiales de cada uno. Hace falta el apellido completo y el primer nombre; si hay dos candidatos igual de
    buenos, el jugador queda afuera (mejor sin dato que con el dato de otro)."""
    indice = _indice_nombres()
    salida = {}
    for nombre in nombres:
        w = _tokens(nombre)
        candidatos = []
        for ap, no, pj in indice:
            n = len(ap)
            pos = next((i for i in range(len(w) - n + 1) if w[i:i + n] == ap), None)
            if pos is None:
                continue
            resto = w[:pos] + w[pos + n:]
            # Puntaje: cómo calza el nombre, cuántas palabras del apellido coinciden y si los nombres son idénticos
            # ("Claudio Morel Rodríguez" es Morel Rodríguez y no Rodríguez; "Christian Giménez" no es "Christian Eduardo").
            if resto and no and resto[0] == no[0]:
                candidatos.append(((3 if pos + n == len(w) else 2, n, resto == no), pj))
            elif resto and no and set(resto) <= set(no):
                candidatos.append(((1, n, False), pj))
        if candidatos:
            mejor = max(c[0] for c in candidatos)
            top = [c for c in candidatos if c[0] == mejor]
            if len(top) == 1:
                salida[nombre] = top[0][1]
    return salida


def semilla(texto: str) -> int:
    return int(hashlib.sha1(texto.encode()).hexdigest()[:8], 16)


# ---------------------------------------------------- ¿Jugaron juntos? --
# "Jugaron juntos" = compartieron al menos un partido oficial en Boca (la lista de compañeros de Historia de Boca).
MIN_PJ_CONEXION = 50
PREGUNTAS_CONEXION = 10


def _anio_torneo(nombre: str) -> int | None:
    m = re.findall(r"(?:19|20)\d\d", nombre or "")
    return int(m[0]) if m else None


def _anios_jugados(j: dict) -> set[int]:
    """Años en los que jugó partidos oficiales (según los torneos), así se ven bien las segundas etapas."""
    return {a for a in (_anio_torneo(t[0]) for t in j.get("tor", []) if t[1]) if a}


def _rango(j: dict) -> tuple[int, int] | None:
    a = _anios_jugados(j)
    return (min(a), max(a)) if a else None


def _etapas(anios: set[int]) -> str:
    """{2009, 2010, 2011, 2024} → "de 2009 a 2011 y en 2024"."""
    tramos, ant = [], None
    for a in sorted(anios):
        if ant is not None and a - ant <= 1:
            tramos[-1][1] = a
        else:
            tramos.append([a, a])
        ant = a
    partes = [f"en {x}" if x == y else f"de {x} a {y}" for x, y in tramos]
    return _lista(partes)


def _lista(cosas: list[str]) -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


def explicar_conexion(a: dict, b: dict, juntos: bool) -> str:
    tor_b = {t[0] for t in b.get("tor", []) if t[1]}
    comunes = [t[0] for t in a.get("tor", []) if t[1] and t[0] in tor_b]
    if juntos:
        if not comunes:
            return "Sí. Compartieron cancha en al menos un partido oficial de Boca."
        if len(comunes) <= 3:
            return f"Sí. Jugaron juntos en {_lista(comunes)}."
        anios = sorted({x for x in (_anio_torneo(t) for t in comunes) if x})
        cuando = f"en {anios[0]}" if anios and anios[0] == anios[-1] else f"entre {anios[0]} y {anios[-1]}" if anios else ""
        return f"Sí. Jugaron juntos en Boca {cuando}: coincidieron en {len(comunes)} torneos.".replace("  ", " ")
    aa, ab = _anios_jugados(a), _anios_jugados(b)
    if not (aa & ab):
        return f"No. {a['n']} jugó en Boca {_etapas(aa)} y {b['n']}, {_etapas(ab)}: no coincidieron."
    if comunes:
        return (f"No. Los dos jugaron {_lista(comunes[:2])}" + (" (y otros torneos)" if len(comunes) > 2 else "") +
                ", pero nunca en el mismo partido oficial.")
    return (f"No. Los dos jugaron partidos oficiales en {_lista([str(x) for x in sorted(aa & ab)])}, "
            f"pero nunca en el mismo partido ({a['n']}: {_etapas(aa)}; {b['n']}: {_etapas(ab)}).")


def _pregunta_conexion(rng, cand: list[dict], todos: dict, dif: int, usados: set) -> dict | None:
    """dif 1: muy conocidos y épocas lejanas; 2: conocidos; 3: menos partidos y los "no" son de la misma época."""
    minimo = {1: 200, 2: 110, 3: MIN_PJ_CONEXION}[dif]
    pool = [j for j in cand if j["pj"] >= minimo and j["id"] not in usados]
    if len(pool) < 10:
        return None
    juntos = rng.random() < 0.5
    for _ in range(400):
        a = rng.choice(pool)
        comp = set(a.get("comp", []))
        ra = _rango(a)
        if juntos:
            opciones = [todos[c] for c in comp if c in todos and c in {p["id"] for p in pool}]
            if dif == 3:  # los difíciles: compartieron pocos torneos
                opciones = [b for b in opciones if len({t[0] for t in a.get("tor", [])} & {t[0] for t in b.get("tor", [])}) <= 3] or opciones
            if not opciones:
                continue
            b = rng.choice(opciones)
        else:
            opciones = []
            for b in pool:
                if b["id"] == a["id"] or b["id"] in comp:
                    continue
                rb = _rango(b)
                if not (ra and rb):
                    continue
                separados = not (_anios_jugados(a) & _anios_jugados(b))
                distancia = min(abs(x - y) for x in _anios_jugados(a) for y in _anios_jugados(b))
                if dif == 1 and separados and distancia >= 3:
                    opciones.append(b)
                elif dif == 2 and (not separados or distancia <= 4):
                    opciones.append(b)
                elif dif == 3 and not separados:
                    opciones.append(b)
            if not opciones:
                continue
            b = rng.choice(opciones)
        if b["id"] in usados or b["id"] == a["id"]:
            continue
        usados.update({a["id"], b["id"]})
        par = [a, b] if rng.random() < 0.5 else [b, a]
        return {"a": par[0]["n"], "b": par[1]["n"], "si": juntos, "dif": dif,
                "exp": explicar_conexion(par[0], par[1], juntos)}
    return None


def datos_conexion(hoy, dias: int = 10, practica: int = 150) -> dict | None:
    """Preguntas de "¿Jugaron juntos?" para hoy y los próximos días (las mismas para todos) y un banco de práctica."""
    import datetime as dt
    import random
    todos = jugadores()
    for i, j in todos.items():
        j["id"] = i
    cand = [j for j in todos.values() if (j.get("pj") or 0) >= MIN_PJ_CONEXION and j.get("n") and j.get("comp") and _rango(j)]
    if len(cand) < 60:
        return None
    salida = {"dias": {}, "practica": [], "fuente": credito()}
    for k in range(dias):
        fecha = (hoy + dt.timedelta(days=k)).isoformat()
        rng = random.Random(semilla("conexion" + fecha))
        usados, lista = set(), []
        for n in range(PREGUNTAS_CONEXION):
            dif = 1 if n < 3 else 2 if n < 7 else 3
            q = _pregunta_conexion(rng, cand, todos, dif, usados)
            if q:
                lista.append(q)
        salida["dias"][fecha] = lista
    rng = random.Random(semilla("conexion-practica" + hoy.isoformat()))
    usados = set()
    for n in range(practica):
        if len(usados) > len(cand) - 20:
            usados = set()
        q = _pregunta_conexion(rng, cand, todos, (n % 3) + 1, usados)
        if q:
            salida["practica"].append(q)
    return salida


# ------------------------------------------------------------ ¿Quién falta? --
# Los que más partidos jugaron en un torneo que Boca ganó, menos uno: hay que adivinar cuál falta.
# Se usan solo los torneos donde ese grupo queda bien cortado (el último de la lista jugó más que el siguiente),
# así la respuesta es una sola.
RONDAS_FALTA = 5
DIF_FALTA = [1, 1, 2, 2, 3]  # la dificultad de cada ronda del día


def _nombre_hdb_titulo(titulo: str, torneos: set) -> str | None:
    """El nombre del título en palmares.json → el nombre del torneo en Historia de Boca."""
    t = titulo
    m = re.search(r"(\d{4})/(\d{2})$", t)
    largo = re.sub(r"(\d{4})/(\d{2})$", lambda x: f"{x.group(1)}/{x.group(1)[:2]}{x.group(2)}", t)
    opciones = [t, largo,
                largo.replace("Campeonato de Primera División", "Campeonato"),
                largo.replace("Superliga Argentina", "Superliga"),
                t.replace("Copa de la Liga Profesional", "Copa Liga Profesional"),
                t.replace("Liga Profesional", "Campeonato"),
                re.sub(r"(Supercopa|Recopa) Sudamericana", r"\1", t),
                t.replace("Copa Argentina 1969", "Copa de Argentina 1969"),
                t.replace("Copa de Oro Nicolás Leoz", "Copa de Oro")]
    if m:
        opciones.append(re.sub(r"(\d{4})/\d{2}$", r"\1", t.replace("Copa Diego Armando Maradona", "Copa Diego Maradona")))
    return next((o for o in opciones if o in torneos), None)


def _corte(filas: list) -> int | None:
    """Cuántos van en la lista: 11 si se puede; si no, 10 o 12. Tiene que haber un corte limpio."""
    for n in (11, 10, 12):
        if len(filas) > n and filas[n - 1][0] > filas[n][0] and filas[n - 1][0] >= 2:
            return n
    return None


def _dif_titulo(a: int) -> int:
    return 1 if a >= 1998 else 2 if a >= 1962 else 3


def torneos_falta() -> list[dict]:
    todos = jugadores()
    palm = leer_json(DATOS / "manual" / "palmares.json", {}) or {}
    titulos_boca = [t for c in palm.get("categorias", []) for t in c.get("titulos", [])]
    consultado = (leer_json(ARCHIVO, {}) or {}).get("consultado", "")
    anio_datos = int(consultado[:4]) if consultado[:4].isdigit() else 9999
    por_torneo: dict[str, list] = {}
    for i, j in todos.items():
        for t in j.get("tor", []):
            if t[1]:
                por_torneo.setdefault(t[0], []).append((t[1], t[2] or 0, i))
    salida = []
    for titulo in titulos_boca:
        nombre = _nombre_hdb_titulo(titulo, set(por_torneo))
        a = _anio_torneo(titulo)
        if not nombre or not a or a >= anio_datos:  # el del año en curso puede estar incompleto
            continue
        filas = sorted(por_torneo[nombre], key=lambda x: (-x[0], -x[1], todos[x[2]]["n"]))
        n = _corte(filas)
        if not n or filas[0][0] < 5:
            continue
        lista = []
        for pj, gol, i in filas[:n]:
            j = todos[i]
            r = _rango(j)
            lista.append({"id": i, "n": j["n"], "pj": pj, "gol": gol, "pjt": j.get("pj") or 0, "golt": j.get("gol") or 0,
                          "puesto": puesto(j), "etapa": (f"{r[0]}" if r and r[0] == r[1] else f"{r[0]} a {r[1]}") if r else "",
                          "lugar": j.get("lugar") or ""})
        salida.append({"titulo": titulo, "torneo": nombre, "anio": a, "dif": _dif_titulo(a), "jugadores": lista})
    return salida


def _escondible(x: dict, dif: int) -> bool:
    """A quién se puede esconder: alguien con una carrera en Boca que se pueda recordar."""
    return x["pjt"] >= {1: 80, 2: 50, 3: 20}[dif]


def datos_falta(hoy, dias: int = 10) -> dict | None:
    """Rondas de hoy y de los próximos días (las mismas para todos) y los torneos para practicar.
    Cada ronda es [índice del torneo, índice del jugador que falta]."""
    import datetime as dt
    import random
    torneos = torneos_falta()
    pools = {d: [k for k, t in enumerate(torneos) if t["dif"] == d and any(_escondible(x, d) for x in t["jugadores"])]
             for d in (1, 2, 3)}
    if any(len(p) < 3 for p in pools.values()):
        return None
    for d, p in pools.items():  # orden fijo: así no se repite un torneo hasta pasar por todos los de su época
        random.Random(semilla(f"falta-orden-{d}")).shuffle(p)
    base = dt.date(2026, 11, 24)
    salida = {"dias": {}, "torneos": torneos, "fuente": credito()}
    for k in range(dias):
        fecha = hoy + dt.timedelta(days=k)
        n = (fecha - base).days
        rng = random.Random(semilla("falta" + fecha.isoformat()))
        rondas, cuenta = [], {1: 0, 2: 0, 3: 0}
        for d in DIF_FALTA:
            por_dia = DIF_FALTA.count(d)
            p = pools[d]
            t = p[(n * por_dia + cuenta[d]) % len(p)]
            cuenta[d] += 1
            cand = [i for i, x in enumerate(torneos[t]["jugadores"]) if _escondible(x, d)]
            rondas.append([t, rng.choice(cand)])
        salida["dias"][fecha.isoformat()] = rondas
    return salida



# ------------------------------------------- partidos posteriores a la descarga --
ARCHIVO_NUEVOS = DATOS / "hdb" / "partidos_nuevos.json"
MAX_PARTIDOS_POR_CORRIDA = 8


def _oficial(slug: str) -> bool:
    slug = slug or ""
    return "friendly" not in slug and (slug.startswith(("arg.", "conmebol.")) or slug == "fifa.cwc")


def _torneo_hdb(slug: str, fecha: str, temporada: str, liga: str) -> str:
    """El nombre del torneo como lo escribe Historia de Boca ("Torneo Clausura 2026", "Copa Sudamericana 2026")."""
    y = fecha[:4]
    if slug == "arg.1":
        if "apertura" in temporada.lower():
            return f"Torneo Apertura {y}"
        if "clausura" in temporada.lower():
            return f"Torneo Clausura {y}"
        return f"Torneo {'Apertura' if int(fecha[5:7]) < 7 else 'Clausura'} {y}"
    fijos = {"arg.copa": "Copa Argentina", "conmebol.libertadores": "Copa Libertadores",
             "conmebol.sudamericana": "Copa Sudamericana", "conmebol.recopa": "Recopa"}
    return f"{fijos.get(slug) or liga or slug} {y}"


def _minuto(texto: str) -> int:
    """"37'" → 37; "90'+3'" → 90."""
    m = re.match(r"\s*(\d+)", texto or "")
    return int(m.group(1)) if m else 0


def leer_partido_espn(resumen: dict, slug: str, fecha: str) -> dict | None:
    """De un resumen de ESPN: resultado, torneo y, por cada jugador de Boca que entró, si fue titular, minutos y goles."""
    comp = ((resumen.get("header") or {}).get("competitions") or [{}])[0]
    estado = ((comp.get("status") or {}).get("type") or {})
    if not estado.get("completed"):
        return None
    equipos = comp.get("competitors") or []
    boca = next((c for c in equipos if "boca juniors" in normalizar((c.get("team") or {}).get("displayName", ""))), None)
    rival = next((c for c in equipos if c is not boca), None)
    plantel = next((r for r in resumen.get("rosters") or []
                    if "boca juniors" in normalizar((r.get("team") or {}).get("displayName", ""))), None)
    if not boca or not rival or not plantel:
        return None
    gb, gr = int(boca.get("score") or 0), int(rival.get("score") or 0)
    todos_los_minutos = [_minuto((x.get("clock") or {}).get("displayValue")) for r in resumen.get("rosters") or []
                         for j in r.get("roster") or [] for x in j.get("plays") or []]
    alargue = "AET" in (estado.get("name", "") + estado.get("detail", "")).upper() or max(todos_los_minutos + [0]) > 100
    duracion = 120 if alargue else 90
    lista = []
    for j in plantel.get("roster") or []:
        st = {x.get("name"): x.get("value") for x in j.get("stats") or []}
        if not (j.get("starter") or j.get("subbedIn") or (st.get("appearances") or 0) >= 1):
            continue
        cambios = [min(_minuto((x.get("clock") or {}).get("displayValue")), duracion) for x in j.get("plays") or [] if x.get("substitution")]
        rojas = [min(_minuto((x.get("clock") or {}).get("displayValue")), duracion) for x in j.get("plays") or [] if x.get("redCard")]
        if j.get("starter"):
            ini = 0
            fin = cambios[0] if j.get("subbedOut") and cambios else duracion
        else:
            ini = cambios[0] if cambios else duracion
            fin = cambios[1] if j.get("subbedOut") and len(cambios) > 1 else duracion
        if rojas:
            fin = min(fin, rojas[0])
        a = j.get("athlete") or {}
        lista.append({"espn": a.get("id"), "n": a.get("displayName", ""), "tit": bool(j.get("starter")),
                      "min": max(0, fin - ini), "gol": int(st.get("totalGoals") or 0)})
    if not lista:
        return None
    temporada = ((resumen.get("header") or {}).get("season") or {}).get("name", "")
    liga = ((resumen.get("header") or {}).get("league") or {}).get("name", "")
    return {"fecha": fecha, "slug": slug, "torneo": _torneo_hdb(slug, fecha, temporada, liga),
            "rival": (rival.get("team") or {}).get("displayName", ""), "goles": [gb, gr],
            "res": "g" if gb > gr else "e" if gb == gr else "p", "duracion": duracion, "jugadores": lista}


def actualizar_partidos_nuevos() -> None:
    """Baja de ESPN los partidos oficiales que Boca jugó después de la descarga de Historia de Boca."""
    from datos_futbol import SITE
    from comun import DATOS_ESPN, http_get_json
    consultado = (leer_json(ARCHIVO, {}) or {}).get("consultado", "")
    if not consultado:
        return
    guardados = leer_json(ARCHIVO_NUEVOS, {}) or {}
    guardados = {k: v for k, v in guardados.items() if v.get("fecha", "") > consultado}  # al volver a bajar la base
    nuevos = 0
    for p in leer_json(DATOS_ESPN / "partidos.json", []) or []:
        fecha = (p.get("fecha") or "")[:10]
        if (p.get("estado") != "finalizado" or not _oficial(p.get("competencia_slug")) or fecha <= consultado
                or p["id"] in guardados or nuevos >= MAX_PARTIDOS_POR_CORRIDA):
            continue
        nuevos += 1
        try:
            partido = leer_partido_espn(http_get_json(f"{SITE}/{p['competencia_slug']}/summary?event={p['id']}"),
                                        p["competencia_slug"], fecha)
        except Exception as e:
            log(f"Historia de Boca: no pude leer el partido {p['id']} en ESPN ({e})")
            continue
        if partido:
            partido["visto"] = ahora().isoformat(timespec="minutes")
            guardados[p["id"]] = partido
            log(f"Historia de Boca: sumo el partido vs {partido['rival']} ({fecha}, {len(partido['jugadores'])} jugadores)")
    guardar_json(ARCHIVO_NUEVOS, dict(sorted(guardados.items(), key=lambda x: x[1]["fecha"])))


def _palabras(nombre: str) -> list[str]:
    return [x for x in re.sub(r"[^a-z ]", " ", normalizar(nombre or "")).split() if x not in ("de", "del", "la", "los", "y")]


def _mismo_nombre(a: str, b: str) -> bool:
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))  # William / Williams


def buscar_por_nombre_espn(nombre: str, todos: dict, desde_anio: int) -> str | None:
    """El id de Historia de Boca de un jugador de ESPN ("Miguel Merentiel" → "Miguel Angel Merentiel"),
    buscando entre los que jugaron en Boca hace poco."""
    pal = _palabras(nombre)
    if not pal:
        return None
    candidatos = []
    for i, j in todos.items():
        if not any((_anio_torneo(t[0]) or 0) >= desde_anio for t in j.get("tor", [])):
            continue
        hdb = _palabras(j.get("n"))
        if all(any(_mismo_nombre(p, h) for h in hdb) for p in pal):
            candidatos.append(i)
    if len(candidatos) == 1:
        return candidatos[0]
    # con un solo nombre en ESPN ("Fabra"), o si hay dos parecidos: el apellido tiene que coincidir con el último
    exactos = [i for i in candidatos if _palabras(todos[i]["n"])[-1] == pal[-1]]
    return exactos[0] if len(exactos) == 1 else None


def sumar_partidos_nuevos(todos: dict) -> None:
    partidos = leer_json(ARCHIVO_NUEVOS, {}) or {}
    consultado = (leer_json(ARCHIVO, {}) or {}).get("consultado", "")
    if not partidos or not consultado:
        return
    desde = int(consultado[:4]) - 1
    cache: dict[str, str | None] = {}
    for pid, p in partidos.items():
        if p.get("fecha", "") <= consultado:
            continue
        ids = []
        for x in p["jugadores"]:
            if x["n"] not in cache:
                cache[x["n"]] = buscar_por_nombre_espn(x["n"], todos, desde)
            i = cache[x["n"]]
            if not i:
                continue
            ids.append(i)
            j = todos[i]
            j["pj"] = (j.get("pj") or 0) + 1
            j["gol"] = (j.get("gol") or 0) + x["gol"]
            j["min"] = (j.get("min") or 0) + x["min"]
            clave = "tit" if x["tit"] else "ing"
            j[clave] = (j.get(clave) or 0) + 1
            j[p["res"]] = (j.get(p["res"]) or 0) + 1
            tor = j.setdefault("tor", [])
            fila = next((t for t in tor if t[0] == p["torneo"]), None)
            if fila:
                fila[1] += 1
                fila[2] += x["gol"]
            else:
                tor.append([p["torneo"], 1, x["gol"]])
        for i in ids:  # los que compartieron cancha quedan como compañeros
            comp = todos[i].setdefault("comp", [])
            for k in ids:
                if k != i and k not in comp:
                    comp.append(k)
