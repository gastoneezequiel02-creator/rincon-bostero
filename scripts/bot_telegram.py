"""Opción 2: el bot de Telegram. Alguien del equipo le reenvía un tweet (o el link, o un texto)
y el bot lo convierte en una nota propia y la publica.

También maneja los botones Publicar / Descartar cuando las notas de RSS están en modo "aprobacion".

Clave necesaria: TELEGRAM_BOT_TOKEN (se crea gratis hablando con @BotFather en Telegram).
No hace falta un servidor: cada vez que corre la automatización (cada ~15 min) el bot lee los
mensajes pendientes y responde.
"""
from __future__ import annotations

import hashlib
import re
import time
import urllib.parse

import ia
from comun import (BORRADORES, ESTADO, IMAGENES_NOTAS, NOTAS, config, guardar_json, guardar_nota, http_get,
                   http_get_json, http_post_json, leer_json, limpiar_html, listar_notas, log, parsear_fecha, secreto)
from noticias_rss import armar_nota

ARCHIVO_ESTADO = ESTADO / "telegram.json"
RE_URL = re.compile(r"https?://\S+")
RE_TWEET = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")
RE_SLUG_EN_LINK = re.compile(r"/notas/([a-z0-9-]+)\.html")

AYUDA = """👋 Soy el bot de {nombre}.

Para publicar una nota, mandame:
• El link de un tweet (x.com/…/status/…), o reenviame el mensaje.
• Opcional: agregá tu propio texto con más datos o contexto.
• Opcional: una foto (propia o con permiso) y la uso como imagen de la nota.
  (Una foto con un texto corto y sin link la guardo en el banco de fotos, no hago nota.)

Para marcar cómo es la info, empezá el mensaje con:
#oficial · #confirmado · #rumor

Para cambiarle la foto a una nota ya publicada:
• Mandame la foto con el texto /foto → va en la última nota.
• /foto nombre-de-la-nota → va en esa nota (los nombres salen en /ultimas).
• O respondé con la foto y /foto a mi mensaje de esa nota.
• Si querés, agregá el crédito al final: /foto nombre-de-la-nota Foto: Juan Pérez

Banco de fotos (las notas las usan cuando el tema coincide):
• Mandame la foto con /banco y qué se ve: /banco Paredes festejando un gol en la Bombonera
• Con /banco general sirve para cualquier nota: /banco general Hinchada con banderas en la Bombonera
• Crédito al final: … Foto: Juan Pérez
• Solo fotos propias o con permiso del autor (nada de diarios ni agencias).
• /banco solo te muestra las últimas; /banco borrar ID saca una.

Comandos:
/ultimas – las últimas 5 notas
/borrar nombre-de-la-nota – despublica una nota
/id – te digo tu ID de Telegram

⏱️ Respondo cada vez que corre la automatización (cada 15 minutos aprox.)."""


def _api(metodo: str, **params):
    token = secreto("TELEGRAM_BOT_TOKEN")
    return http_post_json(f"https://api.telegram.org/bot{token}/{metodo}", params)


def responder(chat_id: int, texto: str, **extra):
    try:
        _api("sendMessage", chat_id=chat_id, text=texto, disable_web_page_preview=True, **extra)
    except Exception as e:
        log(f"Telegram: no pude responder a {chat_id}: {e}")


def url_nota(nota: dict) -> str:
    return f"{config()['sitio']['url'].rstrip('/')}/notas/{nota['slug']}.html"


# --------------------------------------------------------------- tweets --
def leer_tweet(url: str) -> dict | None:
    """Usa el 'embed' público de X (gratis, sin clave) para obtener el texto del tweet."""
    m = RE_TWEET.search(url)
    if not m:
        return None
    url_limpia = f"https://twitter.com/{m.group(1)}/status/{m.group(2)}"
    try:
        datos = http_get_json("https://publish.twitter.com/oembed?omit_script=true&dnt=true&url="
                              + urllib.parse.quote(url_limpia, safe=""))
    except Exception as e:
        log(f"Telegram: no pude leer el tweet {url_limpia}: {e}")
        return {"url": url_limpia, "autor": m.group(1), "texto": ""}
    cuerpo = re.search(r"(?is)<p[^>]*>(.*?)</p>", datos.get("html", ""))
    texto = limpiar_html(cuerpo.group(1)) if cuerpo else ""
    return {"url": url_limpia, "autor": m.group(1), "nombre": datos.get("author_name", ""), "texto": texto}


