#!/usr/bin/env python3
"""Rewire global do workflow conforme spec §7.1."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


RESET_GESTAO_SIMPLES_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{gestao}', 'null'::jsonb),
  '{etapa_atual}',
  to_jsonb('ativa'::text)
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""


BUILD_GESTAO_MSG_CANCELADO_CODE = """const motivo = $('process_gestao_step').first().json.motivo || 'cancelado';
let text;
if (motivo === 'cancelado_pelo_cliente' || motivo === 'cancelado_no_confirma') text = 'Ok, cancelei. Volta quando quiser.';
else if (motivo === 'gestao_vazio') text = 'Não tem operação em andamento.';
else text = 'Cancelado.';
return [{ json: { text, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'reset_gestao_simples' not in nb:
        wf['nodes'].append({
            'id': 'reset_gestao_simples', 'name': 'reset_gestao_simples',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1750, 400],
            'parameters': {'operation': 'executeQuery', 'query': RESET_GESTAO_SIMPLES_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_gestao_simples adicionado')

    if 'build_gestao_msg_cancelado' not in nb:
        wf['nodes'].append({
            'id': 'build_gestao_msg_cancelado', 'name': 'build_gestao_msg_cancelado',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1950, 400],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_GESTAO_MSG_CANCELADO_CODE}
        })
        print('  + build_gestao_msg_cancelado adicionado')

    if 'switch_acao_gestao' not in nb:
        wf['nodes'].append({
            'id': 'switch_acao_gestao', 'name': 'switch_acao_gestao',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [1750, 50],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'avanca', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'AVANCA'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'erro_input', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'ERRO_INPUT'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'executa', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'EXECUTA'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'reset', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'RESET'}
                    ]
                }, 'options': {}
            }
        })
        print('  + switch_acao_gestao adicionado')

    if 'switch_publico_geo_livre' not in nb:
        wf['nodes'].append({
            'id': 'switch_publico_geo_livre', 'name': 'switch_publico_geo_livre',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [2400, 325],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.gestao.novo_valor.tipo }}", 'rightValue': 'publico_livre', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'PUBLICO_LIVRE'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.gestao.novo_valor.tipo }}", 'rightValue': 'geo_livre', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'GEO_LIVRE'}
                    ]
                },
                'options': {'fallbackOutput': 'extra'}
            }
        })
        print('  + switch_publico_geo_livre adicionado')

    if 'extrator_partial' not in nb:
        ext = nb.get('extrator')
        if ext:
            import copy
            clone = copy.deepcopy(ext)
            clone['name'] = 'extrator_partial'
            clone['id'] = 'extrator_partial'
            clone['position'] = [2700, 325]
            wf['nodes'].append(clone)
            print('  + extrator_partial (clone do extrator) adicionado')

    # Re-fetch nb com os nodes novos
    nb = {n['name']: n for n in wf['nodes']}

    # Rewire
    wf['connections']['load_estado'] = {'main': [[{'node': 'em_gestao_valido', 'type': 'main', 'index': 0}]]}
    wf['connections']['em_gestao_valido'] = {
        'main': [
            [{'node': 'process_gestao_step', 'type': 'main', 'index': 0}],
            [{'node': 'classify_intent', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['process_gestao_step'] = {'main': [[{'node': 'switch_acao_gestao', 'type': 'main', 'index': 0}]]}

    wf['connections']['switch_acao_gestao'] = {
        'main': [
            [{'node': 'build_gestao_response', 'type': 'main', 'index': 0}],
            [{'node': 'build_gestao_response', 'type': 'main', 'index': 0}],
            [{'node': 'load_meta_token', 'type': 'main', 'index': 0}],
            [{'node': 'reset_gestao_simples', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['reset_gestao_simples'] = {'main': [[{'node': 'build_gestao_msg_cancelado', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_gestao_msg_cancelado'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    # switch_intent: connect 6 new outputs to list_campanhas
    sw = nb['switch_intent']
    current_outputs = sw['parameters']['rules']['values']
    current_main = wf['connections'].get('switch_intent', {}).get('main', [])
    while len(current_main) < len(current_outputs) + 1:
        current_main.append([])
    for i, rule in enumerate(current_outputs):
        if rule.get('outputKey') in ['PAUSAR', 'REATIVAR', 'ENCERRAR', 'ALTERAR_VERBA', 'ALTERAR_PUBLICO', 'ALTERAR_GEO']:
            current_main[i] = [{'node': 'list_campanhas', 'type': 'main', 'index': 0}]
    wf['connections']['switch_intent']['main'] = current_main

    wf['connections']['list_campanhas'] = {'main': [[{'node': 'init_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['init_gestao'] = {'main': [[{'node': 'build_gestao_response', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_gestao_response'] = {'main': [[{'node': 'persist_estado_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['persist_estado_gestao'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    wf['connections']['load_meta_token'] = {'main': [[{'node': 'execute_gestao_action', 'type': 'main', 'index': 0}]]}
    wf['connections']['execute_gestao_action'] = {
        'main': [
            [{'node': 'meta_update_status', 'type': 'main', 'index': 0}],
            [{'node': 'meta_update_adset_budget', 'type': 'main', 'index': 0}],
            [{'node': 'switch_publico_geo_livre', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['switch_publico_geo_livre'] = {
        'main': [
            [{'node': 'build_extrator_partial_publico_body', 'type': 'main', 'index': 0}],
            [{'node': 'build_extrator_partial_geo_body', 'type': 'main', 'index': 0}],
            [{'node': 'build_targeting_atualizado', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['build_extrator_partial_publico_body'] = {'main': [[{'node': 'extrator_partial', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_extrator_partial_geo_body'] = {'main': [[{'node': 'extrator_partial', 'type': 'main', 'index': 0}]]}
    wf['connections']['extrator_partial'] = {'main': [[{'node': 'build_targeting_atualizado', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_targeting_atualizado'] = {'main': [[{'node': 'meta_update_adset_targeting', 'type': 'main', 'index': 0}]]}

    wf['connections']['meta_update_status'] = {'main': [[{'node': 'check_gestao_result', 'type': 'main', 'index': 0}]]}
    wf['connections']['meta_update_adset_budget'] = {'main': [[{'node': 'check_gestao_result', 'type': 'main', 'index': 0}]]}
    wf['connections']['meta_update_adset_targeting'] = {'main': [[{'node': 'check_gestao_result', 'type': 'main', 'index': 0}]]}

    wf['connections']['check_gestao_result'] = {'main': [[{'node': 'update_db_campanha', 'type': 'main', 'index': 0}]]}
    wf['connections']['update_db_campanha'] = {'main': [[{'node': 'audit_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['audit_gestao'] = {'main': [[{'node': 'reset_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['reset_gestao'] = {'main': [[{'node': 'build_gestao_confirmation_msg', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_gestao_confirmation_msg'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 9.3 (rewire global) aplicada')


if __name__ == '__main__':
    main()
