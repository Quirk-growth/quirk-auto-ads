-- Migration 006: views de métricas + tabela de health check
-- Spec: dashboard de observabilidade (item 1 do hardening sprint)

-- ─── Tabela de health checks (resultado dos pings horários) ───
CREATE TABLE IF NOT EXISTS auto_ads.health_checks (
  id SERIAL PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT NOW(),
  ok BOOLEAN NOT NULL,
  duration_ms INT,
  exec_id TEXT,
  error_node TEXT,
  error_msg TEXT
);
CREATE INDEX IF NOT EXISTS health_checks_ts_idx ON auto_ads.health_checks (ts DESC);

-- ─── View: resumo das últimas 24h ───
CREATE OR REPLACE VIEW auto_ads.metrics_24h AS
SELECT
  COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '24 hours') AS execs_24h,
  COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '1 hour') AS execs_1h,
  -- contagem de eventos por tipo no audit_log
  (SELECT COUNT(*) FROM auto_ads.audit_log WHERE ts > NOW() - INTERVAL '24 hours' AND evento = 'campanha_criada') AS campanhas_criadas_24h,
  (SELECT COUNT(*) FROM auto_ads.audit_log WHERE ts > NOW() - INTERVAL '24 hours' AND evento = 'campanha_parcial') AS campanhas_parciais_24h,
  (SELECT COUNT(*) FROM auto_ads.audit_log WHERE ts > NOW() - INTERVAL '24 hours' AND evento LIKE 'gestao_%') AS gestoes_24h,
  (SELECT COUNT(*) FROM auto_ads.audit_log WHERE ts > NOW() - INTERVAL '24 hours' AND evento = 'precheck_barrado') AS precheck_barrados_24h,
  (SELECT COUNT(*) FROM auto_ads.audit_log WHERE ts > NOW() - INTERVAL '24 hours' AND evento = 'erro_validacao') AS validacoes_falhas_24h,
  -- health checks
  (SELECT COUNT(*) FROM auto_ads.health_checks WHERE ts > NOW() - INTERVAL '24 hours') AS health_runs_24h,
  (SELECT COUNT(*) FROM auto_ads.health_checks WHERE ts > NOW() - INTERVAL '24 hours' AND ok = false) AS health_fails_24h,
  (SELECT MAX(ts) FROM auto_ads.health_checks WHERE ok = true) AS last_ok_ts,
  (SELECT MAX(ts) FROM auto_ads.health_checks WHERE ok = false) AS last_fail_ts
FROM auto_ads.audit_log;

-- ─── View: top 5 motivos de erro nas últimas 24h ───
CREATE OR REPLACE VIEW auto_ads.metrics_erros_24h AS
SELECT
  detalhes->>'classe_erro' AS classe,
  detalhes->>'motivo_erro' AS motivo,
  COUNT(*) AS qtd
FROM auto_ads.audit_log
WHERE ts > NOW() - INTERVAL '24 hours'
  AND detalhes->>'ok' = 'false'
GROUP BY 1, 2
ORDER BY qtd DESC
LIMIT 10;

-- ─── View: campanhas ativas por cliente ───
CREATE OR REPLACE VIEW auto_ads.metrics_campanhas_status AS
SELECT
  c.telefone,
  c.status,
  COUNT(*) AS qtd
FROM auto_ads.campanhas c
GROUP BY 1, 2
ORDER BY 1, 2;
