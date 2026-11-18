"""Funciones compartidas: rutas, configuración, HTTP, archivos JSON, fechas y textos.

Todo usa solo la biblioteca estándar de Python: no hace falta instalar nada.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONTENIDO = RAIZ / "contenido"
NOTAS = CONTENIDO / "notas"
BORRADORES = CONTENIDO / "borradores"
DATOS = RAIZ / "datos"
DATOS_ESPN = DATOS / "espn"
DATOS_MANUAL = DATOS / "manual"
ESTADO = RAIZ / "estado"
SITIO = RAIZ / "sitio"
IMAGENES_NOTAS = SITIO / "estatico" / "img" / "notas"

USER_AGENT = "Mozilla/5.0 (compatible; RinconBosteroBot/1.0; +https://github.com)"


# ----------------------------------------------------------------- registro --
def log(*partes) -> None:
    hora = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{hora}]", *partes, flush=True)


# ------------------------------------------------------------ configuración --
_config_cache: dict | None = None


def config() -> dict:
    global _config_cache
    if _config_cache is None:
        _config_cache = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    return _config_cache


def secreto(nombre: str) -> str:
    """Lee una clave de las variables de entorno (en GitHub: Settings > Secrets)."""
    return os.environ.get(nombre, "").strip()


# ------------------------------------------------------------------- JSON --
def leer_json(ruta: Path, por_defecto=None):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return por_defecto
    except json.JSONDecodeError as e:
        log(f"⚠️  JSON roto en {ruta}: {e}")
        return por_defecto


def guardar_json(ruta: Path, datos) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)


# ------------------------------------------------------------------- HTTP --
def http_get(url: str, *, intentos: int = 3, timeout: int = 25, headers: dict | None = None) -> bytes:
    h = {"User-Agent": USER_AGENT, "Accept-Language": "es-AR,es;q=0.9"}
    if headers:
        h.update(headers)
    ultimo_error = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            ultimo_error = e
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # red caída, timeout, etc.
            ultimo_error = e
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo_error}")


def http_get_json(url: str, **kw):
    return json.loads(http_get(url, **kw).decode("utf-8"))


def http_post_json(url: str, cuerpo, *, timeout: int = 60, headers: dict | None = None):
    datos = json.dumps(cuerpo).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=datos, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")[:500]
        raise RuntimeError(f"HTTP {e.code} en {url.split('?')[0]}: {detalle}") from None


# ------------------------------------------------------------------ fechas --
def zona() -> dt.timezone:
    return dt.timezone(dt.timedelta(hours=config()["sitio"].get("zona_horaria_utc", -3)))


def ahora() -> dt.datetime:
    return dt.datetime.now(zona())


def ahora_iso() -> str:
    return ahora().isoformat(timespec="seconds")


def parsear_fecha(texto: str | None) -> dt.datetime | None:
    if not texto:
        return None
    t = texto.strip()
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        # ESPN a veces manda "2026-11-20T23:00Z"
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+00:00$", t):
            t = t.replace("+00:00", ":00+00:00")
        d = dt.datetime.fromisoformat(t)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(zona())
    except ValueError:
        pass
    try:  # formato RSS: "Wed, 18 Nov 2026 15:04:00 GMT"
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(t).astimezone(zona())
    except Exception:
        return None


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_larga(d: dt.datetime) -> str:
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]}"


def fecha_corta(d: dt.datetime) -> str:
    return f"{d.day} {MESES_CORTOS[d.month - 1]}"


def hora(d: dt.datetime) -> str:
    return d.strftime("%H:%M")


def hace_cuanto(d: dt.datetime) -> str:
    seg = (ahora() - d).total_seconds()
    if seg < 60:
        return "recién"
    if seg < 3600:
        return f"hace {int(seg // 60)} min"
    if seg < 86400:
        h = int(seg // 3600)
        return f"hace {h} h"
    dias = int(seg // 86400)
    if dias == 1:
        return "ayer"
    if dias < 7:
        return f"hace {dias} días"
    return fecha_corta(d)


# ------------------------------------------------------------------ textos --
def slugify(texto: str, largo: int = 80) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:largo].rstrip("-") or "nota"


def huella(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip().lower()


def limpiar_html(html: str) -> str:
    import html as html_mod

    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html or "")
    t = re.sub(r"(?s)<br\s*/?>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    return re.sub(r"[ \t\r\f\v]+", " ", t).strip()


# ------------------------------------------------------------------- notas --
def listar_notas(carpeta: Path = NOTAS) -> list[dict]:
    notas = []
    for f in carpeta.glob("*.json"):
        n = leer_json(f)
        if n:
            notas.append(n)
    notas.sort(key=lambda n: n.get("fecha", ""), reverse=True)
    return notas


def guardar_nota(nota: dict, carpeta: Path = NOTAS) -> Path:
    """Guarda una nota asegurando un slug único. Devuelve la ruta."""
    base = nota.get("slug") or slugify(nota["titulo"])
    slug = base
    i = 2
    while (carpeta / f"{slug}.json").exists() and leer_json(carpeta / f"{slug}.json", {}).get("id") != nota.get("id"):
        slug = f"{base}-{i}"
        i += 1
    nota["slug"] = slug
    ruta = carpeta / f"{slug}.json"
    guardar_json(ruta, nota)
    return ruta


def notas_de_hoy() -> int:
    hoy = ahora().date().isoformat()
    return sum(1 for n in listar_notas() if n.get("fecha", "").startswith(hoy) and n.get("origen") == "rss")


if __name__ == "__main__":
    print("RAIZ:", RAIZ, file=sys.stderr)
