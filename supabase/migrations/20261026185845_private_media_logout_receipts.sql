begin;

-- Retain the exact logout result across lost HTTP/provider responses.
create table public.private_media_logout_receipts (
  user_id uuid not null references public.private_media_owners(user_id),
  request_id uuid not null check (request_id <> '00000000-0000-0000-0000-000000000000'::uuid),
  session_id uuid not null check (session_id <> '00000000-0000-0000-0000-000000000000'::uuid),
  scope text not null check (scope in ('global', 'local', 'others')),
  completed_at timestamptz not null default clock_timestamp(),
  primary key (user_id, request_id)
);
alter table public.private_media_logout_receipts enable row level security;
revoke all on public.private_media_logout_receipts from public, anon, authenticated, service_role;
grant select, insert on public.private_media_logout_receipts to service_role;

create function public.revoke_private_media_session_once(
  p_user_id uuid, p_session_id uuid, p_scope text, p_request_id uuid
)
returns table(completed_at timestamptz, replayed boolean)
language plpgsql volatile security invoker set search_path = ''
as $$
declare v_receipt public.private_media_logout_receipts%rowtype;
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid
     or p_session_id is null or p_session_id = '00000000-0000-0000-0000-000000000000'::uuid
     or p_request_id is null or p_request_id = '00000000-0000-0000-0000-000000000000'::uuid
     or p_scope is null or p_scope not in ('global', 'local', 'others') then
    raise exception 'Invalid media logout request.' using errcode = '22023';
  end if;
  insert into public.private_media_owners(user_id) values(p_user_id) on conflict do nothing;
  perform o.user_id from public.private_media_owners o where o.user_id = p_user_id for update;
  select r.* into v_receipt from public.private_media_logout_receipts r
    where r.user_id = p_user_id and r.request_id = p_request_id;
  if found then
    if v_receipt.session_id <> p_session_id or v_receipt.scope <> p_scope then
      raise exception 'Media logout request binding changed.' using errcode = '22023';
    end if;
    -- This is proof of an earlier commit, not permission for another logout.
    return query select v_receipt.completed_at, true;
    return;
  end if;
  if not public.revoke_private_media_session(p_user_id, p_session_id, p_scope) then
    raise exception 'Media logout unavailable.' using errcode = '42501';
  end if;
  insert into public.private_media_logout_receipts(user_id,request_id,session_id,scope)
    values(p_user_id,p_request_id,p_session_id,p_scope) returning * into v_receipt;
  return query select v_receipt.completed_at, false;
end;
$$;

revoke all on function public.revoke_private_media_session_once(uuid,uuid,text,uuid)
  from public, anon, authenticated;
grant execute on function public.revoke_private_media_session_once(uuid,uuid,text,uuid) to service_role;

commit;