# --------------------------------------------------------------- fotos --
def fotos_del_mensaje(msg: dict) -> list[dict]:
    """La foto del mensaje: la comprimida de Telegram o una imagen mandada como archivo."""
    if msg.get("photo"):
        return msg["photo"]
    doc = msg.get("document") or {}
    if str(doc.get("mime_type", "")).startswith("image/"):
        return [doc]
    return []


def bajar_foto(fotos: list[dict], nombre: str, carpeta=None) -> str | None:
    if not fotos:
        return None
    carpeta = carpeta or IMAGENES_NOTAS
    mayor = max(fotos, key=lambda f: f.get("file_size", 0) or f.get("width", 0))
    try:
        info = _api("getFile", file_id=mayor["file_id"])
        ruta = info["result"]["file_path"]
        token = secreto("TELEGRAM_BOT_TOKEN")
        contenido = http_get(f"https://api.telegram.org/file/bot{token}/{ruta}")
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{nombre}.jpg"
        destino.write_bytes(contenido)
        return f"img/{carpeta.name}/{destino.name}"
    except Exception as e:
        log(f"Telegram: no pude bajar la foto: {e}")
        return None


# ------------------------------------------------------------ aprobación --
def pedir_aprobacion(nota: dict) -> None:
    usuarios = config()["telegram"].get("usuarios_permitidos", [])
    if not secreto("TELEGRAM_BOT_TOKEN") or not usuarios:
        raise RuntimeError("falta TELEGRAM_BOT_TOKEN o usuarios_permitidos")
    texto = (f"📝 Nota nueva para revisar ({nota['estado'].upper()})\n\n"
             f"{nota['titulo']}\n\n{nota['bajada']}\n\n{nota['cuerpo'][0]}\n\n"
             f"Fuentes: {', '.join(f['nombre'] for f in nota.get('fuentes', []))}")
    botones = {"inline_keyboard": [[
        {"text": "✅ Publicar", "callback_data": f"pub:{nota['id']}"},
        {"text": "🗑️ Descartar", "callback_data": f"desc:{nota['id']}"},
    ]]}
    for u in usuarios:
        responder(u, texto[:4000], reply_markup=botones)


def _buscar_borrador(nota_id: str):
    for f in BORRADORES.glob("*.json"):
        n = leer_json(f, {})
        if n.get("id") == nota_id:
            return f, n
    return None, None


def procesar_boton(cb: dict) -> None:
    accion, _, nota_id = (cb.get("data") or "").partition(":")
    archivo, nota = _buscar_borrador(nota_id)
    msg = cb.get("message", {})
    if not archivo:
        resultado = "Esta nota ya fue procesada."
    elif accion == "pub":
        archivo.unlink()
        guardar_nota(nota)
        resultado = f"✅ Publicada: {nota['titulo']}\n{url_nota(nota)}"
    else:
        archivo.unlink()
        resultado = f"🗑️ Descartada: {nota['titulo']}"
    try:
        _api("answerCallbackQuery", callback_query_id=cb["id"])
        _api("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"], text=resultado,
             disable_web_page_preview=True)
    except Exception as e:
        log(f"Telegram: {e}")


