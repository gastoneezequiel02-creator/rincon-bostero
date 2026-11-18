"""Sube el banco de preguntas a la base de datos de Supabase (para el ranking y las cuentas).

Necesita, en GitHub Secrets, SUPABASE_SERVICE_KEY (la clave "service_role" del proyecto) y en config.json
la dirección del proyecto (cuentas > supabase_url). Las respuestas correctas quedan solo en la base de datos:
la web publica las preguntas sin la respuesta cuando las cuentas están activadas.
Cada corrida además mantiene "despierto" el proyecto gratuito de Supabase.
"""
from comun import config, http_post_json, log, secreto


def ejecutar() -> None:
    c = config().get("cuentas") or {}
    clave = secreto("SUPABASE_SERVICE_KEY")
    if not c.get("activado") or not c.get("supabase_url"):
        return
    if not clave:
        log("Cuentas: falta SUPABASE_SERVICE_KEY en los secretos de GitHub; no se actualizan las preguntas.")
        return
    import juegos
    banco = [{k: q[k] for k in ("id", "tema", "texto", "opciones", "correcta", "dato")} for q in juegos.armar()["preguntas"]]
    url = c["supabase_url"].rstrip("/") + "/rest/v1/rpc/sincronizar_preguntas"
    # Las claves nuevas (sb_secret_...) van solo en "apikey"; las viejas (JWT service_role) también como Bearer.
    cabeceras = {"apikey": clave}
    if clave.startswith("eyJ"):
        cabeceras["Authorization"] = f"Bearer {clave}"
    r = http_post_json(url, {"p": banco}, headers=cabeceras)
    log(f"Cuentas: banco de preguntas actualizado ({r.get('activas', '?')} preguntas activas)")


if __name__ == "__main__":
    ejecutar()
