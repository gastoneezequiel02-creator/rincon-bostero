"""Páginas de los jugadores históricos de Boca (base de Historia de Boca, con permiso).

- Una ficha por cada jugador con al menos un partido oficial: jugadores/<slug>.html.
- Con menos de MIN_PJ_INDEXAR partidos la ficha es corta y lleva "noindex" (para no llenar Google de páginas casi vacías).
- Un índice con buscador y filtros: jugadores.html.
"""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict

import jugadores_hdb as jh
from comun import MESES, normalizar

e = html.escape
MIN_PJ_INDEXAR = 10
CARPETA = "jugadores"

GRUPOS_PUESTO = [
    ("Arquero", ("arquero", "guardameta")),
    ("Defensor", ("defensor", "marcador", "lateral", "zaguero", "back", "central", "líbero", "libero", "stopper")),
    ("Mediocampista", ("volante", "medio", "centrohalf", "centro half", "enganche", "insider", "mediocampista", "half")),
    ("Delantero", ("delantero", "puntero", "wing", "centrodelantero", "atacante", "centroforward", "forward", "extremo")),
]


def grupo_puesto(texto: str) -> str:
    t = normalizar(texto)
    for grupo, claves in GRUPOS_PUESTO:
        if any(normalizar(c) in t for c in claves):
            return grupo
    return ""


def _fecha(f: str) -> str:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", f or "")
    if not m:
        return ""
    return f"{int(m.group(1))} de {MESES[int(m.group(2)) - 1]} de {m.group(3)}"


_FICHAS: list[dict] | None = None


def fichas() -> list[dict]:
    """Los jugadores con al menos un partido oficial, con todo lo que muestran las páginas."""
    global _FICHAS
    if _FICHAS is not None:
        return _FICHAS
    todos = jh.jugadores()
    for i, j in todos.items():
        j["id"] = i
    usados, salida = set(), []
    for j in sorted(todos.values(), key=lambda x: -(x.get("pj") or 0)):
        if not (j.get("pj") or 0) or not j.get("n"):
            continue
        slug = j.get("s") or re.sub(r"[^a-z0-9]+", "-", normalizar(j["n"])).strip("-")
        if slug in usados:
            slug = f"{slug}-{j['id']}"
        usados.add(slug)
        anios = jh._anios_jugados(j)
        pu = jh.puesto(j)
        salida.append({**j, "slug": slug, "anios": anios, "puesto_txt": pu, "grupo": grupo_puesto(pu),
                       "etapa": jh._etapas(anios) if anios else "", "debut_anio": jh.anio(j.get("debut")),
                       "titulos": jh.titulos(j)[0]})
    _FICHAS = salida
    return salida


_INDICE: dict | None = None


def _variantes(nombre: str) -> list[str]:
    t = normalizar(nombre).replace(",", " ").split()
    return [" ".join(t)] + ([f"{t[0]} {t[-1]}"] if len(t) > 2 else [])


def url_jugador(nombre: str, pre: str = "") -> str | None:
    """Link a la ficha de un jugador a partir de su nombre ("Martín Palermo", "Palermo, Martín"). None si no hay
    una sola coincidencia."""
    global _INDICE
    if _INDICE is None:
        idx = defaultdict(set)
        for f in fichas():
            nombres = [f["n"]]
            an = f.get("an") or ""
            if "," in an:
                ap, no = an.split(",", 1)
                nombres.append(f"{no.strip()} {ap.strip()}")
                nombres.append(f"{no.strip().split()[0] if no.strip() else ''} {ap.strip()}")
            for n in nombres:
                for v in _variantes(n):
                    idx[v].add(f["slug"])
        _INDICE = idx
    if "," in nombre:
        ap, no = nombre.split(",", 1)
        nombre = f"{no.strip()} {ap.strip()}"
    for v in _variantes(nombre):
        s = _INDICE.get(v) or set()
        if len(s) == 1:
            return f"{pre}{CARPETA}/{next(iter(s))}.html"
    return None


def _foto(f: dict) -> dict | None:
    try:
        import imagenes
    except Exception:
        return None
    for n in [f["n"]] + _variantes(f["n"])[1:]:
        r = imagenes.foto_guardada(n)
        if r:
            return r
    return None


