begin;
set local lock_timeout='2s';

-- Freeze signup through backfill/trigger installation; keep every tombstone.
lock table auth.users, public.profiles in share row exclusive mode nowait;
insert into public.private_media_owners(user_id)
  select u.id from auth.users u on conflict do nothing;

create schema peso_private authorization postgres;
revoke all on schema peso_private from public,anon,authenticated,service_role;
grant usage on schema peso_private to authenticated;

-- Auth's trusted INSERT supplies the identity; no user metadata is consulted.
create function peso_private.initialize_private_media_owner()
returns trigger language plpgsql security definer set search_path='' set lock_timeout='2s'
as $$
begin
  insert into public.private_media_owners(user_id) values(new.id) on conflict do nothing;
  return new;
end;
$$;
alter function peso_private.initialize_private_media_owner() owner to postgres;
revoke all on function peso_private.initialize_private_media_owner() from public,anon,authenticated,service_role,supabase_auth_admin;
create trigger initialize_private_media_owner after insert on auth.users
for each row execute function peso_private.initialize_private_media_owner();

-- Only this boolean decision crosses the private owner-table boundary.
-- Do not create missing owners from a profile/Storage child transaction.
create function peso_private.owned_media_write_is_live(p_user_id uuid)
returns boolean language plpgsql volatile security definer set search_path=''
as $$
declare v_at timestamptz;
begin
  if p_user_id is null or p_user_id is distinct from auth.uid() then return false; end if;
  select o.deleting_at into v_at from public.private_media_owners o
    where o.user_id=p_user_id for update nowait;
  return found and v_at is null;
end;
$$;
alter function peso_private.owned_media_write_is_live(uuid) owner to postgres;
revoke all on function peso_private.owned_media_write_is_live(uuid) from public,anon,authenticated,service_role,supabase_auth_admin;
grant execute on function peso_private.owned_media_write_is_live(uuid) to authenticated;

create function public.fence_owner_profile_write()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if tg_op='UPDATE' and new.id is distinct from old.id then
    raise exception 'Profile identity cannot change.' using errcode='55000';
  end if;
  if current_user='authenticated' then
    if not peso_private.owned_media_write_is_live(new.id) then
      raise exception 'Profile owner is unavailable.' using errcode='55000';
    end if;
  else
    perform public.assert_active_private_media_owner(new.id);
  end if;
  return new;
end;
$$;
revoke all on function public.fence_owner_profile_write() from public,anon;
grant execute on function public.fence_owner_profile_write() to authenticated,service_role;
create trigger fence_owner_profile_write before insert or update on public.profiles
for each row execute function public.fence_owner_profile_write();

-- These restrictive policies add denial to the existing bucket/folder rules.
-- They never authorize access on their own or modify provider Storage metadata.
create policy owner_media_insert_admission on storage.objects as restrictive
for insert to authenticated with check (
  bucket_id not in ('videos','profile-avatars') or (
    (storage.foldername(name))[1]=(select auth.uid())::text
    and peso_private.owned_media_write_is_live((select auth.uid()))
  )
);
create policy owner_media_update_admission on storage.objects as restrictive
for update to authenticated using (
  bucket_id not in ('videos','profile-avatars') or (
    (storage.foldername(name))[1]=(select auth.uid())::text
    and peso_private.owned_media_write_is_live((select auth.uid()))
  )
) with check (
  bucket_id not in ('videos','profile-avatars') or (
    (storage.foldername(name))[1]=(select auth.uid())::text
    and peso_private.owned_media_write_is_live((select auth.uid()))
  )
);

commit;
