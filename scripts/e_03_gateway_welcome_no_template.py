#!/usr/bin/env python3
"""
e_03 — Ajusta o welcome do gateway pra API oficial (sem depender de template).

Na Cloud API, mensagem iniciada pela empresa (welcome no pagamento, ANTES do
cliente falar) exige template aprovado. Pra lançar sem esperar aprovação:

  - Desliga os envios de WhatsApp no welcome (send_welcome / send_welcome_media)
  - MANTÉM: email de boas-vindas + transição de status (mark_onboarding)
  - O cliente é levado a falar primeiro (página de obrigado + email);
    a IA de onboarding do fluxo principal responde dentro da janela de 24h.

Rewire:  switch_router[welcome] -> [ mark_onboarding , build_email_body ]
         (antes ia pra build_welcome_msgs -> ... -> send_welcome -> mark_onboarding)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "2ZnZqb4wFous4uEs"
DISABLE = ["build_welcome_msgs", "if_has_image", "send_welcome", "send_welcome_media"]


def main():
    wf = n8n_api.get_workflow(WF_ID)
    nodes = wf["nodes"]
    conns = wf["connections"]

    # 1) rota welcome vai direto pra status + email (pula os envios WhatsApp)
    conns["switch_router"]["main"][0] = [
        {"node": "mark_onboarding", "type": "main", "index": 0},
        {"node": "build_email_body", "type": "main", "index": 0},
    ]

    # 2) desliga os nós de envio WhatsApp do welcome (ficam no fluxo, inativos)
    for n in nodes:
        if n["name"] in DISABLE:
            n["disabled"] = True

    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    clean.setdefault("executionOrder", "v1")

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=nodes, connections=conns, settings=clean)
    print("✓ Gateway: welcome WhatsApp desligado; email + status mantidos.")
    print("  switch_router[welcome] -> [mark_onboarding, build_email_body]")


if __name__ == "__main__":
    main()
