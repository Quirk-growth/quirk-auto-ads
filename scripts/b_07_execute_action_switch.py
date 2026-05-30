#!/usr/bin/env python3
"""execute_gestao_action (Switch por verbo) + check_gestao_result (Code)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CHECK_GESTAO_RESULT_CODE = """function classify(node) {
  try {
    const r = $(node).first().json;
    if (r?.error) {
      const msg = r.error.message || '';
      if (/Request failed with status code 5\\d\\d/i.test(msg) || /timeout/i.test(msg) || /is_transient.{1,5}true/i.test(msg) || /ECONN/i.test(msg)) {
        return { ok: false, classe: 'infra', motivo: msg.slice(0, 200) };
      }
      const matchUser = msg.match(/error_user_msg\\\\?\\":\\\\?\\"([^\\"]+)/);
      let motivo = matchUser ? matchUser[1].replace(/\\\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))) : msg.slice(0, 200);
      return { ok: false, classe: 'dado', motivo };
    }
    return { ok: true, response_id: r?.id || r?.success || true };
  } catch (e) { return { ok: false, classe: 'infra', motivo: e.message }; }
}

const verbo = $('process_gestao_step').first().json.gestao.verbo;
let result;
if (['PAUSAR', 'REATIVAR', 'ENCERRAR'].includes(verbo)) result = classify('meta_update_status');
else if (verbo === 'ALTERAR_VERBA') result = classify('meta_update_adset_budget');
else if (['ALTERAR_PUBLICO', 'ALTERAR_GEO'].includes(verbo)) result = classify('meta_update_adset_targeting');
else result = { ok: false, classe: 'dado', motivo: 'verbo_desconhecido' };

return [{
  json: {
    ...result,
    verbo,
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    selecionada: $('process_gestao_step').first().json.gestao.selecionada,
    novo_valor: $('process_gestao_step').first().json.gestao.novo_valor
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'execute_gestao_action' not in nb:
        wf['nodes'].append({
            'id': 'execute_gestao_action', 'name': 'execute_gestao_action',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [2800, 100],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'or',
                          'conditions': [
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'PAUSAR', 'operator': {'type': 'string', 'operation': 'equals'}},
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'REATIVAR', 'operator': {'type': 'string', 'operation': 'equals'}},
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ENCERRAR', 'operator': {'type': 'string', 'operation': 'equals'}}
                          ]},
                         'renameOutput': True, 'outputKey': 'STATUS'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ALTERAR_VERBA', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'VERBA'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'or',
                          'conditions': [
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ALTERAR_PUBLICO', 'operator': {'type': 'string', 'operation': 'equals'}},
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ALTERAR_GEO', 'operator': {'type': 'string', 'operation': 'equals'}}
                          ]},
                         'renameOutput': True, 'outputKey': 'TARGETING'}
                    ]
                },
                'options': {}
            }
        })
        print('  + execute_gestao_action adicionado')

    if 'check_gestao_result' not in nb:
        wf['nodes'].append({
            'id': 'check_gestao_result', 'name': 'check_gestao_result',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [3200, 250],
            'parameters': {'language': 'javaScript', 'jsCode': CHECK_GESTAO_RESULT_CODE}
        })
        print('  + check_gestao_result adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 7 aplicada')


if __name__ == '__main__':
    main()
