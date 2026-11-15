begin;

-- The existing archive fence continues to validate identity, membership, live
-- source videos, state ordering and completed artifact details. This additional
-- boundary serializes owner deletion with new work and permits only bounded
-- terminal cleanup without a live owner. It never creates an owner from a child.
create function public.fence_owner_saved_lift_export()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' and new.status in ('expired', 'failed') then
    -- Failure/expiry cannot conceal a new selection, attempt or started_at.
    -- Clearing the artifact and deadline reduces access; completion bookkeeping
    -- may be preserved or advanced finitely, but no serving fields can be added.
    if (pg_catalog.to_jsonb(new) - array['status','archive_path','failure_code','completed_at','expires_at','updated_at'])
         = (pg_catalog.to_jsonb(old) - array['status','archive_path','failure_code','completed_at','expires_at','updated_at'])
       and new.archive_path is null
       and (new.completed_at is not distinct from old.completed_at or
            (new.completed_at is not null and pg_catalog.isfinite(new.completed_at)
             and (old.completed_at is null or not pg_catalog.isfinite(old.completed_at)
                  or new.completed_at >= old.completed_at)))
       and (new.expires_at is not distinct from old.expires_at or new.expires_at is null or
            (new.expires_at is not null and pg_catalog.isfinite(new.expires_at)
             and ((old.expires_at is not null and new.expires_at <= old.expires_at)
                  or (old.expires_at is null and new.expires_at <= pg_catalog.clock_timestamp())))) then
      return new;
    end if;
    raise exception 'Archive terminal cleanup cannot publish or rebind work.' using errcode = '55000';
  end if;
  -- An INSERT or active/completed update already owns its child row. NOWAIT
  -- avoids waiting against owner-first revocation/grant transactions.
  perform public.assert_active_private_media_owner(new.user_id);
  if tg_op = 'UPDATE' and old.user_id is distinct from new.user_id then
    perform public.assert_active_private_media_owner(old.user_id);
  end if;
  return new;
end;
$$;
revoke all on function public.fence_owner_saved_lift_export() from public, anon, authenticated;
grant execute on function public.fence_owner_saved_lift_export() to service_role;
create trigger fence_owner_saved_lift_export before insert or update on public.saved_lift_export_jobs
for each row execute function public.fence_owner_saved_lift_export();

commit;
