#!/usr/bin/env python3
"""
Refatora os 3 nodes Anthropic (agente_principal, classifier, extrator) que estavam
como LangChain LM node (não executável standalone) pra HTTP genéricos batendo direto
na API Anthropic. Mais portável e funciona sem AI Agent node.

Endpoint: POST https://api.anthropic.com/v1/messages
Headers: x-api-key (via credential httpHeaderAuth), anthropic-version: 2023-06-01, content-type: application/json
Body: {model, max_tokens, system, messages}
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-5"


def anthropic_node(node_id, name, position, system_text, user_expr, max_tokens=2000, temperature=0.3):
    """Cria um node HTTP genérico que chama POST /v1/messages com sistema+user."""
    # Escapa system text pra JSON-safe (n8n vai processar como expressão)
    # Usa $fromAI-like: vamos passar system inline (1 mensagem grande)
    import json as _json
    system_escaped = _json.dumps(system_text)[1:-1]  # remove aspas externas

    body = (
        '={\n'
        f'  "model": "{MODEL}",\n'
        f'  "max_tokens": {max_tokens},\n'
        f'  "temperature": {temperature},\n'
        f'  "system": "{system_escaped}",\n'
        '  "messages": [\n'
        f'    {{ "role": "user", "content": "{{{{ {user_expr} }}}}" }}\n'
        '  ]\n'
        '}'
    )

    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "parameters": {
            "method": "POST",
            "url": ANTHROPIC_URL,
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "anthropic-version", "value": "2023-06-01"},
                    {"name": "content-type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body,
            "options": {},
        },
        "credentials": {"httpHeaderAuth": config.ANTHROPIC_HEADER_CRED},
        "retryOnFail": True,
        "maxTries": 2,
        "waitBetweenTries": 2000,
    }


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    # Carrega os 3 prompts
    sys_agente = config.load_prompt("agente_principal")
    sys_classifier = config.load_prompt("classifier")
    sys_extrator = config.load_prompt("extrator")

    # Substitui os 3 nodes
    new_definitions = {
        "agente_principal": anthropic_node(
            "agente_principal", "agente_principal", [1560, 100],
            sys_agente,
            "$('normalize_phone').item.json.mensagem_texto.replace(/\"/g, '\\\\\"').replace(/\\n/g, '\\\\n')",
            max_tokens=1500, temperature=0.3
        ),
        "classifier": anthropic_node(
            "classifier", "classifier", [1780, 100],
            sys_classifier,
            "('Mensagem do cliente: ' + ($('normalize_phone').item.json.mensagem_texto || '') + '\\\\n\\\\nResposta do agente: ' + ($('agente_principal').item.json.content?.[0]?.text || '')).replace(/\"/g, '\\\\\"').replace(/\\n/g, '\\\\n')",
            max_tokens=20, temperature=0
        ),
        "extrator": anthropic_node(
            "extrator", "extrator", [2880, 50],
            sys_extrator,
            "($('build_historico').item.json.historico_atualizado || '').replace(/\"/g, '\\\\\"').replace(/\\n/g, '\\\\n')",
            max_tokens=3000, temperature=0
        ),
    }

    for i, node in enumerate(wf["nodes"]):
        if node["name"] in new_definitions:
            wf["nodes"][i] = new_definitions[node["name"]]
            print(f"  ↻ {node['name']} refatorado pra HTTP")

    n8n_api.update_workflow(
        WF_ID,
        name=wf["name"],
        nodes=wf["nodes"],
        connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"}),
    )
    print(f"\n✓ Workflow atualizado")


if __name__ == "__main__":
    main()
