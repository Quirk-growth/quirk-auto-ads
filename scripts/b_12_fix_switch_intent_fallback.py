#!/usr/bin/env python3
"""
Fix: rewire de B adicionou 6 outputs novos em switch_intent (PAUSAR, REATIVAR,
ENCERRAR, ALTERAR_*) mas o output fallback (OUTRO = índice 9) ficou sem conexão.

Resultado: mensagens normais (que classify_intent classifica como OUTRO) caíam
no switch_intent e morriam silenciosamente — webhook respondia 200 mas o agente
principal nunca rodava.

Fix: conecta switch_intent output 9 → build_agente_body.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    conn = wf['connections'].get('switch_intent', {}).get('main', [])
    while len(conn) < 10:
        conn.append([])
    conn[9] = [{'node': 'build_agente_body', 'type': 'main', 'index': 0}]
    wf['connections']['switch_intent']['main'] = conn
    print('  ↻ switch_intent output 9 (OUTRO fallback) → build_agente_body')

    # Settings clean: n8n API rejeita propriedades extras
    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}

    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Fix aplicado')


if __name__ == '__main__':
    main()
