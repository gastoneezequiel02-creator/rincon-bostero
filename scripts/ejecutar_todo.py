"""Corre toda la automatización en orden. Es lo que ejecuta GitHub Actions cada 15 minutos.

Cada paso está aislado: si uno falla (por ejemplo, ESPN no responde), los demás siguen.
"""
import sys
import traceback

from comun import log


def paso(nombre, funcion):
    try:
        funcion()
        return True
    except Exception as e:
        log(f"❌ Falló «{nombre}»: {e}")
        traceback.print_exc()
        return False


def main(solo_sitio: bool = False):
    import bocastats
    import bot_telegram
    import construir_sitio
    import cronicas
    import datos_futbol
    import historia_de_boca
    import noticias_rss
    import sincronizar_juegos

    ok = True
    if not solo_sitio:
        ok &= paso("datos de fútbol", datos_futbol.ejecutar)
        ok &= paso("datos de Historia de Boca", historia_de_boca.ejecutar)
        ok &= paso("datos de BocaStats", bocastats.ejecutar)
        ok &= paso("bot de Telegram", bot_telegram.ejecutar)
        ok &= paso("noticias RSS", noticias_rss.ejecutar)
        ok &= paso("previas y crónicas", cronicas.ejecutar)
    # El sitio se arma siempre, aunque algo de arriba haya fallado
    if not paso("armar el sitio", construir_sitio.construir):
        sys.exit(1)
    if not solo_sitio:
        paso("preguntas de los juegos en la base de datos", sincronizar_juegos.ejecutar)
    if not ok:
        log("⚠️  Hubo errores en algún paso (ver arriba), pero el sitio se publicó igual.")


if __name__ == "__main__":
    main(solo_sitio="--solo-sitio" in sys.argv)