# ------------------------------------------------------------- mensajes --
def procesar_mensaje(msg: dict, ya_avisados: set) -> None:
    usuario = msg.get("from", {}).get("id")
    chat_id = msg["chat"]["id"]
    permitidos = {int(u) for u in config()["telegram"].get("usuarios_permitidos", [])}
    texto = (msg.get("text") or msg.get("caption") or "").strip()

    if texto.startswith("/id"):
        responder(chat_id, f"Tu ID de Telegram es: {usuario}")
        return
    if usuario not in permitidos:
        if usuario not in ya_avisados:
            responder(chat_id, f"Hola! Todavía no estás habilitado para cargar notas.\n"
                               f"Tu ID es {usuario}: pasáselo al administrador para que lo agregue.")
            ya_avisados.add(usuario)
        return
    if texto.startswith(("/start", "/ayuda", "/help")):
        responder(chat_id, AYUDA.format(nombre=config()["sitio"]["nombre"]))
        return
    # Álbum: Telegram pone el epígrafe solo en la primera foto; las demás heredan el /banco
    grupo = msg.get("media_group_id")
    if grupo:
        if texto:
            EPIGRAFES_DE_ALBUM[grupo] = texto
        else:
            texto = EPIGRAFES_DE_ALBUM.get(grupo, "")
    # Una foto con un epígrafe corto, sin link ni #oficial/#confirmado/#rumor, es una foto para el banco:
    # no alcanza para una nota y la IA no debe inventarla a partir de la descripción de la foto.
    if fotos_del_mensaje(msg) and not texto.startswith("/") and not RE_URL.search(texto) \
            and not re.search(r"(?i)#(oficial|confirmado|rumor)\b", texto) and len(texto) < 160:
        texto = "/banco " + (texto or "general")
    # Ventana configurable: fotos mandadas sin comando en ese rato van al banco (con su epígrafe como descripción)
    ventana = config()["telegram"].get("fotos_al_banco_entre") or []
    if len(ventana) == 2 and fotos_del_mensaje(msg) and not texto.startswith("/") and not RE_URL.search(texto):
        desde, hasta = (parsear_fecha(x) for x in ventana)
        if desde and hasta and desde.timestamp() <= msg.get("date", 0) <= hasta.timestamp():
            texto = "/banco " + (texto or "general")
    if re.match(r"(?i)/banco(@\w+)?\b", texto):
        cargar_al_banco(msg, chat_id, texto)
        return
    if re.match(r"(?i)/foto(@\w+)?\b", texto):
        cambiar_foto(msg, chat_id, texto)
        return
    if texto.startswith("/ultimas"):
        notas = listar_notas()[:5]
        lista = "\n\n".join(f"• {n['titulo']}\n  /foto {n['slug']}\n  /borrar {n['slug']}" for n in notas) \
            or "No hay notas todavía."
        responder(chat_id, lista)
        return
    if texto.startswith("/borrar"):
        slug = texto.split(maxsplit=1)[1].strip() if len(texto.split()) > 1 else ""
        archivo = NOTAS / f"{slug}.json"
        if slug and archivo.exists():
            archivo.unlink()
            responder(chat_id, f"🗑️ Listo, despubliqué «{slug}». Desaparece de la web en la próxima actualización.")
        else:
            responder(chat_id, "No encontré esa nota. Usá /ultimas para ver los nombres.")
        return

    # Marcas de estado: #oficial #confirmado #rumor
    estado_forzado = None
    for marca in ("oficial", "confirmado", "rumor"):
        if re.search(rf"(?i)#{marca}\b", texto):
            estado_forzado = marca
            texto = re.sub(rf"(?i)#{marca}\b", "", texto).strip()

    tweet = None
    for url in RE_URL.findall(texto):
        tweet = leer_tweet(url)
        if tweet:
            texto = texto.replace(url, "").strip()
            break
    reenviado = msg.get("forward_origin") or msg.get("forward_from_chat")
    if reenviado and not tweet:
        texto = f"(Mensaje reenviado) {texto}"

    if not texto and not (tweet and tweet.get("texto")):
        if tweet:
            responder(chat_id, "No pude leer el texto de ese tweet 😕 Pegame el texto del tweet en el mensaje y lo armo.")
        else:
            responder(chat_id, "Mandame el link de un tweet o un texto con la info para armar la nota. /ayuda")
        return

    if not ia.disponible():
        responder(chat_id, "⚠️ Falta configurar la clave de la IA (GEMINI_API_KEY).")
        return
    try:
        r = ia.redactar_desde_mensaje(texto, tweet if tweet and tweet.get("texto") else None)
    except ia.IAError as e:
        log(f"Telegram: {e}")
        responder(chat_id, "⚠️ La IA no respondió ahora. Reenviame el mensaje en un rato.")
        return
    if r.get("es_noticia") is False:
        responder(chat_id, "🤔 Con eso no me alcanza para una nota. ¿Me pasás más datos?")
        return
    if estado_forzado:
        r["estado"] = estado_forzado

    fuentes = []
    if tweet:
        fuentes.append({"nombre": f"@{tweet['autor']} en X", "url": tweet["url"]})
    try:
        nota = armar_nota(r, origen="telegram", fuentes=fuentes, tweet_url=tweet["url"] if tweet else None)
    except ia.IAError:
        responder(chat_id, "⚠️ No pude armar la nota con eso. Probá agregando más contexto.")
        return
    imagen = bajar_foto(fotos_del_mensaje(msg), nota["id"])
    if imagen:
        nota["imagen"] = imagen
    guardar_nota(nota)
    log(f"Telegram: ✅ publicada → {nota['slug']}")
    responder(chat_id, f"✅ Publicada ({nota['estado']}):\n{nota['titulo']}\n\n"
                       f"Aparece en la web en unos minutos:\n{url_nota(nota)}\n\n"
                       f"¿Algo mal? /borrar {nota['slug']}")


