-- Schema do bot de vendas — rode no SQL Editor do Supabase.

create table if not exists produtos (
  id bigint generated always as identity primary key,
  nome text not null,
  preco numeric(10,2) not null default 0,
  criado_em timestamptz not null default now()
);

create table if not exists estoque (
  id bigint generated always as identity primary key,
  produto_id bigint not null references produtos(id) on delete cascade,
  conteudo text not null,
  vendido boolean not null default false,
  criado_em timestamptz not null default now()
);
create index if not exists idx_estoque_prod on estoque(produto_id, vendido);

create table if not exists planos (
  id bigint generated always as identity primary key,
  nome text not null,
  dias int not null,
  preco numeric(10,2) not null,
  cargo_id text,
  criado_em timestamptz not null default now()
);

create table if not exists config (
  guild_id text primary key,
  cargo_cliente text,
  canal_logs text,
  cargo_compras text,
  canal_logs_vendas text,
  cargo_suporte text,
  canal_sugestao text,
  dados_json jsonb default '{}'::jsonb
);
-- canal_logs_salas é guardado dentro de dados_json (jsonb) — sem migration.

create table if not exists sugestoes_log (
  user_id    text not null,
  guild_id   text not null,
  enviada_em timestamptz not null default now(),
  primary key (user_id, guild_id)
);

create table if not exists vendas (
  id bigint generated always as identity primary key,
  user_id text not null,
  tipo text not null,          -- 'produto' ou 'plano'
  ref_id text not null,        -- id do produto ou plano
  valor numeric(10,2) not null,
  status text not null default 'pendente',  -- pendente / pago / entregue
  txid text,
  criado_em timestamptz not null default now(),
  entregue_em timestamptz
);
create index if not exists idx_vendas_txid on vendas(txid);

-- ───────────────────────── ASSINATURAS (vencimento de plano) ─────────────────────────
-- Controla quando o plano de cada cliente vence, pra o bot remover o cargo do
-- plano e limpar a data do nick automaticamente quando expira. Uma linha por
-- (user_id, guild_id) — na renovação, atualiza o vence_em e o cargo.
create table if not exists assinaturas (
  user_id     text not null,
  guild_id    text not null,
  cargo_id    text,                  -- cargo do plano a remover quando vencer
  nome_base   text,                  -- nome sem a data, pra restaurar o nick
  vence_em    timestamptz not null,  -- quando expira (fuso aplicado na escrita)
  ativo       boolean not null default true,
  atualizado_em timestamptz not null default now(),
  primary key (user_id, guild_id)
);
create index if not exists idx_assinaturas_venc on assinaturas(ativo, vence_em);

-- ───────────────────────── WALLET (comissão de vendedores) ─────────────────────────
-- IDs liberados a usar /wallet + a porcentagem de cada venda que vira saldo deles.
create table if not exists wallet_config (
  user_id     text primary key,   -- ID do Discord liberado
  porcentagem numeric(5,2) not null default 0,  -- % do valor da venda que vira saldo
  criado_em   timestamptz not null default now()
);

-- Movimentos da carteira: comissões (entrada) e saques (saída).
create table if not exists wallet_movimentos (
  id        bigint generated always as identity primary key,
  user_id   text not null,
  tipo      text not null,            -- 'comissao' ou 'saque'
  valor     numeric(12,2) not null,   -- comissao: positivo | saque: positivo (debitado)
  venda_id  bigint,                   -- referência da venda (evita crédito duplo)
  criado_em timestamptz not null default now()
);
create index if not exists idx_wallet_mov_user on wallet_movimentos(user_id, criado_em);
create unique index if not exists idx_wallet_mov_venda
  on wallet_movimentos(venda_id, user_id) where tipo = 'comissao';

-- Planos padrão (3 dias R$8, 7 dias R$20, 1 mês R$50)
insert into planos (nome, dias, preco)
select * from (values
  ('1 dia', 1, 2.50),
  ('1 dia + salas infinitas', 1, 4.00),
  ('3 dias + 10 salas inicial', 3, 4.00),
  ('3 dias + 100 salas', 3, 5.50),
  ('3 dias + 300 salas', 3, 8.00),
  ('3 dias + salas infinitas', 3, 11.00),
  ('7 dias', 7, 12.00),
  ('7 dias + 100 salas', 7, 13.00),
  ('7 dias + 300 salas', 7, 15.00),
  ('7 dias + salas infinitas', 7, 20.00)
) as v(nome, dias, preco)
where not exists (select 1 from planos);

-- ───────────────────────── CUPONS DE DESCONTO ─────────────────────────
-- Criados pelos admins com /criar-cupom. Aplicados pelo cliente no botão
-- "Cupom" do painel de confirmar compra (Fase 1).
--   tipo = 'percent'  → valor é a % de desconto (ex: 10 = 10% off)
--   tipo = 'fixo'     → valor é o R$ abatido     (ex: 5 = R$5 off)
create table if not exists cupons (
  id        bigint generated always as identity primary key,
  codigo    text not null,
  tipo      text not null default 'percent',  -- 'percent' | 'fixo'
  valor     numeric(10,2) not null,
  ativo     boolean not null default true,
  criado_em timestamptz not null default now()
);
-- Código único (case-insensitive): guardamos sempre em MAIÚSCULAS no app.
create unique index if not exists idx_cupons_codigo on cupons(codigo);

-- % de desconto POR PLANO de cada cupom. Um cupom pode dar % diferente em
-- cada plano. Se não houver linha pro plano que o cliente compra, o cupom
-- não dá desconto naquele plano.
create table if not exists cupom_planos (
  id        bigint generated always as identity primary key,
  cupom_id  bigint not null references cupons(id) on delete cascade,
  plano_id  bigint not null references planos(id) on delete cascade,
  percent   numeric(5,2) not null,   -- ex: 10 = 10% off nesse plano
  criado_em timestamptz not null default now()
);
-- 1 % por (cupom, plano): redefinir = upsert nessa chave.
create unique index if not exists idx_cupom_planos_uniq
  on cupom_planos(cupom_id, plano_id);
