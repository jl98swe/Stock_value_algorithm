-- Capacity enforcement for concurrent signups.
-- Run after the initial alert tables have been created.
create or replace function public.alert_subscriber_capacity_guard()
returns trigger language plpgsql security definer
set search_path = public
as $$
begin
  if new.status in ('pending','active') and
     (tg_op = 'INSERT' or old.status = 'unsubscribed') then
    perform pg_advisory_xact_lock(847291, 4);
    if (select count(*) from public.alert_subscribers
        where status in ('pending','active')
          and id is distinct from new.id) >= 10 then
      raise exception 'subscription capacity reached' using errcode = 'P0001';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists alert_subscriber_capacity_trigger on public.alert_subscribers;
create trigger alert_subscriber_capacity_trigger
before insert or update of status on public.alert_subscribers
for each row execute function public.alert_subscriber_capacity_guard();

revoke all on function public.alert_subscriber_capacity_guard() from public, anon, authenticated;
