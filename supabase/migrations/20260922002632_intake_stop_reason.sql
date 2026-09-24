-- The same lock serializes stop with reservation admission. Accepted
-- reservations and jobs are deliberately not modified by this operation.
create or replace function public.disable_video_upload_admission()
returns void language plpgsql security invoker
set search_path = public, pg_temp
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('peso:upload-capacity', 0));
  update public.upload_admission_control
    set enabled = false, disabled_reason = 'operator_or_measured_intake_stop', updated_at = now()
    where id = 1;
  if not found then
    raise exception 'Upload admission control is not configured.';
  end if;
end;
$$;
revoke execute on function public.disable_video_upload_admission() from public, anon, authenticated;
grant execute on function public.disable_video_upload_admission() to service_role;
