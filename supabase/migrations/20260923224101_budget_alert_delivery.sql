-- Service-only delivery ledger. An expired claim may be retried; SMTP delivery
-- followed by a crash before acknowledgement can result in one duplicate.
create table public.budget_alert_delivery (
  month_start date not null,
  threshold_usd integer not null check (threshold_usd in (15, 25, 35, 50)),
  claim_id uuid not null,
  claim_expires_at timestamptz not null,
  delivered_at timestamptz,
  primary key (month_start, threshold_usd),
  constraint budget_alert_month_start_check check (month_start = date_trunc('month', month_start::timestamp)::date)
);
alter table public.budget_alert_delivery enable row level security;
revoke all on public.budget_alert_delivery from public, anon, authenticated;
grant select, insert, update on public.budget_alert_delivery to service_role;

create function public.claim_budget_alert(p_month_start date, p_threshold_usd integer, p_claim_id uuid)
returns boolean language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare v_count integer;
begin
  if p_claim_id is null then raise exception 'A claim ID is required.'; end if;
  insert into public.budget_alert_delivery(month_start, threshold_usd, claim_id, claim_expires_at)
    values (p_month_start, p_threshold_usd, p_claim_id, now() + interval '15 minutes')
    on conflict (month_start, threshold_usd) do update
      set claim_id = excluded.claim_id, claim_expires_at = excluded.claim_expires_at
      where public.budget_alert_delivery.delivered_at is null
        and public.budget_alert_delivery.claim_expires_at < now();
  get diagnostics v_count = row_count;
  return v_count = 1;
end;
$$;
revoke execute on function public.claim_budget_alert(date, integer, uuid) from public, anon, authenticated;
grant execute on function public.claim_budget_alert(date, integer, uuid) to service_role;

create function public.complete_budget_alert(p_month_start date, p_threshold_usd integer, p_claim_id uuid)
returns boolean language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare v_count integer;
begin
  update public.budget_alert_delivery set delivered_at = now()
    where month_start = p_month_start and threshold_usd = p_threshold_usd
      and claim_id = p_claim_id and delivered_at is null;
  get diagnostics v_count = row_count;
  return v_count = 1;
end;
$$;
revoke execute on function public.complete_budget_alert(date, integer, uuid) from public, anon, authenticated;
grant execute on function public.complete_budget_alert(date, integer, uuid) to service_role;

create function public.release_budget_alert(p_month_start date, p_threshold_usd integer, p_claim_id uuid)
returns boolean language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare v_count integer;
begin
  update public.budget_alert_delivery set claim_expires_at = now() - interval '1 second'
    where month_start = p_month_start and threshold_usd = p_threshold_usd
      and claim_id = p_claim_id and delivered_at is null;
  get diagnostics v_count = row_count;
  return v_count = 1;
end;
$$;
revoke execute on function public.release_budget_alert(date, integer, uuid) from public, anon, authenticated;
grant execute on function public.release_budget_alert(date, integer, uuid) to service_role;
