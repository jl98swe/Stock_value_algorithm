-- Private transactional queue for Gmail Actions. Apply in Supabase SQL Editor.
create table if not exists public.alert_email_queue (
 id uuid primary key default gen_random_uuid(),
 subscriber_id uuid not null references public.alert_subscribers(id) on delete cascade,
 recipient text not null,
 subject text not null,
 body text not null,
 status text not null default 'pending' check(status in ('pending','sending','sent','failed')),
 attempts integer not null default 0,
 created_at timestamptz not null default now(),
 claimed_at timestamptz,
 sent_at timestamptz
);
create index if not exists alert_email_queue_pending_idx on public.alert_email_queue(created_at) where status='pending';
alter table public.alert_email_queue enable row level security;
revoke all on public.alert_email_queue from anon, authenticated;
grant select, insert, update, delete on public.alert_email_queue to service_role;
