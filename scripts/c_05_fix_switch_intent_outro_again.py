#!/usr/bin/env python3
"""
Fix: switch_intent output 10 (fallback OUTRO) ficou sem conexão depois que
adicionei output 9 (STATUS) no sub-projeto C.

Mensagens normais (intent=OUTRO) iam pra switch_intent mas o fallback
não tinha pra onde rotear → fluxo morria em respond_immediate sem chamar
o agente.

Mesmo bug que o b_12_fix_switch_intent_fallback resolveu no passado.
Cada vez que adiciona output novo no switch_intent, o índice do fallback
muda e precisa ser reconectado.

Acerto definitivo: rodar este script idempotente, que SEMPRE garante que
o último output (fallback) está conectado em build_agente_body.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    sw = nb['switch_intent']
    rules = sw['parameters']['rules']['values']
    n_rules = len(rules)
    fallback_idx = n_rules  # o fallback sempre é o output APÓS o último rule

    conn = wf['connections'].get('switch_intent', {}).get('main', [])
    # Garante que o array tem espaço pro fallback
    while len(conn) < fallback_idx + 1:
        conn.append([])

    expected = [{'node': 'build_agente_body', 'type': 'main', 'index': 0}]
    if conn[fallback_idx] != expected:
        conn[fallback_idx] = expected
        print(f'  ↻ switch_intent output {fallback_idx} (OUTRO fallback) → build_agente_body')
    else:
        print(f'  ✓ switch_intent fallback (output {fallback_idx}) já está OK')

    wf['connections']['switch_intent']['main'] = conn

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Fallback OUTRO reconectado')


if __name__ == '__main__':
    main()
