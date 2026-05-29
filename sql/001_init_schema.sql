-- Quirk Auto Ads — Schema inicial
-- Migration 001
-- Data: 2026-05-28
-- Spec: docs/2026-05-28-quirk-auto-ads-n8n-migration-design.md (Seção 4)

CREATE SCHEMA IF NOT EXISTS auto_ads;

-- ──────────────────────────────────────────────
-- Cadastro multi-cliente
-- Substitui o Data Store do Make
-- access_token NÃO fica aqui (centralizado em ENV — Fase E)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.clientes (
  telefone TEXT PRIMARY KEY,
  ad_account_id TEXT NOT NULL,
  page_id TEXT NOT NULL,
  wa_link TEXT NOT NULL,
  nome_cliente TEXT,
  ativo BOOLEAN DEFAULT TRUE,
  criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Conversas (memória + criativos)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.conversas (
  telefone TEXT PRIMARY KEY REFERENCES auto_ads.clientes(telefone) ON DELETE CASCADE,
  historico TEXT DEFAULT '',
  criativo_url TEXT DEFAULT '',
  ultima_atualizacao TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Tracking de campanhas — Fase E
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.campanhas (
  id BIGSERIAL PRIMARY KEY,
  telefone TEXT REFERENCES auto_ads.clientes(telefone),
  nome_campanha TEXT,
  ad_account_id TEXT,
  campaign_id TEXT,
  adset_id TEXT,
  creative_id TEXT,
  ad_id TEXT,
  status TEXT,
  json_extrator JSONB,
  criada_em TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Audit log — Fase E
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.audit_log (
  id BIGSERIAL PRIMARY KEY,
  telefone TEXT,
  evento TEXT NOT NULL,
  detalhes JSONB,
  ts TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para queries de relatório (Fase F futuro)
CREATE INDEX IF NOT EXISTS idx_campanhas_telefone ON auto_ads.campanhas(telefone);
CREATE INDEX IF NOT EXISTS idx_campanhas_criada ON auto_ads.campanhas(criada_em DESC);
CREATE INDEX IF NOT EXISTS idx_audit_telefone ON auto_ads.audit_log(telefone);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON auto_ads.audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_evento ON auto_ads.audit_log(evento);
