begin;

-- The existing owner/kind/resource/session index covers global inventory.
create index private_media_grants_local_cookie_paths_idx
  on public.private_media_grants(user_id,session_id,resource_kind,resource_id);

create function public.private_media_session_cookie_paths_v2(
  p_user_id uuid,p_session_id uuid,p_after_kind text,p_after_id uuid,p_after_session_id uuid
)
returns table(resource_kind text,resource_id uuid,cookie_session_id uuid)
language plpgsql volatile security invoker set search_path='' set lock_timeout='2s'
as $$
begin
  if p_user_id is null or p_user_id='00000000-0000-0000-0000-000000000000'::uuid
     or p_session_id='00000000-0000-0000-0000-000000000000'::uuid
     or not ((p_after_kind is null and p_after_id is null and p_after_session_id is null)
             or (p_after_kind is not null and p_after_id is not null and p_after_session_id is not null))
     or (p_after_kind is not null and p_after_kind not in ('archive','avatar','video'))
     or p_after_id='00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Invalid media cookie inventory request.' using errcode='22023';
  end if;
  -- Null session is service-selected global scope, not a caller identity.
  perform o.user_id from public.private_media_owners o where o.user_id=p_user_id for share;
  return query
    select paths.kind,paths.resource,paths.cookie_session
    from (
      -- NIL denotes only the legacy resource path, never an authorized session.
      select g.resource_kind as kind,g.resource_id as resource,
        '00000000-0000-0000-0000-000000000000'::uuid as cookie_session
      from public.private_media_grants g
      where g.user_id=p_user_id and (p_session_id is null or g.session_id=p_session_id)
      union
      select g.resource_kind,g.resource_id,g.session_id
      from public.private_media_grants g
      where g.user_id=p_user_id and (p_session_id is null or g.session_id=p_session_id)
    ) paths
    where p_after_kind is null or (paths.kind,paths.resource,paths.cookie_session)>
      (p_after_kind,p_after_id,p_after_session_id)
    order by paths.kind,paths.resource,paths.cookie_session limit 17;
end;
$$;
revoke all on function public.private_media_session_cookie_paths_v2(uuid,uuid,text,uuid,uuid)
  from public,anon,authenticated;
grant execute on function public.private_media_session_cookie_paths_v2(uuid,uuid,text,uuid,uuid) to service_role;

commit;
