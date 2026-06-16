"""
d_07_bump_combinado_596.py

Atualiza o nó `cria_subscription` no workflow "Quirk Auto Ads — Criar Cobrança"
pra UNIFICAR a cobrança quando order_bump=true (1 invoice R$ 596 em vez de 2).

Fluxo Kiwify-style:

COM bump:
  1. POST /v3/payments value=596 (497+99) dueDate=amanhã
     description='Quirk Auto Ads — 1ª mensalidade + Criador de Anúncios (cobrança única)'
     externalReference='dia1-com-bump'
  2. POST /v3/subscriptions value=497 nextDueDate=+31 dias cycle=MONTHLY
     description='Quirk Auto Ads — assinatura mensal (a partir do 2º mês)'
     → cliente paga R$ 596 hoje, R$ 497 daqui a 30 dias, R$ 497 mensalmente

SEM bump (igual antes):
  - POST /v3/subscriptions value=497 nextDueDate=amanhã cycle=MONTHLY

Resposta retorna invoice_url do pagamento principal do dia 1.

Testado E2E em 2026-06-16.
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'aXuUHCG2YN2IVMN2'

CRIA_SUBSCRIPTION_CODE = r"""
// Cria cobrança principal + subscription mensal R$ 497.
// - Sem bump: subscription R$ 497/mês começando amanhã (primeira cobrança = primeira mensalidade)
// - Com bump: payment one-time R$ 596 (497+99) vencendo amanhã + subscription R$ 497/mês
//   começando em +31 dias (pra não cobrar a primeira mensalidade duas vezes)
const prev = $('cria_ou_pega_customer').first().json;
if (!prev.ok) return [{ json: prev }];

const api_key = prev.api_key;
const customer_id = prev.customer_id;
const lead = prev.lead || {};
const order_bump = !!lead.order_bump;
const cfg = $('load_config_asaas').first().json;
const valor_mensal_cents = parseInt(cfg.asaas_product_value_cents || '49700', 10);
const valor_mensal = valor_mensal_cents / 100;
const VALOR_ORDER_BUMP = 99.00;
const valor_dia1 = valor_mensal + (order_bump ? VALOR_ORDER_BUMP : 0);

async function asaas(method, url, body) {
  return await this.helpers.httpRequest({
    method, url,
    headers: { 'access_token': api_key, 'Content-Type': 'application/json' },
    body, json: true, returnFullResponse: false,
  });
}

function ymd(daysAhead) {
  const d = new Date(Date.now() + daysAhead * 24 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10);
}

// Idempotência
let invoice_url = null;
let subscription = null;
let payment_dia1 = null;
let ja_tinha = false;

try {
  const subs = await asaas.call(this, 'GET',
    `https://api.asaas.com/v3/subscriptions?customer=${customer_id}&status=ACTIVE&limit=5`);
  if (subs.data && subs.data.length > 0) {
    ja_tinha = true;
    subscription = subs.data[0];
    const pays = await asaas.call(this, 'GET',
      `https://api.asaas.com/v3/payments?customer=${customer_id}&status=PENDING&limit=5`);
    if (pays.data && pays.data[0]) invoice_url = pays.data[0].invoiceUrl;
  }
} catch(e) {}

if (!subscription) {
  if (order_bump) {
    try {
      payment_dia1 = await asaas.call(this, 'POST', 'https://api.asaas.com/v3/payments', {
        customer: customer_id,
        billingType: 'UNDEFINED',
        value: valor_dia1,
        dueDate: ymd(1),
        description: 'Quirk Auto Ads — 1ª mensalidade + Criador de Anúncios (cobrança única)',
        externalReference: 'dia1-com-bump',
      });
      invoice_url = payment_dia1.invoiceUrl;
    } catch (e) {
      const detail = e?.response?.body || e?.message || String(e);
      return [{ json: { ok: false, erro: 'asaas_criar_payment_dia1', detalhes: detail } }];
    }

    try {
      subscription = await asaas.call(this, 'POST', 'https://api.asaas.com/v3/subscriptions', {
        customer: customer_id,
        billingType: 'UNDEFINED',
        value: valor_mensal,
        nextDueDate: ymd(31),
        cycle: 'MONTHLY',
        description: 'Quirk Auto Ads — assinatura mensal (a partir do 2º mês)',
        externalReference: 'auto-ads-mensal-pos-bump',
      });
    } catch (e) {
      const detail = e?.response?.body || e?.message || String(e);
      return [{ json: {
        ok: true,
        ja_tinha_subscription: false,
        invoice_url,
        payment_dia1_id: payment_dia1.id,
        valor_dia1,
        order_bump_pedido: true,
        subscription_id: null,
        subscription_erro: detail,
        prev,
      }}];
    }
  } else {
    try {
      subscription = await asaas.call(this, 'POST', 'https://api.asaas.com/v3/subscriptions', {
        customer: customer_id,
        billingType: 'UNDEFINED',
        value: valor_mensal,
        nextDueDate: ymd(1),
        cycle: 'MONTHLY',
        description: 'Quirk Auto Ads — assinatura mensal',
        externalReference: 'auto-ads-mensal',
      });
    } catch (e) {
      const detail = e?.response?.body || e?.message || String(e);
      return [{ json: { ok: false, erro: 'asaas_criar_subscription', detalhes: detail } }];
    }

    for (let i = 0; i < 4; i++) {
      await new Promise(r => setTimeout(r, 800));
      try {
        const pays = await asaas.call(this, 'GET',
          `https://api.asaas.com/v3/payments?subscription=${subscription.id}&limit=1`);
        if (pays.data && pays.data.length > 0 && pays.data[0].invoiceUrl) {
          invoice_url = pays.data[0].invoiceUrl;
          break;
        }
      } catch(e) {}
    }
  }
}

return [{ json: {
  ok: true,
  ja_tinha_subscription: ja_tinha,
  subscription_id: subscription ? subscription.id : null,
  payment_dia1_id: payment_dia1 ? payment_dia1.id : null,
  valor_dia1,
  order_bump_pedido: order_bump,
  invoice_url,
  prev,
}}];
"""

wf = get_workflow(WF_ID)
for n in wf['nodes']:
    if n['name'] == 'cria_subscription':
        n['parameters']['jsCode'] = CRIA_SUBSCRIPTION_CODE
        print('✓ cria_subscription atualizado: COM bump = 1 cobrança R$596 + sub mensal a partir do 2º mês')
        break

clean = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean)
