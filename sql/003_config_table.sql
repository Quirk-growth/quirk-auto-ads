-- Tabela de config (key-value) — armazena tokens centralizadamente
-- Substitui $env do n8n por SELECT, eliminando dependência de variáveis de ambiente do servidor
-- Migration 003

CREATE TABLE IF NOT EXISTS auto_ads.config (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL,
  atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Quem rotaciona o token Meta:
-- UPDATE auto_ads.config SET valor = 'NOVO_TOKEN', atualizado_em = NOW() WHERE chave = 'meta_access_token';

INSERT INTO auto_ads.config (chave, valor) VALUES
  ('meta_access_token', 'PREENCHER_APOS_APPLY')
ON CONFLICT (chave) DO NOTHING;
