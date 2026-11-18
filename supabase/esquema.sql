-- =============================================================================
-- Rincón Bostero: cuentas, juegos y ranking (Supabase)
-- Pegá TODO este archivo en Supabase > SQL Editor > New query y tocá "Run".
-- Se puede volver a correr sin problema (no borra datos).
--
-- Cómo funciona la seguridad:
-- - Las respuestas correctas viven SOLO acá. La web pide las preguntas sin la respuesta
--   y cada respuesta se corrige en la base de datos.
-- - En el ranking cuenta solo la PRIMERA respuesta de cada pregunta.
-- - La trivia suma al ranking solo la primera partida de cada tema por día.
-- =============================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- tablas -----
create table if not exists public.perfiles (
  id      uuid primary key references auth.users (id) on delete cascade,
  apodo   text not null unique
          check (char_length(apodo) between 3 and 20 and apodo ~ '^[A-Za-z0-9_ ÁÉÍÓÚÑáéíóúñü.\-]+$'),
  creado  timestamptz not null default now()
);

create table if not exists public.preguntas (
  id          text primary key,
  tema        text not null,
  texto       text not null,
  opciones    jsonb not null,
  correcta    smallint not null,
  dato        text not null default '',
  activa      boolean not null default true,
  actualizada timestamptz not null default now()
);

create table if not exists public.desafios (
  fecha     date primary key,
  preguntas text[] not null
);

create table if not exists public.trivia_sesiones (
  id        uuid primary key default gen_random_uuid(),
  usuario   uuid references public.perfiles (id) on delete cascade,
  tema      text not null,
  fecha     date not null,
  preguntas text[] not null,
  suma      boolean not null default false,   -- primera partida del tema en el día: suma al ranking
  creada    timestamptz not null default now()
);

create table if not exists public.respuestas (
  usuario  uuid not null references public.perfiles (id) on delete cascade,
  modo     text not null check (modo in ('dia', 'trivia')),
  clave    text not null,                     -- la fecha (pregunta del día) o el id de la partida (trivia)
  pregunta text not null,
  opcion   smallint not null,
  correcta boolean not null,
  suma     boolean not null default true,
  fecha    date not null,
  creada   timestamptz not null default now(),
  primary key (usuario, modo, clave, pregunta)
);
create index if not exists respuestas_fecha on public.respuestas (fecha);

-- ------------------------------------------------------------- seguridad -----
alter table public.perfiles        enable row level security;
alter table public.preguntas       enable row level security;
alter table public.desafios        enable row level security;
alter table public.trivia_sesiones enable row level security;
alter table public.respuestas      enable row level security;

revoke all on public.preguntas, public.desafios, public.trivia_sesiones, public.respuestas from anon, authenticated;
revoke all on public.perfiles from anon, authenticated;
grant select on public.perfiles to anon, authenticated;
grant insert (id, apodo), update (apodo) on public.perfiles to authenticated;

drop policy if exists "apodos publicos" on public.perfiles;
create policy "apodos publicos" on public.perfiles for select using (true);
drop policy if exists "crear mi perfil" on public.perfiles;
create policy "crear mi perfil" on public.perfiles for insert with check (id = auth.uid());
drop policy if exists "cambiar mi apodo" on public.perfiles;
create policy "cambiar mi apodo" on public.perfiles for update using (id = auth.uid()) with check (id = auth.uid());

-- ---------------------------------------------------------- utilidades -----
create or replace function public.hoy_ar() returns date
language sql stable set search_path = public as $$ select (now() at time zone 'America/Argentina/Buenos_Aires')::date $$;

-- Arma (una sola vez) las 10 preguntas del día, sin repetir las de los últimos 120 días.
create or replace function public.asegurar_desafio(p_fecha date) returns text[]
language plpgsql security definer set search_path = public as $$
declare
  ids text[];
  cupos jsonb := '{"titulos":2,"superclasico":1,"rivales":2,"historia":2,"idolos":2,"temporada":1}';
  t text; n int; usadas text[];
