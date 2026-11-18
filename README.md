# Rincón Bostero: web automática

La web se actualiza sola cada 15 minutos:

- **Noticias automáticas.** Lee Google Noticias, la IA elige lo importante sobre Boca y escribe una nota propia, citando a los medios.
- **Bot de Telegram.** Le reenviás un tweet (o el link, o un texto) y lo convierte en nota y la publica.
- **Previas y crónicas.** El día antes de cada partido sale la previa, y cuando termina, la nota con el resultado.
- **Datos de Boca.** Fixture y posiciones por competencia, historial contra cada rival, campañas con buscador (Liga, Libertadores, Sudamericana, Copa Argentina, Copa de la Liga, Recopa, Supercopa y Mundial de Clubes) y plantel.
- **Historia de Boca.** Con permiso de historiadeboca.com.ar: historial partido a partido contra los clásicos desde el amateurismo y la sección "Un día como hoy". Todo se muestra dentro de la web, con el crédito "Datos históricos: Historia de Boca".
- **BocaStats.** Con permiso de bocastats.com: historial contra los 240 rivales desde 1905, partido por partido; campañas de todos los torneos; página de Récords (balance histórico, marcas, goleadas, década por década, rivales más enfrentados); goleadores de la temporada y todos los partidos de cada "Un día como hoy".
- **Juegos.** La pregunta del día (10 preguntas diarias iguales para todos, sin repetir de un día a otro, con racha y resultado para compartir), ¿Más o menos?, trivia por temas y Adiviná el ídolo. Las preguntas (más de 300, y más de 500 cuando se cargan todos los datos) se arman solas con los datos de la web; la lista de ídolos está en `datos/manual/idolos.json` y se puede ampliar.
- **Cuentas y ranking (opcional).** Con una base de datos gratuita (Supabase), cada uno entra con su mail o Google, elige un apodo y suma puntos en un ranking semanal, mensual e histórico. Las respuestas se corrigen en el servidor para que nadie pueda hacer trampa. Ver "Activar cuentas y ranking".
- **Extras.** Calendario para el celular (`calendario.ics`), RSS, sitemap para Google y botones para compartir por WhatsApp y X.

**Costo: $0.** Usa el plan gratuito de GitHub (automatización y hosting), de Google Gemini (IA) y de Telegram.
En X no se publica nada.

---

## Puesta en marcha (una sola vez, 20 a 30 minutos)

### 1. Subir el proyecto a GitHub
1. Creá una cuenta en https://github.com (si no tenés).
2. Arriba a la derecha: **+ → New repository**. Nombre: `rincon-bostero`. Marcalo **Public** (así es gratis). Creá el repositorio.
3. En la página del repositorio vacío, hacé clic en **uploading an existing file** y arrastrá **todo el contenido** de la carpeta del proyecto (no la carpeta en sí, lo que hay adentro). Abajo, **Commit changes**.

> ⚠️ En Mac y Windows la carpeta `.github` está oculta y a veces no se sube al arrastrar.
> Fijate que en el repositorio aparezca `.github/workflows/actualizar.yml`. Si no está:
> **Add file → Create new file**, escribí como nombre `.github/workflows/actualizar.yml`,
> pegá el contenido de ese archivo y guardá.

### 2. Sacar la clave gratuita de la IA (Gemini)
1. Entrá a https://aistudio.google.com/apikey con una cuenta de Google.
2. **Create API key** y copiala.
3. En GitHub, en tu repositorio: **Settings → Secrets and variables → Actions → New repository secret**.
   Nombre: `GEMINI_API_KEY`. Valor: la clave. Guardar.

### 3. Crear el bot de Telegram
1. En Telegram, buscá **@BotFather** y mandale `/newbot`.
2. Elegí un nombre (por ejemplo, "Rincón Bostero Redacción") y un usuario que termine en `bot`.
3. BotFather te da un **token** (algo como `123456:ABC-...`). Copialo.
4. En GitHub: **New repository secret**. Nombre: `TELEGRAM_BOT_TOKEN`. Valor: el token.

### 4. Activar la web
1. En GitHub: **Settings → Pages**. En "Source" elegí **GitHub Actions**.
2. Abrí `config.json` (clic en el archivo y después en el lápiz ✏️) y cambiá:
   `"url": "https://gastoneezequiel02-creator.github.io/rincon-bostero"` por tu usuario de GitHub.
   Guardá con **Commit changes**.
3. Andá a la pestaña **Actions**. Si te pregunta, habilitá los workflows. Entrá en
   **Actualizar Rincón Bostero → Run workflow**.
4. En unos minutos la web está en `https://gastoneezequiel02-creator.github.io/rincon-bostero`.

La primera vez tarda un poco más: baja la temporada actual. El historial de años anteriores se completa
de a poco en las siguientes corridas (en unas horas está todo).

