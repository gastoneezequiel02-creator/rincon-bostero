"""Arma la web completa (HTML estático) a partir de las notas y los datos guardados.

Resultado en la carpeta _sitio/, lista para subir a GitHub Pages, Cloudflare Pages o Netlify.
Uso:  python scripts/construir_sitio.py
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from comun import (DATOS_ESPN, DATOS_MANUAL, MESES, MESES_CORTOS as MESES_CORTOS_, RAIZ, SITIO, ahora, config, fecha_corta, fecha_larga, hace_cuanto, hora,
                   leer_json, listar_notas, log, parsear_fecha)

SALIDA = Path(os.environ.get("SALIDA_SITIO", RAIZ / "_sitio"))
DEMO = os.environ.get("DEMO") == "1"
e = html.escape

MENU = [("index.html", "Inicio"), ("noticias.html", "Noticias"), ("juegos.html", "Juegos"), ("fixture.html", "Fixture y posiciones"),
        ("historial.html", "Historial"), ("campanas.html", "Campañas"), ("records.html", "Récords"), ("efemerides.html", "Un día como hoy"),
        ("plantel.html", "Plantel")]
NOMBRE_ESTADO = {"oficial": "Oficial", "confirmado": "Confirmado", "rumor": "Rumor"}
NOMBRE_RES = {"G": "Ganó", "E": "Empató", "P": "Perdió"}


# ================================================================= piezas ==
def sitio() -> dict:
    return config()["sitio"]


def url_abs(ruta: str) -> str:
    return sitio()["url"].rstrip("/") + "/" + ruta.lstrip("/")


def hdb() -> dict:
    """Enlaces a Historia de Boca (historiadeboca.com.ar), si están activados."""
    h = config().get("historia_de_boca") or {}
    return h if h.get("activado") else {}




def bs_opciones() -> dict:
    o = config().get("bocastats") or {}
    return o if o.get("activado") else {}


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.replace(".", " ").split() if p[0].isalpha()]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


def escudo(eq: dict, chico: bool = False, es_boca: bool = False) -> str:
    clase = "escudo-chico" if chico else ""
    if eq.get("escudo"):
        return f'<img class="escudo {clase}" src="{e(eq["escudo"])}" alt="" loading="lazy" width="44" height="44">'
    b = " boca" if es_boca else ""
    return f'<span class="escudo-iniciales {clase}{b}" aria-hidden="true">{e(iniciales(eq.get("nombre", "?")))}</span>'


def tiempo(fecha_iso: str) -> str:
    d = parsear_fecha(fecha_iso)
    if not d:
        return ""
    return f'<time datetime="{e(d.isoformat())}" data-rel>{e(hace_cuanto(d))}</time>'


def badge(estado: str) -> str:
    estado = estado if estado in NOMBRE_ESTADO else "confirmado"
    return f'<span class="estado estado-{estado}">{NOMBRE_ESTADO[estado]}</span>'


def tapa(nota: dict, pre: str, grande: bool = False) -> str:
    if nota.get("imagen"):
        credito = nota.get("imagen_credito", "")
        titulo = f' title="{e(credito)}"' if credito else ""
        return (f'<div class="tapa"><img src="{pre}{e(nota["imagen"])}" alt=""{titulo} '
                f'loading="{"eager" if grande else "lazy"}"></div>')
    return f'<div class="tapa tapa-tipografica" aria-hidden="true"><span>{e(nota.get("categoria", "Boca"))}</span></div>'


def tapa_con_credito(nota: dict, pre: str) -> str:
    credito = nota.get("imagen_credito")
    if not credito:
        return tapa(nota, pre, grande=True)
    return f'<figure class="tapa-figura">{tapa(nota, pre, grande=True)}<figcaption>{e(credito)}</figcaption></figure>'


def link_nota(nota: dict, pre: str) -> str:
    return f'{pre}notas/{e(nota["slug"])}.html'


def cruce(p: dict, pre_goles: bool = True) -> str:
    """'Boca 2 - 1 Rival' respetando quién es local."""
    loc, vis = p["local"], p["visitante"]
    nl = "Boca" if p["condicion"] == "L" else loc["corto"]
    nv = "Boca" if p["condicion"] == "V" else vis["corto"]
    if p["estado"] == "finalizado" and loc.get("goles") is not None:
        medio = f'<span class="goles">{loc["goles"]} - {vis["goles"]}</span>'
    else:
        medio = '<span class="vs-chico">vs</span>'
    pen = ""
    if p.get("penales_boca") is not None:
        pen = f' <small>({p["penales_boca"]}-{p["penales_rival"]} pen.)</small>' if p["condicion"] == "L" else \
              f' <small>({p["penales_rival"]}-{p["penales_boca"]} pen.)</small>'
    return f"{e(nl)} {medio} {e(nv)}{pen}"


def cuando(p: dict, largo: bool = True) -> str:
    d = parsear_fecha(p["fecha"])
    if not d:
        return "Fecha a confirmar"
    f = fecha_larga(d) if largo else fecha_corta(d)
    return f + ("" if p.get("hora_a_confirmar") else f", {hora(d)} h")


# ================================================================ layout ==
def icono_html(pre: str) -> str:
    """Ícono de la pestaña: el logo si está cargado; si no, el ícono dibujado."""
    if (SITIO / "estatico" / "img" / "logo.webp").exists():
        return f'<link rel="icon" href="{pre}img/logo.webp" type="image/webp">'
    return f'<link rel="icon" href="{pre}estatico/icono.svg" type="image/svg+xml">'


def logo_html(pre: str) -> str:
    """El logo de Rincón Bostero si está en sitio/estatico/img/ (logo.png, .jpg, .webp o .svg); si no, un monograma."""
    for ext in ("svg", "png", "webp", "jpg", "jpeg"):
        if (SITIO / "estatico" / "img" / f"logo.{ext}").exists():
            return f'<img class="logo" src="{pre}img/logo.{ext}" alt="" width="60" height="60">'
    return '<span class="logo monograma" aria-hidden="true">RB</span>'


def pagina(titulo: str, cuerpo: str, *, activa: str = "", pre: str = "", descripcion: str = "",
           imagen: str = "", canonica: str = "", franja: str = "") -> str:
    s = sitio()
    titulo_completo = f"{titulo} | {s['nombre']}" if titulo != s["nombre"] else f"{s['nombre']}: {s['lema']}"
    desc = descripcion or s["lema"]
    menu = "".join(
        f'<a href="{pre}{href}"{" aria-current=page" if href == activa else ""}>{e(txt)}</a>' for href, txt in MENU)
    og_img = f'<meta property="og:image" content="{e(url_abs(imagen))}">' if imagen else ""
    fuentes = [x for x in (hdb().get("credito"), bs_opciones().get("credito")) if x]
    credito = f"<br>Datos históricos: {e(' y '.join(fuentes))}." if fuentes else ""
    demo = ('<div class="aviso-demo">Vista previa con datos de ejemplo: las notas, partidos y tablas no son reales.</div>'
            if DEMO else "")
    return f"""<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo_completo)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonica or url_abs(activa or ''))}">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:site_name" content="{e(s['nombre'])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@{e(s.get('twitter', ''))}">
{og_img}
<meta name="theme-color" content="#0b2a6f">
<link rel="alternate" type="application/rss+xml" title="{e(s['nombre'])}" href="{pre}feed.xml">
{icono_html(pre)}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{pre}estatico/estilos.css">
</head>
<body>
{demo}
<header class="cabecera">
  <div class="cabecera-top"><div class="envoltura">
    <a class="marca" href="{pre}index.html">{logo_html(pre)}<span class="marca-texto"><b>{e(s['nombre'])}</b><small>{e(s['lema'])}</small></span></a>
    <a class="cabecera-x" href="https://x.com/{e(s.get('twitter', ''))}" rel="noopener">@{e(s.get('twitter', ''))}<span class="oculto"> en X</span></a>
  </div></div>
  <div class="cabecera-menu"><div class="envoltura"><nav class="menu" aria-label="Secciones">{menu}</nav></div></div>
</header>
{franja}
<main class="envoltura" id="contenido">
{cuerpo}
</main>
<footer class="pie">
  <div class="envoltura">
    <div><strong>{e(s['nombre'])}</strong>Medio partidario de Boca Juniors. No es un sitio oficial del club.{credito}</div>
    <div>Seguinos en <a href="https://x.com/{e(s.get('twitter', ''))}">X (@{e(s.get('twitter', ''))})</a><br>
    <a href="{pre}feed.xml">Suscribite por RSS</a> o <a href="{pre}calendario.ics">agregá los partidos a tu calendario</a><br>
    <a href="{pre}privacidad.html">Privacidad</a></div>
  </div>
</footer>
<script src="{pre}estatico/app.js" defer></script>
</body>
</html>"""


def barra_franja(proximos: list[dict], pre: str) -> str:
    if not proximos:
        return ""
    p = proximos[0]
    d = parsear_fecha(p["fecha"])
    local = "Boca" if p["condicion"] == "L" else p["local"]["nombre"]
    visita = "Boca" if p["condicion"] == "V" else p["visitante"]["nombre"]
    donde = f" en {e(p['estadio'])}" if p.get("estadio") else ""
    en_vivo = p["estado"] == "en_juego"
    cuenta = (f'<div class="franja-cuenta"><span>En juego</span><small>{e(p.get("detalle", ""))}</small></div>' if en_vivo else
              f'<div class="franja-cuenta" data-cuenta="{e(d.isoformat())}"><span data-num></span><small></small></div>')
    return f"""<section class="franja" aria-label="Próximo partido">
  <div class="envoltura">
    <p class="franja-que">{"Ahora" if en_vivo else "Próximo partido"}<b>{e(local)} vs {e(visita)}</b></p>
    <p class="franja-cuando">{e(p['competencia'])}{(' (' + e(p['instancia']) + ')') if p.get('instancia') else ''}.
      {e(cuando(p))}{donde}. <a href="{pre}fixture.html">Ver fixture completo</a></p>
    {cuenta}
  </div>
</section>"""


# ================================================================ páginas ==
def item_lista(n: dict, pre: str) -> str:
    return f"""<li data-grupo="{e(n.get('categoria', ''))}">
  <a href="{link_nota(n, pre)}">{tapa(n, pre)}</a>
  <div>
    <div class="meta"><span class="categoria">{e(n.get('categoria', ''))}</span>{tiempo(n['fecha'])}</div>
    <a href="{link_nota(n, pre)}"><h3>{e(n['titulo'])}</h3></a>
    {badge(n.get('estado', ''))}
  </div>
