"""
d_05_asaas_filter_and_group.py

Ajustes no workflow Webhook Gateway pra:

1. Filtrar webhooks: só processa pagamentos do produto Auto Ads
   (valor === asaas_product_value_cents OU customer já tem groupName do Auto Ads)

2. Após upsert do cliente em `pago_aguardando_meta`, fazer PUT na API do
   Asaas pra setar o `groupName` do customer pro grupo Auto Ads configurado
   em auto_ads.config.asaas_group_name. Isso garante que mesmo se o cliente
   pagou via link Auto Ads mas o Asaas não atribuiu o grupo automaticamente,
   nosso webhook força a atribuição.

Pré-requisitos (preencher em auto_ads.config):
  - asaas_api_key            → API key do Asaas (Settings → Integrações → API)
  - asaas_group_name         → nome do grupo criado no Asaas pra Auto Ads
  - asaas_product_value_cents → 49700 (R$ 497,00 — já preenchido)
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow
import config

WF_ID = '2ZnZqb4wFous4uEs'  # Webhook Gateway

# Parse com filtro: só aceita se valor === valor_produto OU customer.groupName matches
PARSE_CODE_WITH_FILTER = r"""
// Parse payload Asaas + filtra pra processar só pagamentos do Auto Ads
const body = $input.first().json.body || {};
const event = body.event || '';
const payment = body.payment || {};
const customer = payment.customer || {};
const subscription_id = payment.subscription || payment.subscriptionId || customer.id || null;

const phoneRaw = customer.phone || customer.mobilePhone || body.customerPhone || '';
const email = customer.email || body.customerEmail || '';
const nome = customer.name || body.customerName || '';

let telefone = String(phoneRaw).replace(/\D/g, '');
if (telefone.length >= 10 && !telefone.startsWith('55')) telefone = '55' + telefone;

// Carrega config Auto Ads (valor produto + nome grupo)
let valor_esperado_cents = 49700;
let grupo_auto_ads = '';
try {
  const cfg = $('load_config_asaas').first().json;
  valor_esperado_cents = parseInt(cfg.asaas_product_value_cents || '49700', 10);
  grupo_auto_ads = (cfg.asaas_group_name || '').trim();
} catch(e) {}

// Filtra: o pagamento é do produto Auto Ads?
const valor_pago_cents = Math.round((payment.value || 0) * 100);
const customer_group = (customer.groupName || '').trim();

const eh_auto_ads =
  valor_pago_cents === valor_esperado_cents
  || (grupo_auto_ads && customer_group === grupo_auto_ads);

if (!eh_auto_ads) {
  return [{
    json: {
      skip: true,
      motivo: 'pagamento_nao_eh_auto_ads',
      event,
      valor_pago_cents,
      valor_esperado_cents,
      customer_group,
      grupo_auto_ads,
    }
  }];
}

// Mapeamento de evento → status
let novo_status = null;
if (['PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED'].includes(event)) {
  novo_status = 'pago_aguardando_meta';
} else if (['PAYMENT_REFUNDED', 'PAYMENT_CHARGEBACK_REQUESTED', 'PAYMENT_DELETED',
            'SUBSCRIPTION_DELETED', 'SUBSCRIPTION_INACTIVATED'].includes(event)) {
  novo_status = 'inativo';
} else {
  return [{ json: { skip: true, event, motivo: 'evento_ignorado' } }];
}

if (!telefone || telefone.length < 10) {
  return [{ json: { skip: true, motivo: 'telefone_invalido', event, body } }];
}

return [{
  json: {
    skip: false,
    event,
    novo_status,
    telefone,
    email,
    nome,
    subscription_id,
    customer_id: customer.id || null,
    raw_event: body,
  }
}];
"""

# Code que faz PUT no customer Asaas pra setar groupName
ASAAS_SET_GROUP_CODE = r"""
// Seta groupName do customer no Asaas (idempotente)
const r = $input.first().json;
const customer_id = $('parse_payment').first().json.customer_id;

if (!customer_id) {
  return [{ json: { skip: true, motivo: 'sem_customer_id' } }];
}

const cfg = $('load_config_asaas').first().json;
const api_key = cfg.asaas_api_key;
const grupo_nome = (cfg.asaas_group_name || '').trim();

if (!api_key || api_key === 'TODO_PREENCHER' || !grupo_nome || grupo_nome === 'TODO_PREENCHER') {
  return [{ json: { skip: true, motivo: 'asaas_config_incompleta', tip: 'Preencha asaas_api_key e asaas_group_name em auto_ads.config' } }];
}

