"""
d_06_workflow_criar_cobranca.py

Workflow "Quirk Auto Ads — Criar Cobrança" — recebe lead da LP, cria customer
no Asaas com groupName="Auto Ads - Imob" (forma que funciona — só na criação),
cria subscription R$ 497/mês, retorna invoice_url pra LP redirecionar.

Endpoint: POST /webhook/quirk-auto-ads-criar-cobranca
Body esperado: { nome, email, whatsapp, perfil? }

Resposta: { ok, invoice_url, customer_id, subscription_id, ja_existia? }

Fluxo:
  1. Parse + valida campos
  2. Tenta achar customer por email/cpfCnpj (idempotência básica)
  3. Se não existe: cria customer no Asaas COM groupName="Auto Ads - Imob"
  4. Cria subscription R$ 497 mensal (billingType=UNDEFINED → cliente escolhe)
  5. Pega invoiceUrl da primeira cobrança da subscription
  6. Retorna pro frontend
"""

import sys, json
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import _request
import config

WEBHOOK_PATH = 'quirk-auto-ads-criar-cobranca'

# ───────────────────────────────────────────
# Code dos nós
# ───────────────────────────────────────────

PARSE_LEAD_CODE = r"""
// Parse + valida lead vindo da LP
const body = $('webhook').first().json.body || {};

const nome = String(body.nome || '').trim();
const email = String(body.email || '').trim().toLowerCase();
const whatsappRaw = String(body.whatsapp || body.telefone || '').trim();
const perfil = String(body.perfil || '').trim() || null;

// Normaliza telefone
let telefone = whatsappRaw.replace(/\D/g, '');
if (telefone.length >= 10 && !telefone.startsWith('55')) telefone = '55' + telefone;

// Validação básica
const erros = [];
if (nome.length < 2) erros.push('nome muito curto');
if (!email.includes('@')) erros.push('email inválido');
if (telefone.length < 12) erros.push('telefone inválido');

if (erros.length > 0) {
  return [{ json: { ok: false, erro: 'validacao', detalhes: erros } }];
}

return [{ json: { ok: true, nome, email, telefone, perfil, origem: 'lp-auto-ads' } }];
"""

LOAD_CONFIG = """\
SELECT
  MAX(CASE WHEN chave = 'asaas_api_key' THEN valor END) AS asaas_api_key,
  MAX(CASE WHEN chave = 'asaas_group_name' THEN valor END) AS asaas_group_name,
  MAX(CASE WHEN chave = 'asaas_product_value_cents' THEN valor END) AS asaas_product_value_cents
FROM auto_ads.config
WHERE chave IN ('asaas_api_key', 'asaas_group_name', 'asaas_product_value_cents');"""

CRIA_OU_PEGA_CUSTOMER_CODE = r"""
// Procura customer existente por email; se não acha, cria novo COM groupName
const lead = $('parse_lead').first().json;
const cfg = $('load_config_asaas').first().json;
const api_key = cfg.asaas_api_key;
const grupo = (cfg.asaas_group_name || 'Auto Ads - Imob').trim();

if (!api_key || api_key === 'TODO_PREENCHER') {
  return [{ json: { ok: false, erro: 'asaas_sem_api_key' } }];
}

async function asaas(method, url, body) {
  return await this.helpers.httpRequest({
    method,
    url,
    headers: { 'access_token': api_key, 'Content-Type': 'application/json' },
    body,
    json: true,
    returnFullResponse: false,
  });
}

// 1. Procura por email (idempotência: se o cara já clicou e voltou, reusa)
try {
  const search = await asaas.call(this, 'GET',
    `https://api.asaas.com/v3/customers?email=${encodeURIComponent(lead.email)}&limit=1`);
  if (search.data && search.data.length > 0) {
    return [{
      json: {
        ok: true,
        ja_existia: true,
        customer_id: search.data[0].id,
        customer: search.data[0],
        lead,
        api_key,
        grupo,
      }
    }];
  }
} catch (e) {
  // Continua e tenta criar
}

// 2. Cria novo customer COM groupName (só funciona aqui)
try {
  const novo = await asaas.call(this, 'POST', 'https://api.asaas.com/v3/customers', {
    name: lead.nome,
    email: lead.email,
    mobilePhone: lead.telefone,
    groupName: grupo,
    notificationDisabled: false,
    externalReference: 'lp-auto-ads',
  });
  return [{
    json: {
      ok: true,
      ja_existia: false,
      customer_id: novo.id,
      customer: novo,
      lead,
      api_key,
      grupo,
    }
  }];
} catch (e) {
  const detail = e?.response?.body || e?.message || String(e);
  return [{ json: { ok: false, erro: 'asaas_criar_customer', detalhes: detail } }];
}
"""

