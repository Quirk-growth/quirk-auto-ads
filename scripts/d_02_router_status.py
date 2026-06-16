"""
d_02_router_status.py

Substitui o `if_cadastrado` (true/false) por um switch de 5 caminhos baseado
em `clientes.status`:

  not_found   → send_nao_cadastrado (link LP)
  pago_aguardando_meta → send_processando (espera webhook)
  em_onboarding → fluxo onboarding (bot IA + revisão)
  em_revisao  → send_validando ("estamos validando, aguenta")
  ativo       → select_conversa (fluxo Auto Ads existente)
  inativo     → send_inativo (reativar)

Adiciona nós novos:
  - classify_status (Code) — determina rota
  - switch_status (Switch)
  - send_processando, send_validando, send_inativo (HTTP uazapi)
  - sub-fluxo onboarding: build_onboarding_body → onboarding_agent (HTTP Anthropic)
    → parse_onboarding_resp → if_solicita_revisao → (sim: dispara revisão;
    não: send_onboarding_msg)
"""

import sys, json, copy
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow
import config

WF_ID = 'fBUin1UPt5xJEp6g'

# ───────────────────────────────────────────────
# Código dos novos nós
# ───────────────────────────────────────────────

CLASSIFY_STATUS_CODE = r"""
// Determina rota baseado no resultado de select_cliente
const linhas = $('select_cliente').all();
const cliente = (linhas.length > 0) ? linhas[0].json : null;

let rota;
if (!cliente || !cliente.telefone) {
  rota = 'not_found';
} else {
  rota = cliente.status || 'inativo';
}

return [{
  json: {
    rota,
    cliente: cliente || {},
    telefone: $('normalize_phone').first().json.telefone_normalizado,
  }
}];
"""

# Mensagens de cada rota não-IA
MSG_NOT_FOUND = (
    'Oi! Você ainda não é assinante do Quirk Auto Ads.\n\n'
    'Pra ativar por R$ 497/mês (sem fidelidade), acessa: '
    'https://autoads.quirkgrowth.com.br\n\n'
    'Qualquer dúvida sobre o produto, é só me chamar de volta.'
)
MSG_PROCESSANDO = (
    '⏳ Tô processando seu pagamento aqui...\n\n'
    'Em instantes te mando as instruções de ativação. Aguenta um minutinho.'
)
MSG_VALIDANDO = (
    '⏳ Tô validando teu acesso Meta agora...\n\n'
    'Te mando o resultado em segundos.'
)
MSG_INATIVO = (
    '⚠️ Tua assinatura tá inativa.\n\n'
    'Pra reativar e voltar a anunciar, acessa: https://autoads.quirkgrowth.com.br/reativar\n\n'
    'Ou me chama se quiser falar sobre.'
)

# Agente Onboarding — prompt + body builder
ONBOARDING_AGENT_BODY = r"""
const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
const nome = (cliente.nome_cliente || '').split(' ')[0] || 'amigo';
const msg = $('webhook').first().json.body?.message?.content
         || $('webhook').first().json.body?.message?.text
         || '';

// Histórico de conversa (estado.historico_onboarding)
let historico = [];
try {
  historico = JSON.parse(cliente.historico_onboarding || '[]');
} catch(e) {}

const system = `Você é o assistente de onboarding do Quirk Auto Ads.

Cliente: ${nome} (${telefone})
Status atual: em_onboarding

Seu papel: conduzir o cliente pelos passos abaixo até ele dizer que terminou.

Os 4 passos do onboarding:
1. Criar/acessar Business Manager Meta (business.facebook.com)
2. Compartilhar Ad Account com a BM Quirk (ID: 1612905538806887, permissão: Gerenciar)
3. Compartilhar Página Facebook com a BM Quirk (mesmo ID, mesma permissão)
4. Reportar: Nome da Página, link WhatsApp comercial (wa.me/55...) e Ad Account ID

Regras:
- Responda em português, tom direto, sem firula.
- Use no máximo 3-4 linhas por resposta. Seja conciso.
- Se cliente pergunta dúvida, responde de forma curta e prática.
- Se cliente pede pra criar/pausar/alterar campanha: responda APENAS "Termina o onboarding primeiro — só consigo subir anúncio depois que tua Meta tá conectada."
- Se cliente confirma que terminou ("PRONTO", "FIZ", "TERMINEI", "ACABEI", etc) E já reportou os 3 dados do passo 4: responda APENAS com a tag <REVISAO_REQUEST/> sem nenhum outro texto.
- NUNCA invente que campanha subiu. NUNCA invente IDs. NUNCA prometa o que não pode entregar.
- Não use emojis demais (máximo 1 por resposta).`;

const messages = [];
for (const h of historico) {
  messages.push({ role: h.role, content: h.content });
}
messages.push({ role: 'user', content: msg });

return [{
  json: {
    model: 'claude-sonnet-4-5',
    max_tokens: 400,
    temperature: 0.4,
    system,
    messages,
  }
}];
"""

