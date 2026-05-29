#!/usr/bin/env python3
"""Fix: build_historico ainda referencia classifier (removido). Atualiza pra usar classify_intent."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


NEW_CODE = """const histAtual = String($('select_conversa').first().json?.historico || '');
const userMsg = String($('normalize_phone').first().json?.mensagem_texto || '');

const agenteResp = $('agente_principal').first().json;
const agentText = String(agenteResp?.content?.[0]?.text || '');

const intent = String($('classify_intent').first().json?.intent || 'OUTRO');

const novoTurn = `|||TURN|||Cliente: ${userMsg}\\nClaude: ${agentText}`;
const completo = histAtual + novoTurn;
const turns = completo.split('|||TURN|||');
const ultimos20 = turns.slice(-20).join('|||TURN|||');

return [{
  json: {
    historico_atualizado: ultimos20,
    intent,
    agente_resposta: agentText,
    telefone: $('normalize_phone').first().json.telefone_normalizado
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}
    nb['build_historico']['parameters']['jsCode'] = NEW_CODE
    print('  ↻ build_historico atualizado (usa classify_intent)')
    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Fix aplicado')


if __name__ == '__main__':
    main()
