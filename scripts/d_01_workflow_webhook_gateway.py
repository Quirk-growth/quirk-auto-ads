"""
d_01_workflow_webhook_gateway.py

Cria workflow n8n "Quirk Auto Ads — Webhook Gateway" que recebe webhooks do
Asaas (e gateways compatíveis) e gerencia o ciclo de vida da assinatura:

  - PAYMENT_CONFIRMED → cliente.status = 'pago_aguardando_meta' + boas-vindas
  - PAYMENT_REFUNDED / SUBSCRIPTION_DELETED → status = 'inativo' + pausa campanhas

Payload Asaas (PAYMENT_CONFIRMED):
{
  "event": "PAYMENT_CONFIRMED",
  "payment": {
    "id": "pay_abc",
    "subscription": "sub_xyz",
    "customer": "cus_123",
    "value": 497.00,
    ...
  }
}

Pra simplificar a v1: vamos depender do Customer ter sido criado no Asaas com
telefone + email + nome. O webhook olha o customer e cria/atualiza em
auto_ads.clientes.

Workflow path: /webhook/quirk-auto-ads-payment
"""
import sys, json
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import _request
import config

# Postgres credential — reusa a do workflow principal
PG_CRED = config.POSTGRES_CRED  # {'id': '...', 'name': '...'}

WEBHOOK_PATH = 'quirk-auto-ads-payment'

# JS code: parseia payload + extrai dados normalizados
PARSE_CODE = r"""
// Parse payload Asaas (PAYMENT_CONFIRMED, PAYMENT_REFUNDED, SUBSCRIPTION_DELETED)
const body = $input.first().json.body || {};
const event = body.event || '';
const payment = body.payment || {};
const customer = payment.customer || {};
const subscription_id = payment.subscription || payment.subscriptionId || customer.id || null;

// Asaas pode mandar customer como objeto OU só o id. Vamos tentar pegar dados básicos.
// Se vier só ID, esperamos que outro fluxo já tenha cadastrado o customer separadamente.
// Pra MVP: assumir que customer vem com phone + email + name (configurado no checkout do Asaas)
const phoneRaw = customer.phone || customer.mobilePhone || body.customerPhone || '';
const email = customer.email || body.customerEmail || '';
const nome = customer.name || body.customerName || '';

// Normaliza telefone (remover não-dígitos, garantir 55 prefix)
let telefone = String(phoneRaw).replace(/\D/g, '');
if (telefone.length >= 10 && !telefone.startsWith('55')) telefone = '55' + telefone;

// Determina o novo status baseado no evento
let novo_status = null;
if (['PAYMENT_CONFIRMED', 'PAYMENT_RECEIVED'].includes(event)) {
  novo_status = 'pago_aguardando_meta';
} else if (['PAYMENT_REFUNDED', 'PAYMENT_CHARGEBACK_REQUESTED', 'PAYMENT_DELETED',
            'SUBSCRIPTION_DELETED', 'SUBSCRIPTION_INACTIVATED'].includes(event)) {
  novo_status = 'inativo';
} else {
  // evento que não muda status (ex: PAYMENT_OVERDUE, PAYMENT_AWAITING_RISK_ANALYSIS)
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
    raw_event: body,
  }
}];
"""

# UPSERT SQL — usa subscription_id como chave de idempotência se disponível
UPSERT_QUERY = """\
INSERT INTO auto_ads.clientes
  (telefone, nome_cliente, email, gateway, subscription_id, status, subscription_started_at)
VALUES
  ('{{ $json.telefone }}',
   NULLIF('{{ ($json.nome || '').replace(/'/g, "''") }}', ''),
   NULLIF('{{ ($json.email || '').replace(/'/g, "''") }}', ''),
   'asaas',
   NULLIF('{{ $json.subscription_id || '' }}', ''),
   '{{ $json.novo_status }}',
   CASE WHEN '{{ $json.novo_status }}' = 'pago_aguardando_meta' THEN NOW() ELSE NULL END)
ON CONFLICT (telefone) DO UPDATE
SET status = EXCLUDED.status,
    email = COALESCE(EXCLUDED.email, auto_ads.clientes.email),
    nome_cliente = COALESCE(EXCLUDED.nome_cliente, auto_ads.clientes.nome_cliente),
    subscription_id = COALESCE(EXCLUDED.subscription_id, auto_ads.clientes.subscription_id),
    subscription_started_at =
      CASE WHEN EXCLUDED.status = 'pago_aguardando_meta'
                 AND auto_ads.clientes.subscription_started_at IS NULL
           THEN NOW()
           ELSE auto_ads.clientes.subscription_started_at END,
    subscription_canceled_at =
      CASE WHEN EXCLUDED.status = 'inativo' THEN NOW() ELSE NULL END
RETURNING *;"""