try {
  const resp = await this.helpers.httpRequest({
    method: 'POST',
    url: `https://api.asaas.com/v3/customers/${customer_id}`,
    headers: {
      'access_token': api_key,
      'Content-Type': 'application/json',
    },
    body: { groupName: grupo_nome },
    json: true,
    returnFullResponse: false,
  });
  return [{ json: { ok: true, customer_id, group_name: grupo_nome, asaas_response: resp } }];
} catch (e) {
  const detail = e?.response?.body || e?.message || String(e);
  return [{ json: { ok: false, customer_id, error: detail } }];
}
"""

# Carrega keys de config necessárias
LOAD_CONFIG_QUERY = """\
SELECT
  MAX(CASE WHEN chave = 'asaas_api_key' THEN valor END) AS asaas_api_key,
  MAX(CASE WHEN chave = 'asaas_group_name' THEN valor END) AS asaas_group_name,
  MAX(CASE WHEN chave = 'asaas_product_value_cents' THEN valor END) AS asaas_product_value_cents
FROM auto_ads.config
WHERE chave IN ('asaas_api_key', 'asaas_group_name', 'asaas_product_value_cents');"""

# Aplica mudanças
wf = get_workflow(WF_ID)
nodes = wf['nodes']
conns = wf['connections']

# 1. Adiciona load_config_asaas (Postgres) ANTES de parse_payment
load_cfg_node = {
    'parameters': {
        'operation': 'executeQuery',
        'query': LOAD_CONFIG_QUERY,
        'options': {},
    },
    'id': 'load_config_asaas',
    'name': 'load_config_asaas',
    'type': 'n8n-nodes-base.postgres',
    'typeVersion': 2.6,
    'position': [320, 300],
    'credentials': {'postgres': config.POSTGRES_CRED},
}
nodes[:] = [n for n in nodes if n['name'] != 'load_config_asaas']
nodes.append(load_cfg_node)

# 2. Atualiza parse_payment com filtro
for n in nodes:
    if n['name'] == 'parse_payment':
        n['parameters']['jsCode'] = PARSE_CODE_WITH_FILTER

# 3. Adiciona asaas_set_group (Code) APÓS upsert_cliente
# Se o upsert resultou em status=pago_aguardando_meta, faz o PUT
set_group_node = {
    'parameters': {'jsCode': ASAAS_SET_GROUP_CODE},
    'id': 'asaas_set_group',
    'name': 'asaas_set_group',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 2,
    'position': [1100, 80],
}
nodes[:] = [n for n in nodes if n['name'] != 'asaas_set_group']
nodes.append(set_group_node)

# 4. Reposicionar webhook
for n in nodes:
    if n['name'] == 'webhook':
        n['position'] = [120, 300]
    elif n['name'] == 'parse_payment':
        n['position'] = [560, 300]

# 5. Conexões: webhook → load_config_asaas → parse_payment
conns['webhook'] = {'main': [[{'node': 'load_config_asaas', 'type': 'main', 'index': 0}]]}
conns['load_config_asaas'] = {'main': [[{'node': 'parse_payment', 'type': 'main', 'index': 0}]]}

# asaas_set_group entra entre upsert_cliente e switch_action (no caminho de welcome)
# Atualiza fluxo: upsert_cliente → asaas_set_group → switch_action
conns['upsert_cliente'] = {'main': [[{'node': 'asaas_set_group', 'type': 'main', 'index': 0}]]}
conns['asaas_set_group'] = {'main': [[{'node': 'switch_action', 'type': 'main', 'index': 0}]]}

# Salva
clean = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
update_workflow(WF_ID, name=wf['name'], nodes=nodes, connections=conns, settings=clean)
print('✓ Webhook Gateway atualizado')
print('  Novo fluxo:')
print('    webhook → load_config_asaas → parse_payment → if_proseguir(skip?)')
print('    se ok → upsert_cliente → asaas_set_group → switch_action → (welcome|pausa)')
print()
print('  Pré-requisitos pra ativar 100%:')
print('    UPDATE auto_ads.config SET valor = \'<sua_api_key>\' WHERE chave = \'asaas_api_key\';')
print('    UPDATE auto_ads.config SET valor = \'<nome_do_grupo>\' WHERE chave = \'asaas_group_name\';')