EPIGRAFES_DE_ALBUM: dict[str, str] = {}


def cargar_al_banco(msg: dict, chat_id: int, texto: str) -> None:
    """/banco [general] descripción [Foto: crédito] con una foto; /banco solo lista; /banco borrar ID."""
    import banco_imagenes as banco
    resto = re.sub(r"(?i)^/banco(@\w+)?", "", texto).strip()
    fotos = fotos_del_mensaje(msg)
    m = re.match(r"(?i)borrar\s+([0-9a-f]{6,12})\b", resto)
    if m:
        img = banco.borrar(m.group(1).lower())
        responder(chat_id, f"🗑️ Saqué del banco: {img['descripcion']}" if img else "No encontré esa foto en el banco.")
        return
    if not fotos:
        lista = banco.cargar()
        if not lista:
            responder(chat_id, "El banco de fotos está vacío. Mandame una foto con /banco y qué se ve en ella.")
            return
        ultimas = "\n".join(f"• {x['id']} {'(general) ' if x.get('general') else ''}{x['descripcion'][:70]} · usada {x.get('usos', 0)} veces"
                            for x in lista[-8:][::-1])
        generales = sum(1 for x in lista if x.get("general"))
        responder(chat_id, f"🗂️ Banco de fotos: {len(lista)} ({generales} generales).\n\n{ultimas}\n\nPara sacar una: /banco borrar ID")
        return
    general = bool(re.match(r"(?i)general\b", resto))
    if general:
        resto = re.sub(r"(?i)^general\b[\s:,-]*", "", resto)
    credito = ""
    partes = re.split(r"(?i)\b(?:foto|cr[eé]dito)\s*:\s*", resto)
    if len(partes) > 1:
        resto, credito = " ".join(partes[:-1]).strip(" .-–"), partes[-1].strip()
    descripcion = re.sub(r"\s+", " ", resto).strip()
    if len(descripcion) < 6 and not general:
        responder(chat_id, "Contame qué se ve en la foto, así sé en qué notas usarla.\n"
                           "Ej.: /banco Merentiel festejando un gol ante River\n"
                           "o /banco general Hinchada en la Bombonera")
        return
    id_ = hashlib.sha1(f"{msg.get('message_id')}-{chat_id}-{time.time()}".encode()).hexdigest()[:8]
    archivo = bajar_foto(fotos, id_, carpeta=banco.CARPETA)
    if not archivo:
        responder(chat_id, "⚠️ No pude bajar la foto. Mandala de nuevo en un rato.")
        return
    img = banco.agregar(id_, archivo, descripcion or "Foto general", credito, general)
    log(f"Telegram: 🗂️ foto nueva en el banco ({id_})")
    uso = "cualquier nota sin una foto mejor" if general else "las notas que hablen de eso"
    responder(chat_id, f"🗂️ Guardada en el banco ({img['id']}): {img['descripcion']}\n"
                       f"{'Crédito: ' + img['credito'] if img['credito'] else 'Sin crédito (sale como archivo del Rincón)'}\n"
                       f"La voy a usar en {uso}. Para sacarla: /banco borrar {img['id']}")


