"""Préstamos, contratos y valores de mercado del plantel, de «Boca en Números» (Conquista Xeneize), con permiso.

Se baja una vez por día y se guarda reducido en datos/conquista/:
  - prestamos.json: los jugadores cedidos y cómo les va en el club de destino.
  - contratos.json: vencimiento de contrato, valor de mercado y minutos en Boca de cada jugador del plantel.
No se usan los sueldos: son estimaciones externas.
"""
from __future__ import annotations

import datetime as dt
import json

from comun import DATOS, ahora, guardar_json, http_get, leer_json, log

BASE = "https://bocaennumeros.conquistaxeneize.com.ar"
CARPETA = DATOS / "conquista"
CREDITO = "Boca en Números (Conquista Xeneize)"
HORAS = 20


def _bajar(nombre: str) -> dict:
    return json.loads(http_get(f"{BASE}/{nombre}", intentos=2, timeout=40, headers={
        "Accept": "application/json", "User-Agent": "RinconBosteroBot/1.0 (+https://gastoneezequiel02-creator.github.io/rincon-bostero)"
    }).decode("utf-8"))


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def reducir_prestamos(L: dict) -> dict:
    sm = L.get("statistics_meta") or {}
    jugadores = []
    for p in L.get("players", []):
        st = p.get("loan_stats") or {}
        alcance = st.get("scope_label") or st.get("season_label") or ""
        if st.get("coverage") == "league_only" and "liga" not in alcance.lower():
            alcance = (alcance + " · solo liga").strip(" ·")
        elif st.get("coverage") == "partial" and "parcial" not in alcance.lower():
            alcance = (alcance + " · cobertura parcial").strip(" ·")
        jugadores.append({
            "nombre": p.get("name", ""),
            "posicion": p.get("position") or "",
            "club": p.get("destination_club") or "",
            "pais": p.get("country") or "",
            "hasta": p.get("loan_end") or "",
            "hasta_precision": p.get("loan_end_precision") or "",
            "por_confirmar": p.get("recheck_status") == "por_confirmar",  # su revisión marca 20 de 36 así
            "verificado": bool(st.get("verified")),
            "pj": _num(st.get("appearances")),
            "titular": _num(st.get("starts")),
            "minutos": _num(st.get("minutes")),
            "goles": _num(st.get("goals")),
            "asistencias": _num(st.get("assists")),
            "ultima": st.get("last_appearance_date") or "",
            "cifras_hasta": st.get("data_through") or "",
            "alcance": alcance,
        })
    return {"fuente": CREDITO, "corte": sm.get("as_of") or L.get("as_of", ""), "importado": ahora().isoformat(),
            "jugadores": jugadores}


def reducir_contratos(P: dict) -> dict:
    jugadores = []
    for p in P.get("players", []):
        ss = p.get("season_stats") or {}
        jugadores.append({
            "nombre": p.get("name", ""),
            "posicion": p.get("position") or "",
            "grupo": p.get("official_group") or "",
            "nacimiento": p.get("date_of_birth") or p.get("dob") or "",
            "vence": p.get("contract_end") or "",
            "valor_eur": _num(p.get("market_value_eur")),
            "valor_fecha": p.get("market_value_date") or "",
            "valor_fuente": p.get("market_value_provider") or "",
            "pj": _num(ss.get("appearances")),
            "minutos": _num(ss.get("minutes")),
            "goles": _num(ss.get("goals")),
            "asistencias": _num(ss.get("assists")),
            "temporada": ss.get("season"),
        })
    return {"fuente": CREDITO, "corte": P.get("as_of", ""), "importado": ahora().isoformat(), "jugadores": jugadores}


def ejecutar(forzar: bool = False) -> bool:
    previo = leer_json(CARPETA / "prestamos.json", {}) or {}
    if not forzar and previo.get("importado", "") > (ahora() - dt.timedelta(hours=HORAS)).isoformat():
        return False
    try:
        prestamos = reducir_prestamos(_bajar("loans.json"))
        contratos = reducir_contratos(_bajar("players.json"))
    except Exception as e:
        log(f"Boca en Números: no pude leer los datos ({e}). Queda la copia anterior.")
        return False
    if len(prestamos["jugadores"]) < 5 or len(contratos["jugadores"]) < 15:
        log("Boca en Números: vinieron muy pocos datos. Queda la copia anterior.")
        return False
    guardar_json(CARPETA / "prestamos.json", prestamos)
    guardar_json(CARPETA / "contratos.json", contratos)
    log(f"Boca en Números: {len(prestamos['jugadores'])} préstamos y {len(contratos['jugadores'])} contratos (corte {prestamos['corte']})")
    return True


def prestamos() -> dict:
    return leer_json(CARPETA / "prestamos.json", {}) or {}


def contratos() -> dict:
    return leer_json(CARPETA / "contratos.json", {}) or {}


if __name__ == "__main__":
    ejecutar(forzar=True)
