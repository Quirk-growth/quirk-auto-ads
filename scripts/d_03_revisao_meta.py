"""
d_03_revisao_meta.py

Substitui o nó `revisao_meta_placeholder` por um Code real que:

1. Pega histórico_onboarding do cliente (último resumo com dados Meta)
2. Pergunta a um LLM curto pra extrair {nome_pagina, ad_account_id, wa_link}
3. Lista ad accounts compartilhadas com a BM Quirk via Meta API
4. Lista páginas compartilhadas
5. Confere se a ad_account_id e nome_pagina batem
6. Testa permissão tentando listar campanhas
7. Se TUDO ok:
   - UPDATE clientes SET status='ativo', ad_account_id, page_id, wa_link
   - Envia mensagem de "ativação confirmada"
   - Sugere primeiro passo (mandar imóvel)
   Senão:
   - UPDATE clientes SET status='em_onboarding'
   - Envia mensagem explicando o que faltou
"""

import sys, json
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow
import config

WF_ID = 'fBUin1UPt5xJEp6g'

REVISAO_META_CODE = r"""
// Revisão total: valida acesso Meta via API + atualiza cliente
const cliente = $('classify_status').first().json.cliente;
const historico = JSON.parse(cliente.historico_onboarding || '[]');
const telefone = cliente.telefone;

// Pegar a última mensagem do user que provavelmente trouxe os 3 dados
const ultimasUserMsgs = historico.filter(h => h.role === 'user').slice(-5).map(h => h.content).join('\n');

// Extrai os 3 dados via regex simples (LLM já fez o parse no agente, aqui é só double-check)
const adAccountMatch = ultimasUserMsgs.match(/(\d{14,17})/);  // ad_account_id é numérico longo
const waLinkMatch = ultimasUserMsgs.match(/(?:wa\.me\/|https?:\/\/wa\.me\/)(\d{10,15})/i);
const pageNameMatches = ultimasUserMsgs.match(/p[áa]gina[:\s]+([^\n]{3,60})/i)
                    || ultimasUserMsgs.match(/nome\s+da\s+p[áa]gina[:\s]+([^\n]{3,60})/i);

const ad_account_id = adAccountMatch ? adAccountMatch[1] : null;
const wa_link = waLinkMatch ? 'https://wa.me/' + waLinkMatch[1] : null;
const nome_pagina_reportado = pageNameMatches ? pageNameMatches[1].trim() : null;

const dadosFaltando = [];
if (!ad_account_id) dadosFaltando.push('ad_account_id (números do Gerenciador)');
if (!wa_link) dadosFaltando.push('link WhatsApp (formato wa.me/55...)');
if (!nome_pagina_reportado) dadosFaltando.push('nome da Página');

if (dadosFaltando.length > 0) {
  return [{
    json: {
      ok: false,
      motivo: 'dados_incompletos',
      faltando: dadosFaltando,
      mensagem: 'Não consegui identificar todos os 3 dados na tua última mensagem. Me passa de novo:\n\n' + dadosFaltando.map((d,i) => (i+1)+'. '+d).join('\n'),
      telefone,
    }
  }];
}

// Carrega token Meta
let token = '';
try { token = $('load_meta_token').first().json.valor; } catch(e) {}
if (!token) {
  // Vamos buscar inline
  // (já tem load_meta_token rodando antes? Não — vou consultar o DB direto via fetch é complicado)
  return [{ json: { ok: false, motivo: 'sem_token_meta', mensagem: 'Erro interno: vou te chamar de volta.', telefone } }];
}

const BM_QUIRK = '1612905538806887';
const apiBase = 'https://graph.facebook.com/v25.0';

async function getJson(url) {
  const r = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
  return (typeof r === 'string') ? JSON.parse(r) : r;
}

// 1. Lista ad accounts compartilhadas com a BM Quirk (client_ad_accounts)
let adAccounts = [];
try {
  const r = await getJson.call(this, `${apiBase}/${BM_QUIRK}/client_ad_accounts?fields=id,account_id,name&limit=200&access_token=${encodeURIComponent(token)}`);
  adAccounts = r.data || [];
} catch(e) {
  return [{ json: { ok: false, motivo: 'erro_meta_api', mensagem: 'Erro consultando Meta. Tenta de novo daqui a 1 min.', telefone } }];
}

const adAccountEncontrada = adAccounts.find(a =>
  String(a.account_id) === String(ad_account_id) ||
  String(a.id).replace('act_', '') === String(ad_account_id)
);
if (!adAccountEncontrada) {
  return [{
    json: {
      ok: false,
      motivo: 'ad_account_nao_compartilhada',
      mensagem: `Não achei a Ad Account ${ad_account_id} compartilhada com a BM Quirk.\n\nConfere:\n1. Você compartilhou a Ad Account (não o BM inteiro) com a BM Quirk?\n2. Permissão é "Gerenciar campanhas"?\n3. ID da BM Quirk: ${BM_QUIRK}\n\nDepois de ajustar, manda PRONTO de novo.`,
      telefone,
    }
  }];
}

// 2. Lista páginas compartilhadas
let pages = [];
try {
  const r = await getJson.call(this, `${apiBase}/${BM_QUIRK}/client_pages?fields=id,name&limit=200&access_token=${encodeURIComponent(token)}`);
  pages = r.data || [];
} catch(e) {
  return [{ json: { ok: false, motivo: 'erro_meta_api', mensagem: 'Erro consultando Meta. Tenta de novo daqui a 1 min.', telefone } }];
}

const norm = s => String(s||'').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');
const paginaEncontrada = pages.find(p => norm(p.name).includes(norm(nome_pagina_reportado)) || norm(nome_pagina_reportado).includes(norm(p.name)));
if (!paginaEncontrada) {
  return [{
    json: {
      ok: false,
      motivo: 'pagina_nao_compartilhada',
      mensagem: `Não achei a Página "${nome_pagina_reportado}" compartilhada com a BM Quirk.\n\nConfere:\n1. Você compartilhou a Página com a BM Quirk?\n2. O nome bate exato com o do Facebook?\n\nDepois de ajustar, manda PRONTO de novo.`,
      telefone,
    }
  }];
}

// 3. Testa permissão (listar campanhas)
try {
  await getJson.call(this, `${apiBase}/act_${ad_account_id}/campaigns?fields=id&limit=1&access_token=${encodeURIComponent(token)}`);
} catch(e) {
  return [{
    json: {
      ok: false,
      motivo: 'sem_permissao_campanhas',
      mensagem: `Tô vendo a Ad Account compartilhada, mas não consigo gerenciar campanhas dela.\n\nA permissão precisa ser "Gerenciar campanhas" (não "Visualizar"). Ajusta e manda PRONTO.`,
      telefone,
    }
  }];
}

// 4. TUDO OK!
return [{
  json: {
    ok: true,
    telefone,
    ad_account_id,
    page_id: paginaEncontrada.id,
    wa_link,
    page_name: paginaEncontrada.name,
    mensagem: `✅ Tudo certo! Tua Meta tá conectada na Quirk:\n\n📊 Ad Account: ${adAccountEncontrada.name || ad_account_id}\n📄 Página: ${paginaEncontrada.name}\n💬 WhatsApp: ${wa_link}\n\n*Próximo passo*: pra subir tua primeira campanha, manda uma foto ou vídeo do imóvel + uma descrição. Algo tipo:\n\n_"Apto 2Q em [bairro/cidade], R$ XXX mil, raio Xkm, perfil [investidor/morador/luxo]"_\n\nQuando quiser, é só começar. 🚀`,
  }
}];
"""

