"""Conexión con la IA (Google Gemini, plan gratuito) y las instrucciones de redacción.

Clave necesaria: GEMINI_API_KEY (se saca gratis en https://aistudio.google.com/apikey).
"""
from __future__ import annotations

import json
import re
import time

from comun import ESTADO, config, guardar_json, http_get_json, http_post_json, leer_json, log, secreto

BASE = "https://generativelanguage.googleapis.com/v1beta"
_ultimo_llamado = 0.0
PAUSA_ENTRE_LLAMADOS = 7  # segundos: el plan gratis limita pedidos por minuto

CATEGORIAS = ["Actualidad", "Mercado de pases", "Partido", "Plantel", "Juveniles", "Institucional",
              "Fútbol femenino", "Historia"]


class IAError(RuntimeError):
    pass


def disponible() -> bool:
    return bool(secreto("GEMINI_API_KEY"))


# ------------------------------------------------------------ elegir modelo --
def _candidatos_modelo() -> list[str]:
    elegido = config()["ia"].get("modelo", "").strip()
    if elegido:
        return [elegido]
    cache = leer_json(ESTADO / "ia_modelos.json", {})
    if cache.get("modelos") and cache.get("fecha", "") >= time.strftime("%Y-%m-%d", time.gmtime(time.time() - 7 * 86400)):
        return cache["modelos"]

    clave = secreto("GEMINI_API_KEY")
    datos = http_get_json(f"{BASE}/models?pageSize=1000&key={clave}")
    nombres = []
    for m in datos.get("models", []):
        nombre = m.get("name", "").replace("models/", "")
        metodos = m.get("supportedGenerationMethods", [])
        n = nombre.lower()
        if "generateContent" not in metodos or "gemini" not in n:
            continue
        if any(x in n for x in ("pro", "image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer")):
            continue
        nombres.append(nombre)
    # El plan gratis cubre los modelos "flash": si hay alguno, se usan solo esos (los demás suelen dar cupo 0).
    flash = [x for x in nombres if "flash" in x.lower()]
    nombres = flash or nombres

    def puntaje(nombre: str):
        n = nombre.lower()
        version = [int(x) for x in re.findall(r"(\d+)", n.split("-flash")[0])[:2]] or [0]
        estable = 0 if ("preview" in n or "exp" in n) else 1
        lite = 1 if "lite" in n else 0
        latest = 1 if "latest" in n else 0
        return (estable, version, latest, -lite)

    nombres.sort(key=puntaje, reverse=True)
    if not nombres:
        raise IAError("No encontré modelos Gemini Flash disponibles para tu clave.")
    guardar_json(ESTADO / "ia_modelos.json", {"fecha": time.strftime("%Y-%m-%d"), "modelos": nombres[:6]})
    log("IA: modelos candidatos →", ", ".join(nombres[:3]))
    return nombres[:6]


# --------------------------------------------------------------- llamado --
def generar_json(instrucciones: str, pedido: str, *, temperatura: float = 0.6) -> dict:
    """Le pide a Gemini una respuesta en JSON y la devuelve como diccionario."""
    global _ultimo_llamado
    clave = secreto("GEMINI_API_KEY")
    if not clave:
        raise IAError("Falta la clave GEMINI_API_KEY.")

    cuerpo = {
        "systemInstruction": {"parts": [{"text": instrucciones}]},
        "contents": [{"role": "user", "parts": [{"text": pedido}]}],
        "generationConfig": {"temperature": temperatura, "responseMimeType": "application/json"},
    }
    errores = []
    for modelo in _candidatos_modelo():
        for intento in range(2):
            espera = PAUSA_ENTRE_LLAMADOS - (time.time() - _ultimo_llamado)
            if espera > 0:
                time.sleep(espera)
            _ultimo_llamado = time.time()
            try:
                r = http_post_json(f"{BASE}/models/{modelo}:generateContent?key={clave}", cuerpo)
                texto = r["candidates"][0]["content"]["parts"][0]["text"]
                return _parsear_json(texto)
            except RuntimeError as e:
                msg = str(e)
                errores.append(f"{modelo}: {msg[:160]}")
                if "429" in msg and any(x in msg for x in ("limit: 0", "PerDay", "per day", "free_tier")) and "PerMinute" not in msg:
                    log(f"IA: {modelo} sin cupo gratis disponible, pruebo otro modelo")
                    break
                if "429" in msg and intento == 0:
                    log("IA: límite por minuto alcanzado, espero 40 s…")
                    time.sleep(40)
                    continue
                break  # probar con el siguiente modelo
            except (KeyError, IndexError, ValueError) as e:
                errores.append(f"{modelo}: respuesta inesperada ({e})")
                break
    raise IAError("La IA no respondió. " + " | ".join(errores[-3:]))


def _parsear_json(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.M).strip()
    return json.loads(texto)


