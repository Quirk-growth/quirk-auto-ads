#!/usr/bin/env python3
"""switch_intent: adiciona 6 outputs novos pros verbos de gestão."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def add_rule(rules, intent_name, output_key):
    rules.append({
        'conditions': {
            'options': {'caseSensitive': True, 'typeValidation': 'loose'},
            'combinator': 'and',
            'conditions': [{
                'leftValue': "={{ $('classify_intent').item.json.intent }}",
                'rightValue': intent_name,
                'operator': {'type': 'string', 'operation': 'equals'}
            }]
        },
        'renameOutput': True, 'outputKey': output_key
    })


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    sw = nb['switch_intent']
    rules = sw['parameters']['rules']['values']
    existing_keys = {r.get('outputKey') for r in rules}

    novos = [
        ('PAUSAR', 'PAUSAR'),
        ('REATIVAR', 'REATIVAR'),
        ('ENCERRAR', 'ENCERRAR'),
        ('ALTERAR_VERBA', 'ALTERAR_VERBA'),
        ('ALTERAR_PUBLICO', 'ALTERAR_PUBLICO'),
        ('ALTERAR_GEO', 'ALTERAR_GEO'),
    ]
    for intent, key in novos:
        if key not in existing_keys:
            add_rule(rules, intent, key)
            print(f'  + switch_intent output: {key}')

    sw['parameters']['rules']['values'] = rules

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 9.1 aplicada')


if __name__ == '__main__':
    main()
