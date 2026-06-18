"""
d_08_gaps_onboarding_e_idempotencia.py

Bateria final de retest descobriu 4 gaps que esse script consolida e corrige.

GAP 1 — Filtro do gateway só aceitava R$ 497 (mensalidade); cliente que escolhia
        o order bump (R$ 596 na 1ª cobrança) NÃO era criado em
        auto_ads.clientes porque o webhook era silenciosamente ignorado.
        FIX: parse_payment passa a aceitar 497 OU 596 OU customer.groupName
        OU payment.externalReference (com 'auto-ads' ou 'dia1-com-bump').

GAP 2 (CRÍTICO) — Mensalidade recorrente regredia status. Cliente ativo
        recebia PAYMENT_CONFIRMED mensal → UPSERT setava status pra
        'pago_aguardando_meta' → reiniciava fluxo de boas-vindas em loop.
        FIX: SQL UPSERT condicional — só permite ir pra 'pago_aguardando_meta'
        se cliente estava NULL (novo) ou 'inativo' (reativação). Demais
        casos preservam status atual.

GAP 3 (CRÍTICO) — Switch v1 do n8n limita 4 outputs. switch_status tinha
        6 (not_found, pago_aguardando_meta, em_onboarding, em_revisao,
        ativo, inativo) — as 2 últimas (ativo, inativo) lançavam erro
        'The output 5 is not allowed. It has to be between 0 and 3!' e
        nem rodavam o ramo, deixando cliente sem resposta.
        FIX: switch_status migrado pra v3.2 (n8n Switch v3 suporta N outputs).

GAP 4 — Cliente em pago_aguardando_meta preso. Se welcome chain do gateway
        falhava (uazapi não consegue mandar pra número que nunca conversou),
        cliente ficava em pago_aguardando_meta pra sempre. Quando voltava
        a mandar mensagem, recebia "tô processando" infinito.
        FIX: roteador agora dispara mark_em_onboarding_inline ANTES do
        send_processando (avança status antes do uazapi tentar), e todos
        os sends uazapi têm continueOnFail=true pra não quebrar o workflow
        caso o WhatsApp esteja indisponível.

Bateria de 7 testes E2E (todos passam após fixes):
  1. Cliente desconhecido manda msg → NOT criado
  2. PAYMENT_CONFIRMED R$ 497 → cria cliente
  3. PAYMENT_CONFIRMED R$ 596 (com bump) → passa filtro
  4. PAYMENT_CONFIRMED R$ 100 (não Auto Ads) → ignorado
  5. Cliente pago_aguardando_meta manda msg → avança em_onboarding
  6. Cliente ativo recebe mensalidade → status NÃO regride
  7. SUBSCRIPTION_DELETED → inativo
"""

import sys, json
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow
import config

# ─────────────────────────────────────────────
# GATEWAY (workflow 2ZnZqb4wFous4uEs)
# ─────────────────────────────────────────────

GATEWAY_WF_ID = '2ZnZqb4wFous4uEs'