# Switch: se acabou de virar pago_aguardando_meta → dispara welcome
# Se virou inativo → pausa campanhas (sub-fluxo separado, TODO)
SWITCH_CODE = r"""
const r = $input.first().json;
if (r.skip) return [{ json: { action: 'skip', motivo: r.motivo } }];

const status = r.status; // depois do upsert
if (status === 'pago_aguardando_meta') {
  return [{ json: { action: 'welcome', cliente: r } }];
} else if (status === 'inativo') {
  return [{ json: { action: 'pausar_campanhas', cliente: r } }];
}
return [{ json: { action: 'noop', cliente: r } }];
"""

# Welcome messages (5 mensagens em sequência via uazapi)
WELCOME_MESSAGES_CODE = r"""
const cliente = $('webhook').first().json.body || {};
const nome = ($('parse_payment').first().json.nome || '').split(' ')[0] || 'aí';
const telefone = $('parse_payment').first().json.telefone;
const BM_QUIRK_ID = '1612905538806887';

const msgs = [
  `Oi, ${nome}! 👋 Sou o assistente do Quirk Auto Ads.\n\nPagamento confirmado ✓\n\nAntes de você subir o primeiro anúncio, preciso te ajudar a conectar tua conta Meta. Leva uns 10 min.`,
  `*Passo 1 de 4 — Business Manager*\n\nVocê precisa ter um Business Manager Meta.\n\nAcessa: business.facebook.com/overview\n\nSe já tem, ótimo, segue pro próximo. Se não tem, cria um (gratuito, em 1 min) no nome da tua empresa ou nome próprio mesmo. Avisa quando estiver na tela do BM.`,
  `*Passo 2 de 4 — Compartilhar Ad Account*\n\nDentro do teu BM, vai em Configurações → Contas → Contas de anúncios.\n\nSe você ainda não tem uma conta de anúncios, cria uma agora.\n\nDepois compartilha com a BM Quirk:\nID: ${BM_QUIRK_ID}\nPermissão: Gerenciar campanhas\n\nManda PRÓXIMO quando fizer.`,
  `*Passo 3 de 4 — Compartilhar Página*\n\nMesma BM, vai em Configurações → Contas → Páginas.\n\nCompartilha a Página do teu negócio com a BM Quirk (mesmo ID acima, mesma permissão).\n\nManda PRÓXIMO quando fizer.`,
  `*Passo 4 de 4 — Me passa 3 dados*\n\nÚltimo passo. Manda numa mensagem só:\n\n1. *Nome da tua Página Facebook* (exato como aparece)\n2. *Link WhatsApp comercial* (o número que vai aparecer no botão do anúncio, formato wa.me/55...)\n3. *Teu Ad Account ID* (só números, encontra no canto superior do Gerenciador de Anúncios)\n\nQuando enviar os 3, eu valido tudo automaticamente e te libero pra criar campanhas. 🚀`,
];

// Retorna um array de items, um por mensagem (vão pro nó seguinte que envia)
return msgs.map((text, i) => ({
  json: {
    telefone,
    text,
    index: i,
    total: msgs.length,
    delay_ms: i === 0 ? 0 : 1500,  // delay entre mensagens (rápido, não 30s pra demo)
  }
}));
"""

# Após enviar todas → marca em_onboarding
MARK_ONBOARDING_SQL = """\
UPDATE auto_ads.clientes
SET status = 'em_onboarding'
WHERE telefone = '{{ $('parse_payment').first().json.telefone }}'
  AND status = 'pago_aguardando_meta';"""

# Pausa campanhas quando vira inativo
PAUSE_CAMPAIGNS_CODE = r"""
// Lista campanhas ACTIVE do cliente e pausa via Meta API
const cliente = $('parse_payment').first().json;
return [{ json: { telefone: cliente.telefone, todo: 'pausar_campanhas_via_meta_api' } }];
// TODO: implementar pause real. Por ora, só marca a intenção.
"""