### 5. Habilitar a quienes cargan notas por Telegram
1. Cada persona del equipo le escribe `/id` al bot.
2. Esperan hasta 15 minutos (el bot responde cuando corre la automatización): el bot les dice su número.
3. En `config.json`, agregá esos números en `"usuarios_permitidos"`. Por ejemplo: `[123456789, 987654321]`.

Si alguien no autorizado le escribe al bot, el bot no publica nada y le responde con su número.

---

## Activar cuentas y ranking (opcional, unos 15 minutos)

Sin esto los juegos funcionan igual, pero sin cuentas ni ranking.

1. Creá una cuenta gratis en https://supabase.com y tocá **New project**. Nombre: `rincon-bostero`. Elegí una contraseña
   (guardala) y la región **South America (São Paulo)**.
2. Cuando el proyecto esté listo: **SQL Editor → New query**. Abrí el archivo `supabase/esquema.sql` de este proyecto,
   copiá todo, pegalo y tocá **Run**. Tiene que decir "Success".
3. **Authentication → URL Configuration**:
   - Site URL: `https://gastoneezequiel02-creator.github.io/rincon-bostero/juegos.html`
   - Redirect URLs: agregá la misma dirección.
4. **Project Settings → API** (o **Data API**). Copiá:
   - **Project URL** → en `config.json`, dentro de `cuentas`, en `supabase_url`.
   - La clave **anon / public** → en `supabase_anon_key`. Esta clave es pública, puede ir en la web.
   - La clave **service_role** → **¡no va en config.json!** Va en GitHub: Settings → Secrets → New repository secret,
     con el nombre `SUPABASE_SERVICE_KEY`.
5. En `config.json`, poné `"activado": true` dentro de `cuentas` y guardá. En la próxima corrida se cargan las preguntas
   y aparece el ranking.

**Entrar por mail** funciona desde el primer momento: la persona deja su mail y le llega un link. El servicio de mails
gratuito de Supabase manda pocos mails por hora; si se juntan muchos registros, configurá un servicio de mails propio en
**Authentication → Emails → SMTP Settings** (hay opciones gratis, como Resend o Brevo).

**Entrar con Google** (opcional): en **Authentication → Providers → Google** seguí las instrucciones de Supabase para
crear las credenciales en Google Cloud. Cuando esté, poné `"entrar_con_google": true` en `config.json`.

**Moderar apodos:** en **Table Editor → perfiles** podés editar o borrar cualquier apodo.

**Cómo suma el ranking:** 1 punto por acierto en la pregunta del día y en la primera partida de cada tema de la trivia por
día. Solo cuenta la primera respuesta de cada pregunta. Con las cuentas activadas, las respuestas correctas no están en la
página: se corrigen en la base de datos.

## Cómo se usa el bot

Mandale al bot:

- El **link de un tweet** (`https://x.com/.../status/...`). El bot lee el texto del tweet y arma la nota.
- O **reenviale** un mensaje, o **escribí vos** la información.
- Podés sumar **tu propio contexto** en el mismo mensaje ("esto lo confirmó el club", "es para el femenino", etc.).
- Podés mandar una **foto** con el texto: se usa como imagen de la nota. Usá fotos propias o con permiso.

Para indicar qué tan firme es la información, empezá con una marca:

| Marca | Cuándo usarla |
|---|---|
| `#oficial` | Lo comunicó el club |
| `#confirmado` | Es un hecho, aunque no haya comunicado |
| `#rumor` | Trascendido, sondeo, "se habla de…" |

Si no ponés marca, la IA decide sola. Un tweet de un periodista sin confirmación sale como **rumor**.

Comandos del bot: `/ultimas` muestra las últimas 5 notas, `/borrar nombre-de-la-nota` despublica una y `/ayuda` muestra la ayuda.

---

## Ajustes en `config.json`

| Qué querés | Qué cambiar |
|---|---|
| Revisar las notas automáticas antes de publicarlas | `"modo": "aprobacion"`. Te llegan por Telegram con botones **Publicar / Descartar**. |
| Más o menos notas automáticas | `max_notas_por_corrida` y `max_notas_por_dia` |
| Sumar un medio | Agregá su RSS en `"fuentes"`, o una búsqueda de Google Noticias cambiando las palabras en `q=` (ver abajo) |
| Cambiar el tono de las notas | `"tono"` dentro de `"ia"` |
| Apagar previas o crónicas | `previas_automaticas` / `cronicas_automaticas` en `false` |
| Historial desde otro año | `temporada_desde` |

