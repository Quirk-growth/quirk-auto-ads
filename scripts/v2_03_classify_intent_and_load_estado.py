#!/usr/bin/env python3
"""
Adiciona Code nodes `load_estado` e `classify_intent` ao workflow.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


LOAD_ESTADO_CODE = """// Lê estado_json da conversa (default-safe pra cliente novo)
const conv = $('select_conversa').first().json || {};
const def = {etapa_atual: 'coletando_info', criativo: {recebido: false, url: null, mimetype: null, recebido_em: null}, brief: {}, ultima_tentativa: null};
let estado = conv.estado_json;
if (typeof estado === 'string') { try { estado = JSON.parse(estado); } catch(e) { estado = def; } }
if (!estado || typeof estado !== 'object') estado = def;
estado.etapa_atual = estado.etapa_atual || 'coletando_info';
estado.criativo = estado.criativo || def.criativo;
estado.brief = estado.brief || {};
estado.ultima_tentativa = estado.ultima_tentativa || null;

return [{
  json: {
    estado,
    historico: conv.historico || '',
    criativo_url_legado: conv.criativo_url || null
  }
}];
"""

CLASSIFY_INTENT_CODE = """// Detecta intenção do cliente por regex no texto da msg
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

let intent = 'OUTRO';
if (/^(confirmar|confirmado|confirma)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^(sim,?\\s*subir|pode\\s*subir|sobe\\s*ai)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^retry$/i.test(msg)) intent = 'RETRY';
else if (/tent(e|a)r?\\s+(de\\s*novo|novamente)/i.test(msg)) intent = 'RETRY';
else if (/sub(ir|a)\\s+novamente/i.test(msg)) intent = 'RETRY';
else if (/^nova\\s+campanha$/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/come[çc]ar\\s+(uma\\s+)?nova/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/quero\\s+(criar\\s+)?(uma\\s+)?(outra|nova)\\s+campanha/i.test(msg)) intent = 'NOVA_CAMPANHA';

return [{ json: { intent, mensagem_texto: msg } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'load_estado' in nb:
        nb['load_estado']['parameters']['jsCode'] = LOAD_ESTADO_CODE
        print('  ↻ load_estado atualizado')
    else:
        wf['nodes'].append({
            'id': 'load_estado', 'name': 'load_estado',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1300, 100],
            'parameters': {'language': 'javaScript', 'jsCode': LOAD_ESTADO_CODE}
        })
        print('  + load_estado adicionado')

    if 'classify_intent' in nb:
        nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_CODE
        print('  ↻ classify_intent atualizado')
    else:
        wf['nodes'].append({
            'id': 'classify_intent', 'name': 'classify_intent',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1400, 100],
            'parameters': {'language': 'javaScript', 'jsCode': CLASSIFY_INTENT_CODE}
        })
        print('  + classify_intent adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 3 aplicada')


if __name__ == '__main__':
    main()
