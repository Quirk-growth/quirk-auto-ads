#!/usr/bin/env python3
"""Fix crítico: select_conversa não retorna estado_json — load_estado sempre usa default."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


NEW_QUERY = (
    "SELECT $1::text AS telefone, "
    "COALESCE((SELECT historico FROM auto_ads.conversas WHERE telefone = $1), '') AS historico, "
    "COALESCE((SELECT criativo_url FROM auto_ads.conversas WHERE telefone = $1), '') AS criativo_url, "
    "COALESCE((SELECT estado_json FROM auto_ads.conversas WHERE telefone = $1), "
    "'{\"etapa_atual\":\"coletando_info\",\"criativo\":{\"recebido\":false,\"url\":null},\"brief\":{},\"ultima_tentativa\":null}'::jsonb) AS estado_json"
)


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}
    nb['select_conversa']['parameters']['query'] = NEW_QUERY
    print('  ↻ select_conversa retorna estado_json também')
    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Fix crítico aplicado')


if __name__ == '__main__':
    main()
