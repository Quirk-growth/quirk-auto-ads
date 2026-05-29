#!/usr/bin/env python3
"""Fix: build_extrator_body referencia build_historico (não rodou na branch CONFIRMAR).
Atualiza pra usar load_estado.historico."""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    sys_extrator = open('/Users/renanreal/quirk_auto_ads/prompts/extrator.md').read()
    sys_quoted = json.dumps(sys_extrator)

    new_code = f"""const system = {sys_quoted};
const historico = String($('load_estado').first().json?.historico || '').trim();
const userContent = historico || 'sem histórico — não confirmar campanha';

return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 3000,
    temperature: 0,
    system,
    messages: [{{ role: "user", content: userContent }}]
  }}
}}];
"""
    nb['build_extrator_body']['parameters']['jsCode'] = new_code
    print('  ↻ build_extrator_body usa load_estado.historico')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Fix aplicado')


if __name__ == '__main__':
    main()
