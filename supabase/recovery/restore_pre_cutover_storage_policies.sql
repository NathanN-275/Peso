-- Recovery-only artifact from the verified September 23 pre-cutover schema.
-- NOT a migration. Use only on an explicitly selected isolated recovery target.
-- Never apply after security-cutover.sql: this restores direct client writes.
-- Caller must SET peso.recovery_target = 'isolated-storage-policy-rehearsal'.
begin;
do $$
begin
  if current_setting('peso.recovery_target', true) is distinct from 'isolated-storage-policy-rehearsal' then
    raise exception 'Explicit isolated recovery target acknowledgement required';
  end if;
  if not exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'storage' and c.relname = 'objects' and c.relrowsecurity) then
    raise exception 'storage.objects with RLS enabled is required';
  end if;
  if exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects') then
    raise exception 'Target must have no existing Storage object policies';
  end if;
end $$;

CREATE POLICY "Users can delete own private videos" ON "storage"."objects" FOR DELETE TO "authenticated" USING ((("bucket_id" = 'videos'::"text") AND (("storage"."foldername"("name"))[1] = ("auth"."uid"())::"text")));
CREATE POLICY "Users can delete own profile avatars" ON "storage"."objects" FOR DELETE TO "authenticated" USING ((("bucket_id" = 'profile-avatars'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text")));
CREATE POLICY "Users can read own private videos" ON "storage"."objects" FOR SELECT TO "authenticated" USING ((("bucket_id" = 'videos'::"text") AND (("storage"."foldername"("name"))[1] = ("auth"."uid"())::"text")));
CREATE POLICY "Users can read own profile avatars" ON "storage"."objects" FOR SELECT TO "authenticated" USING ((("bucket_id" = 'profile-avatars'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text")));
CREATE POLICY "Users can update own private videos" ON "storage"."objects" FOR UPDATE TO "authenticated" USING ((("bucket_id" = 'videos'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text"))) WITH CHECK ((("bucket_id" = 'videos'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text") AND ("storage"."extension"("name") = ANY (ARRAY['mp4'::"text", 'mov'::"text", 'm4v'::"text", 'webm'::"text"]))));
CREATE POLICY "Users can update own profile avatars" ON "storage"."objects" FOR UPDATE TO "authenticated" USING ((("bucket_id" = 'profile-avatars'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text"))) WITH CHECK ((("bucket_id" = 'profile-avatars'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text")));
CREATE POLICY "Users can upload own private videos" ON "storage"."objects" FOR INSERT TO "authenticated" WITH CHECK ((("bucket_id" = 'videos'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text") AND ("storage"."extension"("name") = ANY (ARRAY['mp4'::"text", 'mov'::"text", 'm4v'::"text", 'webm'::"text"]))));
CREATE POLICY "Users can upload own profile avatars" ON "storage"."objects" FOR INSERT TO "authenticated" WITH CHECK ((("bucket_id" = 'profile-avatars'::"text") AND (("storage"."foldername"("name"))[1] = (( SELECT "auth"."uid"() AS "uid"))::"text")));
commit;
