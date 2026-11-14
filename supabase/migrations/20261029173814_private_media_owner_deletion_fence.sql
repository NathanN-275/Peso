begin;

-- The owner row survives Auth deletion and serializes deletion with media grants.
alter table public.private_media_owners add column deleting_at timestamptz;

create function public.guard_private_media_owner_deletion()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Owner deletion fence must be retained.' using errcode = '55000';
  end if;
  if tg_op = 'INSERT' then
    if new.user_id is null or new.user_id = '00000000-0000-0000-0000-000000000000'::uuid
       or new.deleting_at is not null then
      raise exception 'An owner must be inserted before deletion begins.' using errcode = '55000';
    end if;
  elsif new.user_id is distinct from old.user_id
     or (old.deleting_at is not null and new.deleting_at is distinct from old.deleting_at)
     or (new.deleting_at is not null and not pg_catalog.isfinite(new.deleting_at)) then
    raise exception 'Owner deletion fence cannot change or clear.' using errcode = '55000';
  end if;
  if tg_op = 'UPDATE' and old.deleting_at is null and new.deleting_at is not null then
    -- Direct privileged maintenance updates must revoke grants atomically too.
    update public.private_media_grants g set revoked_at = coalesce(g.revoked_at, new.deleting_at)
      where g.user_id = new.user_id and g.revoked_at is null;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_private_media_owner_deletion() from public, anon, authenticated;
grant execute on function public.guard_private_media_owner_deletion() to service_role;
create trigger guard_private_media_owner_deletion before insert or update or delete
on public.private_media_owners for each row execute function public.guard_private_media_owner_deletion();

-- Begin is idempotent after a lost response and never depends on a live Auth row.
create function public.begin_private_media_owner_deletion(p_user_id uuid)
returns table(deleting_at timestamptz, replayed boolean)
language plpgsql volatile security invoker set search_path = ''
as $$
declare v_at timestamptz;
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'A nonzero owner is required.' using errcode = '22023';
  end if;
  insert into public.private_media_owners(user_id) values (p_user_id) on conflict do nothing;
  select o.deleting_at into v_at from public.private_media_owners o
    where o.user_id = p_user_id for update;
  if v_at is not null then
    return query select v_at, true;
    return;
  end if;
  v_at := pg_catalog.clock_timestamp();
  update public.private_media_owners o set deleting_at = v_at where o.user_id = p_user_id;
  return query select v_at, false;
end;
$$;
revoke all on function public.begin_private_media_owner_deletion(uuid) from public, anon, authenticated;
grant execute on function public.begin_private_media_owner_deletion(uuid) to service_role;

-- One row distinguishes an absent owner, a live owner, and a deleting owner.
create function public.read_private_media_owner_deletion(p_user_id uuid)
returns table(owner_exists boolean, deleting_at timestamptz)
language plpgsql volatile security invoker set search_path = ''
as $$
declare v_at timestamptz; v_exists boolean;
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'A nonzero owner is required.' using errcode = '22023';
  end if;
  select o.deleting_at into v_at from public.private_media_owners o
    where o.user_id = p_user_id for share;
  v_exists := found;
  return query select v_exists, v_at;
end;
$$;
revoke all on function public.read_private_media_owner_deletion(uuid) from public, anon, authenticated;
grant execute on function public.read_private_media_owner_deletion(uuid) to service_role;

-- Grant issuance and byte authorization call this only after the owner row lock.
create or replace function public.private_media_app_session_is_live(p_user_id uuid, p_session_id uuid)
returns boolean language plpgsql volatile security invoker set search_path = ''
as $$
declare v_cutoff timestamptz;
begin
  if exists (select 1 from public.private_media_owners o
             where o.user_id = p_user_id and o.deleting_at is not null) then
    return false;
  end if;
  if not public.private_media_session_is_live(p_user_id, p_session_id)
     or exists (select 1 from public.private_media_session_revocations r
                where r.user_id = p_user_id and r.session_id = p_session_id) then
    return false;
  end if;
  select max(e.cutoff) into v_cutoff from public.private_media_logout_events e
    where e.user_id = p_user_id and e.exempt_session_id is distinct from p_session_id;
  if v_cutoff is not null then
    return public.private_media_session_is_live_since(p_user_id, p_session_id, v_cutoff);
  end if;
  return true;
end;
$$;
revoke all on function public.private_media_app_session_is_live(uuid,uuid) from public, anon, authenticated;
grant execute on function public.private_media_app_session_is_live(uuid,uuid) to service_role;

commit;