</li>"""


def fila_partido(p: dict, *, resultado: bool) -> str:
    d = parsear_fecha(p["fecha"])
    fecha = f"{fecha_corta(d)}<small>{'' if p.get('hora_a_confirmar') or resultado else hora(d) + ' h'}" \
            f"{d.year if resultado else ''}</small>" if d else "A confirmar"
    sub = e(p["competencia"]) + (f" ({e(p['instancia'])})" if p.get("instancia") else "")
    if not resultado and p.get("estadio"):
        sub += f". {e(p['estadio'])}"
    if p["estado"] == "postergado":
        sub += ". Postergado"
    derecha = (f'<span class="lp-res r-{p["resultado"]}" title="{NOMBRE_RES[p["resultado"]]}">{p["resultado"]}</span>'
               if resultado and p.get("resultado") else escudo(p["rival"], chico=True))
    return f"""<li data-grupo="{e(p['competencia_slug'])}">
  <span class="lp-fecha">{fecha}</span>
  <span><span class="lp-cruce">{cruce(p)}</span><span class="lp-sub">{sub}</span></span>
  {derecha}
</li>"""


def mini_tabla(tablas: dict, pre: str) -> str:
    for slug, t in tablas.items():
        for g in t["grupos"]:
            if not any(f.get("es_boca") for f in g["filas"]):
                continue
            filas = g["filas"]
            i_boca = next(i for i, f in enumerate(filas) if f.get("es_boca"))
            visibles = filas[:6] if i_boca < 6 else filas[:3] + filas[i_boca - 1:i_boca + 2]
            cuerpo = "".join(
                f'<tr class="{"fila-boca" if f.get("es_boca") else ""}"><td>{f.get("pos", "")}</td>'
                f'<td class="equipo izq">{escudo({"nombre": f["equipo"], "escudo": f.get("escudo")}, True, f.get("es_boca"))}'
                f'{e(f.get("corto") or f["equipo"])}</td><td>{f.get("pj", "")}</td><td class="pts">{f.get("pts", "")}</td></tr>'
                for f in visibles)
            nombre_grupo = f'{t["nombre"]}' + (f' ({g["nombre"]})' if g["nombre"] != t["nombre"] else "")
            return f"""<section>
  <h2 class="titulo-seccion">Posiciones <a href="{pre}fixture.html#{id_comp(slug)}">Ver tabla</a></h2>
  <p class="nota-dato">{e(nombre_grupo)}</p>
  <table class="tabla-mini"><thead><tr><th>#</th><th class="izq">Equipo</th><th>PJ</th><th>Pts</th></tr></thead>
  <tbody>{cuerpo}</tbody></table>
</section>"""
    return ""


def pagina_inicio(notas, proximos, jugados, tablas) -> str:
    pre = ""
    if notas:
        n = notas[0]
        principal = f"""<article class="principal">
  <a href="{link_nota(n, pre)}">{tapa(n, pre, grande=True)}
    <h2>{e(n['titulo'])}</h2></a>
  <p>{e(n.get('bajada', ''))}</p>
  <div class="meta">{badge(n.get('estado', ''))}<span class="categoria">{e(n.get('categoria', ''))}</span>{tiempo(n['fecha'])}</div>
</article>
<ul class="listado">{''.join(item_lista(x, pre) for x in notas[1:11])}</ul>
<p style="margin-top:28px"><a class="boton secundario" href="noticias.html">Ver todas las noticias</a></p>"""
    else:
        principal = '<div class="vacio">Estamos cargando las noticias: en unos minutos aparecen las primeras.</div>'

    lateral = []
    if jugados:
        u = jugados[0]
        lateral.append(f"""<section class="partido-grande">
  <h2 class="titulo-seccion">Último resultado</h2>
  <p class="comp">{e(u['competencia'])}. {e(cuando(u))}</p>
  <div class="enfrentamiento">
    <div class="eq">{escudo(u['local'], es_boca=u['condicion'] == 'L')}{e(u['local']['corto'])}</div>
    <div class="vs">{u['local']['goles']} - {u['visitante']['goles']}</div>
    <div class="eq">{escudo(u['visitante'], es_boca=u['condicion'] == 'V')}{e(u['visitante']['corto'])}</div>
  </div>
  <p class="donde">{e(u.get('estadio', ''))}</p>
</section>""")
        dia_n = (ahora().date() - __import__("datetime").date(2026, 11, 18)).days + 1
        hs = hincha_semana()
        hincha = ""
        if hs.get("ganadores"):
            nombres = " y ".join(f"<b>{e(g['apodo'])}</b>" for g in hs["ganadores"])
            pts = hs["ganadores"][0]["puntos"]
            hincha = (f'<p class="hincha-semana"><span>Hincha de la semana</span>{nombres}, con {pts} puntos. '
                      f'<a href="juegos.html#ranking">Ver ranking</a></p>')
        lateral.append(f"""<section class="invitacion-juego"><h2 class="titulo-seccion">Pregunta del día #{dia_n}</h2>
<p>10 preguntas sobre la historia de Boca, las mismas para todos. ¿Cuántas sacás?</p>
<a class="boton" href="juegos.html#del-dia">Jugar</a>{hincha}</section>""")
        forma = "".join(f'<li class="r-{p["resultado"]}" title="{NOMBRE_RES[p["resultado"]]} {p["goles_boca"]}-{p["goles_rival"]} '
                        f'vs {e(p["rival"]["nombre"])}">{p["resultado"]}</li>' for p in jugados[:5][::-1] if p.get("resultado"))
        lateral.append(f"""<section><h2 class="titulo-seccion">Cómo viene Boca</h2>
  <ul class="forma" aria-label="Últimos 5 resultados, del más viejo al más nuevo">{forma}</ul>
  <p class="nota-dato">Últimos cinco partidos, el más reciente a la derecha.</p></section>""")
    if len(proximos) > 1:
        filas = "".join(fila_partido(p, resultado=False) for p in proximos[1:4])
        lateral.append(f'<section><h2 class="titulo-seccion">Lo que viene <a href="fixture.html">Fixture</a></h2>'
                       f'<ul class="lista-partidos">{filas}</ul></section>')
    lateral.append(mini_tabla(tablas, pre))
    hoy = ahora()
    items = []
    if hdb():
        import historia_de_boca
        items = [{"anio": x["anio"], "titulo": x["titulo"]} for x in historia_de_boca.efemerides_del_dia(hoy.month, hoy.day)]
    if not items and bs_opciones():
        # sin efemérides guardadas para hoy: partidos oficiales jugados un día como hoy (BocaStats)
        import bocastats
        del_dia = [x for x in bocastats.todos_los_partidos()
                   if not x["amistoso"] and x["fecha"][5:10] == f"{hoy.month:02d}-{hoy.day:02d}" and x["fecha"][:4] < str(hoy.year)]
        del_dia.sort(key=lambda x: (-abs(x["goles_boca"] - x["goles_rival"]), x["fecha"]))
        for x in sorted(del_dia[:5], key=lambda x: x["fecha"]):
            verbo = {"G": "le ganó a", "E": "empató con", "P": "perdió con"}[x["resultado"]]
            items.append({"anio": int(x["fecha"][:4]),
                          "titulo": f'Boca {verbo} {x["rival"]} {x["goles_boca"]}-{x["goles_rival"]} ({x["torneo"]})'})
    if items:
        lista = "".join(f'<li><b>{x["anio"]}</b><span>{e(x["titulo"])}</span></li>' for x in items[:5])
        lateral.append(f"""<section class="efemeride"><h2 class="titulo-seccion">Un día como hoy <a href="efemerides.html">Ver todas</a></h2>
<ul class="efemerides">{lista}</ul></section>""")

    cuerpo = f"""<div class="portada">
<div><h1 class="oculto">Últimas noticias de Boca</h1>{principal}</div>
<aside class="columna-lateral">{''.join(lateral)}</aside>
</div>"""
    return pagina(sitio()["nombre"], cuerpo, activa="index.html", franja=barra_franja(proximos, pre))


def pagina_nota(n: dict, relacionadas: list[dict], proximos) -> str:
    pre = "../"
    d = parsear_fecha(n["fecha"])
    cuerpo_txt = "".join(f"<p>{e(p)}</p>" for p in n["cuerpo"])
    aviso = ('<p class="aviso-rumor"><b>Esto es un rumor.</b> La información todavía no está confirmada '
             'por el club ni por los protagonistas.</p>' if n.get("estado") == "rumor" else "")
    fuentes = ""
    if n.get("fuentes"):
        lista = ", ".join(f'<a href="{e(f["url"])}" rel="nofollow noopener" target="_blank">{e(f["nombre"])}</a>'
                          if f.get("url") else e(f["nombre"]) for f in n["fuentes"])
        fuentes = f'<p class="fuentes">Con información de {lista}.</p>'
    url = url_abs(f"notas/{n['slug']}.html")
    compartir = f"""<div class="compartir">
  <a class="boton" href="https://wa.me/?text={e(quote(n['titulo'] + ' ' + url))}" target="_blank" rel="noopener">Compartir por WhatsApp</a>
  <a class="boton secundario" href="https://x.com/intent/post?text={e(quote(n['titulo']))}&amp;url={e(quote(url))}&amp;via={e(sitio().get('twitter', ''))}" target="_blank" rel="noopener">Compartir en X</a>
</div>"""
    etiquetas = ("<ul class='etiquetas'>" + "".join(f"<li>{e(t)}</li>" for t in n.get("etiquetas", [])) + "</ul>"
                 if n.get("etiquetas") else "")
    rel = ""
    if relacionadas:
        rel = ('<section style="margin-top:48px"><h2 class="titulo-seccion">Más noticias</h2><ul class="listado">'
               + "".join(item_lista(x, pre) for x in relacionadas[:4]) + "</ul></section>")
    ld = json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "headline": n["titulo"],
                     "datePublished": n["fecha"], "description": n.get("bajada", ""),
                     "publisher": {"@type": "Organization", "name": sitio()["nombre"]}}, ensure_ascii=False)
    cuerpo = f"""<article class="nota">
  <div class="meta">{badge(n.get('estado', ''))}<a class="categoria" href="../noticias.html">{e(n.get('categoria', ''))}</a>
    <time datetime="{e(n['fecha'])}">{e(fecha_larga(d))}, {hora(d)} h</time></div>
  <h1>{e(n['titulo'])}</h1>
  <p class="bajada">{e(n.get('bajada', ''))}</p>
  {tapa_con_credito(n, pre) if n.get('imagen') else ''}
  {aviso}
  <div class="cuerpo">{cuerpo_txt}</div>
  {etiquetas}
  {fuentes}
  {compartir}
</article>
{rel}
<script type="application/ld+json">{ld}</script>"""
    return pagina(n["titulo"], cuerpo, pre=pre, descripcion=n.get("bajada", ""), imagen=n.get("imagen", ""),
                  canonica=url, franja=barra_franja(proximos, pre))


def pagina_noticias(notas, proximos) -> str:
    cats = sorted({n.get("categoria", "") for n in notas if n.get("categoria")})
    botones = '<button data-valor="todos" aria-pressed="true">Todas</button>' + "".join(
        f'<button data-valor="{e(c)}" aria-pressed="false">{e(c)}</button>' for c in cats)
    lista = "".join(item_lista(n, "") for n in notas) or '<div class="vacio">Todavía no hay notas.</div>'
    cuerpo = f"""<header class="encabezado-pagina"><h1>Noticias</h1><p>Todo lo que pasa en Boca: primera, mercado de pases, juveniles y el club.</p></header>
