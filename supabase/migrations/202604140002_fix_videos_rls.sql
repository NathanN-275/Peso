alter table public.videos
  alter column user_id type uuid using user_id::uuid,
  alter column user_id set not null;

do $$
declare
  user_id_attnum smallint;
begin
  select attnum
  into user_id_attnum
  from pg_attribute
  where attrelid = 'public.videos'::regclass
    and attname = 'user_id'
    and not attisdropped;

  if user_id_attnum is null then
    raise exception 'public.videos.user_id column is missing';
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.videos'::regclass
      and confrelid = 'auth.users'::regclass
      and contype = 'f'
      and conkey = array[user_id_attnum]
  ) then
    alter table public.videos
      add constraint videos_user_id_fkey
      foreign key (user_id) references auth.users (id) on delete cascade;
  end if;
end;
$$;

alter table public.videos enable row level security;

do $$
declare
  policy_record record;
begin
  for policy_record in
    select policyname
    from pg_policies
    where schemaname = 'public'
      and tablename = 'videos'
  loop
    execute format('drop policy if exists %I on public.videos', policy_record.policyname);
  end loop;
end;
$$;

create policy "Users can view own videos"
on public.videos
for select
to authenticated
using (auth.uid() = user_id);

create policy "Users can insert own videos"
on public.videos
for insert
to authenticated
with check (auth.uid() = user_id);

create policy "Users can update own videos"
on public.videos
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "Users can delete own videos"
on public.videos
for delete
to authenticated
using (auth.uid() = user_id);