CRIA_SUBSCRIPTION_CODE = r"""
// Cria subscription mensal R$ 497 (ou reusa se já existe ativa)
const prev = $('cria_ou_pega_customer').first().json;
if (!prev.ok) return [{ json: prev }];

const api_key = prev.api_key;
const customer_id = prev.customer_id;
const valor_cents = parseInt(($('load_config_asaas').first().json.asaas_product_value_cents) || '49700', 10);
const valor_reais = valor_cents / 100;

async function asaas(method, url, body) {
  return await this.helpers.httpRequest({
    method,
    url,
    headers: { 'access_token': api_key, 'Content-Type': 'application/json' },
    body,
    json: true,
    returnFullResponse: false,
  });
}

// 1. Vê se já tem subscription ATIVA pra esse customer
try {
  const subs = await asaas.call(this, 'GET',
    `https://api.asaas.com/v3/subscriptions?customer=${customer_id}&status=ACTIVE&limit=5`);
  if (subs.data && subs.data.length > 0) {
    // Já tem — pega a primeira cobrança pendente pra mandar o URL
    const sub = subs.data[0];
    const pays = await asaas.call(this, 'GET',
      `https://api.asaas.com/v3/payments?subscription=${sub.id}&status=PENDING&limit=1`);
    const invoiceUrl = (pays.data && pays.data[0]) ? pays.data[0].invoiceUrl : null;
    return [{ json: { ok: true, ja_tinha_subscription: true, subscription_id: sub.id, invoice_url: invoiceUrl, prev } }];
  }
} catch(e) {}

// 2. Cria subscription nova
// nextDueDate: hoje + 1 dia (Asaas exige data futura). Usa string ISO YYYY-MM-DD.
const amanha = new Date(Date.now() + 24 * 60 * 60 * 1000);
const yyyymmdd = amanha.toISOString().slice(0, 10);

let subscription;
try {
  subscription = await asaas.call(this, 'POST', 'https://api.asaas.com/v3/subscriptions', {
    customer: customer_id,
    billingType: 'UNDEFINED',  // cliente escolhe (PIX/cartão/boleto) na invoice
    value: valor_reais,
    nextDueDate: yyyymmdd,
    cycle: 'MONTHLY',
    description: 'Quirk Auto Ads — assinatura mensal',
    externalReference: 'lp-auto-ads',
  });
} catch (e) {
  const detail = e?.response?.body || e?.message || String(e);
  return [{ json: { ok: false, erro: 'asaas_criar_subscription', detalhes: detail } }];
}

// 3. Busca a primeira cobrança gerada pra pegar invoiceUrl
let invoice_url = null;
try {
  // Asaas pode levar alguns ms pra gerar a cobrança — pequeno polling
  for (let i = 0; i < 4; i++) {
    await new Promise(r => setTimeout(r, 800));
    const pays = await asaas.call(this, 'GET',
      `https://api.asaas.com/v3/payments?subscription=${subscription.id}&limit=1`);
    if (pays.data && pays.data.length > 0 && pays.data[0].invoiceUrl) {
      invoice_url = pays.data[0].invoiceUrl;
      break;
    }
  }
} catch(e) {}

return [{
  json: {
    ok: true,
    ja_tinha_subscription: false,
    subscription_id: subscription.id,
    invoice_url,
    prev,
  }
}];
"""

# ───────────────────────────────────────────
# Monta o workflow
# ───────────────────────────────────────────