<div class="filtros" data-filtra="#todas" role="group" aria-label="Filtrar por sección">{botones}</div>
<ul class="listado" id="todas">{lista}</ul>"""
    return pagina("Noticias", cuerpo, activa="noticias.html", franja=barra_franja(proximos, ""))


def botones_competencias(partidos) -> str:
    comps = {}
    for p in partidos:
        comps.setdefault(p["competencia_slug"], p["competencia"])
    return '<button data-valor="todos" aria-pressed="true">Todas</button>' + "".join(
        f'<button data-valor="{e(s)}" aria-pressed="false">{e(n)}</button>' for s, n in comps.items())


def id_comp(slug: str) -> str:
    return slug.replace(".", "-")


def bloque_resultados(jugados: list[dict], id_sec: str) -> str:
    por_anio = defaultdict(list)
    for p in jugados:
        por_anio[p.get("temporada") or "?"].append(p)
    anios = sorted(por_anio, key=lambda x: str(x), reverse=True)
    bloques = ""
    for n, anio in enumerate(anios):
        ps = por_anio[anio]
        g = sum(1 for p in ps if p["resultado"] == "G")
        em = sum(1 for p in ps if p["resultado"] == "E")
        pe = sum(1 for p in ps if p["resultado"] == "P")
        bloques += (f'<div data-temporada="{e(str(anio))}"{" hidden" if n else ""}>'
                    f'<p class="nota-dato">{e(str(anio))}: {len(ps)} partidos, {g} ganados, {em} empatados, {pe} perdidos.</p>'
                    f'<ul class="lista-partidos">{"".join(fila_partido(p, resultado=True) for p in ps)}</ul></div>')
    selector = ""
    if len(anios) > 1:
        opciones = "".join(f'<option value="{e(str(a))}">{e(str(a))}</option>' for a in anios)
        selector = (f'<label for="temp-{id_sec}" class="oculto">Temporada</label>'
                    f'<select id="temp-{id_sec}" class="selector-chico" data-temporadas>{opciones}</select>')
    return (f'<h3 class="titulo-seccion">Resultados {selector}</h3>'
            + (bloques or '<div class="vacio">Todavía no hay resultados en esta competencia.</div>'))


def pagina_fixture(proximos, jugados, tablas) -> str:
    comps = []
    for c in config()["datos_futbol"]["competencias"]:
        pr = [p for p in proximos if p["competencia_slug"] == c["slug"]]
        ju = [p for p in jugados if p["competencia_slug"] == c["slug"]]
        tabla = tablas.get(c["slug"])
        if pr or ju or tabla:
            comps.append((c, pr, ju, tabla))
    # competencias que no están en config.json pero aparecen en los datos
    conocidas = {c["slug"] for c, *_ in comps}
    for slug in dict.fromkeys(p["competencia_slug"] for p in proximos + jugados):
        if slug not in conocidas:
            nombre = next(p["competencia"] for p in proximos + jugados if p["competencia_slug"] == slug)
            comps.append(({"slug": slug, "nombre": nombre},
                          [p for p in proximos if p["competencia_slug"] == slug],
                          [p for p in jugados if p["competencia_slug"] == slug], None))

    activa = proximos[0]["competencia_slug"] if proximos else (comps[0][0]["slug"] if comps else "")
    pestanas = "".join(
        f'<button type="button" data-destino="{id_comp(c["slug"])}" aria-pressed="{"true" if c["slug"] == activa else "false"}">'
        f'{e(c["nombre"])}</button>' for c, *_ in comps)

    secciones = ""
    for c, pr, ju, tabla in comps:
        ids = id_comp(c["slug"])
        prox = (f'<ul class="lista-partidos">{"".join(fila_partido(p, resultado=False) for p in pr)}</ul>' if pr else
                '<p class="vacio">No hay partidos programados por ahora en esta competencia.</p>')
        bloque_tabla = ""
        if tabla:
            grupos = sorted(tabla["grupos"], key=lambda g: not any(f.get("es_boca") for f in g["filas"]))
            for g in grupos:
                nombre_g = g["nombre"] if g["nombre"] and g["nombre"] != tabla["nombre"] else ""
                es_de_boca = any(f.get("es_boca") for f in g["filas"])
                if es_de_boca or len(grupos) <= 2:
                    bloque_tabla += (f'<h4 class="subtitulo-tabla">{e(nombre_g) or "Tabla"}</h4>{tabla_completa(g)}')
                else:
                    bloque_tabla += (f'<details class="otro-grupo"><summary>{e(nombre_g)}</summary>{tabla_completa(g)}</details>')
            bloque_tabla = f'<h3 class="titulo-seccion">Posiciones</h3>{bloque_tabla}'
        secciones += f"""<section class="competencia" data-pestana-id="{ids}">
<h2 class="nombre-competencia">{e(c['nombre'])}</h2>
<h3 class="titulo-seccion">Próximos partidos</h3>
{prox}
{bloque_tabla}
{bloque_resultados(ju, ids)}
</section>"""

    cuerpo = f"""<header class="encabezado-pagina"><h1>Fixture y posiciones</h1>
<p>Los partidos, la tabla y los resultados de Boca en cada competencia. Los horarios están en hora argentina.
<a href="calendario.ics">Agregá el fixture a tu calendario</a> y se actualiza solo.</p></header>
<div class="filtros pestanas" role="group" aria-label="Competencias" data-pestanas>{pestanas}</div>
{secciones or '<div class="vacio">Todavía no hay partidos cargados.</div>'}"""
    return pagina("Fixture y posiciones", cuerpo, activa="fixture.html", franja=barra_franja(proximos, ""))


def tabla_completa(g: dict) -> str:
    filas = "".join(
        f'<tr class="{"fila-boca" if f.get("es_boca") else ""}"><td>{f.get("pos", "")}</td>'
        f'<td class="equipo izq">{escudo({"nombre": f["equipo"], "escudo": f.get("escudo")}, True, f.get("es_boca"))}{e(f["equipo"])}</td>'
        + "".join(f"<td>{f.get(k, '')}</td>" for k in ("pj", "g", "e", "p", "gf", "gc", "dg"))
        + f'<td class="pts">{f.get("pts", "")}</td></tr>' for f in g["filas"])
    return f"""<div class="tabla-scroll"><table>
<thead><tr><th>#</th><th class="izq">Equipo</th><th title="Partidos jugados">PJ</th><th title="Ganados">G</th>
<th title="Empatados">E</th><th title="Perdidos">P</th><th title="Goles a favor">GF</th><th title="Goles en contra">GC</th>
<th title="Diferencia de gol">DG</th><th title="Puntos">Pts</th></tr></thead><tbody>{filas}</tbody></table></div>"""


def _fecha_txt(iso: str) -> str:
    d = parsear_fecha(iso[:10] + "T12:00:00-03:00")
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}" if d else iso


def _bloque(titulo, pj, g, e_, p, gf=None, gc=None, nota="") -> dict:
    return {"titulo": titulo, "pj": pj, "g": g, "e": e_, "p": p, "gf": gf, "gc": gc, "nota": nota}


def datos_historial(historial: dict, partidos: list[dict]) -> tuple[dict, dict]:
    """Arma, para cada rival, los bloques de cifras y la lista de partidos (de todas las fuentes)."""
    import bocastats
    import historia_de_boca
    usar_bs = bool(bocastats.opciones())
    rivales_bs = {r["slug"]: r for r in bocastats.rivales()} if usar_bs else {}
    espn_por_clave = {}
    for h in historial.values():
        slug = bocastats.slug_de(h["rival"]["nombre"]) if usar_bs else None
        espn_por_clave[slug or f"e{h['rival']['id']}"] = h
    claves = list(dict.fromkeys(list(rivales_bs) + list(espn_por_clave)))

    resumen, listas = {}, {}
    for clave in claves:
        h = espn_por_clave.get(clave)
        bs = rivales_bs.get(clave)
        nombre = bocastats.nombre_lindo(clave, bs["nombre"]) if bs else h["rival"]["nombre"]
        corto = nombre if len(nombre) <= 16 else (h["rival"]["corto"] if h else nombre.split(" (")[0])
        bloques = []
        # 1) oficiales partido a partido (BocaStats) + lo jugado después según ESPN
        lista = []
        importados = bocastats.partidos_de(clave) if bs else []
        if importados:
            ultimo = importados[-1]["fecha"]
            lista = [{"fecha": x["fecha"], "competencia": "Amistoso" if x["amistoso"] else x["torneo"],
                      "condicion": x["condicion"], "goles_boca": x["goles_boca"], "goles_rival": x["goles_rival"],
                      "resultado": x["resultado"], "amistoso": x["amistoso"]} for x in importados]
            if h:
                for x in h["partidos"]:
                    if (x["fecha"] or "")[:10] > ultimo:
                        lista.append({**{k: x[k] for k in ("competencia", "condicion", "goles_boca", "goles_rival",
                                                         "penales_boca", "penales_rival", "resultado")},
                                      "fecha": x["fecha"][:10], "amistoso": False})
            of = [x for x in lista if not x["amistoso"]]
            if of:
                bloques.append(_bloque(
                    "Partidos oficiales", len(of), *(sum(1 for x in of if x["resultado"] == r) for r in "GEP"),
                    sum(x["goles_boca"] for x in of), sum(x["goles_rival"] for x in of),
                    f"Todas las competencias oficiales desde {of[0]['fecha'][:4]}. Datos históricos: BocaStats."))
        # 2) campeonatos de liga (Historia de Boca)
        if hdb():
            rival_ref = h["rival"] if h else {"id": None, "nombre": nombre}
            t = historia_de_boca.total_actualizado(rival_ref, partidos) or (
                historia_de_boca.total_actualizado({"id": None, "nombre": nombre}, partidos) if h else None)
            if t:
                extra = f" y {t['sumados']} partidos de liga posteriores" if t.get("sumados") else ""
                bloques.append(_bloque("En campeonatos de liga", t["pj"], t["g"], t["e"], t["p"], t["gf"], t["gc"],
                                       f"Campeonatos de liga de AFA desde el amateurismo. Datos históricos: Historia de Boca, "
                                       f"hasta el {_fecha_txt(t['hasta'])}{extra}."))
                if not lista:
                    imp = historia_de_boca.historial_importado(nombre) or (
                        historia_de_boca.historial_importado(h["rival"]["nombre"]) if h else None)
                    if imp:
                        lista = [{"fecha": x["fecha"], "competencia": x["torneo"], "condicion": x["condicion"],
                                  "goles_boca": x["goles_boca"], "goles_rival": x["goles_rival"],
                                  "resultado": x["resultado"], "amistoso": False} for x in imp.get("partidos", [])]
        # 3) desde 2010 en todas las competencias (ESPN)
        if h:
            bloques.append(_bloque(f"Desde {h['desde']}", h["pj"], h["g"], h["e"], h["p"], h["gf"], h["gc"],
                                   f"Partidos oficiales desde {h['desde']}, actualizados después de cada partido."))
            fechas = {x["fecha"][:10] for x in lista}
            for x in h["partidos"]:
                if (x["fecha"] or "")[:10] not in fechas:
                    lista.append({**{k: x[k] for k in ("competencia", "condicion", "goles_boca", "goles_rival",
                                                     "penales_boca", "penales_rival", "resultado")},
                                  "fecha": x["fecha"][:10], "amistoso": False})
        # 4) dato extra: todos los partidos, con amistosos (índice de BocaStats)
        if bs:
            con_amistosos = [x for x in lista if x.get("amistoso")]
            bloques.append(_bloque("Dato extra: contando amistosos", bs["pj"], bs["g"], bs["e"], bs["p"],
                                   nota="Todos los partidos, incluidos amistosos y la era amateur. Datos históricos: BocaStats."))
        if not bloques:
            continue
        lista.sort(key=lambda x: x["fecha"], reverse=True)
        resumen[clave] = {"nombre": nombre, "corto": corto, "bloques": bloques, "n": len(lista),
                          "orden": max(b["pj"] for b in bloques)}
        listas[clave] = lista
    return resumen, listas


def pagina_historial(resumen: dict, proximos) -> str:
    if not resumen:
        cuerpo = ('<header class="encabezado-pagina"><h1>Historial</h1></header>'
                  '<div class="vacio">El historial se arma solo a medida que se bajan los resultados.</div>')
        return pagina("Historial", cuerpo, activa="historial.html", franja=barra_franja(proximos, ""))
    orden = sorted(resumen, key=lambda k: (-resumen[k]["orden"], resumen[k]["nombre"]))
    opciones = "".join(f'<option value="{e(k)}">{e(resumen[k]["nombre"])} ({resumen[k]["orden"]})</option>' for k in orden)
    datos_json = json.dumps(resumen, ensure_ascii=False).replace("</", "<\\/")
    cuerpo = f"""<header class="encabezado-pagina"><h1>Historial contra cada rival</h1>
