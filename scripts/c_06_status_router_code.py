#!/usr/bin/env python3
"""
Fix: switch_status_ou_normal (Switch nativo) jogava erro 'process_gestao_step
hasn't been executed' quando CONFIRMAR rodava (sub-projeto A).

Causa: a expressão do Switch referenciava $('process_gestao_step') diretamente.
No n8n, $(node) lança erro se o node não rodou na execução atual. No fluxo
CONFIRMAR, process_gestao_step nunca roda — só roda quando vem de gestão (B/C).

Fix: substitui o Switch por Code+IF.
- switch_status_ou_normal vira Code com try/catch — define is_status:bool
- if_status_route (IF novo): se is_status=true → 4 insights; senão → precheck

Idempotente.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CODE_BODY = """let is_status = false;
try {
  const gestao = $('process_gestao_step').first().json?.gestao;
  if (gestao && gestao.verbo === 'STATUS') is_status = true;
} catch(e) {}
return [{ json: { is_status, ...$input.first().json } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'switch_status_ou_normal' not in nb:
        print('ERRO: switch_status_ou_normal não existe — rode c_03 antes')
        sys.exit(1)

    nb['switch_status_ou_normal']['type'] = 'n8n-nodes-base.code'
    nb['switch_status_ou_normal']['typeVersion'] = 2
    nb['switch_status_ou_normal']['parameters'] = {'language': 'javaScript', 'jsCode': CODE_BODY}
    print('  ↻ switch_status_ou_normal: Switch → Code (try/catch)')

    if 'if_status_route' not in nb:
        wf['nodes'].append({
            'id': 'if_status_route', 'name': 'if_status_route',
            'type': 'n8n-nodes-base.if', 'typeVersion': 2,
            'position': [3950, 100],
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [{
                        'leftValue': "={{ $('switch_status_ou_normal').item.json.is_status }}",
                        'rightValue': True,
                        'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}
                    }]
                }
            }
        })
        print('  + if_status_route')

    wf['connections']['load_meta_token'] = {'main': [[{'node': 'switch_status_ou_normal', 'type': 'main', 'index': 0}]]}
    wf['connections']['switch_status_ou_normal'] = {'main': [[{'node': 'if_status_route', 'type': 'main', 'index': 0}]]}
    wf['connections']['if_status_route'] = {
        'main': [
            [{'node': 'meta_insights_today', 'type': 'main', 'index': 0}],
            [{'node': 'precheck_meta_account', 'type': 'main', 'index': 0}]
        ]
    }

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Roteamento STATUS vs normal robusto')


if __name__ == '__main__':
    main()
