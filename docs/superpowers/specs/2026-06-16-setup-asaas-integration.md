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

2. **Atribuição automática de grupo** (workaround):
   ⚠️ **Limitação descoberta**: a API do Asaas (v3) **NÃO permite** alterar o
   `groupName` de um customer existente via PUT ou POST. Testado em 2026-06-16
   com 6 variantes diferentes (POST/PUT × {groupName, groupNames, groups,
   endpoint dedicado}) — todas retornam HTTP 200 mas o grupo segue null.

   Solução pra garantir que clientes do Auto Ads entrem no grupo
   "Auto Ads - Imob":

   **Configurar o link de pagamento no Asaas**:
   1. Painel Asaas → Vendas → Links de pagamento
   2. Edita o link `https://www.asaas.com/c/fze4od4rk8ystswh`
   3. Em "Configurações avançadas" / "Grupo de clientes": seleciona
      "Auto Ads - Imob"
   4. Salva
   5. A partir daí, todo cliente que pagar via esse link é automaticamente
      atribuído ao grupo no momento da criação (que é onde a API aceita o
      campo).

   O nó `asaas_set_group` no workflow ficou como **no-op com nota
   explicativa** — não bloqueia nem tenta a chamada inútil. Se um dia o
   Asaas liberar o endpoint, basta reativar (código antigo no git).

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

---

## Redirecionar pra obrigado.html após o pagamento (opcional)

A página `obrigado.html` (com o botão "Ativar no WhatsApp") pode ser exibida
automaticamente após o pagamento via `callback.successUrl` na cobrança.

**Requisito do Asaas:** é preciso cadastrar o domínio na conta primeiro,
senão a criação da cobrança falha com erro 400 ("Não há nenhum domínio
configurado em sua conta").

Passos:
1. Asaas → Minha Conta → aba Informações → cadastrar site
   `https://autoads.quirkgrowth.com.br`
2. Depois, re-habilitar o callback no workflow "Criar Cobrança"
   (nó cria_subscription): adicionar
   `callback: { successUrl: 'https://autoads.quirkgrowth.com.br/obrigado.html', autoRedirect: true }`
   em cada POST de payment/subscription.

Enquanto o domínio não estiver cadastrado, o callback fica DESABILITADO
(cobrança funciona normal). O cliente ainda recebe o email + WhatsApp com
o link de ativação, então o fluxo não depende desse redirect.