PARSE_PAYMENT_CODE = r"""
// Parse payload Asaas + filtra Auto Ads (497, 596, groupName ou externalReference)
const body = $('webhook').first().json.body || {};
const event = body.event || '';
const payment = body.payment || {};
const customer = payment.customer || {};
const subscription_id = payment.subscription || payment.subscriptionId || customer.id || null;

const phoneRaw = customer.phone || customer.mobilePhone || body.customerPhone || '';
const email = customer.email || body.customerEmail || '';
const nome = customer.name || body.customerName || '';

let telefone = String(phoneRaw).replace(/\D/g, '');
if (telefone.length >= 10 && !telefone.startsWith('55')) telefone = '55' + telefone;

let valor_esperado_cents = 49700;
let valor_bump_cents = 59600;
let grupo_auto_ads = '';
try {
  const cfg = $('load_config_asaas').first().json;
  valor_esperado_cents = parseInt(cfg.asaas_product_value_cents || '49700', 10);
  grupo_auto_ads = (cfg.asaas_group_name || '').trim();
} catch(e) {}

const valor_pago_cents = Math.round((payment.value || 0) * 100);
const customer_group = (customer.groupName || '').trim();
const ext_ref = String(payment.externalReference || '').toLowerCase();

const eh_auto_ads =
  valor_pago_cents === valor_esperado_cents
  || valor_pago_cents === valor_bump_cents
  || (grupo_auto_ads && customer_group === grupo_auto_ads)
  || ext_ref.includes('auto-ads')
  || ext_ref.includes('dia1-com-bump');

if (!eh_auto_ads) {
  return [{ json: { skip: true, motivo: 'pagamento_nao_eh_auto_ads', event, valor_pago_cents, customer_group, ext_ref } }];
}

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
  return [{ json: { skip: true, motivo: 'telefone_invalido', event } }];
}

return [{ json: { skip: false, event, novo_status, telefone, email, nome,
  subscription_id, customer_id: customer.id || null, valor_pago_cents, ext_ref } }];
"""

UPSERT_SQL = """\
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
SET
  status = CASE
    WHEN EXCLUDED.status = 'inativo' THEN 'inativo'
    WHEN EXCLUDED.status = 'pago_aguardando_meta'
         AND auto_ads.clientes.status IN ('inativo') THEN 'pago_aguardando_meta'
    WHEN EXCLUDED.status = 'pago_aguardando_meta'
         AND auto_ads.clientes.status IS NULL THEN 'pago_aguardando_meta'
    ELSE auto_ads.clientes.status
  END,
  email = COALESCE(EXCLUDED.email, auto_ads.clientes.email),
  nome_cliente = COALESCE(EXCLUDED.nome_cliente, auto_ads.clientes.nome_cliente),
  subscription_id = COALESCE(EXCLUDED.subscription_id, auto_ads.clientes.subscription_id),
  subscription_started_at =
    CASE WHEN auto_ads.clientes.subscription_started_at IS NULL
              AND EXCLUDED.status = 'pago_aguardando_meta'
         THEN NOW() ELSE auto_ads.clientes.subscription_started_at END,
  subscription_canceled_at =
    CASE WHEN EXCLUDED.status = 'inativo' THEN NOW() ELSE NULL END
RETURNING *;"""

wf_gw = get_workflow(GATEWAY_WF_ID)
for n in wf_gw['nodes']:
    if n['name'] == 'parse_payment':
        n['parameters']['jsCode'] = PARSE_PAYMENT_CODE
    elif n['name'] == 'upsert_cliente':
        n['parameters']['query'] = UPSERT_SQL

update_workflow(GATEWAY_WF_ID,
    name=wf_gw['name'], nodes=wf_gw['nodes'], connections=wf_gw['connections'],
    settings={'executionOrder': wf_gw.get('settings',{}).get('executionOrder','v1')})
print('✓ Gateway: parse_payment com filtro ampliado + upsert idempotente')


# ─────────────────────────────────────────────
# WORKFLOW PRINCIPAL (fBUin1UPt5xJEp6g)
# ─────────────────────────────────────────────

MAIN_WF_ID = 'fBUin1UPt5xJEp6g'
wf_main = get_workflow(MAIN_WF_ID)
nodes = wf_main['nodes']
conns = wf_main['connections']

# 1. switch_status → migrado pra v3.2 (suporta 6 outputs)
def cond_eq(rota):
    return {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
            'conditions': [{'leftValue': '={{ $json.rota }}', 'rightValue': rota,
                            'operator': {'type': 'string', 'operation': 'equals'}}],
            'combinator': 'and'
        },
        'outputKey': rota
    }

