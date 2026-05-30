#!/usr/bin/env python3
"""HTTP nodes pra Meta UPDATE: status + budget + targeting."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


META_HEADERS = [{'name': 'Content-Type', 'value': 'application/json'}]


def http_node(node_id, name, position, url_expr, body_expr):
    return {
        'id': node_id, 'name': name,
        'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
        'position': position,
        'parameters': {
            'method': 'POST',
            'url': url_expr,
            'sendHeaders': True,
            'headerParameters': {'parameters': META_HEADERS},
            'sendBody': True,
            'specifyBody': 'json',
            'jsonBody': body_expr,
            'options': {},
        },
        'retryOnFail': True, 'maxTries': 2, 'waitBetweenTries': 2000,
        'continueOnFail': True
    }


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'meta_update_status' not in nb:
        wf['nodes'].append(http_node(
            'meta_update_status', 'meta_update_status',
            [3000, 100],
            "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.campaign_id_meta }}",
            """={
  "status": "{{ ({PAUSAR:'PAUSED', REATIVAR:'ACTIVE', ENCERRAR:'ARCHIVED'})[$('process_gestao_step').item.json.gestao.verbo] }}",
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""
        ))
        print('  + meta_update_status adicionado')

    if 'meta_update_adset_budget' not in nb:
        wf['nodes'].append(http_node(
            'meta_update_adset_budget', 'meta_update_adset_budget',
            [3000, 250],
            "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.adset_id_meta }}",
            """={
  "daily_budget": {{ $('process_gestao_step').item.json.gestao.novo_valor.valor * 100 }},
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""
        ))
        print('  + meta_update_adset_budget adicionado')

    if 'meta_update_adset_targeting' not in nb:
        wf['nodes'].append(http_node(
            'meta_update_adset_targeting', 'meta_update_adset_targeting',
            [3000, 400],
            "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.adset_id_meta }}",
            """={
  "targeting": {{ JSON.stringify($('build_targeting_atualizado').item.json.targeting) }},
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""
        ))
        print('  + meta_update_adset_targeting adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 5 aplicada')


if __name__ == '__main__':
    main()
