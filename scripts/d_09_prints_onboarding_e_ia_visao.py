"""
d_09_prints_onboarding_e_ia_visao.py

CAMADA 1 — Prints automáticos durante as boas-vindas
CAMADA 2 — IA com visão (Claude Sonnet) pra analisar prints do cliente

Antes:
- Onboarding 100% texto. Cliente leigo travava porque tinha que decifrar
  instruções escritas pra navegar no Meta Business Suite.

Agora:
- 6 prints estilizados (mockups das telas Meta com setas e destaques) são
  enviados junto com cada mensagem de boas-vindas via uazapi /send/media.
- Quando cliente trava e manda print do que ele tá vendo, o agente IA
  recebe a imagem e analisa via visão do Claude Sonnet.

Os 6 prints (em /lp-quirk-auto-ads/assets/img/onboarding/):
  01-criar-bm.png                       — Criar Business Manager
  02-config-contas.png                  — Configurações → Contas
  03-adicionar-parceiro-adaccount.png   — Modal com ID 1612905538806887
  04-compartilhar-pagina.png            — Aba Páginas
  05-pegar-adaccount-id.png             — Onde achar o ID
  06-pegar-wa-pagina.png                — Resumo dos 3 dados

URL base depois do deploy: https://autoads.quirkgrowth.com.br/assets/img/onboarding/
(precisa ter feito o deploy da LP)

ALTERAÇÕES NO N8N:

1. Workflow Gateway (2ZnZqb4wFous4uEs)
   - build_welcome_msgs agora produz 7 mensagens (1 abertura + 6 com print)
     cada uma com campo image_url opcional
   - novo nó: if_has_image (boolean check)
   - novo nó: send_welcome_media (HTTP POST /send/media uazapi)
   - send_welcome (texto puro) continua pra mensagem 1 (abertura sem print)

2. Workflow Principal (fBUin1UPt5xJEp6g)
   - build_onboarding_body detecta se webhook recebeu imagem; se sim,
     monta payload Claude com content multimodal (text + image base64)
   - parse_onboarding_resp lê _msg_atual_user do build (não do webhook)

LIMITAÇÃO CONHECIDA (TODO v2):
   Mensagens com mídia hoje vão pro branch separado (media_normalize_phone
   → media_download → ...). Pra cliente em em_onboarding mandar print,
   precisa criar bypass: media_download → check status; se em_onboarding,
   redirecionar pro build_onboarding_body com a imagem em mãos.
   Por enquanto, prints DE BAIXO (gateway → cliente) já funcionam.
   Prints DE CIMA (cliente → bot, com visão) precisam ser conectados em
   produção quando a uazapi session estiver ativa pra testar.
"""

import sys, json
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow
import config

# Script é só registro/documentação — as alterações já foram aplicadas
# por subscripts inline (ver commits). Re-executá-lo aplica idempotentemente.

GATEWAY_WF_ID = '2ZnZqb4wFous4uEs'
MAIN_WF_ID = 'fBUin1UPt5xJEp6g'
BM_QUIRK_ID = '1612905538806887'
BASE = 'https://autoads.quirkgrowth.com.br/assets/img/onboarding'

