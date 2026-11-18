"""Notas automáticas de partidos: la previa (el día anterior) y el resultado (al terminar).

Se escriben solo con datos reales del partido (fecha, estadio, goles, historial), nunca inventados.
"""
from __future__ import annotations

import datetime as dt

import ia
from comun import DATOS_ESPN, ESTADO, ahora, config, fecha_larga, guardar_json, guardar_nota, hora, leer_json, log, parsear_fecha
from datos_futbol import proximos_y_ultimos, resumen_partido
from noticias_rss import armar_nota

ARCHIVO = ESTADO / "cronicas.json"


def _forma(jugados: list[dict], n: int = 5) -> list[str]:
    return [f"{p['resultado']} {p['goles_boca']}-{p['goles_rival']} vs {p['rival']['nombre']} ({p['competencia']})"
            for p in jugados[:n]]


def _historial(rival_id: str) -> dict | None:
    h = leer_json(DATOS_ESPN / "historial.json", {}).get(rival_id)
    if not h:
        return None
    return {"desde": h["desde"], "pj": h["pj"], "ganados_boca": h["g"], "empates": h["e"], "ganados_rival": h["p"],
            "ultimo": h["partidos"][0] if h["partidos"] else None}


def _posicion(slug: str) -> str | None:
    tabla = leer_json(DATOS_ESPN / "posiciones.json", {}).get(slug)
    if not tabla:
        return None
    for g in tabla["grupos"]:
        for f in g["filas"]:
            if f.get("es_boca"):
                return f"{f['pos']}° en {g['nombre']} con {f.get('pts')} puntos"
    return None


def ejecutar() -> int:
    cfg = config()["datos_futbol"]
    if not cfg.get("activado") or not ia.disponible():
        return 0
    hechas = leer_json(ARCHIVO, {"previas": [], "cronicas": []})
    proximos, jugados = proximos_y_ultimos()
    publicadas = 0

    # --- Crónica: partidos terminados en las últimas 18 horas
    if cfg.get("cronicas_automaticas"):
        for p in jugados[:3]:
            fecha = parsear_fecha(p["fecha"])
            if (p["id"] in hechas["cronicas"] or not fecha or p["resultado"] is None
                    or ahora() - fecha > dt.timedelta(hours=18)):
                continue
            datos = {
                "competencia": p["competencia"], "instancia": p.get("instancia"),
                "fecha": fecha_larga(fecha), "estadio": p["estadio"],
                "condicion": "local" if p["condicion"] == "L" else "visitante",
                "local": p["local"]["nombre"], "visitante": p["visitante"]["nombre"],
                "resultado_final": f"{p['local']['nombre']} {p['local']['goles']} - {p['visitante']['goles']} {p['visitante']['nombre']}",
                "resultado_para_boca": {"G": "victoria", "E": "empate", "P": "derrota"}[p["resultado"]],
            }
            if p.get("penales_boca") is not None:
                datos["penales"] = f"Boca {p['penales_boca']} - {p['penales_rival']} {p['rival']['nombre']}"
            try:
                datos.update(resumen_partido(p["id"], p["competencia_slug"]))
            except Exception as e:
                log(f"Crónicas: sin detalle de goles ({e})")
            if pos := _posicion(p["competencia_slug"]):
                datos["posicion_actual_de_boca"] = pos
            try:
                nota = armar_nota(ia.redactar_cronica(datos), origen="cronica", partido_id=p["id"])
            except ia.IAError as e:
                log(f"Crónicas: {e}")
                continue
            nota["categoria"], nota["estado"] = "Partido", "oficial"
            guardar_nota(nota)
            hechas["cronicas"].append(p["id"])
            publicadas += 1
            log(f"Crónicas: ✅ resultado publicado → {nota['slug']}")

    # --- Previa: el próximo partido, entre 30 y 6 horas antes
    if cfg.get("previas_automaticas") and proximos:
        p = proximos[0]
        fecha = parsear_fecha(p["fecha"])
        faltan = fecha - ahora()
        if (p["id"] not in hechas["previas"] and dt.timedelta(hours=6) < faltan < dt.timedelta(hours=30)
                and not p.get("hora_a_confirmar")):
            datos = {
                "competencia": p["competencia"], "instancia": p.get("instancia"),
                "rival": p["rival"]["nombre"], "condicion": "local" if p["condicion"] == "L" else "visitante",
                "dia": fecha_larga(fecha), "hora": hora(fecha) + " (hora argentina)",
                "estadio": p["estadio"], "ultimos_resultados_de_boca": _forma(jugados),
            }
            if h := _historial(p["rival"]["id"]):
                datos["historial_reciente_contra_el_rival"] = h
            try:
                import historia_de_boca
                if t := historia_de_boca.total_actualizado(p["rival"], leer_json(DATOS_ESPN / "partidos.json", [])):
                    datos["historial_total_en_ligas_de_afa"] = {
                        "partidos": t["pj"], "ganados_boca": t["g"], "empates": t["e"], "ganados_rival": t["p"],
                        "fuente": "Historia de Boca (mencionala si usás este dato)"}
            except Exception as e:
                log(f"Crónicas: sin historial total ({e})")
            if pos := _posicion(p["competencia_slug"]):
                datos["posicion_actual_de_boca"] = pos
            try:
                nota = armar_nota(ia.redactar_previa(datos), origen="previa", partido_id=p["id"])
                nota["categoria"], nota["estado"] = "Partido", "oficial"
                guardar_nota(nota)
                hechas["previas"].append(p["id"])
                publicadas += 1
                log(f"Crónicas: ✅ previa publicada → {nota['slug']}")
            except ia.IAError as e:
                log(f"Crónicas: {e}")

    hechas = {k: v[-60:] for k, v in hechas.items()}
    guardar_json(ARCHIVO, hechas)
    return publicadas


if __name__ == "__main__":
    ejecutar()