<p>Los {len(resumen)} rivales que enfrentó Boca desde 1905, con todos los partidos. Elegí un rival
(entre paréntesis, cuántas veces se enfrentaron).</p></header>
<div class="filtros"><label class="oculto" for="rival">Rival</label><select id="rival" class="selector-rival">{opciones}</select></div>
<div id="historial-resultado"></div>
<script type="application/json" id="datos-historial">{datos_json}</script>"""
    return pagina("Historial", cuerpo, activa="historial.html", franja=barra_franja(proximos, ""))


def _es_final(instancia: str) -> bool:
    from comun import normalizar
    n = normalizar(instancia)
    return "final" in n and not any(x in n for x in ("semi", "cuartos", "octavos", "avos", "de final"))


def resultado_campana(partidos: list[dict], tabla: dict | None) -> tuple[str, str]:
    """Devuelve (texto del resultado, clase) para una campaña: posición en la tabla o instancia alcanzada."""
    partidos = sorted(partidos, key=lambda p: p["fecha"] or "")
    finales = [p for p in partidos if _es_final(p.get("instancia", ""))]
    if finales:
        gb = sum(p["goles_boca"] for p in finales)
        gr = sum(p["goles_rival"] for p in finales)
        ultimo = finales[-1]
        gano = gb > gr or (gb == gr and (ultimo.get("penales_boca") or 0) > (ultimo.get("penales_rival") or 0))
        return ("Campeón", "campeon") if gano else ("Subcampeón", "sub")
    if tabla and tabla.get("pos"):
        grupo = f' en {tabla["grupo"]}' if tabla.get("grupo") and tabla["grupo"] != tabla.get("competencia") else ""
        texto = f'{tabla["pos"]}° de {tabla["equipos"]}{grupo}'
        instancia = partidos[-1].get("instancia", "") if partidos else ""
        if instancia and not instancia.lower().startswith(("grupo", "fase de grupos", "fecha")):
            texto += f'. Llegó a {instancia.split(",")[0].lower()}'
        return texto, ""
    if partidos and partidos[-1].get("instancia"):
        return f'Llegó a {partidos[-1]["instancia"].split(",")[0].lower()}', ""
    return "", ""


# Familias de competencias (para filtrar y buscar en Campañas)
FAMILIAS = [
    ("liga", "Liga argentina", "liga argentina primera division campeonato torneo metropolitano nacional apertura clausura superliga liga profesional",
     r"campeonato|torneo|superliga|liga profesional|primera divisi|metropolitano|nacional|apertura|clausura|inicial|transici|liguilla|reducido|desempate|octogonal|hexagonal|temporada|final"),
    ("copa-liga", "Copa de la Liga", "copa de la liga profesional lpf superliga", r"copa (de la )?liga|copa superliga"),
    ("libertadores", "Copa Libertadores", "libertadores conmebol", r"libertadores(?!.*supercopa)"),
    ("sudamericana", "Copa Sudamericana", "sudamericana conmebol", r"(?<!super)copa sudamericana|copa conmebol sudamericana"),
    ("copa-argentina", "Copa Argentina", "copa argentina", r"copa (de )?argentina"),
    ("recopa", "Recopa Sudamericana", "recopa conmebol", r"recopa"),
    ("mundial", "Intercontinental y Mundial", "intercontinental mundial de clubes toyota fifa", r"intercontinental|mundial|toyota"),
    ("otras-conmebol", "Otras copas internacionales", "supercopa sudamericana copa de oro master conmebol rioplatense",
     r"supercopa (sudamericana|libertadores|joao)|copa de oro|master|conmebol|rioplatense|tie|aldao|ibarguren"),
    ("supercopa", "Supercopas y copas nacionales", "supercopa argentina trofeo de campeones copa de honor competencia escobar confraternidad",
     r"supercopa|trofeo|copa de honor|copa competencia|escobar|confraternidad|copa de competencia|copa ibarguren|copa adrian|copa británica"),
    ("ascenso", "Segunda División (1908-1912)", "segunda division intermedia ascenso copa bullrich", r"segunda divisi|bullrich|intermedia"),
    ("amistosos", "Amistosos", "amistoso amistosos", r"amistos"),
]
FAMILIA_ESPN = {"arg.1": "liga", "arg.copa_lpf": "copa-liga", "conmebol.libertadores": "libertadores",
                "conmebol.sudamericana": "sudamericana", "conmebol.recopa": "recopa", "arg.copa": "copa-argentina",
                "arg.supercopa": "supercopa", "fifa.cwc": "mundial"}


ORDEN_DETECCION = [
    ("amistosos", r"amistos"), ("ascenso", r"segunda divisi|bullrich|intermedia"), ("recopa", r"recopa"),
    ("otras-conmebol", r"supercopa (sudamericana|libertadores|joao)"), ("sudamericana", r"sudamericana"),
    ("libertadores", r"libertadores"), ("mundial", r"intercontinental|mundial|toyota"),
    ("copa-liga", r"copa (de la )?liga|copa superliga"),
    ("supercopa", r"supercopa|trofeo|copa de honor|competencia|escobar|confraternidad|ibarguren|adrian|britanica"),
    ("copa-argentina", r"copa (de )?argentina"),
    ("otras-conmebol", r"copa de oro|master|conmebol|rioplatense|\btie\b|aldao|mercosur|merconorte|iberoamericana|interamericana|atlantico"),
    ("liga", r"campeonato|torneo|superliga|liga profesional|primera divisi|metropolitano|nacional|apertura|clausura|"
             r"inicial|transici|liguilla|reducido|desempate|octogonal|hexagonal|temporada|finales"),
]


def familia_de(torneo: str) -> str:
    from comun import normalizar
    n = normalizar(torneo)
    for clave, patron in ORDEN_DETECCION:
        if re.search(patron, n):
            return clave
    return "supercopa"


def titulos_lista(palmares: dict) -> list[tuple[str, str, str]]:
    """[(categoría, título, año)] a partir de datos/manual/palmares.json."""
    salida = []
    for cat in palmares.get("categorias", []):
        for t in cat.get("titulos", []):
            m = re.search(r"(\d{4})", t)
            salida.append((cat["nombre"], t, m.group(1) if m else ""))
    return salida


def marcar_titulos(filas: list[dict], palmares: dict) -> None:
    """Marca como 'Campeón' la campaña que corresponde a cada título del palmarés."""
    from comun import normalizar
    vacias = {"de", "la", "del", "y", "copa", "torneo", "campeonato", "primera", "division", "argentina", "argentino", "liga"}
    for _, titulo, anio in titulos_lista(palmares):
        if not anio:
            continue
        if re.search(r"(?i)tabla anual|campe[oó]n de liga", titulo):
            # título por tabla anual: suma de los torneos de liga de ese año
            anual = [f for f in filas if f["fam"] == "liga" and f["anio"] == anio and f["nombre"].lower().startswith("tabla anual")]
            if anual:
                anual[0]["res"], anual[0]["clase"] = "Campeón", "campeon"
                continue
            del_anio = [f for f in filas if f["fam"] == "liga" and f["anio"] == anio]
            if len(del_anio) == 1:
                del_anio[0]["res"], del_anio[0]["clase"] = "Campeón (tabla anual)", "campeon"
            elif del_anio and not any(f["nombre"].lower().startswith("tabla anual") for f in filas):
                filas.append(dict(anio=anio, fam="liga", nombre="Tabla anual (Campeón de Liga)", res="Campeón", clase="campeon",
                                  pj=sum(f["pj"] for f in del_anio),
                                  c={k: sum(f["c"][k] for f in del_anio) for k in "gep"},
                                  gf=sum(f["gf"] for f in del_anio), gc=sum(f["gc"] for f in del_anio)))
            continue
        fam = familia_de(titulo)
        palabras = set(re.findall(r"[a-z]+", normalizar(titulo))) - vacias
        candidatas = []
        for f in filas:
            if f["fam"] != fam or not f["anio"].isdigit() or abs(int(f["anio"]) - int(anio)) > 1:
                continue
            propias = set(re.findall(r"[a-z]+", normalizar(f["nombre"]))) - vacias
            candidatas.append((len(palabras & propias), int(f["anio"]) == int(anio), -len(propias - palabras), f))
        if not candidatas:
            continue
        if len(candidatas) > 1:
            candidatas.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
            primero, segundo = candidatas[0], candidatas[1]
            if (primero[0], primero[1], primero[2]) == (segundo[0], segundo[1], segundo[2]):
                continue  # ambiguo: mejor no marcar nada
        candidatas[0][3]["res"], candidatas[0][3]["clase"] = "Campeón", "campeon"


def bloque_titulos(palmares: dict) -> str:
    lista = titulos_lista(palmares)
    if not lista:
        return ""
    por_cat = defaultdict(list)
    for cat, titulo, anio in lista:
        por_cat[cat].append((titulo, anio))
    cats = "".join(
        f'<details class="cat-titulos"><summary><b>{len(ts)}</b> {e(cat)}</summary>'
        f'<ul>{"".join(f"<li>{e(t)}</li>" for t, _ in sorted(ts, key=lambda x: x[1]))}</ul></details>'
        for cat, ts in por_cat.items())
    ultimo = max(lista, key=lambda x: x[2])
    fuente = f'<p class="nota-dato">Títulos oficiales. Fuente: {e(palmares["fuente"])}.</p>' if palmares.get("fuente") else ""
    return f"""<section class="titulos"><h2 class="titulo-seccion">Títulos</h2>