NEW_WELCOME_CODE = r'''
const cliente = $('webhook').first().json.body || {};
const nome = ($('parse_payment').first().json.nome || '').split(' ')[0] || 'aí';
const telefone = $('parse_payment').first().json.telefone;
const BM_QUIRK = "''' + BM_QUIRK_ID + r'''";
const BASE = "''' + BASE + r'''";

const msgs = [
  { text:
      `Oi, ${nome}! 👋 Sou o assistente do Quirk Auto Ads.\n\n` +
      `Pagamento confirmado ✓\n\n` +
      `Antes de subir teu primeiro anúncio, vou te orientar passo a passo a conectar tua conta Meta com a nossa BM. Leva uns 10 minutos, e vou mandar prints de cada etapa pra ficar fácil.` },
  { text:
      `*Passo 1 de 4 — Business Manager*\n\n` +
      `Acessa business.facebook.com e faz login com tua conta Facebook pessoal.\n\n` +
      `Se ainda não tem um Business Manager, clica em *"+ Criar conta"* (no print). Avisa quando estiver dentro.`,
    image_url: `${BASE}/01-criar-bm.png` },
  { text:
      `*Passo 2 de 4 — Compartilhar Ad Account*\n\n` +
      `Vai em *Configurações → Contas → Contas de anúncios* e clica em *"Adicionar"*.`,
    image_url: `${BASE}/02-config-contas.png` },
  { text:
      `Cola o ID da BM Quirk:\n\n\`${BM_QUIRK}\`\n\n` +
      `*Permissão:* tem que ser "Gerenciar campanhas". Clica em Convidar.`,
    image_url: `${BASE}/03-adicionar-parceiro-adaccount.png` },
  { text:
      `*Passo 3 de 4 — Compartilhar Página*\n\n` +
      `Mesma BM, agora na aba *Páginas*. Mesmo processo, mesmo ID (${BM_QUIRK}), mesma permissão.`,
    image_url: `${BASE}/04-compartilhar-pagina.png` },
  { text:
      `*Passo 4 — Dado 1: Ad Account ID*\n\n` +
      `No Gerenciador de Anúncios, canto superior esquerdo. Só os números.`,
    image_url: `${BASE}/05-pegar-adaccount-id.png` },
  { text:
      `*Dados 2 e 3: Link WA + Nome Página*\n\n` +
      `Manda tudo numa mensagem só.\n\nQuando você mandar, eu valido tudo em 1 min e libero pra criar campanhas. 🚀`,
    image_url: `${BASE}/06-pegar-wa-pagina.png` },
];

return msgs.map((m, i) => ({
  json: { telefone, text: m.text, image_url: m.image_url || null,
          has_image: !!m.image_url, index: i, total: msgs.length }
}));
'''

NEW_BUILD_ONB = r"""
const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
const nome = (cliente.nome_cliente || '').split(' ')[0] || 'amigo';
const wh = $('webhook').first().json.body || {};
const msgTexto = wh?.message?.content || wh?.message?.text || '';
const mediaType = wh?.message?.mediaType || '';
const ehImagem = mediaType === 'image' || /^image\//i.test(wh?.message?.mimetype || '');

let imageBase64 = null;
let imageMime = 'image/jpeg';
if (ehImagem) {
  try {
    const md = $('media_download').first().json;
    if (md?.base64) {
      imageBase64 = md.base64;
      imageMime = md.mimetype || 'image/jpeg';
    } else if (md?.fileURL) {
      const r = await this.helpers.httpRequest({
        method: 'GET', url: md.fileURL,
        encoding: 'arraybuffer', returnFullResponse: false,
      });
      imageBase64 = Buffer.from(r).toString('base64');
      imageMime = md.mimetype || 'image/jpeg';
    }
  } catch(e) {}
}

let historico = [];
try { historico = JSON.parse(cliente.historico_onboarding || '[]'); } catch(e) {}

const system = `Você é o assistente de onboarding do Quirk Auto Ads.
Cliente: ${nome} (${telefone})
Status: em_onboarding

Os 4 passos:
1. Criar BM em business.facebook.com
2. Compartilhar Ad Account com BM Quirk (ID: 1612905538806887, Gerenciar)
3. Compartilhar Página (mesmo ID, mesma permissão)
4. Reportar: Nome Página + wa.me/55... + Ad Account ID

Regras:
- Português direto, máx 4-5 linhas, tom amigável.
- Se cliente mandou IMAGEM/PRINT: analisa e diz o que ele precisa fazer/clicar.
- Se cliente pede comando Auto Ads: bloqueia ("Termina o onboarding primeiro").
- Quando os 3 dados aparecerem: responda APENAS com <REVISAO_REQUEST/>.
- NUNCA invente IDs, NUNCA finja que campanha subiu.`;

const messages = [];
for (const h of historico) messages.push({ role: h.role, content: h.content });

const userContent = [];
if (msgTexto) userContent.push({ type: 'text', text: msgTexto });
if (imageBase64) {
  userContent.push({
    type: 'image',
    source: { type: 'base64', media_type: imageMime, data: imageBase64 },
  });
}
messages.push({ role: 'user',
  content: userContent.length === 1 && userContent[0].type === 'text'
    ? userContent[0].text : userContent
});

return [{ json: {
  model: 'claude-sonnet-4-5', max_tokens: 600, temperature: 0.4,
  system, messages,
  _msg_atual_user: msgTexto || '[imagem]',
}}];
"""