# ------------------------------------------------------------ instrucciones --
def _base_editorial() -> str:
    tono = config()["ia"]["tono"]
    return f"""Sos el redactor de "{config()['sitio']['nombre']}". {tono}

REGLAS QUE NO SE NEGOCIAN:
- Usá SOLO la información que te paso. No agregues nombres, fechas, cifras, lesiones, montos ni frases entre comillas que no estén en el material.
- No copies oraciones del material: redactá todo con tus palabras.
- Si el material habla de algo no confirmado (sondeo, interés, "podría", "se habla de", trascendido de un periodista), la nota es un RUMOR y tiene que decirlo con claridad.
- Si la fuente es el club o un comunicado oficial, es OFICIAL. Si lo informan medios como hecho, es CONFIRMADO.
- Títulos con gancho pero honestos: nada de clickbait engañoso.
- Español rioplatense. Párrafos cortos (2 a 4 oraciones)."""


FORMATO_NOTA = """Devolvé SOLO este JSON:
{
  "titulo": "máximo 90 caracteres",
  "bajada": "una o dos oraciones que resumen la noticia",
  "cuerpo": ["párrafo 1", "párrafo 2", "..."],
  "categoria": "una de: """ + ", ".join(CATEGORIAS) + """",
  "estado": "oficial | confirmado | rumor",
  "etiquetas": ["2 a 5 temas o nombres propios clave"]
}
Largo del cuerpo: entre 3 y 6 párrafos, según cuánta información haya. Si hay poca información, hacé una nota corta: es preferible a rellenar."""


def seleccionar_noticias(candidatos: list[dict], titulos_recientes: list[str], maximo: int) -> list[dict]:
    """Agrupa titulares sobre el mismo tema y elige cuáles merecen nota."""
    instrucciones = _base_editorial() + """

Tu tarea ahora es de EDITOR: recibís titulares de distintos medios y decidís qué publicar."""
    lista = "\n".join(f"[{i}] ({c['fuente']}) {c['titulo']} — {c.get('resumen', '')[:220]}" for i, c in enumerate(candidatos))
    recientes = "\n".join(f"- {t}" for t in titulos_recientes[:40]) or "(ninguna)"
    pedido = f"""TITULARES NUEVOS:
{lista}

NOTAS QUE YA PUBLICAMOS (no repetir el mismo tema salvo que haya un dato nuevo importante):
{recientes}

1. Descartá lo que no sea sobre Boca Juniors (primera, reserva, femenino o institucional), lo que sea apuestas, publicidad, otro deporte que no sea fútbol, u opinión sin hechos.
2. Agrupá los titulares que hablan del MISMO hecho.
3. Elegí como máximo {maximo} temas, los más importantes primero.

Devolvé SOLO este JSON:
{{"temas": [{{"indices": [números de los titulares del tema], "motivo": "por qué vale la pena, en 10 palabras"}}]}}
Si nada vale la pena, devolvé {{"temas": []}}."""
    r = generar_json(instrucciones, pedido, temperatura=0.2)
    return r.get("temas", [])


def redactar_desde_fuentes(material: list[dict]) -> dict:
    """material: lista de {fuente, titulo, resumen, texto}"""
    partes = []
    for m in material:
        partes.append(f"FUENTE: {m['fuente']}\nTÍTULO: {m['titulo']}\nRESUMEN: {m.get('resumen', '')}\nTEXTO: {m.get('texto', '')[:3500]}")
    pedido = "MATERIAL:\n\n" + "\n\n---\n\n".join(partes) + "\n\n" + FORMATO_NOTA
    return generar_json(_base_editorial(), pedido)


def redactar_desde_mensaje(texto_usuario: str, tweet: dict | None) -> dict:
    """Nota a partir de lo que alguien del equipo mandó al bot (y el tweet, si había link)."""
    extra = ""
    if tweet:
        extra = f"\n\nTWEET DE REFERENCIA (de @{tweet.get('autor', '?')}):\n{tweet.get('texto', '')}"
    pedido = f"""Alguien del equipo nos pasó esto para que lo conviertas en nota. Lo que escribe la persona del equipo es nuestra información (puede incluir contexto o confirmar algo).

MENSAJE DEL EQUIPO:
{texto_usuario or '(sin texto, solo el tweet)'}{extra}

Si el tweet es de un periodista o hincha y nadie lo confirma, tratalo como RUMOR y mencioná quién lo dijo ("según informó…").
{FORMATO_NOTA}
Agregá además el campo "es_noticia": false si el material no alcanza para una nota (por ejemplo, es un chiste o un saludo)."""
    return generar_json(_base_editorial(), pedido)


def redactar_cronica(datos_partido: dict) -> dict:
    pedido = f"""Escribí la crónica breve de este partido de Boca a partir de estos DATOS (son exactos, no agregues otros):
{json.dumps(datos_partido, ensure_ascii=False, indent=1)}

No inventes jugadas, sensaciones del DT ni declaraciones. Podés comentar qué significa el resultado en la tabla solo si el dato está incluido.
{FORMATO_NOTA}
La categoría es "Partido" y el estado es "oficial"."""
    return generar_json(_base_editorial(), pedido, temperatura=0.5)


def redactar_previa(datos_partido: dict) -> dict:
    pedido = f"""Escribí la previa de este partido de Boca a partir de estos DATOS (son exactos, no agregues otros; no inventes formaciones ni bajas):
{json.dumps(datos_partido, ensure_ascii=False, indent=1)}

Incluí día, hora, estadio y competencia, y si hay historial o forma reciente, usalo.
{FORMATO_NOTA}
La categoría es "Partido" y el estado es "oficial"."""
    return generar_json(_base_editorial(), pedido, temperatura=0.5)
