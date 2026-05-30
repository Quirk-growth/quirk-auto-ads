#!/usr/bin/env python3
"""Cria send_gestao_msg (UAZAPI HTTP) dedicado pra B + reroteia toda gestão pra ele."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # Sender dedicado pra B — lê de qualquer node anterior que tenha {text, telefone}
    if 'send_gestao_msg' not in nb:
        wf['nodes'].append({
            'id': 'send_gestao_msg', 'name': 'send_gestao_msg',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
            'position': [4400, 200],
            'parameters': {
                'method': 'POST',
                'url': 'https://quirkgrowth.uazapi.com/send/text',
                'sendHeaders': True,
                'headerParameters': {'parameters': [{'name': 'Content-Type', 'value': 'application/json'}]},
                'sendBody': True,
                'contentType': 'json',
                'bodyParameters': {
                    'parameters': [
                        {'name': 'number', 'value': "={{ $json.telefone }}"},
                        {'name': 'text', 'value': "={{ $json.text }}"}
                    ]
                },
                'options': {},
                'authentication': 'predefinedCredentialType',
                'nodeCredentialType': 'httpHeaderAuth'
            },
            'credentials': {'httpHeaderAuth': config.UAZAPI_HEADER_CRED}
        })
        print('  + send_gestao_msg adicionado')

    # Reroteia tudo da gestão pra send_gestao_msg em vez de media_send_confirma
    # persist_estado_gestao → send_gestao_msg
    wf['connections']['persist_estado_gestao'] = {'main': [[{'node': 'send_gestao_msg', 'type': 'main', 'index': 0}]]}
    # build_gestao_msg_cancelado → send_gestao_msg
    wf['connections']['build_gestao_msg_cancelado'] = {'main': [[{'node': 'send_gestao_msg', 'type': 'main', 'index': 0}]]}
    # build_gestao_confirmation_msg → send_gestao_msg
    wf['connections']['build_gestao_confirmation_msg'] = {'main': [[{'node': 'send_gestao_msg', 'type': 'main', 'index': 0}]]}

    # Branch ERRO_INPUT do switch_acao_gestao precisa passar pelo build_gestao_response
    # antes de ir pro send_gestao_msg. Mas no rewire anterior eu apontei pra build_gestao_response.
    # Pra ERRO_INPUT, build_gestao_response NÃO deve persistir (só mostra msg) → vai pro send_gestao_msg direto.
    # Então preciso separar: cria build_gestao_response_erro que NÃO persiste.
    # Ou: roteia AVANCA → build_gestao_response → persist → send_gestao_msg
    #     ERRO_INPUT → build_gestao_response → send_gestao_msg (sem persist)
    #
    # Solução simples: 2 outputs de build_gestao_response — um pra AVANCA (com persist) e um pra ERRO_INPUT (sem persist).
    # Mas n8n Code node só tem 1 output. Solução: switch_acao_gestao já roteia, então mantemos AVANCA e ERRO_INPUT
    # passando pelo build_gestao_response, mas o output de build_gestao_response sempre vai pra send_gestao_msg.
    # O persist só roda no caminho de init_gestao (entrada nova de gestão).
    wf['connections']['build_gestao_response'] = {'main': [[{'node': 'send_gestao_msg', 'type': 'main', 'index': 0}]]}

    # Como init_gestao já vai pra build_gestao_response, mantém esse caminho.
    # Mas pra INIT (vinda do switch_intent → list_campanhas → init_gestao), precisa de persist ANTES do send.
    # Vou simplificar: init_gestao → persist_estado_gestao → build_gestao_response → send_gestao_msg
    wf['connections']['init_gestao'] = {'main': [[{'node': 'persist_estado_gestao', 'type': 'main', 'index': 0}]]}
    # persist_estado_gestao agora vai pra build_gestao_response (que devolve a msg) → send_gestao_msg
    wf['connections']['persist_estado_gestao'] = {'main': [[{'node': 'build_gestao_response', 'type': 'main', 'index': 0}]]}

    # AVANCA do switch_acao_gestao: process_gestao_step já populou gestao (selecionada/passo).
    # Precisa persistir esse estado novo antes de mandar a msg. Então:
    # switch_acao_gestao AVANCA → persist_estado_gestao → build_gestao_response → send_gestao_msg
    # switch_acao_gestao ERRO_INPUT → build_gestao_response → send_gestao_msg (NÃO persiste)
    wf['connections']['switch_acao_gestao'] = {
        'main': [
            [{'node': 'persist_estado_gestao', 'type': 'main', 'index': 0}],
            [{'node': 'build_gestao_response', 'type': 'main', 'index': 0}],
            [{'node': 'load_meta_token', 'type': 'main', 'index': 0}],
            [{'node': 'reset_gestao_simples', 'type': 'main', 'index': 0}]
        ]
    }

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Sender dedicado + rerouting concluído')


if __name__ == '__main__':
    main()
