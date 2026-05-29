#!/usr/bin/env python3
"""Fix nodes que ainda referenciam build_historico ou outros nodes deprecated.

Nodes a corrigir:
- audit_validacao_falhou: telefone via normalize_phone
- audit_campanha_criada: já usa check_meta_results.telefone, OK
- insert_campanha: já usa check_meta_results.telefone, OK
- send_resposta: já usa build_historico (OK na OUTRO branch)
- send_confirmacao_cliente: já usa check_meta_results, OK

Verificar todos via varredura.
"""
import os, sys, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # 1) audit_validacao_falhou — telefone vem de normalize_phone agora
    new_audit_query = """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes)
VALUES (
  '{{ $('normalize_phone').item.json.telefone_normalizado }}',
  'erro_validacao',
  '{{ JSON.stringify({motivos: $('validate').item.json.motivos, json: $('validate').item.json.json_extrator}).replace(/'/g, "''") }}'::jsonb
)"""
    nb['audit_validacao_falhou']['parameters']['query'] = new_audit_query
    print('  ↻ audit_validacao_falhou usa normalize_phone')

    # 2) Varredura: lista quem referencia build_historico
    refs = []
    for n in wf['nodes']:
        for key in ['jsCode', 'query', 'jsonBody']:
            val = n['parameters'].get(key, '')
            if isinstance(val, str) and 'build_historico' in val:
                refs.append((n['name'], key))
        # bodyParameters (HTTP)
        for p in (n['parameters'].get('bodyParameters', {}) or {}).get('parameters', []):
            if 'build_historico' in str(p.get('value', '')):
                refs.append((n['name'], f"body.{p.get('name')}"))

    print(f'\nNodes que ainda referenciam build_historico: {len(refs)}')
    for r in refs:
        print(f'  - {r}')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Fix aplicado')


if __name__ == '__main__':
    main()
