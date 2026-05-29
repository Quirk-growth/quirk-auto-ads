#!/usr/bin/env python3
"""
Fixes pra memória + integração limpa:

1. build_agente_body: passa histórico como contexto (estava só com mensagem atual)
2. Confere que classifier vê última troca corretamente
3. Garante que cada build_*_body trata casos vazios (primeira conversa)
4. Roda checks finais nas integrações: Postgres, Anthropic, UAZAPI, Meta token
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    # ─────────────────────────────────────────
    # FIX 1: build_agente_body com histórico
    # ─────────────────────────────────────────
    sys_agente = config.load_prompt("agente_principal")
    sys_agente_quoted = json.dumps(sys_agente)

    new_agente_body_code = f"""const system = {sys_agente_quoted};
const historico = String($('select_conversa').first().json?.historico || '').trim();
const novaMsg = String($('normalize_phone').first().json.mensagem_texto || '').trim();

let userContent;
if (historico) {{
  userContent = `Histórico da conversa até agora:\\n${{historico}}\\n\\nNova mensagem do cliente: ${{novaMsg}}`;
}} else {{
  userContent = novaMsg;
}}

return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 1500,
    temperature: 0.3,
    system,
    messages: [{{ role: "user", content: userContent }}]
  }}
}}];
"""

    # ─────────────────────────────────────────
    # FIX 2: build_classifier_body com contexto da última troca
    # ─────────────────────────────────────────
    sys_classifier = config.load_prompt("classifier")
    sys_classifier_quoted = json.dumps(sys_classifier)

    new_classifier_body_code = f"""const system = {sys_classifier_quoted};
const msg = String($('normalize_phone').first().json?.mensagem_texto || '');
const resp = $('agente_principal').first().json;
// Anthropic API retorna content como array de blocks
const agentResp = String(resp?.content?.[0]?.text || '');

const userContent = `Mensagem do cliente: ${{msg}}\\n\\nResposta do agente: ${{agentResp}}`;

return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 20,
    temperature: 0,
    system,
    messages: [{{ role: "user", content: userContent }}]
  }}
}}];
"""

    # ─────────────────────────────────────────
    # FIX 3: build_extrator_body — robustez
    # ─────────────────────────────────────────
    sys_extrator = config.load_prompt("extrator")
    sys_extrator_quoted = json.dumps(sys_extrator)

    new_extrator_body_code = f"""const system = {sys_extrator_quoted};
const historico = String($('build_historico').first().json?.historico_atualizado || '').trim();
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

    # Aplicar
    fixes = {
        "build_agente_body": new_agente_body_code,
        "build_classifier_body": new_classifier_body_code,
        "build_extrator_body": new_extrator_body_code,
    }
    for node in wf["nodes"]:
        if node["name"] in fixes:
            node["parameters"]["jsCode"] = fixes[node["name"]]
            print(f"  ↻ {node['name']} refatorado (agora com histórico/contexto)")

    # ─────────────────────────────────────────
    # FIX 4: build_historico — extrair texto do Anthropic response corretamente
    # ─────────────────────────────────────────
    for node in wf["nodes"]:
        if node["name"] == "build_historico":
            new_code = """const histAtual = String($('select_conversa').first().json?.historico || '');
const userMsg = String($('normalize_phone').first().json?.mensagem_texto || '');

// Anthropic API: response em $('agente_principal').json.content[0].text
const agenteResp = $('agente_principal').first().json;
const agentText = String(agenteResp?.content?.[0]?.text || '');

const classResp = $('classifier').first().json;
const classText = String(classResp?.content?.[0]?.text || 'PENDENTE').trim().toUpperCase();

const novoTurn = `|||TURN|||Cliente: ${userMsg}\\nClaude: ${agentText}`;
const completo = histAtual + novoTurn;
const turns = completo.split('|||TURN|||');
const ultimos20 = turns.slice(-20).join('|||TURN|||');

return [{
  json: {
    historico_atualizado: ultimos20,
    classifier_result: classText,
    agente_resposta: agentText,
    telefone: $('normalize_phone').first().json.telefone_normalizado
  }
}];
"""
            node["parameters"]["jsCode"] = new_code
            print(f"  ↻ build_historico refatorado (lê content[0].text do Anthropic)")

    # ─────────────────────────────────────────
    # FIX 5: send_resposta — usar build_historico.agente_resposta
    # ─────────────────────────────────────────
    for node in wf["nodes"]:
        if node["name"] == "send_resposta":
            # Confirmar que pega de $('build_historico').item.json.agente_resposta
            body_params = node["parameters"].get("bodyParameters", {}).get("parameters", [])
            for p in body_params:
                if p.get("name") == "text":
                    p["value"] = "={{ $('build_historico').item.json.agente_resposta }}"
                    print("  ↻ send_resposta.text -> $('build_historico').item.json.agente_resposta")
                if p.get("name") == "number":
                    p["value"] = "={{ $('build_historico').item.json.telefone }}"

    n8n_api.update_workflow(
        WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"}),
    )
    print(f"\n✓ Workflow atualizado")

    # ─────────────────────────────────────────
    # Auditoria final das integrações
    # ─────────────────────────────────────────
    print("\n" + "="*60)
    print("AUDITORIA DE INTEGRAÇÕES")
    print("="*60)

    postgres_nodes = []
    http_uazapi = []
    http_anthropic = []
    http_meta = []

    for node in wf["nodes"]:
        if node["type"] == "n8n-nodes-base.postgres":
            postgres_nodes.append(node["name"])
        elif node["type"] == "n8n-nodes-base.httpRequest":
            url = node["parameters"].get("url", "")
            if "uazapi" in url:
                http_uazapi.append(node["name"])
            elif "anthropic.com" in url:
                http_anthropic.append(node["name"])
            elif "facebook.com" in url:
                http_meta.append(node["name"])

    print(f"\nPostgres ({len(postgres_nodes)} nodes): {postgres_nodes}")
    print(f"  Credential ID: {config.POSTGRES_CRED['id']}")

    print(f"\nUAZAPI ({len(http_uazapi)} nodes): {http_uazapi}")
    print(f"  Credential ID: {config.UAZAPI_HEADER_CRED['id']}")

    print(f"\nAnthropic ({len(http_anthropic)} nodes): {http_anthropic}")
    print(f"  Credential ID: {config.ANTHROPIC_HEADER_CRED['id']}")

    print(f"\nMeta API ({len(http_meta)} nodes): {http_meta}")
    print(f"  Token via Postgres SELECT (load_meta_token)")


if __name__ == "__main__":
    main()
