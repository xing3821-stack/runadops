-- ===========================================================
-- runadops 操盘控制台 · 建表脚本
-- 用法:Supabase → SQL Editor → New query → 全文粘贴 → Run(只需跑一次)
-- 对应手册第 6 节。重复执行是安全的。
-- ===========================================================

-- 账号档案:角色 owner / admin / member
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  name text,
  role text not null default 'member',
  created_at timestamptz default now()
);

-- 全部业务数据都放这一张表,用 type 区分:
--   client   客户        package  套餐
--   project  投放项目    payment  收款
--   settings 投放配置(下拉选项,全站一条)
create table if not exists public.records (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  data jsonb not null default '{}',
  updated_at timestamptz default now(),
  updated_by uuid
);
create index if not exists records_type_idx on public.records(type);

-- 行级安全
alter table public.profiles enable row level security;
alter table public.records  enable row level security;

drop policy if exists "profiles_read"        on public.profiles;
drop policy if exists "profiles_insert_self" on public.profiles;
drop policy if exists "profiles_update_self" on public.profiles;
drop policy if exists "records_all_auth"     on public.records;

create policy "profiles_read"        on public.profiles for select to authenticated using (true);
create policy "profiles_insert_self" on public.profiles for insert to authenticated with check (auth.uid() = id);
create policy "profiles_update_self" on public.profiles for update to authenticated using (auth.uid() = id);
create policy "records_all_auth"     on public.records  for all    to authenticated using (true) with check (true);

-- 实时同步(控制台靠这个让全员看到同一套数据)
do $do$
begin
  begin
    alter publication supabase_realtime add table public.records;
  exception when duplicate_object then null;
  end;
  begin
    alter publication supabase_realtime add table public.profiles;
  exception when duplicate_object then null;
  end;
end
$do$;

-- 新用户注册时自动建档案;第一个注册的人 = owner
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare cnt int;
begin
  select count(*) into cnt from public.profiles;
  insert into public.profiles(id, email, name, role)
  values (new.id, new.email, split_part(coalesce(new.email,'user'),'@',1),
          case when cnt = 0 then 'owner' else 'member' end)
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute procedure public.handle_new_user();


-- ===========================================================
-- 可选加固(默认不启用)
-- -----------------------------------------------------------
-- 上面的 records_all_auth 允许任何登录用户删除数据;控制台界面
-- 里对 member 隐藏了删除按钮,但那只是前端限制——会用 API 的人
-- 仍然删得掉。要让"只有 owner/admin 能删"变成数据库级规则,
-- 把下面整段取消注释后执行:
-- ===========================================================
-- drop policy if exists "records_all_auth" on public.records;
--
-- create policy "records_select" on public.records for select to authenticated using (true);
-- create policy "records_insert" on public.records for insert to authenticated with check (true);
-- create policy "records_update" on public.records for update to authenticated using (true) with check (true);
-- create policy "records_delete" on public.records for delete to authenticated using (
--   exists (select 1 from public.profiles p where p.id = auth.uid() and p.role in ('owner','admin'))
-- );
--
-- -- 同时防止成员自己改自己的角色(配合上面一起用):
-- drop policy if exists "profiles_update_self" on public.profiles;
-- create policy "profiles_update_self" on public.profiles for update to authenticated
--   using (auth.uid() = id)
--   with check (auth.uid() = id and role = (select p.role from public.profiles p where p.id = auth.uid()));