PARSE_ONBOARDING_RESP = r"""
const resp = $input.first().json;
const txt = resp?.content?.[0]?.text || '';
const solicita_revisao = /<REVISAO_REQUEST\s*\/?>/i.test(txt);

// Limpa tag se sobrou junto
const limpo = txt.replace(/<REVISAO_REQUEST\s*\/?>/gi, '').trim();

const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
const userMsg = $('webhook').first().json.body?.message?.content
             || $('webhook').first().json.body?.message?.text
             || '';

// Atualiza histórico
let historico = [];
try { historico = JSON.parse(cliente.historico_onboarding || '[]'); } catch(e) {}
historico.push({ role: 'user', content: userMsg });
if (limpo) historico.push({ role: 'assistant', content: limpo });
// Limita a 30 turnos pra não explodir
if (historico.length > 60) historico = historico.slice(-60);

return [{
  json: {
    solicita_revisao,
    text: limpo,
    telefone,
    novo_historico: JSON.stringify(historico),
  }
}];
"""

# Quando solicita_revisao=true: muda status pra em_revisao + chama revisão
TRIGGER_REVISAO_SQL = """\
UPDATE auto_ads.clientes
SET status = 'em_revisao',
    historico_onboarding = '{{ ($json.novo_historico || '[]').replace(/'/g, "''") }}'
WHERE telefone = '{{ $json.telefone }}';"""

# Quando não solicita revisão: persiste histórico
PERSIST_HIST_SQL = """\
UPDATE auto_ads.clientes
SET historico_onboarding = '{{ ($json.novo_historico || '[]').replace(/'/g, "''") }}'
WHERE telefone = '{{ $json.telefone }}';"""

# ───────────────────────────────────────────────
# Aplicar as mudanças no workflow
# ───────────────────────────────────────────────

# Antes, precisamos adicionar coluna historico_onboarding no DB
import psycopg2
db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
conn = psycopg2.connect(db_url)
cur = conn.cursor()
cur.execute("""
  ALTER TABLE auto_ads.clientes
  ADD COLUMN IF NOT EXISTS historico_onboarding text DEFAULT '[]'::text
""")
conn.commit()
conn.close()
print('✓ Coluna historico_onboarding adicionada')


wf = get_workflow(WF_ID)
nodes = wf['nodes']
conns = wf['connections']

# Posições — vou colocar os novos nós numa faixa nova (y=2400, abaixo das faixas existentes)
# Faixa onboarding: y=2400
ROW_Y = 2400
X_START = 1000

def add_node(node_id, name, type_, params, x, y, type_version=2, credentials=None):
    node = {
        'parameters': params,
        'id': node_id,
        'name': name,
        'type': type_,
        'typeVersion': type_version,
        'position': [x, y],
    }
    if credentials:
        node['credentials'] = credentials
    # Substitui se já existe
    nodes[:] = [n for n in nodes if n['name'] != name]
    nodes.append(node)
    return node

# 1. classify_status (Code, após select_cliente)
add_node('classify_status', 'classify_status', 'n8n-nodes-base.code',
         {'jsCode': CLASSIFY_STATUS_CODE}, X_START, ROW_Y, type_version=2)

