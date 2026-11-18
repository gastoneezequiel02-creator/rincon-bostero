"""Opción 1: noticias 100% automáticas a partir de RSS (Google Noticias y los medios que agregues).

Lee los titulares nuevos, la IA elige y agrupa los que valen la pena, y redacta una nota propia
citando las fuentes. Según config.json se publica directo o va a aprobación por Telegram.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
import xml.etree.ElementTree as ET

import ia
from comun import (BORRADORES, ESTADO, ahora, ahora_iso, config, guardar_json, guardar_nota, http_get, huella,
                   leer_json, limpiar_html, listar_notas, log, normalizar, notas_de_hoy, parsear_fecha)

ARCHIVO_VISTOS = ESTADO / "rss_vistos.json"
HORAS_MAXIMAS = 36


def leer_feed(fuente: dict) -> list[dict]:
    crudo = http_get(fuente["url"])
    raiz = ET.fromstring(crudo)
    items = []
    for it in raiz.iter("item"):
        titulo = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        medio = (it.findtext("source") or "").strip()
        resumen = limpiar_html(it.findtext("description") or "")
        # Google Noticias pone " - Medio" al final del título
        if medio and titulo.endswith(" - " + medio):
            titulo = titulo[: -len(" - " + medio)].strip()
        if not medio:
            medio = fuente["nombre"]
        if normalizar(resumen).startswith(normalizar(titulo)[:40]):
            resumen = ""  # en Google Noticias la descripción repite el título
        items.append({
            "titulo": titulo,
            "link": link,
            "fuente": medio,
            "resumen": resumen[:400],
            "fecha": (parsear_fecha(it.findtext("pubDate")) or ahora()).isoformat(),
        })
    # Atom (algunos medios)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for en in raiz.findall("a:entry", ns):
        link_el = en.find("a:link", ns)
        items.append({
            "titulo": (en.findtext("a:title", default="", namespaces=ns)).strip(),
            "link": link_el.get("href", "") if link_el is not None else "",
            "fuente": fuente["nombre"],
            "resumen": limpiar_html(en.findtext("a:summary", default="", namespaces=ns))[:400],
            "fecha": (parsear_fecha(en.findtext("a:updated", default="", namespaces=ns)) or ahora()).isoformat(),
        })
    return items


def _palabras(t: str) -> set[str]:
    return {p for p in re.findall(r"[a-z0-9]{4,}", normalizar(t))}


def parecido(a: str, b: str) -> float:
    pa, pb = _palabras(a), _palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def texto_del_articulo(url: str) -> str:
    """Intenta leer el texto de la nota original para darle contexto a la IA."""
    if not url or "news.google.com" in url:
        return ""
    try:
        html = http_get(url, intentos=1, timeout=15).decode("utf-8", "ignore")
    except Exception:
        return ""
    parrafos = [limpiar_html(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)]
    parrafos = [p for p in parrafos if len(p) > 60 and "cookies" not in p.lower()]
    return "\n".join(parrafos[:14])


def ejecutar() -> int:
    cfg = config()["noticias_rss"]
    if not cfg.get("activado"):
        log("RSS: desactivado en config.json")
        return 0

    vistos: dict = leer_json(ARCHIVO_VISTOS, {})
    limite = (ahora() - dt.timedelta(days=7)).isoformat()
    vistos = {k: v for k, v in vistos.items() if v >= limite}

    claves = [normalizar(k) for k in cfg.get("palabras_clave", [])]
    recientes = [n["titulo"] for n in listar_notas()[:60]]
    corte = ahora() - dt.timedelta(hours=HORAS_MAXIMAS)

    candidatos, nuevos_vistos = [], {}
    for fuente in cfg.get("fuentes", []):
        try:
            items = leer_feed(fuente)
        except Exception as e:
            log(f"RSS: no pude leer «{fuente['nombre']}»: {e}")
            continue
        for it in items:
            h = huella(normalizar(it["titulo"]))
            if h in vistos or h in nuevos_vistos:
                continue
            nuevos_vistos[h] = ahora_iso()
            if parsear_fecha(it["fecha"]) < corte:
                continue
            texto = normalizar(it["titulo"] + " " + it["resumen"])
            if claves and not any(k in texto for k in claves):
                continue
            if any(parecido(it["titulo"], r) > 0.6 for r in recientes):
                continue
            if any(parecido(it["titulo"], c["titulo"]) > 0.8 for c in candidatos):
                continue
            candidatos.append(it)

    log(f"RSS: {len(candidatos)} titulares nuevos sobre Boca")
    if not candidatos:
        guardar_json(ARCHIVO_VISTOS, {**vistos, **nuevos_vistos})
        return 0
    if not ia.disponible():
        log("RSS: falta GEMINI_API_KEY, no puedo redactar. Los titulares se vuelven a intentar la próxima vez.")
        return 0

    cupo = min(cfg.get("max_notas_por_corrida", 3), cfg.get("max_notas_por_dia", 25) - notas_de_hoy())
    if cupo <= 0:
        log("RSS: se alcanzó el máximo de notas automáticas del día.")
        guardar_json(ARCHIVO_VISTOS, {**vistos, **nuevos_vistos})
        return 0

    candidatos = candidatos[:20]  # menos titulares por corrida: la IA responde más rápido y gasta menos cupo gratis
    publicadas = 0
    try:
        temas = ia.seleccionar_noticias(candidatos, recientes, cupo)
    except ia.IAError as e:
        log(f"RSS: {e}")
        return 0  # no marco como vistos: se reintenta en la próxima corrida

    for tema in temas[:cupo]:
        idx = [i for i in tema.get("indices", []) if isinstance(i, int) and 0 <= i < len(candidatos)]
        if not idx:
            continue
        material = []
        for i in idx[:4]:
            c = candidatos[i]
            material.append({**c, "texto": texto_del_articulo(c["link"])})
        try:
            r = ia.redactar_desde_fuentes(material)
            nota = armar_nota(r, origen="rss", fuentes=[{"nombre": m["fuente"], "url": m["link"]} for m in material])
        except ia.IAError as e:
            log(f"RSS: no se pudo redactar «{material[0]['titulo']}»: {e}")
            continue
        if cfg.get("modo") == "aprobacion":
            ruta = guardar_nota(nota, BORRADORES)
            try:
                import bot_telegram
                bot_telegram.pedir_aprobacion(nota)
            except Exception as e:
                log(f"RSS: borrador guardado pero no pude avisar por Telegram: {e}")
            log(f"RSS: borrador para aprobar → {ruta.name}")
        else:
            ruta = guardar_nota(nota)
            log(f"RSS: ✅ publicada → {ruta.name}")
        publicadas += 1

    guardar_json(ARCHIVO_VISTOS, {**vistos, **nuevos_vistos})
    return publicadas


def armar_nota(r: dict, *, origen: str, fuentes: list | None = None, **extra) -> dict:
    from ia import CATEGORIAS

    cuerpo = r.get("cuerpo") or []
    if isinstance(cuerpo, str):
        cuerpo = [p.strip() for p in cuerpo.split("\n") if p.strip()]
    estado = (r.get("estado") or "confirmado").lower()
    if estado not in ("oficial", "confirmado", "rumor"):
        estado = "confirmado"
    categoria = r.get("categoria") if r.get("categoria") in CATEGORIAS else "Actualidad"
    nota = {
        "id": uuid.uuid4().hex[:12],
        "titulo": (r.get("titulo") or "").strip(),
        "bajada": (r.get("bajada") or "").strip(),
        "cuerpo": [str(p).strip() for p in cuerpo if str(p).strip()],
        "categoria": categoria,
        "estado": estado,
        "etiquetas": [str(e) for e in (r.get("etiquetas") or [])][:6],
        "fuentes": fuentes or [],
        "origen": origen,
        "fecha": ahora_iso(),
    }
    nota.update({k: v for k, v in extra.items() if v})
    if not nota["titulo"] or not nota["cuerpo"]:
        raise ia.IAError("La IA devolvió una nota vacía.")
    return nota


if __name__ == "__main__":
    ejecutar()