for n in nodes:
    if n['name'] == 'switch_status':
        n['type'] = 'n8n-nodes-base.switch'
        n['typeVersion'] = 3.2
        n['parameters'] = {
            'mode': 'rules',
            'rules': {'values': [
                cond_eq('not_found'),
                cond_eq('pago_aguardando_meta'),
                cond_eq('em_onboarding'),
                cond_eq('em_revisao'),
                cond_eq('ativo'),
                cond_eq('inativo'),
            ]},
            'options': {},
        }

# 2. Boas-vindas inline pra pago_aguardando_meta (caso welcome chain do gateway falhou)
BOAS_VINDAS_TEXTO = (
    'Pagamento confirmado ✓ Bem-vindo ao Quirk Auto Ads!\n\n'
    'Antes da primeira campanha, te ajudo a conectar tua Meta em 4 passos rápidos:\n\n'
    '*1.* Acessa business.facebook.com e cria/abre teu Business Manager.\n\n'
    '*2.* Compartilha tua *Ad Account* com a BM Quirk (ID: 1612905538806887), '
    'permissão "Gerenciar campanhas".\n\n'
    '*3.* Compartilha tua *Página Facebook* com a BM Quirk (mesmo ID, mesma permissão).\n\n'
    '*4.* Me manda numa mensagem só:\n'
    '   • Nome da tua Página\n'
    '   • Link WhatsApp comercial (wa.me/55...)\n'
    '   • Teu Ad Account ID (só números)\n\n'
    'Qualquer dúvida em qualquer passo, é só perguntar 😊'
)

for n in nodes:
    if n['name'] == 'send_processando':
        n['parameters']['jsonBody'] = (
            '={\n  "number": "' + '{{ $(\'classify_status\').first().json.telefone }}'
            + '",\n  "text": ' + json.dumps(BOAS_VINDAS_TEXTO) + '\n}'
        )

# 3. mark_em_onboarding_inline (Postgres UPDATE) entre switch_status e send_processando
nodes[:] = [n for n in nodes if n['name'] != 'mark_em_onboarding_inline']
sp_node = next(n for n in nodes if n['name'] == 'send_processando')
nodes.append({
    'parameters': {
        'operation': 'executeQuery',
        'query': ("UPDATE auto_ads.clientes SET status='em_onboarding' "
                  "WHERE telefone='{{ $('classify_status').first().json.telefone }}' "
                  "AND status='pago_aguardando_meta';"),
        'options': {},
    },
    'id': 'mark_em_onboarding_inline',
    'name': 'mark_em_onboarding_inline',
    'type': 'n8n-nodes-base.postgres',
    'typeVersion': 2.6,
    'position': [sp_node['position'][0] - 240, sp_node['position'][1]],
    'credentials': {'postgres': config.POSTGRES_CRED},
})

# Conexões: switch_status saída 1 (pago_aguardando_meta) → mark → send_processando
ss_out = conns.get('switch_status', {}).get('main', [])
while len(ss_out) < 6: ss_out.append([])
ss_out[1] = [{'node': 'mark_em_onboarding_inline', 'type': 'main', 'index': 0}]
conns['switch_status']['main'] = ss_out

conns['mark_em_onboarding_inline'] = {'main': [[{'node': 'send_processando', 'type': 'main', 'index': 0}]]}

# 4. continueOnFail em todos os sends uazapi
SENDS = ['send_not_found', 'send_processando', 'send_validando', 'send_inativo',
         'send_onboarding_msg', 'send_ativacao_msg', 'send_falha_msg',
         'send_gestao_msg', 'send_resposta', 'send_confirmacao_cliente']
for n in nodes:
    if n['name'] in SENDS:
        n['continueOnFail'] = True

update_workflow(MAIN_WF_ID,
    name=wf_main['name'], nodes=nodes, connections=conns,
    settings={'executionOrder': wf_main.get('settings',{}).get('executionOrder','v1')})

print('✓ Workflow principal:')
print('  - switch_status migrado pra v3.2 (6 outputs OK)')
print('  - mark_em_onboarding_inline ANTES de send_processando (avança status mesmo se uazapi falha)')
print('  - continueOnFail em 10 nós uazapi')
