begin;

-- Retained grants preserve cookie paths after resource metadata or sessions disappear.
create index private_media_grants_cookie_paths_idx
  on public.private_media_grants(user_id, resource_kind, resource_id, session_id);

create function public.private_media_session_cookie_paths(
  p_user_id uuid, p_session_id uuid, p_after_kind text, p_after_id uuid
)
returns table(resource_kind text, resource_id uuid)
language plpgsql volatile security invoker set search_path = ''
as $$
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid
     or p_session_id = '00000000-0000-0000-0000-000000000000'::uuid
     or (p_after_kind is null) <> (p_after_id is null)
     or (p_after_kind is not null and p_after_kind not in ('archive', 'video'))
     or p_after_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Invalid media cookie inventory request.' using errcode = '22023';
  end if;
  -- Null session is reserved by the service for the fixed global logout route.
  perform o.user_id from public.private_media_owners o where o.user_id = p_user_id for share;
  return query select distinct g.resource_kind, g.resource_id
    from public.private_media_grants g
    where g.user_id = p_user_id
      and (p_session_id is null or g.session_id = p_session_id)
      and (p_after_kind is null or (g.resource_kind,g.resource_id) > (p_after_kind,p_after_id))
    order by g.resource_kind,g.resource_id limit 33;
end;
$$;
revoke all on function public.private_media_session_cookie_paths(uuid,uuid,text,uuid)
  from public,anon,authenticated;
grant execute on function public.private_media_session_cookie_paths(uuid,uuid,text,uuid) to service_role;

commit;
