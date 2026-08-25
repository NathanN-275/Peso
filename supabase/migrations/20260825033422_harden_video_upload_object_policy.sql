-- Storage rejects executable and other unsupported object names before an
-- authenticated client can leave them in the private videos bucket.
drop policy if exists "Users can upload own private videos" on storage.objects;
create policy "Users can upload own private videos"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = (select auth.uid())::text
  and storage.extension(name) = any (array['mp4', 'mov', 'm4v', 'webm'])
);

drop policy if exists "Users can update own private videos" on storage.objects;
create policy "Users can update own private videos"
on storage.objects
for update
to authenticated
using (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = (select auth.uid())::text
)
with check (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = (select auth.uid())::text
  and storage.extension(name) = any (array['mp4', 'mov', 'm4v', 'webm'])
);