# 2. switch_status (Switch)
add_node('switch_status', 'switch_status', 'n8n-nodes-base.switch',
         {
             'dataType': 'string',
             'value1': '={{ $json.rota }}',
             'rules': {'rules': [
                 {'value2': 'not_found'},
                 {'value2': 'pago_aguardando_meta'},
                 {'value2': 'em_onboarding'},
                 {'value2': 'em_revisao'},
                 {'value2': 'ativo'},
                 {'value2': 'inativo'},
             ]},
         }, X_START + 240, ROW_Y, type_version=1)

# 3. send_not_found (envia link da LP)
def http_send_uazapi(name, x, y, text_value):
    return add_node(
        name, name, 'n8n-nodes-base.httpRequest',
        {
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
            'jsonBody': ('={\n  "number": "' + '{{ $(\'classify_status\').first().json.telefone }}'
                       + '",\n  "text": ' + json.dumps(text_value) + '\n}'),
            'options': {},
        },
        x, y, type_version=4.2,
        credentials={'httpHeaderAuth': config.UAZAPI_HEADER_CRED}
    )

http_send_uazapi('send_not_found',    X_START + 480, ROW_Y - 240, MSG_NOT_FOUND)
http_send_uazapi('send_processando',  X_START + 480, ROW_Y - 120, MSG_PROCESSANDO)
http_send_uazapi('send_validando',    X_START + 480, ROW_Y + 240, MSG_VALIDANDO)
http_send_uazapi('send_inativo',      X_START + 480, ROW_Y + 360, MSG_INATIVO)

# 4. Onboarding agent: body builder + HTTP Anthropic + parse
add_node('build_onboarding_body', 'build_onboarding_body', 'n8n-nodes-base.code',
         {'jsCode': ONBOARDING_AGENT_BODY}, X_START + 480, ROW_Y, type_version=2)

add_node('onboarding_agent', 'onboarding_agent', 'n8n-nodes-base.httpRequest',
         {
             'method': 'POST',
             'url': 'https://api.anthropic.com/v1/messages',
             'sendHeaders': True,
             'headerParameters': {'parameters': [
                 {'name': 'anthropic-version', 'value': '2023-06-01'},
                 {'name': 'content-type', 'value': 'application/json'},
             ]},
             'authentication': 'predefinedCredentialType',
             'nodeCredentialType': 'httpHeaderAuth',
             'sendBody': True,
             'specifyBody': 'json',
             'jsonBody': '={{ JSON.stringify($json) }}',
             'options': {},
         }, X_START + 720, ROW_Y, type_version=4.2,
         credentials={'httpHeaderAuth': config.ANTHROPIC_HEADER_CRED})

add_node('parse_onboarding_resp', 'parse_onboarding_resp', 'n8n-nodes-base.code',
         {'jsCode': PARSE_ONBOARDING_RESP}, X_START + 960, ROW_Y, type_version=2)

# 5. if_solicita_revisao
add_node('if_solicita_revisao', 'if_solicita_revisao', 'n8n-nodes-base.if',
         {
             'conditions': {
                 'boolean': [{
                     'value1': '={{ $json.solicita_revisao }}',
                     'value2': True,
                 }],
             },
         }, X_START + 1200, ROW_Y, type_version=1)

# 6a. Caso solicita revisão: marca status + chama revisao_meta (a ser criado depois)
add_node('trigger_revisao', 'trigger_revisao', 'n8n-nodes-base.postgres',
         {
             'operation': 'executeQuery',
             'query': TRIGGER_REVISAO_SQL,
             'options': {},
         }, X_START + 1440, ROW_Y - 120, type_version=2.6,
         credentials={'postgres': config.POSTGRES_CRED})

# Stub do revisao_meta — vai ser substituído no próximo passo
add_node('revisao_meta_placeholder', 'revisao_meta_placeholder', 'n8n-nodes-base.code',
         {'jsCode': '// será substituído por d_03_revisao_meta.py\nreturn [{ json: { ok: true, todo: \"revisao\" } }];'},
         X_START + 1680, ROW_Y - 120, type_version=2)