begin
  select preguntas into ids from desafios where fecha = p_fecha;
  if ids is not null then return ids; end if;
  select coalesce(array_agg(x), '{}') into usadas
    from desafios d, unnest(d.preguntas) x where d.fecha > p_fecha - 120 and d.fecha < p_fecha;
  ids := '{}';
  for t, n in select key, value::int from jsonb_each_text(cupos) loop
    ids := ids || coalesce((select array_agg(id) from (
      select id from preguntas where activa and tema = t and not (id = any (usadas)) order by random() limit n) s), '{}');
  end loop;
  if coalesce(array_length(ids, 1), 0) < 10 then   -- si un tema no alcanza, se completa con otros
    ids := ids || coalesce((select array_agg(id) from (
      select id from preguntas where activa and not (id = any (ids)) and not (id = any (usadas))
      order by random() limit 10 - coalesce(array_length(ids, 1), 0)) s), '{}');
  end if;
  if coalesce(array_length(ids, 1), 0) < 10 then   -- banco chico: se permite repetir
    ids := ids || coalesce((select array_agg(id) from (
      select id from preguntas where activa and not (id = any (ids))
      order by random() limit 10 - coalesce(array_length(ids, 1), 0)) s), '{}');
  end if;
  if coalesce(array_length(ids, 1), 0) = 0 then raise exception 'Todavía no hay preguntas cargadas'; end if;
  select array_agg(x order by random()) into ids from unnest(ids) x;
  insert into desafios (fecha, preguntas) values (p_fecha, ids) on conflict (fecha) do nothing;
  select preguntas into ids from desafios where fecha = p_fecha;
  return ids;
end $$;

-- ----------------------------------------------------- pregunta del día -----
create or replace function public.desafio_hoy()
returns table (orden int, id text, tema text, texto text, opciones jsonb, respondida smallint, era_correcta smallint)
language plpgsql security definer set search_path = public as $$
declare ids text[];
begin
  ids := asegurar_desafio(hoy_ar());
  return query
    select o.n::int, p.id, p.tema, p.texto, p.opciones, r.opcion,
           case when r.opcion is null then null else p.correcta end
    from unnest(ids) with ordinality o(pid, n)
    join preguntas p on p.id = o.pid
    left join respuestas r on r.usuario = auth.uid() and r.modo = 'dia' and r.clave = hoy_ar()::text and r.pregunta = p.id
    order by o.n;
end $$;

create or replace function public.responder_dia(p_pregunta text, p_opcion int) returns jsonb
language plpgsql security definer set search_path = public as $$
declare q preguntas; previa respuestas; hoy date := hoy_ar();
begin
  if not (p_pregunta = any (asegurar_desafio(hoy))) then raise exception 'La pregunta no es de hoy'; end if;
  select * into q from preguntas where id = p_pregunta;
  if auth.uid() is not null and exists (select 1 from perfiles where id = auth.uid()) then
    insert into respuestas (usuario, modo, clave, pregunta, opcion, correcta, fecha)
      values (auth.uid(), 'dia', hoy::text, p_pregunta, p_opcion, p_opcion = q.correcta, hoy)
      on conflict do nothing;
    select * into previa from respuestas where usuario = auth.uid() and modo = 'dia' and clave = hoy::text and pregunta = p_pregunta;
    return jsonb_build_object('correcta', q.correcta, 'dato', q.dato, 'es_correcta', previa.correcta, 'opcion_valida', previa.opcion);
  end if;
  return jsonb_build_object('correcta', q.correcta, 'dato', q.dato, 'es_correcta', p_opcion = q.correcta, 'opcion_valida', p_opcion);
end $$;