<div class="titulos-total"><b>{len(lista)}</b><span>títulos oficiales. El último: {e(ultimo[1])}.</span></div>
<div class="titulos-cats">{cats}</div>{fuente}</section>"""


def pagina_campanas(temporadas: dict, jugados: list[dict], palmares: dict, proximos) -> str:
    from comun import normalizar
    import bocastats
    nombres_fam = {c: n for c, n, _, _ in FAMILIAS}
    alias_fam = {c: al for c, _, al, _ in FAMILIAS}
    orden_fam = [c for c, *_ in FAMILIAS]

    # 1) campañas según ESPN (desde 2010, con posición o instancia)
    grupos_espn = defaultdict(list)
    for p in jugados:
        if p.get("resultado") and p.get("temporada"):
            grupos_espn[(p["competencia_slug"], str(p["temporada"]))].append(p)
    for anio, torneos in temporadas.items():
        for slug in torneos:
            grupos_espn.setdefault((slug, str(anio)), [])
    espn = {}
    for (slug, anio), ps in grupos_espn.items():
        tabla = temporadas.get(anio, {}).get(slug)
        res, clase = resultado_campana(ps, tabla)
        nombre = next((c["nombre"] for c in config()["datos_futbol"]["competencias"] if c["slug"] == slug),
                      ps[0]["competencia"] if ps else slug)
        cuenta = {k: sum(1 for p in ps if p["resultado"] == k.upper()) for k in ("g", "e", "p")}
        gf, gc = sum(p["goles_boca"] for p in ps), sum(p["goles_rival"] for p in ps)
        pj = len(ps)
        if not ps and tabla:
            cuenta = {k: tabla.get(k) or 0 for k in ("g", "e", "p")}
            gf, gc, pj = tabla.get("gf") or 0, tabla.get("gc") or 0, tabla.get("pj") or 0
        espn[(FAMILIA_ESPN.get(slug, "supercopa"), anio, nombre)] = dict(
            anio=anio, fam=FAMILIA_ESPN.get(slug, "supercopa"), nombre=nombre, res=res, clase=clase, pj=pj,
            c=cuenta, gf=gf, gc=gc)

    # 2) campañas según BocaStats (desde 1905, un torneo por fila)
    historicos = [p for p in (bocastats.todos_los_partidos() if bocastats.opciones() else [])
                  if not p["amistoso"] and p["torneo"]]  # en Campañas no se cuentan los amistosos
    por_torneo = defaultdict(list)
    for p in historicos:
        por_torneo[p["torneo"]].append(p)
    filas = []
    cubiertos = set()
    for etiqueta, ps in por_torneo.items():
        fam = familia_de(etiqueta)
        anio = ps[0]["fecha"][:4]
        nombre = re.sub(r"\s*\d{4}(\s*/\s*\d{2,4})?\s*$", "", etiqueta).strip() or etiqueta
        if re.search(r"\d{4}\s*/\s*\d{2,4}\s*$", etiqueta):
            nombre += " " + re.search(r"\d{4}\s*/\s*\d{2,4}\s*$", etiqueta).group(0).replace(" ", "")
        cuenta = {k: sum(1 for p in ps if p["resultado"] == k.upper()) for k in ("g", "e", "p")}
        filas.append(dict(anio=anio, fam=fam, nombre=nombre, res="", clase="", pj=len(ps), c=cuenta,
                          gf=sum(p["goles_boca"] for p in ps), gc=sum(p["goles_rival"] for p in ps)))
    # 3) campañas según Historia de Boca (catálogo oficial completo, con la tabla de posiciones cuando existe):
    #    donde hay datos de Historia de Boca reemplazan a los de BocaStats de esa competencia y ese año
    import historia_de_boca as hdb
    filas_hdb = []
    camp_hdb = hdb.campanias()
    con_cortos = {c["anio"] for c in camp_hdb if re.search(r"apertura|clausura", normalizar(c["nombre"]))}
    for c in camp_hdb:
        nombre = c["nombre"]
        if normalizar(nombre) == "supercopa" and c["anio"] < 2010:
            nombre = "Supercopa Sudamericana"
        if normalizar(nombre) == "campeonato" and c["anio"] in con_cortos:
            nombre = "Tabla anual"  # suma Apertura y Clausura: no se cuenta dos veces en los totales
        fam = "liga" if nombre == "Tabla anual" else familia_de(nombre)
        filas_hdb.append(dict(anio=str(c["anio"]), fam=fam, nombre=nombre, res="", clase="", pj=c["pj"],
                              c={k: c[k] for k in "gep"}, gf=c["gf"], gc=c["gc"], tabla=c.get("tabla")))
    if hdb.catalogo_completo():
        filas = filas_hdb  # el catálogo de Historia de Boca ya cubre todas las campañas oficiales
    elif filas_hdb:
        cubiertas = {(f["fam"], f["anio"]) for f in filas_hdb}
        filas = [f for f in filas if (f["fam"], f["anio"]) not in cubiertas] + filas_hdb
    # el resultado de ESPN se suma a la fila de BocaStats cuando hay una sola de esa competencia ese año
    por_fam_anio = defaultdict(list)
    for f in filas:
        por_fam_anio[(f["fam"], f["anio"])].append(f)
    for (fam, anio, nombre), r in espn.items():
        candidatas = por_fam_anio.get((fam, anio), [])
        if candidatas:
            cubiertos.add((fam, anio, nombre))
            if len(candidatas) == 1 and r["res"]:
                candidatas[0]["res"], candidatas[0]["clase"] = r["res"], r["clase"]
    filas += [r for k, r in espn.items() if k not in cubiertos]

    marcar_titulos(filas, palmares)
    for f in filas:
        f["texto"] = normalizar(f"{f['nombre']} {nombres_fam.get(f['fam'], '')} {alias_fam.get(f['fam'], '')} {f['anio']} {f['res']}")
    filas.sort(key=lambda f: (-int(f["anio"]) if f["anio"].isdigit() else 0, orden_fam.index(f["fam"]), f["nombre"]))
    filas = [f for f in filas if f["fam"] != "amistosos"]
    presentes = {f["fam"]: nombres_fam[f["fam"]] for f in filas}
    orden = orden_fam

    def celda_resultado(f):
        res = f'<span class="logro {f["clase"]}">{e(f["res"])}</span>' if f["clase"] else (e(f["res"]) or "–")
        if f.get("tabla"):
            res += (f' <button type="button" class="ver-tabla" data-tabla="{e(f["tabla"])}" '
                    f'aria-expanded="false">Tabla</button>')
        return res

    def suma(f):  # la tabla anual repite partidos del Apertura y el Clausura: no entra en los totales
        return 0 if f["nombre"].lower().startswith("tabla anual") else 1

    cuerpo_tabla = "".join(
        f'<tr data-comp="{e(f["fam"])}" data-texto="{e(f["texto"])}" data-pj="{f["pj"] * suma(f)}" data-g="{f["c"]["g"] * suma(f)}" '
        f'data-e="{f["c"]["e"] * suma(f)}" data-p="{f["c"]["p"] * suma(f)}" data-gf="{f["gf"] * suma(f)}" data-gc="{f["gc"] * suma(f)}" '
        f'data-campeon="{1 if f["clase"] == "campeon" else 0}">'
        f'<td class="pts">{e(f["anio"])}</td><td class="izq">{e(f["nombre"])}</td><td class="izq">{celda_resultado(f)}</td>'
        f'<td>{f["pj"]}</td><td>{f["c"]["g"]}</td><td>{f["c"]["e"]}</td><td>{f["c"]["p"]}</td><td>{f["gf"]}</td><td>{f["gc"]}</td></tr>'
        for f in filas)
    filas_viejas = filas
    filas = [(f["anio"],) for f in filas_viejas]

    botones = '<button type="button" data-comp="todas" aria-pressed="true">Todas</button>' + "".join(
        f'<button type="button" data-comp="{e(slug)}" aria-pressed="false">{e(nombre)}</button>'
        for slug, nombre in sorted(presentes.items(), key=lambda x: orden.index(x[0]) if x[0] in orden else 99))

    titulos = bloque_titulos(palmares)

    desde = min((f[0] for f in filas if f[0].isdigit()), default="")
    cuerpo = f"""<header class="encabezado-pagina"><h1>Campañas</h1>
<p>Cómo le fue a Boca en cada torneo oficial{f", desde {e(desde)}" if desde else ""}. Buscá un torneo o un año, o elegí una competencia. Donde dice «Tabla», tocalo para ver la tabla de posiciones de ese campeonato.</p></header>
{titulos}
<div class="buscador-campanas">
  <label for="buscar-campana" class="oculto">Buscar</label>
  <input id="buscar-campana" type="search" placeholder="Buscá: libertadores, copa argentina 2024, campeón…" autocomplete="off">
