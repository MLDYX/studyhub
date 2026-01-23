-- Uruchom w Supabase SQL Editor przed logowaniem username/hasło
alter table users add column if not exists username text unique;
alter table users add column if not exists password_hash text;
create unique index if not exists users_username_lower_idx on users (lower(username));

-- Kalendarz: dodatkowe pola i indeksy
alter table calendar_events add column if not exists color_key text default 'Niebieski';
alter table calendar_events add column if not exists deleted_at timestamptz;
alter table calendar_events add column if not exists source_id text;
alter table calendar_events add column if not exists source_type text;
create index if not exists calendar_events_user_active_idx on calendar_events (user_id, deleted_at);

-- Poczta: persystencja maili wyłączona (brak zmian w schemacie mail_messages/mail_attachments)

-- Notatki: prosty model (tytul + tresc + zalaczniki + soft delete)
alter table notes add column if not exists user_id uuid;
alter table notes add column if not exists title text;
alter table notes add column if not exists content text;
alter table notes add column if not exists deleted_at timestamptz;
alter table notes add column if not exists created_at timestamptz default now();
alter table notes add column if not exists updated_at timestamptz default now();

create table if not exists notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text not null,
  content text,
  deleted_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists notes_user_active_idx on notes (user_id, deleted_at);
create index if not exists notes_title_idx on notes using btree (title);

create table if not exists note_attachments (
  id uuid primary key default gen_random_uuid(),
  note_id uuid references notes(id) on delete cascade,
  blob_path text not null,
  file_name text not null,
  mime_type text,
  size_bytes int,
  created_at timestamptz default now()
);
create index if not exists note_attachments_note_idx on note_attachments (note_id);
