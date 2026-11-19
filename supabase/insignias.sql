-- =============================================================================
-- Rincón Bostero: insignias y «Hincha de la semana» (se agrega a esquema.sql)
-- Se puede volver a correr sin problema.
-- =============================================================================

-- Resumen del usuario: además del apodo, la racha y la posición semanal, devuelve los números
-- que la web usa para dar las insignias.
create or replace function public.mi_resumen() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  ap text; racha int := 0; dia date := hoy_ar(); pos bigint; pts bigint;
  v_dias int; v_perfectos int; v_aciertos int; v_mejor int; v_temas int; v_semanas int;
  inicio_semana date := hoy_ar() - ((extract(isodow from hoy_ar())::int) - 1);
begin
  select apodo into ap from perfiles where id = auth.uid();
  if ap is null then return jsonb_build_object('apodo', null); end if;
  if not exists (select 1 from respuestas where usuario = auth.uid() and modo = 'dia' and fecha = dia) then dia := dia - 1; end if;
  while exists (select 1 from respuestas where usuario = auth.uid() and modo = 'dia' and fecha = dia) loop
    racha := racha + 1; dia := dia - 1;
  end loop;
  select r.posicion, r.puntos into pos, pts from ranking('semana') r where r.soy_yo;

  select count(distinct fecha) into v_dias from respuestas where usuario = auth.uid() and modo = 'dia';
  select count(*) into v_perfectos from (
    select fecha from respuestas where usuario = auth.uid() and modo = 'dia'
    group by fecha having count(*) filter (where correcta) >= 10) z;
  select count(*) into v_aciertos from respuestas where usuario = auth.uid() and correcta;
  select coalesce(max(c), 0) into v_mejor from (
    select count(*) c from (
      select fecha, fecha - (row_number() over (order by fecha))::int as grupo
      from (select distinct fecha from respuestas where usuario = auth.uid() and modo = 'dia') d) x
    group by grupo) y;
  select count(distinct tema) into v_temas from trivia_sesiones where usuario = auth.uid();
  with s as (
    select usuario, date_trunc('week', fecha)::date as sem, count(*) filter (where correcta and suma) as p
    from respuestas where fecha < inicio_semana group by 1, 2
  ), r as (select usuario, sem, rank() over (partition by sem order by p desc) as rk from s where p > 0)
  select count(*) into v_semanas from r where usuario = auth.uid() and rk = 1;

  return jsonb_build_object('apodo', ap, 'racha', racha, 'posicion_semana', pos, 'puntos_semana', coalesce(pts, 0),
    'dias_total', v_dias, 'perfectos', v_perfectos, 'aciertos_total', v_aciertos, 'mejor_racha', greatest(v_mejor, racha),
    'temas_trivia', v_temas, 'semanas_primero', v_semanas);
end $$;

-- El que más puntos sumó la semana pasada (lunes a domingo). Si hay empate, todos los primeros (hasta 3).
create or replace function public.hincha_de_la_semana() returns jsonb
language sql stable security definer set search_path = public as $$
  with lim as (
    select hoy_ar() - ((extract(isodow from hoy_ar())::int) - 1) - 7 as desde,
           hoy_ar() - ((extract(isodow from hoy_ar())::int) - 1) - 1 as hasta
  ), pts as (
    select r.usuario, count(*) filter (where r.correcta and r.suma) as puntos
    from respuestas r, lim where r.fecha between lim.desde and lim.hasta group by r.usuario
  ), rk as (select usuario, puntos, rank() over (order by puntos desc) as pos from pts where puntos > 0)
  select jsonb_build_object('desde', (select desde from lim), 'hasta', (select hasta from lim),
    'ganadores', coalesce((select jsonb_agg(jsonb_build_object('apodo', g.apodo, 'puntos', g.puntos) order by g.apodo)
                           from (select pf.apodo, rk.puntos from rk join perfiles pf on pf.id = rk.usuario
                                 where rk.pos = 1 order by pf.apodo limit 3) g), '[]'::jsonb));
$$;

revoke execute on function public.hincha_de_la_semana() from public;
grant execute on function public.hincha_de_la_semana() to anon, authenticated;
grant execute on function public.mi_resumen() to authenticated;