# ──────────────────────────────────────────────
# Aplicar no Gateway
# ──────────────────────────────────────────────
wf = get_workflow(GATEWAY_WF_ID)
nodes = wf['nodes']; conns = wf['connections']

for n in nodes:
    if n['name'] == 'build_welcome_msgs':
        n['parameters']['jsCode'] = NEW_WELCOME_CODE

# if_has_image + send_welcome_media
nodes[:] = [n for n in nodes if n['name'] not in ('if_has_image', 'send_welcome_media')]
bwm = next(n for n in nodes if n['name'] == 'build_welcome_msgs')
x = bwm['position'][0] + 240; y = bwm['position'][1]

nodes.append({
    'parameters': {'conditions': {'boolean': [{'value1': '={{ !!$json.image_url }}', 'value2': True}]}},
    'id': 'if_has_image', 'name': 'if_has_image',
    'type': 'n8n-nodes-base.if', 'typeVersion': 1,
    'position': [x, y],
})
nodes.append({
    'parameters': {
        'method': 'POST',
        'url': 'https://quirkgrowth.uazapi.com/send/media',
        'sendHeaders': True,
        'headerParameters': {'parameters': [{'name':'Content-Type','value':'application/json'}]},
        'authentication': 'predefinedCredentialType',
        'nodeCredentialType': 'httpHeaderAuth',
        'sendBody': True, 'specifyBody': 'json',
        'jsonBody': ('={\n'
            '  "number": "{{ $json.telefone }}",\n'
            '  "type": "image",\n'
            '  "media": {{ JSON.stringify($json.image_url) }},\n'
            '  "text": {{ JSON.stringify($json.text) }}\n}'),
        'options': {'batching': {'batch': {'batchSize': 1, 'batchInterval': 1500}}},
    },
    'id': 'send_welcome_media', 'name': 'send_welcome_media',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [x + 240, y - 80],
    'credentials': {'httpHeaderAuth': config.UAZAPI_HEADER_CRED},
    'continueOnFail': True,
})

conns['build_welcome_msgs'] = {'main': [[{'node': 'if_has_image', 'type':'main', 'index':0}]]}
conns['if_has_image'] = {'main': [
    [{'node': 'send_welcome_media', 'type':'main', 'index':0}],
    [{'node': 'send_welcome',       'type':'main', 'index':0}],
]}
conns['send_welcome_media'] = {'main': [[{'node':'mark_onboarding','type':'main','index':0}]]}

update_workflow(GATEWAY_WF_ID, name=wf['name'], nodes=nodes, connections=conns,
                settings={'executionOrder': wf.get('settings',{}).get('executionOrder','v1')})
print('✓ Gateway: build_welcome com 7 msgs + if_has_image + send_welcome_media')

# ──────────────────────────────────────────────
# Aplicar no Principal
# ──────────────────────────────────────────────
wf_main = get_workflow(MAIN_WF_ID)
for n in wf_main['nodes']:
    if n['name'] == 'build_onboarding_body':
        n['parameters']['jsCode'] = NEW_BUILD_ONB

NEW_PARSE = r"""
const resp = $input.first().json;
const txt = resp?.content?.[0]?.text || '';
const solicita_revisao = /<REVISAO_REQUEST\s*\/?>/i.test(txt);
const limpo = txt.replace(/<REVISAO_REQUEST\s*\/?>/gi, '').trim();
const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
const userMsg = $('build_onboarding_body').first().json._msg_atual_user || '';
let historico = [];
try { historico = JSON.parse(cliente.historico_onboarding || '[]'); } catch(e) {}
historico.push({ role: 'user', content: userMsg });
if (limpo) historico.push({ role: 'assistant', content: limpo });
if (historico.length > 60) historico = historico.slice(-60);
return [{ json: { solicita_revisao, text: limpo, telefone,
  novo_historico: JSON.stringify(historico) }}];
"""
for n in wf_main['nodes']:
    if n['name'] == 'parse_onboarding_resp':
        n['parameters']['jsCode'] = NEW_PARSE

update_workflow(MAIN_WF_ID, name=wf_main['name'], nodes=wf_main['nodes'],
                connections=wf_main['connections'],
                settings={'executionOrder': wf_main.get('settings',{}).get('executionOrder','v1')})
print('✓ Principal: build_onboarding_body com visão Claude + parse adaptado')
