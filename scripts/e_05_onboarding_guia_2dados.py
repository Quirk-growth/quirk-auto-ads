#!/usr/bin/env python3
"""
e_05 — Novo fluxo de onboarding (aprovado com Renan em 2026-07-02):

- build_onboarding_body: envia o link do guia (autoads.quirkgrowth.com.br/onboarding.html),
  tira dúvidas em vez de recitar passos, NÃO pede link wa.me (orienta integração do WhatsApp
  na Fanpage), e reduz de 3 -> 2 dados pra concluir (Página + Conta de Anúncios).
- revisao_meta: extrai os dados de TODA a conversa (fix da "janela de 5 msgs"), remove a
  exigência de wa_link, e valida a Página contra client_pages + owned_pages (páginas próprias
  da BM), casando pelo nome citado na conversa (sem exigir formato rígido).

Código dos nós versionado em scripts/nodes/*.js
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "fBUin1UPt5xJEp6g"
NODES_DIR = os.path.join(os.path.dirname(__file__), "nodes")
MAP = {
    "build_onboarding_body": "build_onboarding_body.js",
    "revisao_meta": "revisao_meta.js",
}


def main():
    wf = n8n_api.get_workflow(WF_ID)
    done = []
    for n in wf["nodes"]:
        if n["name"] in MAP:
            js = open(os.path.join(NODES_DIR, MAP[n["name"]])).read()
            n["parameters"]["jsCode"] = js
            done.append(n["name"])

    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    clean.setdefault("executionOrder", "v1")

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=clean)
    print("✓ Aplicado:", done)


if __name__ == "__main__":
    main()