def pagina_ficha(f: dict, por_id: dict, pagina, franja, url_abs) -> str:
    pre = "../"
    j = f
    bio = jh.limpiar_bio(j.get("bio", ""))
    if bio and bio[-1] not in ".!?)»\"":
        bio += "…"  # la biografía viene cortada de la fuente
    url_hdb = f"https://historiadeboca.com.ar/jugadores/{j['s']}/{j['id']}/1905/2026/6.html" if j.get("s") else ""
    cifras = [(j["pj"], "partidos oficiales"), (j.get("gol") or 0, "goles")]
    if j.get("tit") is not None and j.get("pj"):
        cifras.append((j.get("tit") or 0, "como titular"))
    if j.get("min"):
        cifras.append((f'{j["min"]:,}'.replace(",", "."), "minutos"))
    if j.get("g") is not None and (j.get("g") or j.get("e") or j.get("p")):
        cifras.append((f'{j.get("g") or 0}-{j.get("e") or 0}-{j.get("p") or 0}', "ganados, empatados y perdidos"))
    if j["titulos"]:
        cifras.append((j["titulos"], "títulos con Boca" if j["titulos"] != 1 else "título con Boca"))
    cifras_html = "".join(f"<div><b>{e(str(v))}</b>{e(t)}</div>" for v, t in cifras)
    datos = []
    if j.get("puesto_txt"):
        datos.append(("Puesto", j["puesto_txt"][:1].upper() + j["puesto_txt"][1:]))
    if j.get("etapa"):
        datos.append(("En Boca", j["etapa"][:1].upper() + j["etapa"][1:]))
    if _fecha(j.get("debut")):
        datos.append(("Debut", _fecha(j["debut"])))
    if _fecha(j.get("desp")) and j.get("desp") != j.get("debut"):
        datos.append(("Último partido", _fecha(j["desp"])))
    nac = _fecha(j.get("nac"))
    lugar = j.get("ciu") or j.get("lugar") or ""
    if nac or lugar:
        datos.append(("Nacimiento", ", ".join(x for x in (nac, lugar) if x)))
    if _fecha(j.get("fall")):
        datos.append(("Fallecimiento", _fecha(j["fall"])))
    dor = sorted(j.get("dor") or [], key=lambda x: -x[1])
    if dor:
        datos.append(("Camiseta", ", ".join(f"{d[0]} ({d[1]} {'partido' if d[1] == 1 else 'partidos'})" for d in dor[:4])))
    datos_html = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in datos)
    tor = [t for t in j.get("tor") or [] if t[1]]
    tor_html = ""
    if tor:
        filas = "".join(f'<tr><td class="izq">{e(t[0])}</td><td>{t[1]}</td><td>{t[2]}</td></tr>' for t in tor)
        tabla = (f'<div class="tabla-scroll"><table><thead><tr><th class="izq">Torneo</th><th>PJ</th><th>Goles</th></tr></thead>'
                 f'<tbody>{filas}</tbody></table></div>')
        tor_html = (f'<section><h2 class="titulo-seccion">Torneo por torneo</h2>'
                    + (f'<details class="ficha-torneos"><summary>Ver los {len(tor)} torneos</summary>{tabla}</details>' if len(tor) > 12 else tabla)
                    + "</section>")
    comp = [por_id[c] for c in j.get("comp") or [] if c in por_id and c != j["id"]]
    comp_html = ""
    if comp:
        comp.sort(key=lambda x: -x["pj"])
        enlaces = "".join(f'<li><a href="{e(c["slug"])}.html">{e(c["n"])}</a> <small>{c["pj"]} PJ</small></li>' for c in comp[:16])
        comp_html = (f'<section><h2 class="titulo-seccion">Compañeros</h2><p class="nota-dato">Compartió cancha en partidos '
                     f'oficiales con {len(comp)} jugadores. Algunos de los que más jugaron en Boca:</p><ul class="ficha-companeros">{enlaces}</ul>'
                     f'<p class="nota-dato">¿Sabés quién jugó con quién? <a href="{pre}juegos.html#conexion">Jugá a ¿Quién jugó con quién?</a></p></section>')
    foto = _foto(j)
    foto_html = (f'<figure class="ficha-foto"><img src="{pre}{e(foto["imagen"])}" alt="{e(j["n"])}" loading="lazy">'
                 f'<figcaption>{e(foto.get("credito", ""))}</figcaption></figure>') if foto else ""
    corta = j["pj"] < MIN_PJ_INDEXAR
    ld = json.dumps({"@context": "https://schema.org", "@type": "Person", "name": j["n"],
                     "url": url_abs(f"{CARPETA}/{j['slug']}.html"),
                     "memberOf": {"@type": "SportsTeam", "name": "Boca Juniors"},
                     **({"birthDate": _iso(j.get("nac"))} if _iso(j.get("nac")) else {}),
                     **({"description": bio[:300]} if bio else {})}, ensure_ascii=False).replace("</", "<\\/")
    desc = (f"{j['n']}: {j['pj']} partidos oficiales y {j.get('gol') or 0} goles en Boca"
            + (f" ({j['etapa']})" if j.get("etapa") else "") + ". Debut, torneos, camisetas y compañeros.")
    cuerpo = f"""<nav class="miga"><a href="{pre}jugadores.html">Jugadores históricos</a></nav>
<article class="ficha-jugador">
<header class="ficha-cabeza">
  {foto_html}
  <div><h1>{e(j['n'])}</h1>
  <p class="ficha-sub">{e(" · ".join(x for x in (j.get("grupo"), j.get("etapa")) if x))}</p></div>
</header>
<div class="cifras-records">{cifras_html}</div>
<dl class="ficha-datos">{datos_html}</dl>
{f'<section><h2 class="titulo-seccion">Su historia en Boca</h2><p class="ficha-bio">{e(bio)}</p></section>' if bio else ''}
{'' if corta else tor_html}
{'' if corta else comp_html}
<p class="nota-dato">Partidos oficiales. Datos: Historia de Boca{f' (<a href="{e(url_hdb)}" rel="noopener">ver su ficha allá</a>)' if url_hdb else ""}.</p>
</article>
<script type="application/ld+json">{ld}</script>"""
    return pagina(j["n"], cuerpo, activa="jugadores.html", pre=pre, descripcion=desc,
                  imagen=foto["imagen"] if foto else "", franja=franja(pre), robots="noindex, follow" if corta else "")


