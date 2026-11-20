-- Mission 21: private user-uploaded images for authenticated Vision requests.
-- Additive only: existing conversations, messages and brochure assets are untouched.
begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('chat-uploads', 'chat-uploads', false, 5242880,
        array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- Restrictive scope guard ensures any pre-existing broad permissive storage
-- policy cannot grant access to another user's files in this bucket.
drop policy if exists chat_uploads_owner_scope_guard on storage.objects;
create policy chat_uploads_owner_scope_guard
on storage.objects as restrictive
for all to anon, authenticated
using (
    bucket_id = 'chat-uploads'
    and auth.uid() is not null
    and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
    bucket_id = 'chat-uploads'
    and auth.uid() is not null
    and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists chat_uploads_owner_select on storage.objects;
create policy chat_uploads_owner_select
on storage.objects for select to authenticated
using (
    bucket_id = 'chat-uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists chat_uploads_owner_delete on storage.objects;
create policy chat_uploads_owner_delete
on storage.objects for delete to authenticated
using (
    bucket_id = 'chat-uploads'
    and (storage.foldername(name))[1] = auth.uid()::text
);

-- Uploads and overwrite are backend-only; clients can read their own image
-- objects to mint short-lived signed URLs, and delete their own on chat delete.
commit;