**Notas más completas:** con Google Noticias la IA solo ve los títulos, así que las notas salen cortas. Si sumás
el RSS directo de un medio, la IA puede leer la nota original y escribir una más completa. Por ejemplo (verificá
que funcionen antes de agregarlos): `https://www.lanumero12.com.ar/feed`, `https://soyboca.com.ar/rss.xml`,
`https://planetabj.com/rss/feed`. Se agregan así dentro de `"fuentes"`:
`{"nombre": "La Número 12", "url": "https://www.lanumero12.com.ar/feed"}`

**Historia de Boca.** Una vez por semana la web baja el historial partido a partido contra River, Independiente,
Racing, San Lorenzo, Huracán, Estudiantes, Vélez, Newell's y Central, y lo verifica: si los partidos que leyó no
coinciden con los totales de la página, no lo usa y se queda con la versión anterior (queda avisado en Actions).
Los totales de respaldo están en `datos/manual/historial_oficial.json`. Para sumar otro rival, agregalo ahí con el
link a su página de historial en Historia de Boca. A los totales se les suman solos los partidos de liga posteriores.
Las efemérides de "Un día como hoy" se leen una vez por día y se guardan, así que con el tiempo la web arma su propio
almanaque de los 365 días. Para apagar todo, poné `"activado": false` en `historia_de_boca` dentro de `config.json`.

**BocaStats.** Una vez por semana se actualiza el índice de rivales y los récords; los goleadores, una vez por día.
El partido por partido de los 240 rivales se baja de a 40 por corrida (la primera vez tarda unas dos horas en
completarse) y después se renueva cada semana. Cada rival se verifica: si la cantidad de partidos leídos no coincide con
la que informa BocaStats, no se usa y queda la versión anterior. En `datos/bocastats/` hay una copia inicial del índice
de rivales, los récords y los goleadores, así que la web tiene datos desde el primer momento. Para apagarlo, poné
`"activado": false` en `bocastats` dentro de `config.json`.

Para cargar a mano el **historial total** contra un rival (desde el amateurismo) o la lista de **títulos**,
completá los archivos de `datos/manual/` (las instrucciones están adentro de cada uno).

---

## Preguntas frecuentes

**¿La IA puede inventar cosas?** Está instruida para usar solo la información que recibe, citar las fuentes,
marcar los rumores y no inventar declaraciones ni datos. Igual puede equivocarse: si querés control total, usá el
modo `aprobacion`. Si algo salió mal, `/borrar` desde Telegram la despublica.

**¿Por qué no publica tantas notas?** El plan gratis de Gemini tiene un límite de pedidos por día. Con los valores
por defecto (hasta 25 notas automáticas por día) alcanza de sobra.

**El bot no responde al instante.** Es normal: responde cada vez que corre la automatización (cada 15 a 20
minutos). Es lo que permite que todo sea gratis, sin un servidor prendido todo el día.

**Los datos de fútbol dejaron de actualizarse.** Vienen de los datos públicos de ESPN, que no son una API oficial.
Si cambian, hay que ajustar solo `scripts/datos_futbol.py`. Las noticias y el bot siguen funcionando igual.

**¿Puedo usar un dominio propio (.com.ar)?** Sí. Se compra en NIC Argentina y se configura en **Settings → Pages →
Custom domain**. Después cambiá `"url"` en `config.json`.

**¿Dónde veo si algo falló?** En la pestaña **Actions**. Cada corrida tiene un registro en castellano de lo que hizo.

---

## Qué hace cada archivo

```
config.json                  ← todo lo que se puede ajustar
scripts/ejecutar_todo.py     ← corre todo en orden (lo usa GitHub cada 15 min)
scripts/noticias_rss.py      ← opción 1: noticias automáticas desde RSS
scripts/bot_telegram.py      ← opción 2: el bot de Telegram
scripts/datos_futbol.py      ← fixture, resultados, tablas, historial y plantel (ESPN)
scripts/cronicas.py          ← previas y notas de resultado automáticas
scripts/ia.py                ← la IA (Gemini) y las reglas de redacción
scripts/historia_de_boca.py  ← historial partido a partido y efemérides de historiadeboca.com.ar
scripts/juegos.py            ← preguntas y datos de los juegos (salen de los datos reales)
scripts/sincronizar_juegos.py ← sube las preguntas a la base de datos del ranking
supabase/esquema.sql         ← base de datos de cuentas y ranking (se pega una vez en Supabase)
scripts/bocastats.py         ← 240 rivales, partidos desde 1905, récords y goleadores de bocastats.com
scripts/construir_sitio.py   ← arma las páginas de la web
sitio/estatico/              ← diseño (estilos.css) y comportamiento (app.js)
contenido/notas/             ← cada nota publicada es un archivo .json (se puede editar a mano)
datos/                       ← datos de fútbol (automáticos) y manuales
.github/workflows/           ← la programación de la automatización
```

Para probar en una computadora (opcional, requiere Python 3.10 o más nuevo):
`python scripts/ejecutar_todo.py`. El sitio queda en la carpeta `_sitio/`.
