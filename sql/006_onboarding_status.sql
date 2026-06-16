-- Migration 006: adiciona status + dados de assinatura à tabela clientes
-- Onboarding autônomo Quirk Auto Ads (spec 2026-06-16)

BEGIN;

-- 1. Novas colunas
ALTER TABLE auto_ads.clientes
  ADD COLUMN IF NOT EXISTS status                   text,
  ADD COLUMN IF NOT EXISTS email                    text,
  ADD COLUMN IF NOT EXISTS gateway                  text,
  ADD COLUMN IF NOT EXISTS subscription_id          text,
  ADD COLUMN IF NOT EXISTS subscription_started_at  timestamptz,
  ADD COLUMN IF NOT EXISTS subscription_canceled_at timestamptz,
  ADD COLUMN IF NOT EXISTS status_atualizado_em     timestamptz DEFAULT NOW();

-- 2. Migrar clientes existentes (ativo=true → status='ativo', resto → 'inativo')
UPDATE auto_ads.clientes
SET status = CASE WHEN ativo = true THEN 'ativo' ELSE 'inativo' END,
    status_atualizado_em = NOW()
WHERE status IS NULL;

-- 3. Tornar status NOT NULL (depois da migration de dados)
ALTER TABLE auto_ads.clientes
  ALTER COLUMN status SET NOT NULL;

-- 4. Constraint pra valores válidos
ALTER TABLE auto_ads.clientes
  DROP CONSTRAINT IF EXISTS clientes_status_check;
ALTER TABLE auto_ads.clientes
  ADD CONSTRAINT clientes_status_check
    CHECK (status IN ('pago_aguardando_meta', 'em_onboarding', 'em_revisao', 'ativo', 'inativo'));

-- 5. Idempotência via subscription_id único (NULL ok pra múltiplos sem assinatura ainda)
CREATE UNIQUE INDEX IF NOT EXISTS clientes_subscription_id_uniq
  ON auto_ads.clientes (subscription_id)
  WHERE subscription_id IS NOT NULL;

-- 6. Trigger pra manter status_atualizado_em sempre fresco
CREATE OR REPLACE FUNCTION auto_ads.update_status_atualizado_em()
RETURNS trigger AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    NEW.status_atualizado_em = NOW();
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS clientes_status_audit ON auto_ads.clientes;
CREATE TRIGGER clientes_status_audit
  BEFORE UPDATE ON auto_ads.clientes
  FOR EACH ROW
  EXECUTE FUNCTION auto_ads.update_status_atualizado_em();

-- 7. As colunas Meta (ad_account_id, page_id, wa_link) precisam aceitar NULL
-- pra clientes em onboarding (ainda não preencheram). Eram NOT NULL.
ALTER TABLE auto_ads.clientes
  ALTER COLUMN ad_account_id DROP NOT NULL,
  ALTER COLUMN page_id       DROP NOT NULL,
  ALTER COLUMN wa_link       DROP NOT NULL;

COMMIT;