# Monta o workflow
nodes = [
    {
        'parameters': {
            'httpMethod': 'POST',
            'path': WEBHOOK_PATH,
            'responseMode': 'lastNode',
            'options': {},
        },
        'id': 'webhook',
        'name': 'webhook',
        'type': 'n8n-nodes-base.webhook',
        'typeVersion': 2,
        'position': [200, 300],
        'webhookId': WEBHOOK_PATH,
    },
    {
        'parameters': {'jsCode': PARSE_CODE},
        'id': 'parse_payment',
        'name': 'parse_payment',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [440, 300],
    },
    {
        'parameters': {
            'conditions': {
                'string': [{
                    'value1': '={{ $json.skip }}',
                    'operation': 'notEqual',
                    'value2': 'true',
                }],
            },
        },
        'id': 'if_proseguir',
        'name': 'if_proseguir',
        'type': 'n8n-nodes-base.if',
        'typeVersion': 1,
        'position': [680, 300],
    },
    {
        'parameters': {
            'operation': 'executeQuery',
            'query': UPSERT_QUERY,
            'options': {},
        },
        'id': 'upsert_cliente',
        'name': 'upsert_cliente',
        'type': 'n8n-nodes-base.postgres',
        'typeVersion': 2.6,
        'position': [920, 240],
        'credentials': {'postgres': PG_CRED},
    },
    {
        'parameters': {'jsCode': SWITCH_CODE},
        'id': 'switch_action',
        'name': 'switch_action',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [1160, 240],
    },
    {
        'parameters': {
            'dataType': 'string',
            'value1': '={{ $json.action }}',
            'rules': {
                'rules': [
                    {'value2': 'welcome'},
                    {'value2': 'pausar_campanhas'},
                ],
            },
        },
        'id': 'switch_router',
        'name': 'switch_router',
        'type': 'n8n-nodes-base.switch',
        'typeVersion': 1,
        'position': [1400, 240],
    },
    {
        'parameters': {'jsCode': WELCOME_MESSAGES_CODE},
        'id': 'build_welcome_msgs',
        'name': 'build_welcome_msgs',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [1640, 140],
    },
    {
        'parameters': {
            'method': 'POST',
            'url': 'https://quirkgrowth.uazapi.com/send/text',
            'sendHeaders': True,
            'headerParameters': {'parameters': [
                {'name': 'Content-Type', 'value': 'application/json'},
            ]},
            'authentication': 'predefinedCredentialType',
            'nodeCredentialType': 'httpHeaderAuth',
            'sendBody': True,
            'specifyBody': 'json',
            'jsonBody': '={\n  "number": "{{ $json.telefone }}",\n  "text": {{ JSON.stringify($json.text) }},\n  "delay": {{ $json.delay_ms }}\n}',
            'options': {'batching': {'batch': {'batchSize': 1, 'batchInterval': 1500}}},
        },
        'id': 'send_welcome',
        'name': 'send_welcome',
        'type': 'n8n-nodes-base.httpRequest',
        'typeVersion': 4.2,
        'position': [1880, 140],
        'credentials': {'httpHeaderAuth': config.UAZAPI_HEADER_CRED},
    },
    {
        'parameters': {
            'operation': 'executeQuery',
            'query': MARK_ONBOARDING_SQL,
            'options': {},
        },
        'id': 'mark_onboarding',
        'name': 'mark_onboarding',
        'type': 'n8n-nodes-base.postgres',
        'typeVersion': 2.6,
        'position': [2120, 140],
        'credentials': {'postgres': PG_CRED},
    },
    {
        'parameters': {'jsCode': PAUSE_CAMPAIGNS_CODE},
        'id': 'pause_campaigns',
        'name': 'pause_campaigns',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [1640, 340],
    },
    {
        'parameters': {
            'respondWith': 'json',
            'responseBody': '={ "ok": true, "received": "{{ $json.event || $json.action || \'noop\' }}" }',
            'options': {},
        },
        'id': 'respond_ok',
        'name': 'respond_ok',
        'type': 'n8n-nodes-base.respondToWebhook',
        'typeVersion': 1,
        'position': [2360, 240],
    },
]

connections = {
    'webhook': {'main': [[{'node': 'parse_payment', 'type': 'main', 'index': 0}]]},
    'parse_payment': {'main': [[{'node': 'if_proseguir', 'type': 'main', 'index': 0}]]},
    'if_proseguir': {'main': [
        [{'node': 'upsert_cliente', 'type': 'main', 'index': 0}],  # true
        [{'node': 'respond_ok', 'type': 'main', 'index': 0}],       # false (skip)
    ]},
    'upsert_cliente': {'main': [[{'node': 'switch_action', 'type': 'main', 'index': 0}]]},
    'switch_action': {'main': [[{'node': 'switch_router', 'type': 'main', 'index': 0}]]},
    'switch_router': {'main': [
        [{'node': 'build_welcome_msgs', 'type': 'main', 'index': 0}],  # welcome
        [{'node': 'pause_campaigns', 'type': 'main', 'index': 0}],     # pausar_campanhas
    ]},
    'build_welcome_msgs': {'main': [[{'node': 'send_welcome', 'type': 'main', 'index': 0}]]},
    'send_welcome': {'main': [[{'node': 'mark_onboarding', 'type': 'main', 'index': 0}]]},
    'mark_onboarding': {'main': [[{'node': 'respond_ok', 'type': 'main', 'index': 0}]]},
    'pause_campaigns': {'main': [[{'node': 'respond_ok', 'type': 'main', 'index': 0}]]},
}

# Cria workflow
payload = {
    'name': 'Quirk Auto Ads — Webhook Gateway',
    'nodes': nodes,
    'connections': connections,
    'settings': {'executionOrder': 'v1'},
}

result = _request('POST', '/workflows', payload)
wf_id = result.get('id')
print(f'✓ Workflow criado: {wf_id}')
print(f'  Webhook URL: https://n8n.quirkgrowth.online/webhook/{WEBHOOK_PATH}')
print(f'  Test URL:    https://n8n.quirkgrowth.online/webhook-test/{WEBHOOK_PATH}')

# Ativa o workflow
_request('POST', f'/workflows/{wf_id}/activate')
print('✓ Workflow ativado')

# Salva ID pra referência
with open('/Users/renanreal/quirk_auto_ads/n8n_workflow/.webhook_gateway_id', 'w') as f:
    f.write(wf_id)
