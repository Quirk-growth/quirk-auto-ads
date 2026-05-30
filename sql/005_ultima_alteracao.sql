-- Migration 005 — ultima_alteracao em auto_ads.campanhas
-- Spec: docs/superpowers/specs/2026-05-30-quirk-auto-ads-B-gestao-campanhas-design.md §9.1

ALTER TABLE auto_ads.campanhas
ADD COLUMN IF NOT EXISTS ultima_alteracao TIMESTAMPTZ;

UPDATE auto_ads.campanhas SET ultima_alteracao = criada_em WHERE ultima_alteracao IS NULL;

ALTER TABLE auto_ads.campanhas
ALTER COLUMN ultima_alteracao SET DEFAULT NOW();