</div>
<div class="filtros" role="group" aria-label="Competencias" data-filtro-campanas>{botones}</div>
<div class="resumen-campanas" id="resumen-campanas" aria-live="polite"></div>
<div class="tabla-scroll"><table id="tabla-campanas"><thead><tr><th>Año</th><th class="izq">Competencia</th><th class="izq">Resultado</th>
<th title="Partidos jugados">PJ</th><th title="Ganados">G</th><th title="Empatados">E</th><th title="Perdidos">P</th>
<th title="Goles a favor">GF</th><th title="Goles en contra">GC</th></tr></thead>
<tbody>{cuerpo_tabla}</tbody></table></div>
<p class="vacio" id="sin-campanas" hidden>No hay campañas que coincidan con la búsqueda.</p>
<p class="nota-dato">Datos históricos y tablas de posiciones: Historia de Boca y BocaStats. Resultados y posiciones recientes: ESPN.</p>"""
    return pagina("Campañas", cuerpo, activa="campanas.html", franja=barra_franja(proximos, ""))


ORDEN_POS = ["Arquero", "Goalkeeper", "Defensor", "Defender", "Mediocampista", "Midfielder", "Delantero", "Forward"]
TRAD_POS = {"Goalkeeper": "Arqueros", "Defender": "Defensores", "Midfielder": "Mediocampistas", "Forward": "Delanteros",
            "Arquero": "Arqueros", "Defensor": "Defensores", "Mediocampista": "Mediocampistas", "Delantero": "Delanteros"}


def pagina_plantel(plantel: dict, proximos) -> str:
    grupos = defaultdict(list)
    for j in plantel.get("jugadores", []):
        grupos[j.get("posicion") or "Otros"].append(j)
    bloques = ""
    for pos in sorted(grupos, key=lambda x: ORDEN_POS.index(x) if x in ORDEN_POS else 99):
        js = sorted(grupos[pos], key=lambda j: int(j["numero"]) if str(j.get("numero", "")).isdigit() else 99)
        tarjetas = "".join(
            f'<div class="jugador"><span class="num">{e(str(j.get("numero") or ""))}</span><span><b>{e(j["nombre"])}</b>'
            f'<small>{e(str(j["edad"])) + " años" if j.get("edad") else ""}{", " + e(j["nacionalidad"]) if j.get("nacionalidad") else ""}</small></span></div>'
            for j in js)
        bloques += f'<h2 class="titulo-seccion">{e(TRAD_POS.get(pos, pos))}</h2><div class="plantel">{tarjetas}</div>'
    goleadores = ""
    gol = leer_json(RAIZ / "datos" / "bocastats" / "goleadores.json", {}) if bs_opciones() else {}
    if gol.get("jugadores"):
        filas = "".join(
            f'<tr><td>{i}</td><td class="izq"><b>{e(j["nombre"])}</b><br><small class="nota-dato">{e(j.get("posicion", ""))}</small></td>'
            f'<td class="pts">{j["goles"]}</td>'
            f'<td class="izq">{e(", ".join(f"{v} {k}" for k, v in (j.get("desglose") or {}).items()))}</td>'
            f'<td>{"" if j.get("asistencias_liga") is None else j["asistencias_liga"]}</td>'
            f'<td>{"" if j.get("pj_liga") is None else j["pj_liga"]}</td></tr>'
            for i, j in enumerate(gol["jugadores"], 1))
        total = sum(j["goles"] for j in gol["jugadores"])
        goleadores = f"""<section style="margin-bottom:44px"><h2 class="titulo-seccion">Goleadores {e(str(gol.get("temporada", "")))}</h2>
<div class="tabla-scroll"><table><thead><tr><th>#</th><th class="izq">Jugador</th><th>Goles</th><th class="izq">Por competencia</th>
<th title="Asistencias en la Liga">Asist.</th><th title="Partidos jugados en la Liga">PJ</th></tr></thead><tbody>{filas}</tbody></table></div>
<p class="nota-dato">{total} goles en todas las competencias oficiales. Asistencias y partidos jugados: solo Liga. Datos: BocaStats.</p></section>"""
    cuerpo = f"""<header class="encabezado-pagina"><h1>Plantel</h1><p>Los jugadores del plantel profesional, con su número de camiseta, y los goleadores de la temporada.</p></header>
{goleadores}
{bloques or '<div class="vacio">El plantel se carga solo en la próxima actualización.</div>'}"""
    return pagina("Plantel", cuerpo, activa="plantel.html", franja=barra_franja(proximos, ""))


def pagina_efemerides(mes: int, dia: int, items: list[dict], dias: list[str], proximos, pre: str = "",
                      partidos_dia: list[dict] | None = None) -> str:
    hoy = ahora()
    es_hoy = (mes, dia) == (hoy.month, hoy.day)
    titulo = f"Un día como hoy, {dia} de {MESES[mes - 1]}"
    lista = "".join(
        f'<li><b>{x["anio"]}</b><div><h3>{e(x["titulo"])}</h3>'
        f'{("<p>" + e(x["detalle"]) + "</p>") if x.get("detalle") else ""}</div></li>' for x in items)
    otros = "".join(
        f'<a href="{pre}efemerides/{d}.html"{" aria-current=page" if d == f"{mes:02d}-{dia:02d}" else ""}>'
        f'{int(d[3:])} {MESES_CORTOS_[int(d[:2]) - 1]}</a>' for d in dias)
    fuentes = [x for x in (hdb().get("credito") if items else None, bs_opciones().get("credito") if partidos_dia else None) if x]
    credito = f'<p class="nota-dato">Datos históricos: {e(" y ".join(fuentes))}.</p>' if fuentes else ""
    bloque_partidos = ""
    if partidos_dia:
        filas = "".join(
            f'<li><span class="lp-fecha">{p["fecha"][:4]}</span><span><span class="lp-cruce">'
            + (f'{e(p["rival"])} <span class="goles">{p["goles_rival"]} - {p["goles_boca"]}</span> Boca' if p["condicion"] == "V"
               else f'Boca <span class="goles">{p["goles_boca"]} - {p["goles_rival"]}</span> {e(p["rival"])}')
            + f'</span><span class="lp-sub">{e("Amistoso" if p["amistoso"] else p["torneo"])}</span></span>'
            f'<span class="lp-res r-{p["resultado"]}">{p["resultado"]}</span></li>'
            for p in sorted(partidos_dia, key=lambda x: x["fecha"]))
        bloque_partidos = (f'<section style="margin-top:36px"><h2 class="titulo-seccion">Todos los partidos de un {dia} de {MESES[mes - 1]} '
                           f'({len(partidos_dia)})</h2><ul class="lista-partidos">{filas}</ul></section>')
    cuerpo = f"""<header class="encabezado-pagina"><h1>{e(titulo)}</h1>
<p>Lo que pasó en la historia de Boca un {dia} de {MESES[mes - 1]}: partidos, cumpleaños y fechas para recordar.</p></header>
{f'<ul class="almanaque">{lista}</ul>' if items else ('' if partidos_dia else '<div class="vacio">Todavía no hay efemérides cargadas para este día.</div>')}
{bloque_partidos}
{credito}
{f'<section style="margin-top:40px"><h2 class="titulo-seccion">Otros días</h2><nav class="dias">{otros}</nav></section>' if len(dias) > 1 else ''}"""
    return pagina(titulo, cuerpo, activa="efemerides.html" if es_hoy and not pre else "", pre=pre,
                  franja=barra_franja(proximos, pre))


def secciones_rankings() -> list[str]:
    """Rankings históricos de jugadores y técnicos (Historia de Boca, partidos oficiales)."""
    import historia_de_boca as hdb
    rk = hdb.rankings()
    partes = []
    jug = rk.get("jugadores") or {}
    orden = ["goles", "partidos", "penales", "cabeza", "expulsiones", "amonestaciones"]
    unidad = {"goles": "goles", "partidos": "partidos", "penales": "penales", "cabeza": "de cabeza",
              "expulsiones": "rojas", "amonestaciones": "amarillas"}
    tarjetas = ""
    for clave in [c for c in orden if c in jug]:
        r = jug[clave]
        items = ""
        for i, f in enumerate(r["filas"][:10], 1):
            extra = ""
            if clave == "goles" and f.get("partidos"):
                extra = f'<small>en {f["partidos"]} partidos</small>'
            elif clave == "partidos" and f.get("goles") is not None:
                extra = f'<small>{f["goles"]} goles</small>'
            items += (f'<li><span class="rk-pos">{i}</span><span class="rk-nombre">{e(f["nombre"])}{extra}</span>'
                      f'<span class="rk-valor">{f["valor"]}<small>{unidad[clave]}</small></span></li>')
        tarjetas += f'<article class="ranking"><h3>{e(r["titulo"])}</h3><ol>{items}</ol></article>'
    if tarjetas:
        partes.append(f"""<section><h2 class="titulo-seccion">Jugadores</h2><div class="rankings">{tarjetas}</div>
<p class="nota-dato">Partidos oficiales desde 1905. Las asistencias no tienen registro histórico confiable: las de la temporada están en <a href="plantel.html">Plantel</a>. Fuente: Historia de Boca.</p></section>""")
    tec = [t for t in rk.get("tecnicos") or [] if t.get("pj")]
    if tec:
        con_balance = [t for t in tec if "g" in t]
        por_victorias = len(con_balance) >= len(tec) * 0.6
        lista = sorted(con_balance, key=lambda t: -t["g"]) if por_victorias else sorted(tec, key=lambda t: -t["pj"])
        filas = ""
        for i, t in enumerate(lista[:15], 1):
            if "g" in t:
                pct = round(100 * (3 * t["g"] + t["e"]) / (3 * t["pj"]))
                cifras = f'<td>{t["pj"]}</td><td class="pts">{t["g"]}</td><td>{t["e"]}</td><td>{t["p"]}</td><td>{pct}%</td>'
            else:
                cifras = f'<td>{t["pj"]}</td><td colspan="4" class="nota-dato">sin desglose</td>'
            filas += f'<tr><td>{i}</td><td class="izq"><b>{e(t["nombre"])}</b></td>{cifras}</tr>'
        criterio = "más victorias" if por_victorias else "más partidos dirigidos"
        partes.append(f"""<section><h2 class="titulo-seccion">Técnicos con {criterio}</h2><div class="tabla-scroll"><table>
<thead><tr><th>#</th><th class="izq">Técnico</th><th>PJ</th><th>G</th><th>E</th><th>P</th><th title="Puntos obtenidos sobre los posibles, contando 3 por victoria">Efectividad</th></tr></thead>
<tbody>{filas}</tbody></table></div>
<p class="nota-dato">Partidos oficiales. Efectividad: puntos obtenidos sobre los posibles (3 por victoria). Fuente: Historia de Boca.</p></section>""")
    return partes


def pagina_records(historicos: list[dict], proximos) -> str:
    import bocastats
    rec = leer_json(RAIZ / "datos" / "bocastats" / "records.json", {}) if bs_opciones() else {}
    partes = []
    oficiales = [p for p in historicos if not p["amistoso"]]
    b = rec.get("balance")
    nota_balance = "No incluye amistosos."
    if len(oficiales) > 3000:
        b = {"pj": len(oficiales), **{k: sum(1 for p in oficiales if p["resultado"] == k.upper()) for k in "gep"},
             "gf": sum(p["goles_boca"] for p in oficiales), "gc": sum(p["goles_rival"] for p in oficiales)}
    elif b:
        nota_balance = "Por ahora incluye amistosos: cuando termine de cargarse la base partido a partido, se muestran solo los oficiales."
    if b:
        pct = round(100 * b["g"] / b["pj"]) if b["pj"] else 0
        partes.append(f"""<section class="balance-historico"><h2 class="titulo-seccion">Balance histórico</h2>
