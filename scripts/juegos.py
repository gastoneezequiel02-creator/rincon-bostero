"""Arma los datos de los juegos (preguntas, '¿Más o menos?' e ídolos) a partir de los datos reales de la web.

Todas las preguntas salen de datos verificados: títulos, historiales, récords, goleadores y la lista de ídolos.
No hay preguntas escritas a mano ni generadas por IA, así que las respuestas siempre coinciden con lo que
muestra el resto de la web.
"""
from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict

from comun import DATOS, DATOS_ESPN, DATOS_MANUAL, leer_json, normalizar

TEMAS = {
    "titulos": "Títulos y copas",
    "superclasico": "Superclásico",
    "rivales": "Clásicos y rivales",
    "historia": "Historia y récords",
    "idolos": "Ídolos",
    "temporada": "La temporada",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _id(texto: str) -> str:
    return hashlib.sha1(texto.encode()).hexdigest()[:10]


def _pregunta(tema, texto, correcta, distractores, dato="", rng=None) -> dict | None:
    """Arma una pregunta con 4 opciones únicas y mezcladas (siempre igual para el mismo texto)."""
    opciones = [str(correcta)]
    for d in distractores:
        d = str(d)
        if d not in opciones and normalizar(d) != normalizar(str(correcta)):
            opciones.append(d)
        if len(opciones) == 4:
            break
    if len(opciones) < 4:
        return None
    r = random.Random(_id(texto))
    r.shuffle(opciones)
    return {"id": _id(texto), "tema": tema, "texto": texto, "opciones": opciones,
            "correcta": opciones.index(str(correcta)), "dato": dato}


def _numeros_cerca(valor: int, rng: random.Random, paso: int | None = None) -> list[int]:
    paso = paso or max(1, round(valor * 0.08))
    candidatos = {valor + paso * k for k in (-3, -2, -1, 1, 2, 3)}
    candidatos = [c for c in candidatos if c >= 0 and c != valor]
    rng.shuffle(candidatos)
    return candidatos


# ------------------------------------------------------------------ títulos --
def _titulos() -> list[tuple[str, str, int]]:
    pal = leer_json(DATOS_MANUAL / "palmares.json", {}) or {}
    salida = []
    for cat in pal.get("categorias", []):
        for t in cat.get("titulos", []):
            m = re.search(r"(\d{4})", t)
            if m:
                base = re.sub(r"\s*\(.*?\)", "", t)
                base = re.sub(r"\s*\d{4}(/\d{2,4})?\s*", " ", base).strip()
                if base.lower().startswith("campeón de liga"):
                    base = "Liga por tabla anual"
                salida.append((cat["nombre"], base, int(m.group(1))))
    return salida


def _fin_de_temporada() -> dict:
    """Para títulos de temporadas partidas ("2017/18"), el año en que terminó la temporada, por categoría."""
    pal = leer_json(DATOS_MANUAL / "palmares.json", {}) or {}
    salida = defaultdict(set)
    for cat in pal.get("categorias", []):
        for t in cat.get("titulos", []):
            if m := re.search(r"(\d{4})/(\d{2,4})", t):
                salida[cat["nombre"]].add(int(m.group(1)) + 1)
    return salida


def preguntas_titulos(rng) -> list[dict]:
    ts = _titulos()
    if not ts:
        return []
    qs = []
    por_nombre = defaultdict(list)
    cat_de = {}
    anios_cat = defaultdict(set)
    for cat, nombre, anio in ts:
        por_nombre[nombre].append(anio)
        cat_de[nombre] = cat
        anios_cat[cat].add(anio)
    for cat, anios_fin in _fin_de_temporada().items():
        anios_cat[cat] |= anios_fin
    tope = max(a for _, _, a in ts)  # no se ofrecen años que todavía no pasaron
    femenino = ("Copa", "Supercopa", "Recopa", "Superliga", "Liga")
    total = len(ts)
    qs.append(_pregunta("titulos", "¿Cuántos títulos oficiales tiene Boca?", total, _numeros_cerca(total, rng, 2),
                        f"Boca tiene {total} títulos oficiales."))
    for nombre, anios in por_nombre.items():
        anios.sort()
        # un año en el que Boca ganó otro título de la misma categoría podría confundir (ej.: Liga 2026)
        otros = [a for a in range(anios[0] - 12, min(anios[-1] + 12, tope) + 1)
                 if a not in anios and a not in anios_cat[cat_de[nombre]] and a >= 1905]
        la = nombre.startswith(femenino)
        if len(anios) > 1:
            qs.append(_pregunta("titulos", f"¿Cuántas veces ganó Boca la {nombre}?" if la
                                else f"¿Cuántas veces ganó Boca el {nombre}?", len(anios),
                                _numeros_cerca(len(anios), rng, 1), f"La ganó en {', '.join(map(str, anios))}."))
            cerca = [a for a in otros if abs(a - anios[0]) <= 12]
            if len(cerca) >= 3:
                qs.append(_pregunta("titulos", f"¿En qué año ganó Boca su primera {nombre}?" if la
                                    else f"¿En qué año ganó Boca su primer {nombre}?", anios[0],
                                    rng.sample(cerca, 3), f"Fue en {anios[0]}."))
        else:
            cerca = [a for a in otros if abs(a - anios[0]) <= 10]
            if len(cerca) >= 3:
                qs.append(_pregunta("titulos", f"¿En qué año ganó Boca {'la' if la else 'el'} {nombre}?", anios[0],
                                    rng.sample(cerca, 3)))
    # ¿qué título ganó en tal año?
    por_anio = defaultdict(list)
    for _, nombre, anio in ts:
        por_anio[anio].append(nombre)
    internacionales = [n for c, n, _ in ts if c.startswith("Copas internacionales")]
    for anio, nombres in por_anio.items():
        if len(nombres) != 1 or nombres[0] not in internacionales:
            continue
        falsos = [n for n in set(internacionales) if n not in nombres]
        rng.shuffle(falsos)
        qs.append(_pregunta("titulos", f"¿Qué copa internacional ganó Boca en {anio}?", nombres[0], falsos))
    # por categoría y por década
    por_cat = defaultdict(int)
    for c, _, _ in ts:
        por_cat[c] += 1
    for c, n in por_cat.items():
        if n > 1:
            qs.append(_pregunta("titulos", f"¿Cuántos títulos de la categoría «{c}» tiene Boca?", n, _numeros_cerca(n, rng, 2)))
    por_dec = defaultdict(int)
    for _, _, a in ts:
        por_dec[a // 10 * 10] += 1
    for dec, n in por_dec.items():
        qs.append(_pregunta("titulos", f"¿Cuántos títulos oficiales ganó Boca en los años {dec}?", n, _numeros_cerca(n, rng, 1),
                            f"En los {dec}: " + ", ".join(f"{nm} {a}" for _, nm, a in ts if a // 10 * 10 == dec) + "."))
    mejor_dec = max(por_dec.items(), key=lambda x: x[1])
    if sum(1 for v in por_dec.values() if v == mejor_dec[1]) == 1:
        qs.append(_pregunta("titulos", "¿En qué década ganó Boca más títulos?", f"Años {mejor_dec[0]}",
                            [f"Años {d}" for d, _ in sorted(por_dec.items(), key=lambda x: -x[1])[1:6]],
                            f"Ganó {mejor_dec[1]} títulos en esa década."))
    # ¿cuál de estos títulos ganó? (los falsos son ediciones que Boca no ganó)
    existe = {"Copa Libertadores": (1960, 2025), "Copa Sudamericana": (2002, 2025), "Recopa Sudamericana": (1989, 2025),
              "Copa Intercontinental": (1960, 2004), "Copa Argentina": (2011, 2025), "Supercopa Argentina": (2012, 2025)}
    for comp, (desde, hasta) in existe.items():
        ganadas = por_nombre.get(comp, [])
        # se evitan los años vecinos a un título: algunas ediciones se nombran por la temporada (2019/20, etc.)
        no_ganadas = [a for a in range(desde, hasta + 1) if all(abs(a - g) > 1 for g in ganadas)]
        for a in ganadas:
            falsos = [f"{comp} {x}" for x in rng.sample(no_ganadas, min(3, len(no_ganadas)))]
            q = _pregunta("titulos", f"¿Cuál de estas ediciones de la {comp} ganó Boca?", f"{comp} {a}", falsos,
                          f"Boca ganó la {comp} en {', '.join(map(str, sorted(ganadas)))}.")
            if q:
                q["id"] = _id(q["texto"] + str(a))
                qs.append(q)
    return [q for q in qs if q]


# ---------------------------------------------------------------- historial --
def _historiales_liga() -> list[dict]:
    """Totales en campeonatos de liga (Historia de Boca) contra los clásicos, actualizados."""
    try:
        import historia_de_boca
    except Exception:
        return []
    partidos = leer_json(DATOS_ESPN / "partidos.json", []) or []
    salida = []
    for r in historia_de_boca.historiales().get("rivales", []):
        nombre = r["nombres"][0]
        espn = next((p["rival"] for p in partidos if normalizar(p["rival"]["nombre"]) in map(normalizar, r["nombres"])), None)
        t = historia_de_boca.total_actualizado(espn or {"id": None, "nombre": nombre}, partidos)
        if t:
            corto = {"River Plate": "River", "Racing Club": "Racing", "Estudiantes de La Plata": "Estudiantes",
                     "Vélez Sarsfield": "Vélez", "Newell's Old Boys": "Newell's"}.get(nombre, nombre)
            salida.append({"nombre": corto, **t})
    return salida


def preguntas_rivales(rng) -> list[dict]:
    hs = _historiales_liga()
    qs = []
    if not hs:
        return qs
    nota = "En campeonatos de liga, según Historia de Boca."
    for h in hs:
        tema = "superclasico" if h["nombre"] == "River" else "rivales"
        qs.append(_pregunta(tema, f"En campeonatos de liga, ¿cuántas veces le ganó Boca a {h['nombre']}?", h["g"],
                            _numeros_cerca(h["g"], rng), f"{h['g']} victorias, {h['e']} empates y {h['p']} derrotas. {nota}"))
        qs.append(_pregunta(tema, f"En campeonatos de liga, ¿cuántos partidos jugaron Boca y {h['nombre']}?", h["pj"],
                            _numeros_cerca(h["pj"], rng), nota))
        if tema == "superclasico":
            qs.append(_pregunta(tema, "En campeonatos de liga, ¿cuántos Superclásicos terminaron empatados?", h["e"],
                                _numeros_cerca(h["e"], rng), nota))
            qs.append(_pregunta(tema, "En campeonatos de liga, ¿cuántos goles le hizo Boca a River?", h["gf"],
                                _numeros_cerca(h["gf"], rng, 10), nota))
            qs.append(_pregunta(tema, "En campeonatos de liga, ¿cuántas veces le ganó River a Boca?", h["p"],
                                _numeros_cerca(h["p"], rng), nota))
            qs.append(_pregunta(tema, "En campeonatos de liga, ¿cuántos goles le hizo River a Boca?", h["gc"],
                                _numeros_cerca(h["gc"], rng, 10), nota))
            dif = h["g"] - h["p"]
            if dif > 0:
                qs.append(_pregunta(tema, "En campeonatos de liga, ¿por cuántos partidos le saca ventaja Boca a River en el historial?",
                                    dif, _numeros_cerca(dif, rng, 2), f"Boca ganó {h['g']} y River {h['p']}. {nota}"))
    for h in hs:
        tema = "superclasico" if h["nombre"] == "River" else "rivales"
        qs.append(_pregunta(tema, f"En campeonatos de liga, ¿cuántas veces empataron Boca y {h['nombre']}?", h["e"],
                            _numeros_cerca(h["e"], rng), nota))
        qs.append(_pregunta(tema, f"En campeonatos de liga, ¿cuántos goles le hizo Boca a {h['nombre']}?", h["gf"],
                            _numeros_cerca(h["gf"], rng, 10), nota))
        if tema == "rivales":
            qs.append(_pregunta(tema, f"En campeonatos de liga, ¿cuántas veces le ganó {h['nombre']} a Boca?", h["p"],
                                _numeros_cerca(h["p"], rng), nota))
    for clave, frase in (("p", "más derrotas"), ("e", "más empates"), ("pj", "más partidos jugados"), ("gf", "más goles a favor")):
        for _ in range(8):
            grupo = rng.sample(hs, 4)
            mejor = max(grupo, key=lambda h: h[clave])
            if sum(1 for h in grupo if h[clave] == mejor[clave]) > 1:
                continue
            q = _pregunta("rivales", f"En campeonatos de liga, ¿contra cuál de estos rivales tiene Boca {frase}?", mejor["nombre"],
                          [h["nombre"] for h in grupo if h is not mejor],
                          " ".join(f"{h['nombre']}: {h[clave]}." for h in sorted(grupo, key=lambda h: -h[clave])))
            if q:
                q["id"] = _id(q["texto"] + "".join(sorted(h["nombre"] for h in grupo)))
                qs.append(q)
    # ¿contra cuál tiene más victorias?
    for _ in range(12):
        grupo = rng.sample(hs, 4)
        mejor = max(grupo, key=lambda h: h["g"])
        if sum(1 for h in grupo if h["g"] == mejor["g"]) > 1:
            continue
        q = _pregunta("rivales", "En campeonatos de liga, ¿contra cuál de estos rivales tiene Boca más victorias?",
                      mejor["nombre"], [h["nombre"] for h in grupo if h is not mejor],
                      " ".join(f"{h['nombre']}: {h['g']}." for h in sorted(grupo, key=lambda h: -h["g"])))
        if q:
            q["id"] = _id(q["texto"] + "".join(sorted(h["nombre"] for h in grupo)))
            qs.append(q)
    return [q for q in qs if q]


# ----------------------------------------------------------- historia y récords --
def preguntas_historia(rng) -> list[dict]:
    qs = [
        _pregunta("historia", "¿En qué año se fundó Boca Juniors?", 1905, [1901, 1908, 1913],
                  "Boca se fundó el 3 de abril de 1905 en La Boca."),
    ]
    rec = leer_json(DATOS / "bocastats" / "records.json", {}) or {}
    marcas = list(rec.get("marcas", []))
    try:  # las rachas se calculan partido a partido (sin anulados ni giras), no se toman de la copia guardada
        import bocastats
        of = [p for p in bocastats.todos_los_partidos() if not p["amistoso"]]
        if len(of) > 3000:
            r = bocastats.mejores_rachas(bocastats.todos_los_partidos())
            calc = {"Racha de victorias más larga": r["victorias"][0], "Racha invicta más larga": r["invicto"][0]}
            marcas = [dict(m, valor=f"{len(calc[m['titulo']])} partidos",
                           detalle=f"Del {calc[m['titulo']][0]['fecha'][:4]} al {calc[m['titulo']][-1]['fecha'][:4]}.")
                      if m["titulo"] in calc else m for m in marcas]
    except Exception:
        pass
    for m in marcas:
        t, v, d = m["titulo"], m["valor"], m.get("detalle", "")
        if t == "Mayor goleada" and (g := re.search(r"Boca (\d+)-(\d+) (.+)", v)):
            anio = re.search(r"(\d{4})", d)
            qs.append(_pregunta("historia", f"¿A qué rival le ganó Boca {g.group(1)}-{g.group(2)}, la mayor goleada de su historia"
                                f"{f', en {anio.group(1)}' if anio else ''}?", g.group(3), ["Lanús", "Chacarita", "Atlanta", "Platense"], d))
        elif t == "Peor derrota" and (g := re.search(r"Boca (\d+)-(\d+) (.+)", v)):
            anio = re.search(r"(\d{4})", d)
            qs.append(_pregunta("historia", f"¿Contra quién sufrió Boca su peor derrota, {g.group(1)}-{g.group(2)}"
                                f"{f' en {anio.group(1)}' if anio else ''}?", g.group(3), ["Alumni", "Racing", "Porteño", "Estudiantes"], d))
        elif t == "Primer partido" and (g := re.search(r"Boca (\d+)-(\d+) (.+)", v)):
            qs.append(_pregunta("historia", "¿Contra quién jugó Boca su primer partido, en 1905?", g.group(3),
                                ["Alumni", "Belgrano Athletic", "Quilmes", "Atlanta"], f"Boca {g.group(1)}-{g.group(2)} {g.group(3)}, {d}."))
        elif t == "Racha invicta más larga" and (n := re.search(r"(\d+)", v)):
            n = int(n.group(1))
            qs.append(_pregunta("historia", "¿Cuántos partidos seguidos sin perder logró Boca entre 1924 y 1926, su mejor racha invicta?",
                                n, _numeros_cerca(n, rng, 4), d))
        elif t == "Racha de victorias más larga" and (n := re.search(r"(\d+)", v)):
            n = int(n.group(1))
            anio = re.search(r"(\d{4})", d)
            qs.append(_pregunta("historia", f"¿Cuántas victorias seguidas logró Boca en su mejor racha{f', que empezó en {anio.group(1)}' if anio else ''}?",
                                n, _numeros_cerca(n, rng, 2), d))
    # partidos históricos de la base de BocaStats (si está cargada)
    try:
        import bocastats
        oficiales = [p for p in bocastats.todos_los_partidos() if not p["amistoso"]]
    except Exception:
        oficiales = []
    grandes = ["River", "Racing", "Independiente", "San Lorenzo", "Estudiantes (LP)", "Huracán", "Vélez"]
    if len(oficiales) > 3000:
        # balances por rival y por década, solo partidos oficiales
        por_rival = defaultdict(lambda: {"pj": 0, "g": 0})
        por_dec = defaultdict(lambda: {"pj": 0, "g": 0})
        for p in oficiales:
            for d in (por_rival[p["rival"]], por_dec[int(p["fecha"][:3] + "0")]):
                d["pj"] += 1
                d["g"] += p["resultado"] == "G"
        frecuentes = sorted(por_rival.items(), key=lambda x: -x[1]["pj"])[:30]
        for nombre, v in frecuentes:
            tema = "superclasico" if nombre == "River" else "rivales"
            qs.append(_pregunta(tema, f"Contando todas las competencias oficiales, ¿cuántas veces le ganó Boca a {nombre}?", v["g"],
                                _numeros_cerca(v["g"], rng), f"{v['g']} victorias en {v['pj']} partidos oficiales."))
        mejor = max(por_dec.items(), key=lambda x: x[1]["g"])
        qs.append(_pregunta("historia", "¿En qué década ganó Boca más partidos oficiales?", f"Años {mejor[0]}",
                            [f"Años {d}" for d, _ in sorted(por_dec.items(), key=lambda x: -x[1]["g"])[1:6]],
                            f"Ganó {mejor[1]['g']} partidos en esa década."))
        primero_river = next((p for p in oficiales if p["rival"] == "River"), None)
        if primero_river:
            a = int(primero_river["fecha"][:4])
            qs.append(_pregunta("superclasico", "¿En qué año se jugó el primer Superclásico oficial?", a, [a - 5, a + 3, a + 8, a - 2]))
        candidatos = [p for p in oficiales if p["rival"] in grandes and abs(p["goles_boca"] - p["goles_rival"]) >= 3]
        rng.shuffle(candidatos)
        for p in candidatos[:120]:
            d, m, a = int(p["fecha"][8:10]), int(p["fecha"][5:7]), p["fecha"][:4]
            res = "ganó" if p["resultado"] == "G" else "perdió"
            qs.append(_pregunta("historia", f"El {d} de {MESES[m - 1]} de {a}, Boca {res} {max(p['goles_boca'], p['goles_rival'])}-"
                                f"{min(p['goles_boca'], p['goles_rival'])} ({p['torneo']}). ¿Contra quién?",
                                p["rival"], [g for g in grandes if g != p["rival"]][:5]))
    # efemérides guardadas: "¿qué pasó un 18 de noviembre de 1945?"
    # una por día: la efeméride destacada; las opciones falsas son destacadas de otros días (mismo estilo de redacción)
    import historia_de_boca
    destacadas = {k: next((x for x in v if x.get("destacado")), None) for k, v in historia_de_boca.efemerides_guardadas().items()}
    destacadas = {k: v for k, v in destacadas.items() if v}
    for clave, it in sorted(destacadas.items(), key=lambda kv: _id("efemeride" + kv[0]))[:60]:  # 60 fijas, para no tapar al resto
        mes, dia = int(clave[:2]), int(clave[3:])
        otros = [x["titulo"] for k, x in destacadas.items() if k != clave and x["anio"] != it["anio"] and x.get("tipo") == it.get("tipo")]
        otros = sorted(otros, key=lambda t: _id(t + clave))[:3]
        if len(otros) >= 3:
            qs.append(_pregunta("historia", f"¿Qué pasó en la historia de Boca un {dia} de {MESES[mes - 1]} de {it['anio']}?",
                                it["titulo"], otros, it.get("detalle", "")))
    return [q for q in qs if q]


# -------------------------------------------------------------------- ídolos --
def idolos() -> list[dict]:
    return (leer_json(DATOS_MANUAL / "idolos.json", {}) or {}).get("idolos", [])


def preguntas_idolos(rng) -> list[dict]:
    ids = idolos()
    qs = []
    if len(ids) < 6:
        return qs
    paises = sorted({i["pais"] for i in ids} | {"Paraguay", "Chile", "Perú"})
    for i in ids:
        dec = i["debut"] // 10 * 10
        qs.append(_pregunta("idolos", f"¿En qué década llegó {i['nombre']} a la Primera de Boca?", f"Años {dec}",
                            [f"Años {dec + k}" for k in (-20, -10, 10, 20) if 1920 <= dec + k <= 2020],
                            f"Debutó o llegó en {i['debut']}."))
        if i["pais"] != "Argentina":
            qs.append(_pregunta("idolos", f"¿De qué país es {i['nombre']}?", i["pais"],
                                [p for p in paises if p != i["pais"]]))
        if i.get("apodo"):
            otros = [x["apodo"] for x in ids if x.get("apodo") and x is not i]
            rng.shuffle(otros)
            qs.append(_pregunta("idolos", f"¿Cómo le dicen a {i['nombre']}?", i["apodo"], otros))
    posiciones = ["Arquero", "Defensor", "Mediocampista", "Delantero"]
    for i in ids:
        qs.append(_pregunta("idolos", f"¿En qué posición jugaba {i['nombre']}?", i["posicion"],
                            [x for x in posiciones if x != i["posicion"]]))
    for _ in range(25):
        grupo = rng.sample(ids, 4)
        primero = min(grupo, key=lambda i: i["debut"])
        if sum(1 for i in grupo if i["debut"] == primero["debut"]) > 1:
            continue
        q = _pregunta("idolos", "¿Cuál de estos jugadores llegó primero a Boca?", primero["nombre"],
                      [i["nombre"] for i in grupo if i is not primero],
                      " ".join(f"{i['nombre']}: {i['debut']}." for i in sorted(grupo, key=lambda i: i["debut"])))
        if q:
            q["id"] = _id(q["texto"] + "".join(sorted(i["nombre"] for i in grupo)))
            qs.append(q)
    extranjeros = [i for i in ids if i["pais"] != "Argentina"]
    argentinos = [i for i in ids if i["pais"] == "Argentina"]
    for i in extranjeros:
        q = _pregunta("idolos", f"¿Cuál de estos jugadores nació en {i['pais']}?", i["nombre"],
                      [x["nombre"] for x in rng.sample(argentinos, 3)])
        if q:
            q["id"] = _id(q["texto"] + i["nombre"])
            qs.append(q)
    con = [i for i in ids if i["libertadores"]]
    sin = [i for i in ids if not i["libertadores"]]
    for i in rng.sample(con, min(8, len(con))):
        q = _pregunta("idolos", "¿Cuál de estos jugadores ganó la Copa Libertadores con Boca?", i["nombre"],
                      [x["nombre"] for x in rng.sample(sin, min(3, len(sin)))])
        if q:
            q["id"] = _id(q["texto"] + i["nombre"])
            qs.append(q)
    return [q for q in qs if q]


# ------------------------------------------------------------------ temporada --
def preguntas_temporada(rng) -> list[dict]:
    qs = []
    gol = leer_json(DATOS / "bocastats" / "goleadores.json", {}) or {}
    js = gol.get("jugadores", [])
    t = gol.get("temporada")
    if len(js) >= 4:
        top = js[0]
        if js[1]["goles"] < top["goles"]:
            qs.append(_pregunta("temporada", f"¿Quién es el goleador de Boca en la temporada {t}?", top["nombre"],
                                [j["nombre"] for j in js[1:6]], f"{top['nombre']} lleva {top['goles']} goles."))
            qs.append(_pregunta("temporada", f"¿Cuántos goles lleva {top['nombre']} en la temporada {t}?", top["goles"],
                                _numeros_cerca(top["goles"], rng, 2)))
        for comp in ("Copa Argentina", "Libertadores", "Sudamericana"):
            con = [j for j in js if (j.get("desglose") or {}).get(comp)]
            sin = [j for j in js if j.get("desglose") and not j["desglose"].get(comp)]
            if con and len(sin) >= 3:
                elegido = rng.choice(con)
                q = _pregunta("temporada", f"¿Cuál de estos jugadores hizo goles en la {'Copa ' if comp != 'Copa Argentina' else ''}{comp} {t}?",
                              elegido["nombre"], [j["nombre"] for j in rng.sample(sin, 3)])
                if q:
                    qs.append(q)
    if len(js) >= 4:
        total = sum(j["goles"] for j in js)
        qs.append(_pregunta("temporada", f"¿Cuántos goles hizo Boca entre todos sus goleadores en la temporada {t}?", total,
                            _numeros_cerca(total, rng, 4)))
        con_asist = [j for j in js if j.get("asistencias_liga") is not None]
        if con_asist:
            top_a = max(con_asist, key=lambda j: j["asistencias_liga"])
            if sum(1 for j in con_asist if j["asistencias_liga"] == top_a["asistencias_liga"]) == 1:
                qs.append(_pregunta("temporada", f"¿Quién dio más asistencias en la Liga {t}?", top_a["nombre"],
                                    [j["nombre"] for j in sorted(con_asist, key=lambda j: -j["asistencias_liga"])[1:5]],
                                    f"{top_a['nombre']} dio {top_a['asistencias_liga']} asistencias."))
        for j in js[:10]:
            qs.append(_pregunta("temporada", f"¿Cuántos goles lleva {j['nombre']} en la temporada {t}?", j["goles"],
                                _numeros_cerca(j["goles"], rng, 1)))
    partidos = leer_json(DATOS_ESPN / "partidos.json", []) or []
    fin = sorted([p for p in partidos if p["estado"] == "finalizado" and p.get("resultado")], key=lambda p: p["fecha"] or "")
    for u in fin[-15:]:
        d = u["fecha"][:10]
        real = f"{u['goles_boca']}-{u['goles_rival']}"
        falsos = [f"{a}-{b}" for a, b in ((u['goles_rival'], u['goles_boca']), (u['goles_boca'] + 1, u['goles_rival']),
                                            (u['goles_boca'], u['goles_rival'] + 1), (u['goles_boca'] + 2, u['goles_rival'] + 1))]
        qs.append(_pregunta("temporada", f"¿Cómo terminó Boca contra {u['rival']['nombre']} el {int(d[8:10])} de {MESES[int(d[5:7]) - 1]}"
                            f" ({u['competencia']})? Goles de Boca primero.", real, falsos))
    por_comp = defaultdict(list)
    for p in fin:
        if str(p.get("temporada")) == str(fin[-1].get("temporada")) if fin else False:
            por_comp[p["competencia"]].append(p)
    for comp, ps in por_comp.items():
        g = sum(1 for p in ps if p["resultado"] == "G")
        if len(ps) >= 4:
            qs.append(_pregunta("temporada", f"¿Cuántos partidos ganó Boca en la {comp} {fin[-1]['temporada']}?", g,
                                _numeros_cerca(g, rng, 1), f"Ganó {g} de {len(ps)}."))
    plantel = (leer_json(DATOS_ESPN / "plantel.json", {}) or {}).get("jugadores", [])
    numeros = [j for j in plantel if str(j.get("numero", "")).isdigit()]
    for j in numeros:
        otros = [int(x["numero"]) for x in numeros if x is not j]
        rng.shuffle(otros)
        qs.append(_pregunta("temporada", f"¿Qué número de camiseta usa {j['nombre']}?", int(j["numero"]), otros))
    rv = [p for p in fin if normalizar(p["rival"]["nombre"]).startswith("river")]
    if len(rv) >= 3:
        desde = rv[0]["fecha"][:4]
        for clave, frase in (("G", "ganó Boca"), ("E", "terminaron empatados"), ("P", "ganó River")):
            n = sum(1 for p in rv if p["resultado"] == clave)
            qs.append(_pregunta("superclasico", f"Desde {desde}, contando todas las competencias, ¿cuántos Superclásicos {frase}?", n,
                                _numeros_cerca(n, rng, 1), f"{len(rv)} Superclásicos desde {desde}."))
        n = sum(p["goles_boca"] for p in rv)
        qs.append(_pregunta("superclasico", f"Desde {desde}, ¿cuántos goles le hizo Boca a River en Superclásicos oficiales?", n,
                            _numeros_cerca(n, rng, 2)))
    super_ = sorted([p for p in partidos if p["estado"] == "finalizado" and p.get("resultado")
                     and normalizar(p["rival"]["nombre"]).startswith("river")], key=lambda p: p["fecha"] or "")
    if super_:
        u = super_[-1]
        real = f"{u['goles_boca']}-{u['goles_rival']}"
        falsos = [f"{a}-{b}" for a, b in ((u['goles_rival'], u['goles_boca']), (u['goles_boca'] + 1, u['goles_rival']),
                                            (u['goles_boca'], u['goles_rival'] + 1), (u['goles_boca'] + 2, u['goles_rival']))]
        qs.append(_pregunta("superclasico", f"¿Cómo terminó el último Superclásico, por {u['competencia']}? (goles de Boca primero)", real, falsos))
    jugados = sorted([p for p in partidos if p["estado"] == "finalizado" and p.get("resultado")], key=lambda p: p["fecha"] or "")
    if jugados:
        u = jugados[-1]
        real = f"{u['goles_boca']}-{u['goles_rival']}"
        falsos = [f"{a}-{b}" for a, b in ((u['goles_boca'] + 1, u['goles_rival']), (u['goles_rival'], u['goles_boca']),
                                            (u['goles_boca'], u['goles_rival'] + 1), (u['goles_boca'] + 1, u['goles_rival'] + 1))]
        qs.append(_pregunta("temporada", f"¿Cómo salió Boca en su último partido, contra {u['rival']['nombre']} ({u['competencia']})?"
                            " (goles de Boca primero)", real, falsos))
    ts = _titulos()
    if ts:
        ultimo = max(ts, key=lambda x: x[2])
        qs.append(_pregunta("temporada", "¿Cuál fue el último título que ganó Boca?", f"{ultimo[1]} {ultimo[2]}",
                            [f"{n} {a}" for _, n, a in sorted(ts, key=lambda x: -x[2])[1:6]]))
    return [q for q in qs if q]


# -------------------------------------------------------------- ¿más o menos? --
def datos_mas_o_menos() -> list[dict]:
    """Grupos de cosas comparables: [{pregunta, unidad, items: [{nombre, valor}]}]."""
    grupos = []
    hs = _historiales_liga()
    if len(hs) >= 3:
        grupos.append({"pregunta": "¿Contra quién tiene Boca más victorias en campeonatos de liga?", "unidad": "victorias",
                       "items": [{"nombre": h["nombre"], "valor": h["g"]} for h in hs]})
        grupos.append({"pregunta": "¿Contra quién jugó Boca más partidos de liga?", "unidad": "partidos",
                       "items": [{"nombre": h["nombre"], "valor": h["pj"]} for h in hs]})
        grupos.append({"pregunta": "¿A quién le hizo Boca más goles en campeonatos de liga?", "unidad": "goles",
                       "items": [{"nombre": h["nombre"], "valor": h["gf"]} for h in hs]})
    try:
        import bocastats
        oficiales = [p for p in bocastats.todos_los_partidos() if not p["amistoso"]]
    except Exception:
        oficiales = []
    if len(oficiales) > 3000:
        por = defaultdict(lambda: {"pj": 0, "g": 0})
        nombres = {}
        for p in oficiales:
            por[p["rival_slug"]]["pj"] += 1
            por[p["rival_slug"]]["g"] += p["resultado"] == "G"
            nombres[p["rival_slug"]] = p["rival"]
        frecuentes = [k for k, v in por.items() if v["pj"] >= 15]
        grupos.append({"pregunta": "¿Contra quién jugó Boca más partidos oficiales?", "unidad": "partidos oficiales",
                       "items": [{"nombre": nombres[k], "valor": por[k]["pj"]} for k in frecuentes]})
        grupos.append({"pregunta": "¿A quién le ganó Boca más veces en partidos oficiales?", "unidad": "victorias",
                       "items": [{"nombre": nombres[k], "valor": por[k]["g"]} for k in frecuentes]})
    ts = _titulos()
    if ts:
        cuenta = defaultdict(int)
        for _, n, _a in ts:
            cuenta[n] += 1
        grupos.append({"pregunta": "¿Qué ganó Boca más veces?", "unidad": "títulos",
                       "items": [{"nombre": n, "valor": v} for n, v in cuenta.items()]})
    gol = (leer_json(DATOS / "bocastats" / "goleadores.json", {}) or {})
    if len(gol.get("jugadores", [])) >= 4:
        grupos.append({"pregunta": f"¿Quién hizo más goles en la temporada {gol.get('temporada', '')}?", "unidad": "goles",
                       "items": [{"nombre": j["nombre"], "valor": j["goles"]} for j in gol["jugadores"]]})
    try:
        grupos += grupos_rankings()
    except Exception as e:
        print(f"Juegos: no pude armar los duelos de rankings: {e}")
    return [g for g in grupos if len({i["valor"] for i in g["items"]}) >= 3]


# ------------------------------------------------------------ fotos --------
def _con_foto(item: dict) -> dict:
    """Agrega la foto libre (Wikimedia) de la persona, si ya se bajó."""
    try:
        import imagenes
        f = imagenes.foto_guardada(item["nombre"])
    except Exception:
        f = None
    if f:
        item = {**item, "foto": f["imagen"], "credito": f["credito"].replace("Foto de archivo: ", "")}
    return item


def grupos_rankings() -> list[dict]:
    """Duelos de jugadores y técnicos a partir de los rankings históricos (Historia de Boca)."""
    rk = leer_json(DATOS / "hdb" / "rankings.json", {}) or {}
    js = rk.get("jugadores") or {}
    textos = {
        "goles": ("¿Quién hizo más goles en Boca?", "goles"),
        "partidos": ("¿Quién jugó más partidos en Boca?", "partidos"),
        "cabeza": ("¿Quién hizo más goles de cabeza en Boca?", "goles de cabeza"),
        "penales": ("¿Quién convirtió más penales en Boca?", "penales"),
        "amonestaciones": ("¿Quién vio más tarjetas amarillas en Boca?", "amarillas"),
        "expulsiones": ("¿A quién expulsaron más veces jugando en Boca?", "expulsiones"),
    }
    grupos = []
    for clave, (preg, unidad) in textos.items():
        filas = (js.get(clave) or {}).get("filas", [])
        if len(filas) >= 6:
            grupos.append({"pregunta": preg, "unidad": unidad, "personas": True, "fuente": "Historia de Boca, partidos oficiales",
                           "items": [_con_foto({"nombre": f["nombre"], "valor": f["valor"]}) for f in filas]})
    tec = rk.get("tecnicos") or []
    if len(tec) >= 6:
        grupos.append({"pregunta": "¿Qué técnico ganó más partidos dirigiendo a Boca?", "unidad": "victorias", "personas": True,
                       "fuente": "Historia de Boca, partidos oficiales",
                       "items": [_con_foto({"nombre": t["nombre"], "valor": t["g"]}) for t in tec]})
    return grupos


# ------------------------------------------------------- ¿en qué año fue? --
ORD_F = ["primera", "segunda", "tercera", "cuarta", "quinta", "sexta", "séptima", "octava", "novena", "décima"]
ORD_M = ["primer", "segundo", "tercer", "cuarto", "quinto", "sexto", "séptimo", "octavo", "noveno", "décimo"]


def eventos_anio() -> list[dict]:
    """Hechos con año exacto, todos sacados de datos verificados de la web."""
    eventos = []
    pal = leer_json(DATOS_MANUAL / "palmares.json", {}) or {}
    por_tipo = defaultdict(list)
    for cat in pal.get("categorias", []):
        for t in cat.get("titulos", []):
            if "/" in t:
                continue  # temporadas partidas (2017/18): el año es ambiguo
            m = re.search(r"\b(19\d{2}|20\d{2})\b", t)
            if not m:
                continue
            base = re.sub(r"\s*\(.*?\)", "", t)
            base = re.sub(r"\s*\b(19|20)\d{2}\b\s*", " ", base).strip()
            por_tipo[base].append(int(m.group(1)))
    for base, anios in por_tipo.items():
        anios.sort()
        if base.lower().startswith(("campeonato de primera", "campeón de liga")):
            continue  # demasiados y muy parecidos entre sí
        masc = base.lower().startswith(("torneo", "campeonato", "metropolitano", "nacional"))
        for i, a in enumerate(anios):
            if len(anios) == 1:
                texto = f"Boca gana {'el' if masc else 'la'} {base}"
            elif i < len(ORD_F):
                texto = f"Boca gana su {(ORD_M if masc else ORD_F)[i]} {base}"
            else:
                continue
            eventos.append({"id": _id(f"tit-{base}-{a}"), "tipo": "Título", "texto": texto, "anio": a,
                            "dato": f"{base} {a}."})
    try:
        import bocastats
        partidos = [p for p in bocastats.todos_los_partidos() if not p["amistoso"]]
    except Exception:
        partidos = []
    for p in partidos:
        if p.get("rival_slug") != "river":
            continue
        gb, gr = p.get("goles_boca"), p.get("goles_rival")
        if gb is None or gr is None or abs(gb - gr) < 3:
            continue
        comp = re.sub(r"\s*\b(19|20)\d{2}\b(/\d{2,4})?", "", p.get("torneo", "")).strip(" -") or "un torneo oficial"
        lugar = "de local" if p.get("condicion") == "L" else "de visitante" if p.get("condicion") == "V" else "en cancha neutral"
        art = "la" if re.match(r"(?i)(copa|supercopa|recopa|liga)", comp) else "el"
        if gb > gr:
            texto = f"Superclásico: Boca le gana {gb}-{gr} a River {lugar}, por {art} {comp}"
        else:
            texto = f"Superclásico: Boca pierde {gb}-{gr} con River {lugar}, por {art} {comp}"
        anio = int(p["fecha"][:4])
        eventos.append({"id": _id(f"sc-{p['fecha']}"), "tipo": "Superclásico", "texto": texto, "anio": anio,
                        "dato": f"Fue el {int(p['fecha'][8:10])} de {MESES[int(p['fecha'][5:7]) - 1]} de {anio}."})
    rec = leer_json(DATOS / "bocastats" / "records.json", {}) or {}
    textos = {"Mayor goleada": "La goleada más grande de la historia de Boca: {valor}",
              "Peor derrota": "La peor derrota de la historia de Boca: {valor}",
              "Primer partido": "El primer partido de la historia de Boca: {valor}"}
    for m in rec.get("marcas", []):
        anios = re.findall(r"\b(19\d{2}|20\d{2})\b", m.get("detalle", ""))
        if m.get("titulo") in textos and len(set(anios)) == 1:
            eventos.append({"id": _id("rec-" + m["titulo"]), "tipo": "Récord", "texto": textos[m["titulo"]].format(valor=m["valor"]),
                            "anio": int(anios[0]), "dato": m["detalle"] + "."})
    return eventos


# ---------------------------------------------------------- grilla bostera --
MIN_GRILLA = 15  # clubes con al menos esta cantidad de jugadores compartidos con Boca


def datos_grilla() -> dict | None:
    """Jugadores de Boca (Wikidata) y los clubes que sirven para armar la grilla. La grilla del día la arma la web."""
    d = leer_json(DATOS / "wikidata" / "jugadores_boca.json", {}) or {}
    clubes = {q: c for q, c in (d.get("clubes") or {}).items() if c.get("jugadores", 0) >= MIN_GRILLA}
    if len(clubes) < 8:
        return None
    orden = sorted(clubes, key=lambda q: -clubes[q]["jugadores"])
    indice = {q: i for i, q in enumerate(orden)}
    jugadores = []
    for nombre, cs in d.get("jugadores", []):
        jugadores.append([nombre] + sorted(indice[c] for c in cs if c in indice))
    return {"fuente": "Wikidata", "consultado": d.get("consultado", "")[:10],
            "clubes": [clubes[q]["nombre"] for q in orden], "jugadores": jugadores}


# ------------------------------------------------------------------- armado --
def armar() -> dict:
    rng = random.Random(1905)
    preguntas = []
    for f in (preguntas_titulos, preguntas_rivales, preguntas_historia, preguntas_idolos, preguntas_temporada):
        try:
            preguntas += f(rng)
        except Exception as e:  # una fuente rota no tiene que dejar sin juegos al resto
            print(f"Juegos: no pude armar {f.__name__}: {e}")
    vistas, unicas = set(), []
    for q in preguntas:
        if q["id"] not in vistas:
            vistas.add(q["id"])
            unicas.append(q)
    temas = {k: v for k, v in TEMAS.items() if sum(1 for q in unicas if q["tema"] == k) >= 4}
    try:
        eventos = eventos_anio()
    except Exception as e:
        print(f"Juegos: no pude armar ¿En qué año fue?: {e}")
        eventos = []
    return {"temas": temas, "preguntas": unicas, "mas_o_menos": datos_mas_o_menos(), "anio": eventos,
            "idolos": [_con_foto({k: i.get(k) for k in ("nombre", "apodo", "posicion", "pais", "debut", "libertadores",
                                                         "intercontinental")}) for i in idolos()]}


if __name__ == "__main__":
    d = armar()
    print({t: sum(1 for q in d["preguntas"] if q["tema"] == t) for t in TEMAS}, len(d["mas_o_menos"]), len(d["idolos"]))
