"""Base de jugadores de Boca, importada de Historia de Boca (con permiso).

datos/hdb/jugadores.json se baja desde el navegador del dueño (Historia de Boca bloquea a GitHub), igual que
las efemérides. Por cada jugador trae: partidos oficiales, goles, titularidades, minutos, debut y despedida,
nacimiento, lugar de nacimiento, biografía, partidos y goles por torneo, dorsales y con quién jugó
(compañeros en al menos un partido oficial).

De acá salen "¿Quién soy?", las dificultades de la Grilla y "¿Quién jugó con quién?".
"""
from __future__ import annotations

import hashlib
import re

from comun import DATOS, leer_json, normalizar

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
    return _cargar()


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
