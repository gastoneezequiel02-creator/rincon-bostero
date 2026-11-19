"""Banco de imágenes propio del Rincón.

El equipo manda fotos por Telegram con /banco y una descripción ("Paredes festejando un gol en la Bombonera").
Se guardan en sitio/estatico/img/banco/ y en datos/manual/banco_imagenes.json, y las notas las usan cuando
el tema coincide con la descripción. Las marcadas como "general" (hinchada, estadio, camiseta…) sirven para
cualquier nota sin foto mejor, rotando para que no se repitan.

Solo van fotos propias o con permiso de su autor: nada de fotos de diarios ni de agencias.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from comun import DATOS_MANUAL, SITIO, ahora, guardar_json, leer_json, normalizar, parsear_fecha

ARCHIVO = DATOS_MANUAL / "banco_imagenes.json"
CARPETA = SITIO / "estatico" / "img" / "banco"
DIAS_SIN_REPETIR = 2      # una foto usada hace menos de esto se evita si hay otra que sirva
PUNTAJE_MINIMO = 3        # una palabra en común con el título vale 3; con la bajada o las etiquetas, 1

VACIAS = set("""boca juniors xeneize xeneizes bostero bosteros club equipo plantel para como desde hasta sobre entre
ante tras contra pero porque cuando donde este esta estos estas ese esos esas fueron sera seria tiene tienen hace hacia
todo todos toda todas mucho muy mas menos tambien solo cada otro otra otros otras despues antes ahora luego dijo
segun foto fotos imagen general partido""".split())


def cargar() -> list[dict]:
    return (leer_json(ARCHIVO, {}) or {}).get("imagenes", [])


def guardar(lista: list[dict]) -> None:
    guardar_json(ARCHIVO, {
        "_que_es": "Banco de imágenes propio. Se carga por Telegram con /banco. 'general': sirve para cualquier nota. "
                   "Solo fotos propias o con permiso de su autor.",
        "imagenes": lista})


def raices(texto: str) -> set[str]:
    """Palabras con contenido, recortadas a su raíz (festeja/festejo/festejando → festej)."""
    return {p[:6] for p in re.findall(r"[a-z0-9]{4,}", normalizar(texto or "")) if p not in VACIAS}


def nuevo_id(contenido: bytes) -> str:
    return hashlib.sha1(contenido).hexdigest()[:8]


def agregar(id_: str, archivo: str, descripcion: str, credito: str = "", general: bool = False) -> dict:
    lista = [x for x in cargar() if x["id"] != id_]
    img = {"id": id_, "archivo": archivo, "descripcion": descripcion.strip()[:300], "credito": credito.strip()[:120],
           "general": general, "cargada": ahora().isoformat(timespec="minutes"), "usos": 0, "ultimo_uso": ""}
    lista.append(img)
    guardar(lista)
    return img


def borrar(id_: str) -> dict | None:
    lista = cargar()
    img = next((x for x in lista if x["id"] == id_), None)
    if not img:
        return None
    guardar([x for x in lista if x["id"] != id_])
    (SITIO / "estatico" / img["archivo"]).unlink(missing_ok=True)
    return img


def _reciente(img: dict) -> bool:
    d = parsear_fecha(img.get("ultimo_uso") or "")
    return bool(d) and ahora() - d < dt.timedelta(days=DIAS_SIN_REPETIR)


def _puntaje(img: dict, nota: dict) -> int:
    """Cada palabra de la descripción que aparece en el título o entre los protagonistas vale 3;
    si solo aparece en la bajada o las etiquetas, 1."""
    desc = raices(img.get("descripcion", ""))
    fuerte = raices(" ".join([nota.get("titulo", ""), " ".join(nota.get("protagonistas") or [])]))
    debil = raices(" ".join([nota.get("bajada", ""), " ".join(nota.get("etiquetas") or [])]))
    return 3 * len(desc & fuerte) + len((desc - fuerte) & debil)


def elegir(nota: dict, general: bool = False) -> dict | None:
    """Una foto del banco para la nota: las específicas si el tema coincide; con general=True, las generales.
    Deja anotado el uso para rotarlas."""
    lista = cargar()
    if general:
        candidatas = [(0, x) for x in lista if x.get("general")]
    else:
        candidatas = [(_puntaje(x, nota), x) for x in lista if not x.get("general")]
        candidatas = [c for c in candidatas if c[0] >= PUNTAJE_MINIMO]
    candidatas = [c for c in candidatas if (SITIO / "estatico" / c[1]["archivo"]).exists()]
    if not candidatas:
        return None
    frescas = [c for c in candidatas if not _reciente(c[1])]
    if not frescas:
        return None  # todas las que sirven se usaron hace poco: mejor otra foto que repetir
    candidatas = frescas
    puntos, img = sorted(candidatas, key=lambda c: (-c[0], c[1].get("usos", 0), c[1].get("ultimo_uso", "")))[0]
    img["usos"] = img.get("usos", 0) + 1
    img["ultimo_uso"] = ahora().isoformat(timespec="minutes")
    guardar(lista)
    credito = f"Foto: {img['credito']}" if img.get("credito") else "Foto: archivo del Rincón Bostero"
    return {"imagen": img["archivo"], "credito": credito}