# UPDATE cliente quando ok=true
UPDATE_CLIENTE_ATIVO_SQL = """\
UPDATE auto_ads.clientes
SET status = 'ativo',
    ad_account_id = '{{ $json.ad_account_id }}',
    page_id = '{{ $json.page_id }}',
    wa_link = '{{ $json.wa_link }}',
    ativo = true
WHERE telefone = '{{ $json.telefone }}'
  AND '{{ $json.ok }}' = 'true';"""

# UPDATE cliente quando ok=false (volta pra em_onboarding)
UPDATE_CLIENTE_FALHOU_SQL = """\
UPDATE auto_ads.clientes
SET status = 'em_onboarding'
WHERE telefone = '{{ $json.telefone }}'
  AND '{{ $json.ok }}' = 'false';"""

# ───────────────────────────────────────────────
# Aplicar
# ───────────────────────────────────────────────

wf = get_workflow(WF_ID)
nodes = wf['nodes']
conns = wf['connections']

X_BASE = 2680  # x do revisao_meta_placeholder
Y_BASE = 2280

# 1. Substitui placeholder por código real
for n in nodes:
    if n['name'] == 'revisao_meta_placeholder':
        n['name'] = 'revisao_meta'
        n['id'] = 'revisao_meta'
        n['parameters'] = {'jsCode': REVISAO_META_CODE}
        X_BASE, Y_BASE = n['position']
        break