<div class="cifras-records">
  <div><b>{b['pj']:,}</b>partidos</div><div><b>{b['g']:,}</b>victorias</div><div><b>{b['e']:,}</b>empates</div>
  <div><b>{b['p']:,}</b>derrotas</div><div><b>{b['gf']:,}</b>goles a favor</div><div><b>{b['gc']:,}</b>goles en contra</div>
</div>
<p class="nota-dato">Boca ganó el {pct}% de sus partidos oficiales desde 1905. {nota_balance}</p></section>""".replace(",", "."))
    palm = leer_json(DATOS_MANUAL / "palmares.json", {})
    if titulos_lista(palm):
        partes.append(bloque_titulos(palm).replace("<h2 class=\"titulo-seccion\">Títulos</h2>",
                                                    '<h2 class="titulo-seccion">Títulos <a href="campanas.html">Ver campañas</a></h2>'))
    if rec.get("marcas"):
        marcas = list(rec["marcas"])
        if len(oficiales) > 3000:  # el rival más enfrentado, contando solo oficiales
            cuenta = defaultdict(int)
            for p in oficiales:
                cuenta[p["rival"]] += 1
            top = max(cuenta.items(), key=lambda x: x[1])
            marcas = [dict(m, valor=top[0], detalle=f"{top[1]} partidos oficiales") if m["titulo"] == "Rival más enfrentado" else m
                      for m in marcas]
        else:
            marcas = [m for m in marcas if m["titulo"] != "Rival más enfrentado"]
        items = "".join(f'<li><span class="nota-dato">{e(m["titulo"])}</span><b>{e(m["valor"])}</b><span>{e(m.get("detalle", ""))}</span></li>'
                        for m in marcas)
        partes.append(f'<section><h2 class="titulo-seccion">Marcas históricas</h2><ul class="marcas">{items}</ul></section>')
    partes += secciones_rankings()
    if len(oficiales) > 500:
        goleadas = sorted(oficiales, key=lambda p: (-(p["goles_boca"] - p["goles_rival"]), -p["goles_boca"], p["fecha"]))[:10]
        def fila(p):
            cruce = (f'{e(p["rival"])} <span class="goles">{p["goles_rival"]} - {p["goles_boca"]}</span> Boca' if p["condicion"] == "V"
                     else f'Boca <span class="goles">{p["goles_boca"]} - {p["goles_rival"]}</span> {e(p["rival"])}')
            return (f'<li><span class="lp-fecha">{int(p["fecha"][8:10])} {MESES_CORTOS_[int(p["fecha"][5:7]) - 1]}<small>{p["fecha"][:4]}</small></span>'
                    f'<span><span class="lp-cruce">{cruce}</span><span class="lp-sub">{e(p["torneo"])}</span></span>'
                    f'<span class="lp-res r-{p["resultado"]}">{p["resultado"]}</span></li>')
        partes.append(f'<section><h2 class="titulo-seccion">Las 10 goleadas más grandes</h2><ul class="lista-partidos">{"".join(fila(p) for p in goleadas)}</ul>'
                      f'<p class="nota-dato">Partidos oficiales.</p></section>')
        por_decada = defaultdict(lambda: {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0})
        for p in oficiales:
            d = por_decada[p["fecha"][:3] + "0"]
            d["pj"] += 1
            d[p["resultado"].lower()] += 1
            d["gf"] += p["goles_boca"]
            d["gc"] += p["goles_rival"]
        filas = "".join(f'<tr><td class="pts">{k}</td><td>{v["pj"]}</td><td>{v["g"]}</td><td>{v["e"]}</td><td>{v["p"]}</td>'
                        f'<td>{v["gf"]}</td><td>{v["gc"]}</td><td>{round(100 * v["g"] / v["pj"])}%</td></tr>'
                        for k, v in sorted(por_decada.items()))
        partes.append(f"""<section><h2 class="titulo-seccion">Década por década</h2><div class="tabla-scroll"><table>
<thead><tr><th>Década</th><th>PJ</th><th>G</th><th>E</th><th>P</th><th>GF</th><th>GC</th><th>% victorias</th></tr></thead>
<tbody>{filas}</tbody></table></div><p class="nota-dato">Partidos oficiales.</p></section>""")
    rivales = []
    if len(oficiales) > 3000:
        agrupado = defaultdict(lambda: {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0})
        for p in oficiales:
            a = agrupado[p["rival_slug"]]
            a["pj"] += 1
            a[p["resultado"].lower()] += 1
            a["gf"] += p["goles_boca"]
            a["gc"] += p["goles_rival"]
        nombres = {r["slug"]: r["nombre"] for r in bocastats.rivales()}
        rivales = [{"slug": k, "nombre": nombres.get(k, k), **v, "dg": v["gf"] - v["gc"]} for k, v in agrupado.items()]
        rivales = sorted(rivales, key=lambda r: -r["pj"])[:15]
        nota_rivales = "Partidos oficiales."
    elif bs_opciones():
        rivales = sorted(bocastats.rivales(), key=lambda r: -r["pj"])[:15]
        nota_rivales = "Por ahora incluye amistosos: cuando termine de cargarse la base partido a partido, se muestran solo los oficiales."
    if rivales:
        filas = "".join(f'<tr><td class="izq"><a href="historial.html#{e(r["slug"])}">{e(bocastats.nombre_lindo(r["slug"], r["nombre"]))}</a></td>'
                        f'<td>{r["pj"]}</td><td>{r["g"]}</td><td>{r["e"]}</td><td>{r["p"]}</td>'
                        f'<td>{"+" if (r.get("dg") or 0) > 0 else ""}{r.get("dg") if r.get("dg") is not None else ""}</td></tr>' for r in rivales)
        partes.append(f"""<section><h2 class="titulo-seccion">Los rivales más enfrentados</h2><div class="tabla-scroll"><table>
<thead><tr><th class="izq">Rival</th><th>PJ</th><th>G</th><th>E</th><th>P</th><th>DG</th></tr></thead><tbody>{filas}</tbody></table></div>
<p class="nota-dato">{nota_rivales} <a href="historial.html">Ver el historial contra cada rival</a>.</p></section>""")
    if not partes:
        partes.append('<div class="vacio">Los récords aparecen cuando se cargan los datos históricos.</div>')
    act = rec.get("actualizado_fuente")
    pie = f'<p class="nota-dato" style="margin-top:28px">Datos históricos: Historia de Boca y BocaStats{f" (BocaStats al {_fecha_txt(act)})" if act else ""}.</p>' if rec else ""
    cuerpo = f"""<header class="encabezado-pagina"><h1>Récords</h1><p>Los números de Boca desde 1905: balance, goleadores, los que más jugaron, técnicos, goleadas y rivales.</p></header>
<div class="records">{"".join(partes)}</div>{pie}"""
    return pagina("Récords", cuerpo, activa="records.html", franja=barra_franja(proximos, ""))


def cuentas() -> dict:
    c = config().get("cuentas") or {}
    return c if c.get("activado") and c.get("supabase_url") and c.get("supabase_anon_key") else {}


_HINCHA = None


def hincha_semana() -> dict:
    """El primero del ranking de la semana pasada (se consulta una vez por armado de la web)."""
    global _HINCHA
    if _HINCHA is not None:
        return _HINCHA
    _HINCHA = {}
    c = cuentas()
    if not c:
        return _HINCHA
    try:
        from comun import http_post_json
        _HINCHA = http_post_json(c["supabase_url"].rstrip("/") + "/rest/v1/rpc/hincha_de_la_semana", {}, timeout=20,
                                 headers={"apikey": c["supabase_anon_key"]}) or {}
    except Exception as ex:
        log(f"Sitio: no pude leer el hincha de la semana ({ex})")
    return _HINCHA


GLIFO_IDOLO = ('<svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="28" r="15"/>'
               '<path d="M12 78c2-18 14-28 28-28s26 10 28 28z"/></svg>')
GLIFO_GRILLA = '<span class="g-grilla" aria-hidden="true">' + "".join(
    f'<i class="{"on" if k in (0, 4, 5, 7) else ""}"></i>' for k in range(9)) + "</span>"


def pagina_juegos(proximos) -> str:
    import juegos
    datos = juegos.armar()
    datos["cantidades"] = {t: sum(1 for q in datos["preguntas"] if q["tema"] == t) for t in datos["temas"]}
    c = cuentas()
    if c:  # con cuentas, las respuestas viven solo en la base de datos: la página no las lleva
        datos["preguntas"] = []
    datos["hay_grilla"] = bool(juegos.datos_grilla())
    datos_json = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    dia_n = (ahora().date() - __import__("datetime").date(2026, 11, 18)).days + 1

    # (id, nombre, descripción corta, glifo, id de la caja)
    lista = [
        ("idolo", "Adiviná el ídolo", "Una foto borrosa y 6 intentos. Cada intento la aclara un poco más.",
         GLIFO_IDOLO, "juego-idolo"),
        ("mas-o-menos", "¿Más o menos?", "Cara a cara: ¿quién hizo más goles, quién jugó más partidos? Hasta que le erres.",
         '<span class="g-texto">+<small>/</small>−</span>', "juego-mom"),
        ("anio", "¿En qué año fue?", "5 momentos de la historia de Boca. Cuanto más cerca del año, más puntos.",
         '<span class="g-texto">19<small>··</small></span>', "juego-anio"),
        ("grilla", "Grilla bostera", "Nombrá jugadores de Boca que también pasaron por los clubes de cada fila y columna.",
         GLIFO_GRILLA, "juego-grilla"),
        ("trivia", "Trivia por temas", "10 preguntas del tema que elijas: títulos, Superclásico, ídolos y más.",
         '<span class="g-texto g-abcd">A B<br>C D</span>', "juego-trivia"),
    ]
    if not datos["hay_grilla"]:
        lista = [x for x in lista if x[0] != "grilla"]
    tarjetas = "".join(
        f'<a class="jtarjeta" href="#{k}"><span class="jt-glifo">{g}</span><span class="jt-cuerpo">'
        f'<b>{e(n)}</b><span>{e(d)}</span><span class="jt-estado" data-estado="{k}"></span></span></a>'
        for k, n, d, g, _c in lista)
    secciones = [("del-dia", f"Pregunta del día #{dia_n}",
                  "10 preguntas por día, las mismas para todos y sin repetir. Mantené la racha.", "juego-dia")]
    secciones += [(k, n, d, caja) for k, n, d, _g, caja in lista]
    secciones += [("ranking", "Ranking", "Los que más saben de Boca. Suman la pregunta del día y la trivia.", "juego-ranking"),
                  ("insignias", "Tus insignias", "Se ganan jugando. Las de la cuenta se ven en cualquier dispositivo.",
                   "juego-insignias")]
    cuerpo_secc = "".join(
        f'<section class="juego" data-juego="{k}" hidden><a class="volver" href="#">Todos los juegos</a>'
        f'<h2 class="juego-titulo">{e(t)}</h2><p class="juego-bajada">{e(d)}</p>'
        f'<div class="juego-caja" id="{caja}"><p class="nota-dato">Cargando…</p></div></section>'
        for k, t, d, caja in secciones)
    sb_attrs = ""
    if c:
        sb_attrs = f' data-supabase-url="{e(c["supabase_url"])}" data-supabase-key="{e(c["supabase_anon_key"])}"'
        if c.get("entrar_con_google"):
            sb_attrs += ' data-google="1"'
    sb_script = ('<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>' if c else "")
    cuerpo = f"""<div class="juegos" data-dia="{dia_n}">