def _iso(f: str) -> str:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", f or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def pagina_indice(pagina, franja) -> str:
    fs = fichas()
    filas = []
    for f in fs:
        dec = (f["debut_anio"] // 10 * 10) if f.get("debut_anio") else ""
        filas.append(f'<tr data-n="{e(normalizar(f["n"] + " " + (f.get("an") or "")))}" data-g="{e(f.get("grupo") or "")}" data-d="{dec}" '
                     f'data-pj="{f["pj"]}" data-gol="{f.get("gol") or 0}" data-a="{f.get("debut_anio") or 0}">'
                     f'<td class="izq"><a href="{CARPETA}/{e(f["slug"])}.html">{e(f["n"])}</a></td>'
                     f'<td class="izq">{e(f.get("grupo") or "")}</td><td class="izq">{e(f.get("etapa") or "")}</td>'
                     f'<td class="pts">{f["pj"]}</td><td>{f.get("gol") or 0}</td></tr>')
    decadas = sorted({f["debut_anio"] // 10 * 10 for f in fs if f.get("debut_anio")})
    op_dec = "".join(f'<option value="{d}">{"Primeros años" if d < 1910 else ("Años " + str(d)[2:]) if d < 2000 else str(d) + "-" + str(d + 9)}</option>'
                     for d in decadas)
    op_pos = "".join(f'<option value="{g}">{g}s</option>' for g, _c in GRUPOS_PUESTO)
    mas100 = sum(1 for f in fs if f["pj"] >= 100)
    cuerpo = f"""<header class="encabezado-pagina"><h1>Jugadores históricos</h1>
<p>Los {len(fs):,} jugadores que vistieron la camiseta de Boca en partidos oficiales desde 1905, con su ficha: partidos, goles, torneos, camisetas y compañeros.</p></header>
<div class="buscador-jugadores">
  <label class="oculto" for="bj-texto">Buscar jugador</label>
  <input id="bj-texto" type="search" placeholder="Buscá por nombre o apellido" autocomplete="off">
  <label class="oculto" for="bj-pos">Puesto</label><select id="bj-pos"><option value="">Todos los puestos</option>{op_pos}</select>
  <label class="oculto" for="bj-dec">Década</label><select id="bj-dec"><option value="">Todas las épocas</option>{op_dec}</select>
  <label class="oculto" for="bj-orden">Orden</label><select id="bj-orden"><option value="pj">Más partidos</option><option value="gol">Más goles</option><option value="a">Debut más reciente</option><option value="az">Alfabético</option></select>
</div>
<p class="nota-dato" id="bj-cuenta" aria-live="polite"></p>
<div class="tabla-scroll"><table class="tabla-jugadores"><thead><tr><th class="izq">Jugador</th><th class="izq">Puesto</th><th class="izq">En Boca</th><th>PJ</th><th>Goles</th></tr></thead>
<tbody id="bj-filas">{"".join(filas)}</tbody></table></div>
<p class="nota-dato"><button type="button" class="boton secundario" id="bj-mas" hidden>Ver más</button></p>
<p class="nota-dato">{mas100} jugadores tienen 100 partidos oficiales o más. Datos: Historia de Boca (partidos oficiales).</p>
<script>
(function () {{
  var filas = [].slice.call(document.querySelectorAll("#bj-filas tr")), tbody = document.getElementById("bj-filas");
  var txt = document.getElementById("bj-texto"), pos = document.getElementById("bj-pos"), dec = document.getElementById("bj-dec"), ord = document.getElementById("bj-orden");
  var cuenta = document.getElementById("bj-cuenta"), mas = document.getElementById("bj-mas"), limite = 100;
  function norm(s) {{ return (s || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().trim(); }}
  function pintar() {{
    var q = norm(txt.value), g = pos.value, d = dec.value, o = ord.value;
    var vis = filas.filter(function (f) {{
      return (!q || f.dataset.n.indexOf(q) >= 0) && (!g || f.dataset.g === g) && (!d || f.dataset.d === d);
    }});
    vis.sort(function (a, b) {{
      if (o === "az") return a.dataset.n < b.dataset.n ? -1 : 1;
      return (+b.dataset[o === "a" ? "a" : o]) - (+a.dataset[o === "a" ? "a" : o]);
    }});
    filas.forEach(function (f) {{ f.hidden = true; }});
    vis.forEach(function (f, i) {{ tbody.appendChild(f); f.hidden = i >= limite; }});
    cuenta.textContent = vis.length === 1 ? "1 jugador" : vis.length.toLocaleString("es-AR") + " jugadores";
    mas.hidden = vis.length <= limite;
  }}
  [txt, pos, dec, ord].forEach(function (el) {{ el.addEventListener(el === txt ? "input" : "change", function () {{ limite = 100; pintar(); }}); }});
  mas.addEventListener("click", function () {{ limite += 200; pintar(); }});
  pintar();
}})();
</script>"""
    return pagina("Jugadores históricos", cuerpo.replace(f"{len(fs):,}", f"{len(fs):,}".replace(",", ".")), activa="jugadores.html",
                  descripcion=f"Los {len(fs)} jugadores de la historia de Boca Juniors: partidos, goles, torneos y compañeros de cada uno.",
                  franja=franja(""))


def generar(escribir, salida, pagina, franja, url_abs) -> list[str]:
    """Escribe el índice y todas las fichas. Devuelve las direcciones para el sitemap (solo las fichas que se indexan)."""
    fs = fichas()
    if not fs:
        return []
    (salida / CARPETA).mkdir(exist_ok=True)
    por_id = {f["id"]: f for f in fs}
    escribir("jugadores.html", pagina_indice(pagina, franja))
    urls = []
    for f in fs:
        escribir(f"{CARPETA}/{f['slug']}.html", pagina_ficha(f, por_id, pagina, franja, url_abs))
        if f["pj"] >= MIN_PJ_INDEXAR:
            urls.append(f"{CARPETA}/{f['slug']}.html")
    return urls