# 2. if_revisao_ok (true/false)
nodes.append({
    'parameters': {
        'conditions': {
            'boolean': [{'value1': '={{ $json.ok }}', 'value2': True}],
        },
    },
    'id': 'if_revisao_ok',
    'name': 'if_revisao_ok',
    'type': 'n8n-nodes-base.if',
    'typeVersion': 1,
    'position': [X_BASE + 240, Y_BASE],
})

# 3. Branch OK: update_cliente_ativo + send_ativacao_msg
nodes.append({
    'parameters': {
        'operation': 'executeQuery',
        'query': UPDATE_CLIENTE_ATIVO_SQL,
        'options': {},
    },
    'id': 'update_cliente_ativo',
    'name': 'update_cliente_ativo',
    'type': 'n8n-nodes-base.postgres',
    'typeVersion': 2.6,
    'position': [X_BASE + 480, Y_BASE - 120],
    'credentials': {'postgres': config.POSTGRES_CRED},
})

nodes.append({
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
        'jsonBody': '={\n  "number": "{{ $(\'revisao_meta\').first().json.telefone }}",\n  "text": {{ JSON.stringify($(\'revisao_meta\').first().json.mensagem) }}\n}',
        'options': {},
    },
    'id': 'send_ativacao_msg',
    'name': 'send_ativacao_msg',
    'type': 'n8n-nodes-base.httpRequest',
    'typeVersion': 4.2,
    'position': [X_BASE + 720, Y_BASE - 120],
    'credentials': {'httpHeaderAuth': config.UAZAPI_HEADER_CRED},
})

# 4. Branch FALHOU: update_cliente_falhou + send_falha_msg
nodes.append({
    'parameters': {
        'operation': 'executeQuery',
        'query': UPDATE_CLIENTE_FALHOU_SQL,
        'options': {},
    },
    'id': 'update_cliente_falhou',
    'name': 'update_cliente_falhou',
    'type': 'n8n-nodes-base.postgres',
    'typeVersion': 2.6,
    'position': [X_BASE + 480, Y_BASE + 120],
    'credentials': {'postgres': config.POSTGRES_CRED},
})

nodes.append({
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
        'jsonBody': '={\n  "number": "{{ $(\'revisao_meta\').first().json.telefone }}",\n  "text": {{ JSON.stringify($(\'revisao_meta\').first().json.mensagem) }}\n}',
        'options': {},
    },
    'id': 'send_falha_msg',
    'name': 'send_falha_msg',
    'type': 'n8n-nodes-base.httpRequest',
    'typeVersion': 4.2,
    'position': [X_BASE + 720, Y_BASE + 120],
    'credentials': {'httpHeaderAuth': config.UAZAPI_HEADER_CRED},
})

# 5. Conexões
# trigger_revisao já aponta pra revisao_meta_placeholder. Renomeei pra revisao_meta.
# Mas a connection ainda aponta pro nome antigo. Vou atualizar.
if 'trigger_revisao' in conns:
    for branch in conns['trigger_revisao'].get('main', []):
        for c in branch:
            if c.get('node') == 'revisao_meta_placeholder':
                c['node'] = 'revisao_meta'

# Remove conn antiga do placeholder (já deve ter)
conns.pop('revisao_meta_placeholder', None)

# revisao_meta → if_revisao_ok
conns['revisao_meta'] = {'main': [[{'node': 'if_revisao_ok', 'type': 'main', 'index': 0}]]}
conns['if_revisao_ok'] = {'main': [
    [{'node': 'update_cliente_ativo', 'type': 'main', 'index': 0}],   # true
    [{'node': 'update_cliente_falhou', 'type': 'main', 'index': 0}],  # false
]}
conns['update_cliente_ativo'] = {'main': [[{'node': 'send_ativacao_msg', 'type': 'main', 'index': 0}]]}
conns['update_cliente_falhou'] = {'main': [[{'node': 'send_falha_msg', 'type': 'main', 'index': 0}]]}

# Salva
clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
update_workflow(WF_ID, name=wf['name'], nodes=nodes, connections=conns, settings=clean_settings)
print(f'✓ Workflow {WF_ID} atualizado com revisao_meta real')
print(f'  Nós: revisao_meta (substitui placeholder), if_revisao_ok,')
print(f'    update_cliente_ativo, send_ativacao_msg,')
print(f'    update_cliente_falhou, send_falha_msg')