# 6b. Caso não solicita revisão: persiste histórico + manda mensagem
add_node('persist_hist', 'persist_hist', 'n8n-nodes-base.postgres',
         {
             'operation': 'executeQuery',
             'query': PERSIST_HIST_SQL,
             'options': {},
         }, X_START + 1440, ROW_Y + 120, type_version=2.6,
         credentials={'postgres': config.POSTGRES_CRED})

# send_onboarding_msg — manda texto do agente pra uazapi
add_node('send_onboarding_msg', 'send_onboarding_msg', 'n8n-nodes-base.httpRequest',
         {
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
             'jsonBody': '={\n  "number": "{{ $(\'parse_onboarding_resp\').first().json.telefone }}",\n  "text": {{ JSON.stringify($(\'parse_onboarding_resp\').first().json.text) }}\n}',
             'options': {},
         }, X_START + 1680, ROW_Y + 120, type_version=4.2,
         credentials={'httpHeaderAuth': config.UAZAPI_HEADER_CRED})


# ───────────────────────────────────────────────
# Reconfigura conexões
# ───────────────────────────────────────────────

# 1. select_cliente → classify_status (substitui if_cadastrado)
conns['select_cliente'] = {'main': [[{'node': 'classify_status', 'type': 'main', 'index': 0}]]}

# 2. classify_status → switch_status
conns['classify_status'] = {'main': [[{'node': 'switch_status', 'type': 'main', 'index': 0}]]}

# 3. switch_status — 6 saídas
conns['switch_status'] = {'main': [
    [{'node': 'send_not_found', 'type': 'main', 'index': 0}],         # not_found
    [{'node': 'send_processando', 'type': 'main', 'index': 0}],       # pago_aguardando_meta
    [{'node': 'build_onboarding_body', 'type': 'main', 'index': 0}],  # em_onboarding
    [{'node': 'send_validando', 'type': 'main', 'index': 0}],         # em_revisao
    [{'node': 'select_conversa', 'type': 'main', 'index': 0}],        # ativo (fluxo atual)
    [{'node': 'send_inativo', 'type': 'main', 'index': 0}],           # inativo
]}

# 4. Onboarding chain
conns['build_onboarding_body'] = {'main': [[{'node': 'onboarding_agent', 'type': 'main', 'index': 0}]]}
conns['onboarding_agent'] = {'main': [[{'node': 'parse_onboarding_resp', 'type': 'main', 'index': 0}]]}
conns['parse_onboarding_resp'] = {'main': [[{'node': 'if_solicita_revisao', 'type': 'main', 'index': 0}]]}
conns['if_solicita_revisao'] = {'main': [
    [{'node': 'trigger_revisao', 'type': 'main', 'index': 0}],   # true
    [{'node': 'persist_hist', 'type': 'main', 'index': 0}],      # false
]}
conns['trigger_revisao'] = {'main': [[{'node': 'revisao_meta_placeholder', 'type': 'main', 'index': 0}]]}
conns['persist_hist'] = {'main': [[{'node': 'send_onboarding_msg', 'type': 'main', 'index': 0}]]}

# 5. Remover if_cadastrado das conexões (não usado mais)
conns.pop('if_cadastrado', None)

# ───────────────────────────────────────────────
# Salvar
# ───────────────────────────────────────────────

clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
update_workflow(WF_ID, name=wf['name'], nodes=nodes,
                connections=conns, settings=clean_settings)
print(f'✓ Workflow {WF_ID} atualizado')
print(f'  Nós adicionados: classify_status, switch_status, send_not_found,')
print(f'    send_processando, send_validando, send_inativo,')
print(f'    build_onboarding_body, onboarding_agent, parse_onboarding_resp,')
print(f'    if_solicita_revisao, trigger_revisao, persist_hist, send_onboarding_msg,')
print(f'    revisao_meta_placeholder')
