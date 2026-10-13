-- Private subscription storage. Apply in Supabase SQL editor, never in public Pages data.
create extension if not exists pgcrypto;
create table if not exists public.alert_subscribers (
 id uuid primary key default gen_random_uuid(),
 email text not null,
 email_normalized text generated always as (lower(btrim(email))) stored,
 status text not null default 'pending' check (status in ('pending','active','unsubscribed')),
 consent_at timestamptz not null default now(),
 confirmed_at timestamptz,
 unsubscribed_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 constraint valid_email check (length(email) between 3 and 254 and position('@' in email)>1)
);
create unique index if not exists alert_subscriber_email_uq on public.alert_subscribers(email_normalized);
create table if not exists public.alert_preferences (
 subscriber_id uuid primary key references public.alert_subscribers(id) on delete cascade,
 channels text[] not null default array['email']::text[],
 topics text[] not null default array['signals']::text[],
 strategy text not null default 'all',
 tickers text[] not null default array[]::text[],
 updated_at timestamptz not null default now(),
 constraint channels_valid check (channels <@ array['email','push']::text[] and cardinality(channels)>0),
 constraint topics_valid check (topics <@ array['signals','near_signals','reports_upcoming','reports_updated','stop_loss','data_issues']::text[] and cardinality(topics)>0),
 constraint strategy_valid check (strategy in ('all','standard','ma200','report_avoidance','standard_stop_loss_10'))
);
create table if not exists public.alert_tokens (
 token_hash text primary key,
 subscriber_id uuid not null references public.alert_subscribers(id) on delete cascade,
 purpose text not null check (purpose in ('confirm','manage','unsubscribe')),
 expires_at timestamptz not null,
 consumed_at timestamptz,
 created_at timestamptz not null default now()
);
create index if not exists alert_tokens_subscriber_idx on public.alert_tokens(subscriber_id);
create table if not exists public.alert_push_subscriptions (
 id uuid primary key default gen_random_uuid(),
 subscriber_id uuid not null references public.alert_subscribers(id) on delete cascade,
 endpoint text not null unique,
 p256dh text not null,
 auth text not null,
 created_at timestamptz not null default now()
);
create table if not exists public.alert_delivery_log (
 id uuid primary key default gen_random_uuid(),
 subscriber_id uuid not null references public.alert_subscribers(id) on delete cascade,
 channel text not null check (channel in ('email','push')),
 trading_date date not null,
 digest_key text not null,
 status text not null check (status in ('pending','sent','failed')),
 provider_message_id text,
 created_at timestamptz not null default now(),
 sent_at timestamptz,
 unique(subscriber_id,channel,trading_date,digest_key)
);
create index if not exists alert_delivery_date_idx on public.alert_delivery_log(trading_date);
alter table public.alert_subscribers enable row level security;
alter table public.alert_preferences enable row level security;
alter table public.alert_tokens enable row level security;
alter table public.alert_push_subscriptions enable row level security;
alter table public.alert_delivery_log enable row level security;
-- No anonymous or authenticated client policies. Only backend service role accesses tables.
revoke all on public.alert_subscribers,public.alert_preferences,public.alert_tokens,public.alert_push_subscriptions,public.alert_delivery_log from anon,authenticated;
