#!/usr/bin/env python3
"""
Fix: agente_principal ignorava ESTADO_BLOCK e respondia "validando e subindo"
mesmo com campanha já ativa.

Causa: LLM se ancorava no histórico (msgs anteriores pedindo criativo) e
ignorava a instrução "etapa=ativa → confirme com campaign_id".

Solução: BYPASS o agente_principal quando check_meta_results.ok=true.
Resposta vira determinística (build_resposta_ativa Code node):
  ✅ Campanha **<nome>** subiu no Meta Ads!
  📋 IDs: Campaign, Adset, Creative, Ad
  🚦 Status: PAUSED no Meta — entra no Ads Manager e ATIVA...

Nodes novos:
- switch_resposta_meta: roteador depois de audit_campanha_criada
  - ATIVA (ok=true) → build_resposta_ativa
  - fallback (erro) → build_agente_body (mantém fluxo antigo pra erros)
- build_resposta_ativa: monta msg templatizada com IDs reais

Ajustes:
- update_estado_etapa v2: detecta check_meta_results.ok e força etapa=ativa
- build_historico v2: fallback pra build_resposta_ativa quando agente_principal não rodou

NOTA: este script é DOCUMENTAÇÃO do fix; o estado já foi aplicado no
n8n via comandos diretos durante debug. Rodar este script é idempotente.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


BUILD_RESPOSTA_ATIVA_CODE = """// Resposta templatizada quando campanha subiu (bypass do LLM)
const r = $('check_meta_results').first().json;
const nome = r.json_extrator?.campanha?.nome || 'sua campanha';

const text = `✅ Campanha **${nome}** subiu no Meta Ads!\\n\\n` +
  `📋 IDs:\\n` +
  `• Campaign: ${r.campaign_id}\\n` +
  `• Adset: ${r.adset_id}\\n` +
  `• Creative: ${r.creative_id}\\n` +
  `• Ad: ${r.ad_id}\\n\\n` +
  `🚦 Status: PAUSED no Meta — entra no Ads Manager e ATIVA quando estiver tudo certo.\\n\\n` +
  `Qualquer ajuste posterior, é só me chamar (PAUSAR / REATIVAR / ALTERAR VERBA / ALTERAR PUBLICO / ALTERAR GEO / ENCERRAR).`;

return [{
  json: {
    content: [{type: 'text', text}]
  }
}];
"""


SWITCH_RULES = {
    'rules': {
        'values': [
            {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [{
                        'leftValue': "={{ $('check_meta_results').item.json.ok ? 'true' : 'false' }}",
                        'rightValue': 'true',
                        'operator': {'type': 'string', 'operation': 'equals'}
                    }]
                },
                'renameOutput': True, 'outputKey': 'ATIVA'
            }
        ]
    },
    'options': {'fallbackOutput': 'extra'}
}


UPDATE_ESTADO_ETAPA_V2 = """const estado = $('load_estado').first().json.estado;
const brief = estado.brief || {};
const tem_criativo = !!(estado.criativo?.recebido);

const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);
const verbaOk = typeof brief.campanha?.verba_diaria === 'number' && brief.campanha.verba_diaria >= 10 && brief.campanha.verba_diaria <= 100;

let novaEtapa = estado.etapa_atual;

try {
  const cmr = $('check_meta_results').first().json;
  if (cmr?.ok) {
    novaEtapa = 'ativa';
    estado.etapa_atual = novaEtapa;
    return [{ json: { estado, brief_completo: true, tem_criativo: true } }];
  }
} catch(e) {}

if (estado.etapa_atual === 'coletando_info') {
  if (briefCompleto && verbaOk && !tem_criativo) novaEtapa = 'aguardando_criativo';
  else if (briefCompleto && verbaOk && tem_criativo) novaEtapa = 'pronta_pra_subir';
} else if (estado.etapa_atual === 'aguardando_criativo') {
  if (tem_criativo) novaEtapa = 'pronta_pra_subir';
  else if (!briefCompleto) novaEtapa = 'coletando_info';
}

estado.etapa_atual = novaEtapa;

return [{ json: { estado, brief_completo: briefCompleto, tem_criativo } }];
"""


BUILD_HISTORICO_V2 = """const histAtual = String($('select_conversa').first().json?.historico || '');
const userMsg = String($('normalize_phone').first().json?.mensagem_texto || '');

let agenteResp = null;
try { agenteResp = $('agente_principal').first().json; } catch(e) {}
let agentText = String(agenteResp?.content?.[0]?.text || '');

if (!agentText) {
  try {
    const r = $('build_resposta_ativa').first().json;
    agentText = String(r?.content?.[0]?.text || '');
  } catch(e) {}
}

const novoTurn = `|||TURN|||Cliente: ${userMsg}\\nClaude: ${agentText}`;
const completo = histAtual + novoTurn;
const turns = completo.split('|||TURN|||');
const ultimos20 = turns.slice(-20).join('|||TURN|||');

return [{
  json: {
    historico_atualizado: ultimos20,
    classifier_result: 'PENDENTE',
    agente_resposta: agentText,
    telefone: $('normalize_phone').first().json.telefone_normalizado
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'build_resposta_ativa' not in nb:
        wf['nodes'].append({
            'id': 'build_resposta_ativa', 'name': 'build_resposta_ativa',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [6000, 100],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_RESPOSTA_ATIVA_CODE}
        })
        print('+ build_resposta_ativa adicionado')
    else:
        nb['build_resposta_ativa']['parameters']['jsCode'] = BUILD_RESPOSTA_ATIVA_CODE
        print('↻ build_resposta_ativa atualizado')

    if 'switch_resposta_meta' not in nb:
        wf['nodes'].append({
            'id': 'switch_resposta_meta', 'name': 'switch_resposta_meta',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [5900, 200],
            'parameters': SWITCH_RULES
        })
        print('+ switch_resposta_meta adicionado')

    nb['update_estado_etapa']['parameters']['jsCode'] = UPDATE_ESTADO_ETAPA_V2
    nb['build_historico']['parameters']['jsCode'] = BUILD_HISTORICO_V2

    wf['connections']['audit_campanha_criada'] = {'main': [[{'node': 'switch_resposta_meta', 'type': 'main', 'index': 0}]]}
    wf['connections']['switch_resposta_meta'] = {
        'main': [
            [{'node': 'build_resposta_ativa', 'type': 'main', 'index': 0}],
            [{'node': 'build_agente_body', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['build_resposta_ativa'] = {'main': [[{'node': 'update_estado_etapa', 'type': 'main', 'index': 0}]]}

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Bypass agente_principal em check_meta_results.ok → build_resposta_ativa direto')


if __name__ == '__main__':
    main()
