# Setup Integração Asaas — guia rápido

Pra finalizar a configuração do gateway, preencher 2 chaves em `auto_ads.config`:

```sql
-- 1. API key do Asaas (Settings → Integrações → API)
UPDATE auto_ads.config SET valor = '$AACT...sua_api_key...'
WHERE chave = 'asaas_api_key';

-- 2. Nome EXATO do grupo de clientes criado pra Auto Ads no Asaas
--    (Conta → Clientes → Grupos)
UPDATE auto_ads.config SET valor = 'Quirk Auto Ads'  -- exemplo
WHERE chave = 'asaas_group_name';
```

## Como funciona

1. **Filtro de pagamentos**:
   O webhook do Asaas envia eventos de TODOS os pagamentos da conta. Pra processar
   só os do Auto Ads, o nó `parse_payment` filtra por:
   - `payment.value === 497.00` (R$ 497,00 — definido em `asaas_product_value_cents`)
   - OU `customer.groupName === asaas_group_name`

   Pagamentos fora desses critérios são silenciosamente ignorados (HTTP 200,
   sem criar cliente nem mandar boas-vindas).

2. **Atribuição automática de grupo**:
   Após processar um pagamento válido, o nó `asaas_set_group` faz POST
   `/v3/customers/{customer_id}` na API do Asaas setando `groupName` pro
   valor configurado em `asaas_group_name`. Isso garante que mesmo se o
   Asaas não classificou automaticamente, o customer fica organizado no
   grupo correto.

   Se `asaas_api_key` ou `asaas_group_name` estiver com `TODO_PREENCHER`,
   o nó silenciosamente faz skip — não bloqueia o fluxo.

## Configurar webhook no Asaas

Em `Conta → Integrações → Webhooks → Novo Webhook`:

- **URL**: `https://n8n.quirkgrowth.online/webhook/quirk-auto-ads-payment`
- **Versão da API**: v3
- **Eventos**:
  - `PAYMENT_CONFIRMED` (cobrança paga)
  - `PAYMENT_RECEIVED` (idem, redundante mas seguro)
  - `PAYMENT_REFUNDED` (estornado)
  - `PAYMENT_CHARGEBACK_REQUESTED` (chargeback)
  - `SUBSCRIPTION_DELETED` (assinatura cancelada)
  - `SUBSCRIPTION_INACTIVATED` (assinatura inativada)

## Verificar config

```sql
SELECT chave,
       CASE WHEN length(valor) > 40
            THEN substring(valor, 1, 12) || '...' || substring(valor from length(valor)-3)
            ELSE valor END AS valor_resumido,
       length(valor) AS tamanho
FROM auto_ads.config
WHERE chave LIKE 'asaas_%'
ORDER BY chave;
```

Esperado depois de tudo configurado:

| chave | valor_resumido | tamanho |
|-------|----------------|---------|
| asaas_api_key | `$AACT...xx99` | ~70 |
| asaas_group_id | (vazio, opcional) | 0 |
| asaas_group_name | `Quirk Auto Ads` | 14 |
| asaas_product_value_cents | `49700` | 5 |

## Testar end-to-end depois de configurar

```bash
cd /Users/renanreal/quirk_auto_ads
python3 scripts/d_04_test_e2e_onboarding.py
```

Vai simular:
1. Cliente desconhecido manda mensagem → gate trava (link da LP)
2. Webhook do Asaas dispara → cliente criado + boas-vindas + status=em_onboarding
3. Cliente faz pergunta → agente IA responde
4. Cliente reporta 3 dados Meta → revisão dispara → como ad_account é fake, falha
   com mensagem amigável e volta pra em_onboarding

O happy path da revisão (status=ativo) só é validado em produção com uma Ad
Account real compartilhada com a BM Quirk.
