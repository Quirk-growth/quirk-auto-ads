#!/usr/bin/env python3
"""
Refator v2 dos 3 nodes Anthropic:

Substitui body inline com {{ }} (que quebra com aspas/newlines) por:
1. Code node que MONTA o body como objeto JS, com escape seguro
2. HTTP node simplificado que envia $json como JSON

Estrutura por chamada Anthropic (3 instâncias):
  [build_<X>_body] (Code) → [<X>] (HTTP /v1/messages)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-5"


def build_body_code_node(node_id, name, position, system_prompt, user_content_expr, max_tokens=2000, temperature=0.3):
    """
    Cria um Code node que retorna {model, max_tokens, temperature, system, messages}.
    user_content_expr é uma expressão JS pura que produz a string content.
    """
    # Escapa o system prompt como string JS literal (precisa estar dentro de backticks ou aspas duplas com escape)
    # Vamos usar JSON.stringify() pra criar a string segura
    import json as _json
    system_quoted = _json.dumps(system_prompt)  # produz "...escapes válidos JSON..."

    js_code = f"""const system = {system_quoted};
const userContent = String({user_content_expr} || "");

return [{{
  json: {{
    model: "{MODEL}",
    max_tokens: {max_tokens},
    temperature: {temperature},
    system,
    messages: [{{ role: "user", content: userContent }}]
  }}
}}];
"""
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
        "parameters": {
            "language": "javaScript",
            "jsCode": js_code,
        },
    }


def anthropic_http_node(node_id, name, position):
    """HTTP node simplificado que envia o objeto vindo do node anterior como JSON."""
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
            "jsonBody": "={{ JSON.stringify($json) }}",
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

    sys_agente = config.load_prompt("agente_principal")
    sys_classifier = config.load_prompt("classifier")
    sys_extrator = config.load_prompt("extrator")

    # Remove os 3 nodes Anthropic antigos
    OLD_NAMES = {"agente_principal", "classifier", "extrator"}
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in OLD_NAMES]

    # Build new nodes (Code + HTTP por Anthropic call)
    new_nodes = [
        # ─── Agente principal ───
        build_body_code_node(
            "build_agente_body", "build_agente_body", [1500, 100],
            sys_agente,
            "$('normalize_phone').first().json.mensagem_texto",
            max_tokens=1500, temperature=0.3,
        ),
        anthropic_http_node("agente_principal", "agente_principal", [1700, 100]),

        # ─── Classifier ───
        build_body_code_node(
            "build_classifier_body", "build_classifier_body", [1900, 100],
            sys_classifier,
            ("'Mensagem do cliente: ' + ($('normalize_phone').first().json.mensagem_texto || '') + "
             "'\\n\\nResposta do agente: ' + ($('agente_principal').first().json.content?.[0]?.text || '')"),
            max_tokens=20, temperature=0,
        ),
        anthropic_http_node("classifier", "classifier", [2100, 100]),

        # ─── Extrator ───
        build_body_code_node(
            "build_extrator_body", "build_extrator_body", [2880, 50],
            sys_extrator,
            "$('build_historico').first().json.historico_atualizado",
            max_tokens=3000, temperature=0,
        ),
        anthropic_http_node("extrator", "extrator", [3080, 50]),
    ]

    wf["nodes"].extend(new_nodes)

    # Reposiciona nodes do meio para acomodar os novos
    POSITION_FIXES = {
        "build_historico": [2300, 100],
        "upsert_conversa": [2500, 100],
        "send_resposta": [2700, 100],
        "if_confirmado": [2900, 100],
        # extrator está em [3080, 50] (acima)
        "parse_extrator": [3280, 50],
        "validate": [3480, 50],
        "if_valid": [3680, 50],
        "load_meta_token": [3880, -100],
        "meta_d1_campaign": [4080, -100],
        "meta_d2_adset": [4280, -100],
        "meta_d3_creative": [4480, -100],
        "meta_d4_ad": [4680, -100],
        "insert_campanha": [4880, -100],
        "audit_campanha_criada": [5080, -100],
        "send_confirmacao_cliente": [5280, -100],
        "audit_validacao_falhou": [3880, 200],
    }
    for node in wf["nodes"]:
        if node["name"] in POSITION_FIXES:
            node["position"] = POSITION_FIXES[node["name"]]

    # Update connections (insere build_<X>_body entre upstream e <X>)
    wf["connections"]["select_conversa"] = {"main": [[{"node": "build_agente_body", "type": "main", "index": 0}]]}
    wf["connections"]["build_agente_body"] = {"main": [[{"node": "agente_principal", "type": "main", "index": 0}]]}
    wf["connections"]["agente_principal"] = {"main": [[{"node": "build_classifier_body", "type": "main", "index": 0}]]}
    wf["connections"]["build_classifier_body"] = {"main": [[{"node": "classifier", "type": "main", "index": 0}]]}
    # classifier → build_historico (já existe)
    wf["connections"]["classifier"] = {"main": [[{"node": "build_historico", "type": "main", "index": 0}]]}
    # if_confirmado (true) → build_extrator_body em vez de extrator
    wf["connections"]["if_confirmado"] = {
        "main": [
            [{"node": "build_extrator_body", "type": "main", "index": 0}],
            []
        ]
    }
    wf["connections"]["build_extrator_body"] = {"main": [[{"node": "extrator", "type": "main", "index": 0}]]}
    # extrator → parse_extrator (já existe)
    wf["connections"]["extrator"] = {"main": [[{"node": "parse_extrator", "type": "main", "index": 0}]]}

    n8n_api.update_workflow(
        WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"})
    )
    print(f"✓ Refatorado: 6 nodes Anthropic (3 build + 3 HTTP)")
    print(f"  Total nodes: {len(wf['nodes'])}")


if __name__ == "__main__":
    main()
