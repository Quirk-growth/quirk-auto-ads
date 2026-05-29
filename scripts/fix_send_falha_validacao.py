#!/usr/bin/env python3
"""
UX FIX: quando validate.ok=false, hoje grava em audit_log e fica em silêncio.
Cliente fica sem saber o que aconteceu (mandou CONFIRMADO, agente respondeu
"subindo agora", mas nada chega).

FIX:
- Adiciona node `send_falha_validacao` (HTTP UAZAPI send_text) que manda
  msg pro cliente explicando o que faltou.
- Plugado depois de audit_validacao_falhou.
- Lê motivos de validate e manda lista bonitinha.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    nb = {n['name']: n for n in wf['nodes']}

    # Texto condicional baseado em motivos
    text_expr = (
        "={{ (() => {"
        "const motivos = $('validate').item.json.motivos || [];"
        "const map = {"
        "'criativo_url vazio': 'Faltou o criativo (imagem ou vídeo do imóvel). Manda aqui antes de confirmar.',"
        "'verba_diaria < 10': 'A verba diária está abaixo do mínimo (R$ 10/dia).',"
        "'verba_diaria > 100': 'A verba diária está acima do limite de segurança (R$ 100/dia).',"
        "'objetivo_meta vazio': 'Faltou o objetivo da campanha.',"
        "'geo vazio': 'Faltou a região/cidade do imóvel.',"
        "'publico_escolhido vazio': 'Faltou definir o público-alvo.',"
        "'ad_account_id vazio': 'Sua conta de anúncios não está configurada — me avisa pra arrumar.',"
        "'targeting_meta vazio': 'Problema no targeting da campanha — vou ajustar e te aviso.',"
        "'geo_locations vazio': 'Falta a localização geográfica do anúncio.'"
        "};"
        "const linhas = motivos.map(m => '• ' + (map[m] || m));"
        "return '⚠️ Não consegui subir a campanha. Faltou:\\n\\n' + linhas.join('\\n') + '\\n\\nResolve aí e me avisa pra eu subir.';"
        "})() }}"
    )

    if 'send_falha_validacao' not in nb:
        new_node = {
            "id": "send_falha_validacao",
            "name": "send_falha_validacao",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [3880, 350],
            "parameters": {
                "method": "POST",
                "url": "https://quirkgrowth.uazapi.com/send/text",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "sendBody": True,
                "contentType": "json",
                "bodyParameters": {
                    "parameters": [
                        {"name": "number", "value": "={{ $('build_historico').item.json.telefone }}"},
                        {"name": "text", "value": text_expr}
                    ]
                },
                "options": {},
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "httpHeaderAuth"
            },
            "credentials": {"httpHeaderAuth": config.UAZAPI_HEADER_CRED}
        }
        wf['nodes'].append(new_node)
        print("  + send_falha_validacao adicionado")
    else:
        nb['send_falha_validacao']['parameters']['bodyParameters']['parameters'] = [
            {"name": "number", "value": "={{ $('build_historico').item.json.telefone }}"},
            {"name": "text", "value": text_expr}
        ]
        print("  ↻ send_falha_validacao atualizado")

    # Conecta: audit_validacao_falhou → send_falha_validacao
    wf['connections']['audit_validacao_falhou'] = {
        "main": [[{"node": "send_falha_validacao", "type": "main", "index": 0}]]
    }
    print("  ↻ audit_validacao_falhou → send_falha_validacao")

    n8n_api.update_workflow(
        WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"}),
    )
    print(f"\n✓ Workflow atualizado")


if __name__ == "__main__":
    main()