-- ------------------------------------------------------------------ trivia -----
create or replace function public.trivia_iniciar(p_tema text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare ids text[]; sid uuid; hoy date := hoy_ar(); con_usuario boolean;
begin
  select array_agg(id) into ids from (select id from preguntas where activa and tema = p_tema order by random() limit 10) s;
  if ids is null then raise exception 'Tema sin preguntas'; end if;
  con_usuario := auth.uid() is not null and exists (select 1 from perfiles where id = auth.uid());
  insert into trivia_sesiones (usuario, tema, fecha, preguntas, suma)
    values (case when con_usuario then auth.uid() end, p_tema, hoy, ids,
            con_usuario and not exists (select 1 from trivia_sesiones where usuario = auth.uid() and tema = p_tema and fecha = hoy))
    returning id into sid;
  return jsonb_build_object('sesion', sid, 'suma', (select suma from trivia_sesiones where id = sid), 'preguntas',
    (select jsonb_agg(jsonb_build_object('id', p.id, 'tema', p.tema, 'texto', p.texto, 'opciones', p.opciones) order by o.n)
     from unnest(ids) with ordinality o(pid, n) join preguntas p on p.id = o.pid));
end $$;

create or replace function public.responder_trivia(p_sesion uuid, p_pregunta text, p_opcion int) returns jsonb
language plpgsql security definer set search_path = public as $$
declare s trivia_sesiones; q preguntas; previa respuestas;
begin
  select * into s from trivia_sesiones where id = p_sesion;
  if s.id is null or not (p_pregunta = any (s.preguntas)) then raise exception 'Partida no válida'; end if;
  select * into q from preguntas where id = p_pregunta;
  if s.usuario is not null and s.usuario = auth.uid() then
    insert into respuestas (usuario, modo, clave, pregunta, opcion, correcta, suma, fecha)
      values (auth.uid(), 'trivia', s.id::text, p_pregunta, p_opcion, p_opcion = q.correcta, s.suma, s.fecha)
      on conflict do nothing;
    select * into previa from respuestas where usuario = auth.uid() and modo = 'trivia' and clave = s.id::text and pregunta = p_pregunta;
    return jsonb_build_object('correcta', q.correcta, 'dato', q.dato, 'es_correcta', previa.correcta);
  end if;
  return jsonb_build_object('correcta', q.correcta, 'dato', q.dato, 'es_correcta', p_opcion = q.correcta);
end $$;

-- ----------------------------------------------------------------- ranking -----
-- Puntos: 1 por cada acierto de la pregunta del día y de la trivia (primera partida de cada tema por día).
create or replace function public.ranking(p_periodo text default 'semana')
returns table (posicion bigint, apodo text, puntos bigint, aciertos_dia bigint, aciertos_trivia bigint, dias_jugados bigint, soy_yo boolean)
language sql stable security definer set search_path = public as $$
  with desde as (
    select case p_periodo
      when 'semana' then hoy_ar() - ((extract(isodow from hoy_ar())::int) - 1)
      when 'mes'    then date_trunc('month', hoy_ar())::date
      else date '2000-01-01' end as d
  ), puntos as (
    select r.usuario,
           count(*) filter (where r.correcta and r.suma) as puntos,
           count(*) filter (where r.correcta and r.modo = 'dia') as aciertos_dia,
           count(*) filter (where r.correcta and r.suma and r.modo = 'trivia') as aciertos_trivia,
           count(distinct r.fecha) filter (where r.modo = 'dia') as dias_jugados,
           max(r.creada) as ultima
    from respuestas r, desde where r.fecha >= desde.d
    group by r.usuario
  )
  select rank() over (order by p.puntos desc), pf.apodo, p.puntos, p.aciertos_dia, p.aciertos_trivia, p.dias_jugados,
         p.usuario = auth.uid()
  from puntos p join perfiles pf on pf.id = p.usuario
  where p.puntos > 0
  order by p.puntos desc, p.ultima asc
  limit 100;
$$;

-- Resumen del usuario: apodo, racha de días seguidos jugando la pregunta del día y posición semanal.
create or replace function public.mi_resumen() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare ap text; racha int := 0; dia date := hoy_ar(); pos bigint; pts bigint;
begin
  select apodo into ap from perfiles where id = auth.uid();
  if ap is null then return jsonb_build_object('apodo', null); end if;
  if not exists (select 1 from respuestas where usuario = auth.uid() and modo = 'dia' and fecha = dia) then dia := dia - 1; end if;
  while exists (select 1 from respuestas where usuario = auth.uid() and modo = 'dia' and fecha = dia) loop
    racha := racha + 1; dia := dia - 1;
  end loop;
  select r.posicion, r.puntos into pos, pts from ranking('semana') r where r.soy_yo;
  return jsonb_build_object('apodo', ap, 'racha', racha, 'posicion_semana', pos, 'puntos_semana', coalesce(pts, 0));
end $$;

-- Borrar la cuenta y todos sus datos (derecho del usuario).
create or replace function public.borrar_mi_cuenta() returns void
language plpgsql security definer set search_path = public, auth as $$
begin
  if auth.uid() is null then raise exception 'No hay sesión'; end if;
  delete from auth.users where id = auth.uid();
end $$;

-- ----------------------------------------- carga de preguntas (solo GitHub) -----
-- La llama la automatización con la clave de servicio: agrega/actualiza el banco
-- y desactiva las preguntas que ya no existen.
create or replace function public.sincronizar_preguntas(p jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  insert into preguntas (id, tema, texto, opciones, correcta, dato, activa, actualizada)
    select x->>'id', x->>'tema', x->>'texto', x->'opciones', (x->>'correcta')::smallint, coalesce(x->>'dato', ''), true, now()
    from jsonb_array_elements(p) x
  on conflict (id) do update set tema = excluded.tema, texto = excluded.texto, opciones = excluded.opciones,
    correcta = excluded.correcta, dato = excluded.dato, activa = true, actualizada = now();
  update preguntas set activa = false where activa and id not in (select x->>'id' from jsonb_array_elements(p) x);
  select count(*) into n from preguntas where activa;
  perform asegurar_desafio(hoy_ar());
  return jsonb_build_object('activas', n);
end $$;

-- ------------------------------------------------------------------ permisos -----
revoke execute on all functions in schema public from public, anon, authenticated;
grant execute on function public.hoy_ar(), public.desafio_hoy(), public.responder_dia(text, int),
  public.trivia_iniciar(text), public.responder_trivia(uuid, text, int), public.ranking(text)
  to anon, authenticated;
grant execute on function public.mi_resumen(), public.borrar_mi_cuenta() to authenticated;
grant execute on function public.sincronizar_preguntas(jsonb), public.asegurar_desafio(date) to service_role;
