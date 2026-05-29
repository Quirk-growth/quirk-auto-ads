-- Migration 004 — estado_json (state machine pro fluxo state-aware v2)
-- Spec: docs/superpowers/specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md §4

ALTER TABLE auto_ads.conversas
ADD COLUMN IF NOT EXISTS estado_json JSONB NOT NULL DEFAULT '{
  "etapa_atual": "coletando_info",
  "criativo": {"recebido": false, "url": null, "mimetype": null, "recebido_em": null},
  "brief": {},
  "ultima_tentativa": null
}'::jsonb;

-- Index pra queries por etapa (sub-projetos B e C vão usar)
CREATE INDEX IF NOT EXISTS conversas_etapa_idx
  ON auto_ads.conversas ((estado_json ->> 'etapa_atual'));

-- Populate linhas existentes com criativo já recebido (caso houver criativo_url)
UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  estado_json,
  '{criativo}',
  jsonb_build_object(
    'recebido', true,
    'url', criativo_url,
    'mimetype', NULL,
    'recebido_em', ultima_atualizacao
  )
)
WHERE criativo_url IS NOT NULL AND length(trim(criativo_url)) > 5;