nodes = [
    {
        'parameters': {
            'httpMethod': 'POST',
            'path': WEBHOOK_PATH,
            'responseMode': 'responseNode',
            'options': {'responseData': 'allEntries'},
        },
        'id': 'webhook',
        'name': 'webhook',
        'type': 'n8n-nodes-base.webhook',
        'typeVersion': 2,
        'position': [200, 300],
        'webhookId': WEBHOOK_PATH,
    },
    {
        'parameters': {
            'operation': 'executeQuery',
            'query': LOAD_CONFIG,
            'options': {},
        },
        'id': 'load_config_asaas',
        'name': 'load_config_asaas',
        'type': 'n8n-nodes-base.postgres',
        'typeVersion': 2.6,
        'position': [400, 300],
        'credentials': {'postgres': config.POSTGRES_CRED},
    },
    {
        'parameters': {'jsCode': PARSE_LEAD_CODE},
        'id': 'parse_lead',
        'name': 'parse_lead',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [620, 300],
    },
    {
        'parameters': {
            'conditions': {'boolean': [{'value1': '={{ $json.ok }}', 'value2': True}]},
        },
        'id': 'if_valido',
        'name': 'if_valido',
        'type': 'n8n-nodes-base.if',
        'typeVersion': 1,
        'position': [840, 300],
    },
    {
        'parameters': {'jsCode': CRIA_OU_PEGA_CUSTOMER_CODE},
        'id': 'cria_ou_pega_customer',
        'name': 'cria_ou_pega_customer',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [1060, 220],
    },
    {
        'parameters': {'jsCode': CRIA_SUBSCRIPTION_CODE},
        'id': 'cria_subscription',
        'name': 'cria_subscription',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [1280, 220],
    },
    {
        'parameters': {
            'respondWith': 'json',
            'responseBody': '={{ JSON.stringify($json) }}',
            'options': {
                'responseCode': 200,
                'responseHeaders': {
                    'entries': [
                        {'name': 'Access-Control-Allow-Origin', 'value': '*'},
                        {'name': 'Access-Control-Allow-Methods', 'value': 'POST, OPTIONS'},
                        {'name': 'Access-Control-Allow-Headers', 'value': 'Content-Type'},
                    ]
                },
            },
        },
        'id': 'respond',
        'name': 'respond',
        'type': 'n8n-nodes-base.respondToWebhook',
        'typeVersion': 1,
        'position': [1500, 300],
    },
    {
        'parameters': {
            'respondWith': 'json',
            'responseBody': '={{ JSON.stringify($json) }}',
            'options': {
                'responseCode': 400,
                'responseHeaders': {
                    'entries': [
                        {'name': 'Access-Control-Allow-Origin', 'value': '*'},
                    ]
                },
            },
        },
        'id': 'respond_erro',
        'name': 'respond_erro',
        'type': 'n8n-nodes-base.respondToWebhook',
        'typeVersion': 1,
        'position': [1060, 400],
    },
]

connections = {
    'webhook': {'main': [[{'node': 'load_config_asaas', 'type': 'main', 'index': 0}]]},
    'load_config_asaas': {'main': [[{'node': 'parse_lead', 'type': 'main', 'index': 0}]]},
    'parse_lead': {'main': [[{'node': 'if_valido', 'type': 'main', 'index': 0}]]},
    'if_valido': {'main': [
        [{'node': 'cria_ou_pega_customer', 'type': 'main', 'index': 0}],  # ok=true
        [{'node': 'respond_erro', 'type': 'main', 'index': 0}],            # ok=false
    ]},
    'cria_ou_pega_customer': {'main': [[{'node': 'cria_subscription', 'type': 'main', 'index': 0}]]},
    'cria_subscription': {'main': [[{'node': 'respond', 'type': 'main', 'index': 0}]]},
}

# Cria workflow
payload = {
    'name': 'Quirk Auto Ads — Criar Cobrança',
    'nodes': nodes,
    'connections': connections,
    'settings': {'executionOrder': 'v1'},
}

import os
ID_FILE = '/Users/renanreal/quirk_auto_ads/n8n_workflow/.criar_cobranca_id'
if os.path.exists(ID_FILE):
    wf_id = open(ID_FILE).read().strip()
    _request('PUT', f'/workflows/{wf_id}', payload)
    print(f'✓ Workflow atualizado: {wf_id}')
else:
    r = _request('POST', '/workflows', payload)
    wf_id = r.get('id')
    with open(ID_FILE, 'w') as f:
        f.write(wf_id)
    _request('POST', f'/workflows/{wf_id}/activate')
    print(f'✓ Workflow criado e ativado: {wf_id}')

print(f'  URL: https://n8n.quirkgrowth.online/webhook/{WEBHOOK_PATH}')