def cambiar_foto(msg: dict, chat_id: int, texto: str) -> None:
    """/foto [nombre-de-la-nota] [crédito]: pone la foto del mensaje en una nota ya publicada."""
    fotos = fotos_del_mensaje(msg)
    if not fotos:
        responder(chat_id, "Mandame la foto con el texto /foto (en el epígrafe de la foto).\n"
                           "Va en la última nota, o en la que digas: /foto nombre-de-la-nota\n"
                           "Los nombres de las notas salen en /ultimas.")
        return
    resto = re.sub(r"(?i)^/foto(@\w+)?", "", texto).strip()
    partes = resto.split(maxsplit=1)
    slug = None
    if partes and (NOTAS / f"{partes[0].strip()}.json").exists():
        slug = partes[0].strip()
        resto = partes[1] if len(partes) > 1 else ""
    if not slug:
        # Respondiendo a un mensaje del bot que tiene el link de una nota
        citado = msg.get("reply_to_message") or {}
        enlaces = RE_SLUG_EN_LINK.findall((citado.get("text") or "") + " " + (citado.get("caption") or ""))
        enlaces = [x for x in dict.fromkeys(enlaces) if (NOTAS / f"{x}.json").exists()]
        if len(enlaces) == 1:
            slug = enlaces[0]
    if not slug and partes and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){2,}", partes[0].strip()):
        responder(chat_id, f"No encontré la nota «{partes[0].strip()}». Usá /ultimas para ver los nombres.")
        return
    if not slug:
        notas = listar_notas()
        if not notas:
            responder(chat_id, "Todavía no hay notas publicadas.")
            return
        slug = notas[0]["slug"]

    archivo = NOTAS / f"{slug}.json"
    nota = leer_json(archivo, {})
    if not nota:
        responder(chat_id, "No pude abrir esa nota. Probá de nuevo en un rato.")
        return
    # Nombre nuevo cada vez, así los navegadores no muestran la foto vieja guardada
    imagen = bajar_foto(fotos, f"{nota.get('id', slug)}-{int(time.time())}")
    if not imagen:
        responder(chat_id, "⚠️ No pude bajar la foto. Mandala de nuevo en un rato.")
        return
    anterior = nota.get("imagen", "")
    if anterior.startswith("img/notas/"):
        (IMAGENES_NOTAS / anterior.split("/")[-1]).unlink(missing_ok=True)
    nota["imagen"] = imagen
    credito = re.sub(r"\s+", " ", resto).strip()[:120]
    if credito:
        nota["imagen_credito"] = credito
    else:
        nota.pop("imagen_credito", None)
    guardar_json(archivo, nota)
    log(f"Telegram: 🖼️ foto nueva en {slug}")
    responder(chat_id, f"🖼️ Listo, cambié la foto de:\n{nota['titulo']}\n\n"
                       f"Se ve en la web en la próxima actualización:\n{url_nota(nota)}")


def ejecutar() -> int:
    if not config()["telegram"].get("activado"):
        return 0
    if not secreto("TELEGRAM_BOT_TOKEN"):
        log("Telegram: falta TELEGRAM_BOT_TOKEN, salteo el bot.")
        return 0
    estado = leer_json(ARCHIVO_ESTADO, {"offset": 0})
    try:
        r = _api("getUpdates", offset=estado["offset"], timeout=0, allowed_updates=["message", "callback_query"])
    except Exception as e:
        log(f"Telegram: {e}")
        return 0
    updates = r.get("result", [])
    log(f"Telegram: {len(updates)} mensajes nuevos")
    avisados: set = set()
    for up in updates:
        estado["offset"] = up["update_id"] + 1
        guardar_json(ARCHIVO_ESTADO, estado)  # si algo falla, no se reprocesa el mismo mensaje
        try:
            if "callback_query" in up:
                procesar_boton(up["callback_query"])
            elif "message" in up:
                procesar_mensaje(up["message"], avisados)
        except Exception as e:
            log(f"Telegram: error procesando un mensaje: {e}")
    return len(updates)


if __name__ == "__main__":
    ejecutar()