<div class="cuenta" id="cuenta" hidden></div>
<div class="portada-juegos" id="portada-juegos">
  <header class="juegos-cabeza"><h1>Juegos</h1><p>¿Cuánto sabés de Boca? Todo sale de los datos de la web: títulos, historiales, récords y ídolos.</p></header>
  <a class="jdia" href="#del-dia">
    <span class="jdia-numero"><small>Pregunta del día</small>#{dia_n}</span>
    <span class="jdia-texto"><b>10 preguntas nuevas hoy</b><span>Las mismas para todos. Compartí tu resultado y mantené la racha.</span>
      <span class="jt-estado" data-estado="del-dia"></span></span>
    <span class="jdia-ir">Jugar</span>
  </a>
  <div class="jtarjetas">{tarjetas}</div>
  <div class="jextra">
    <a class="jextra-item" href="#ranking"><b>Ranking</b><span data-estado="ranking">Semana, mes e histórico</span></a>
    <a class="jextra-item" href="#insignias"><b>Insignias</b><span data-estado="insignias">Mirá cuáles ganaste</span></a>
  </div>
</div>
{cuerpo_secc}
</div>
<script type="application/json" id="datos-juegos" data-url="{e(url_abs("juegos.html"))}"{sb_attrs}>{datos_json}</script>
{sb_script}
<script src="estatico/juegos.js" defer></script>"""
    return pagina("Juegos", cuerpo, activa="juegos.html", franja=barra_franja(proximos, ""))


def pagina_privacidad(proximos) -> str:
    s = sitio()
    cuerpo = f"""<article class="nota">
<h1>Privacidad</h1>
<div class="cuerpo">
<p>{e(s['nombre'])} es un medio partidario. Para leer la web no hace falta registrarse y no te pedimos ningún dato.</p>
<h2>Si creás una cuenta para los juegos</h2>
<p>Guardamos tu mail (o tu cuenta de Google), el apodo que elijas y tus respuestas en la pregunta del día y la trivia. Lo usamos solo para
el ranking y para que tu racha se mantenga en cualquier dispositivo. Tu mail no se muestra en ningún lado: en el ranking solo aparece tu apodo.</p>
<p>Los datos se guardan en Supabase, el servicio de base de datos que usamos. No los vendemos ni los compartimos con nadie.</p>
<h2>Borrar tu cuenta</h2>
<p>Cuando quieras, entrá a Juegos y tocá «Borrar mi cuenta»: se eliminan tu cuenta, tu apodo y todos tus puntos.</p>
<h2>Lo que queda en tu navegador</h2>
<p>Las rachas y récords de los juegos se guardan en tu propio navegador (almacenamiento local). Si borrás los datos del navegador, se pierden.
No usamos cookies de publicidad.</p>
<h2>Apodos</h2>
<p>Los apodos ofensivos se borran sin aviso.</p>
</div></article>"""
    return pagina("Privacidad", cuerpo, activa="", franja=barra_franja(proximos, ""))


# ============================================================ otros archivos ==
def calendario_ics(proximos, jugados) -> str:
    def esc(t):
        return t.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{sitio()['nombre']}//Fixture//ES",
              f"X-WR-CALNAME:Boca – {sitio()['nombre']}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
              "REFRESH-INTERVAL;VALUE=DURATION:PT6H"]
    import datetime as dt
    sello = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for p in jugados[:20][::-1] + proximos:
        d = parsear_fecha(p["fecha"])
        if not d:
            continue
        u = d.astimezone(dt.timezone.utc)
        fin = u + dt.timedelta(hours=2)
        local = "Boca" if p["condicion"] == "L" else p["local"]["nombre"]
        visita = "Boca" if p["condicion"] == "V" else p["visitante"]["nombre"]
        titulo = f"{local} vs {visita}"
        if p["estado"] == "finalizado" and p["local"].get("goles") is not None:
            titulo = f"{local} {p['local']['goles']}-{p['visitante']['goles']} {visita}"
        lineas += ["BEGIN:VEVENT", f"UID:boca-{p['id']}@rinconbostero", f"DTSTAMP:{sello}",
                   f"DTSTART:{u.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{fin.strftime('%Y%m%dT%H%M%SZ')}",
                   f"SUMMARY:{esc(titulo)}", f"DESCRIPTION:{esc(p['competencia'])}",
                   f"LOCATION:{esc(p.get('estadio', ''))}", "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(lineas) + "\r\n"


def feed_rss(notas) -> str:
    from email.utils import format_datetime
    items = ""
    for n in notas[:30]:
        d = parsear_fecha(n["fecha"])
        url = url_abs(f"notas/{n['slug']}.html")
        items += (f"<item><title>{e(n['titulo'])}</title><link>{e(url)}</link><guid>{e(url)}</guid>"
                  f"<pubDate>{format_datetime(d)}</pubDate><category>{e(n.get('categoria', ''))}</category>"
                  f"<description>{e(n.get('bajada', ''))}</description></item>")
    s = sitio()
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(s["nombre"])}</title>'
            f'<link>{e(url_abs(""))}</link><description>{e(s["lema"])}</description><language>es-AR</language>'
            f'{items}</channel></rss>')


def sitemap(notas) -> str:
    urls = [url_abs(h) for h, _ in MENU] + [url_abs(f"notas/{n['slug']}.html") for n in notas]
    if hdb():
        import historia_de_boca
        urls += [url_abs(f"efemerides/{d}.html") for d in historia_de_boca.efemerides_guardadas()]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{e(u)}</loc></url>" for u in urls) + "</urlset>")


ICONO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#0b2a6f"/>
<rect y="25" width="64" height="14" fill="#f5b700"/></svg>"""


# ================================================================= armar ==
def construir() -> None:
    from datos_futbol import proximos_y_ultimos

    notas = [n for n in listar_notas() if n.get("titulo") and n.get("slug")]
    partidos = leer_json(DATOS_ESPN / "partidos.json", [])
    proximos, jugados = proximos_y_ultimos(partidos)
    tablas = leer_json(DATOS_ESPN / "posiciones.json", {})
    historial = leer_json(DATOS_ESPN / "historial.json", {})
    temporadas = leer_json(DATOS_ESPN / "temporadas.json", {})
    plantel = leer_json(DATOS_ESPN / "plantel.json", {})
    palmares = leer_json(DATOS_MANUAL / "palmares.json", {})

    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    (SALIDA / "notas").mkdir(parents=True)
    shutil.copytree(SITIO / "estatico", SALIDA / "estatico")
    (SALIDA / "estatico" / "icono.svg").write_text(ICONO, encoding="utf-8")
    if (SITIO / "estatico" / "img").exists():
        shutil.copytree(SITIO / "estatico" / "img", SALIDA / "img", dirs_exist_ok=True)

    def escribir(ruta: str, contenido: str):
        (SALIDA / ruta).write_text(contenido, encoding="utf-8")

    escribir("index.html", pagina_inicio(notas, proximos, jugados, tablas))
    escribir("noticias.html", pagina_noticias(notas, proximos))
    escribir("fixture.html", pagina_fixture(proximos, jugados, tablas))
    # la vieja dirección de Posiciones lleva a la página unificada
    escribir("posiciones.html", '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=fixture.html">'
                                '<link rel="canonical" href="fixture.html"><a href="fixture.html">Fixture y posiciones</a>')
    resumen_hist, listas_hist = datos_historial(historial, partidos)
    escribir("historial.html", pagina_historial(resumen_hist, proximos))
    (SALIDA / "historial").mkdir(exist_ok=True)
    for clave, lista in listas_hist.items():
        escribir(f"historial/{clave}.json", json.dumps(lista, ensure_ascii=False, separators=(",", ":")))
    escribir("campanas.html", pagina_campanas(temporadas, jugados, palmares, proximos))
    escribir("plantel.html", pagina_plantel(plantel, proximos))
    import bocastats
    import historia_de_boca
    historicos = bocastats.todos_los_partidos() if bs_opciones() else []
    por_dia = defaultdict(list)
    for x in historicos:
        if not x["amistoso"]:
            por_dia[x["fecha"][5:10]].append(x)
    guardadas = historia_de_boca.efemerides_guardadas() if hdb() else {}
    dias = sorted(set(guardadas) | set(por_dia))
    if dias or hdb():
        (SALIDA / "efemerides").mkdir(exist_ok=True)
        hoy = ahora()
        clave_hoy = f"{hoy.month:02d}-{hoy.day:02d}"
        escribir("efemerides.html", pagina_efemerides(hoy.month, hoy.day, guardadas.get(clave_hoy, []), dias, proximos,
                                                      partidos_dia=por_dia.get(clave_hoy)))
        for d in dias:
            escribir(f"efemerides/{d}.html", pagina_efemerides(int(d[:2]), int(d[3:]), guardadas.get(d, []), dias, proximos,
                                                              pre="../", partidos_dia=por_dia.get(d)))
    escribir("records.html", pagina_records(historicos, proximos))
    escribir("juegos.html", pagina_juegos(proximos))
    import juegos as _juegos
    grilla = _juegos.datos_grilla()
    if grilla:
        escribir("grilla.json", json.dumps(grilla, ensure_ascii=False, separators=(",", ":")))
    escribir("privacidad.html", pagina_privacidad(proximos))
    for i, n in enumerate(notas):
        misma_cat = [x for x in notas if x is not n and x.get("categoria") == n.get("categoria")][:2]
        otras = [x for x in notas if x is not n and x not in misma_cat][:4 - len(misma_cat)]
        escribir(f"notas/{n['slug']}.html", pagina_nota(n, misma_cat + otras, proximos))
    escribir("calendario.ics", calendario_ics(proximos, jugados))
    escribir("feed.xml", feed_rss(notas))
    escribir("sitemap.xml", sitemap(notas))
    escribir("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {url_abs('sitemap.xml')}\n")
    raiz = url_abs("")
    escribir("404.html", pagina("Página no encontrada",
                                '<div class="vacio"><h1>No encontramos esa página</h1><p>Puede que la nota se haya '
                                f'despublicado. <a href="{e(raiz)}index.html">Volvé a la portada</a>.</p></div>', pre=raiz))
    escribir(".nojekyll", "")
    log(f"Sitio: {len(notas)} notas, {len(proximos)} próximos, {len(jugados)} resultados → {SALIDA}")


if __name__ == "__main__":
    sys.exit(construir())
