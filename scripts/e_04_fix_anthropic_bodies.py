#!/usr/bin/env python3
"""
e_04 — Corrige o 400 da Anthropic ("Extra inputs are not permitted").

Os nós de IA enviam JSON.stringify($json) inteiro pro /v1/messages, então
campos auxiliares top-level (ex: _msg_atual_user no build_onboarding_body)
vazam pro request e a Anthropic rejeita.

Fix: no jsonBody, filtra chaves top-level que começam com '_'. Nenhum
parâmetro válido da API começa com '_', e os nós downstream continuam lendo
o campo do BUILDER (não do HTTP), então nada quebra.

Bug pré-existente (não da migração uazapi->Cloud), mas bloqueia a resposta
da IA — então entra no pacote "integração funcionando".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "fBUin1UPt5xJEp6g"
ANTHROPIC_NODES = ["onboarding_agent", "agente_principal", "extrator", "extrator_partial"]

OLD = "={{ JSON.stringify($json) }}"
NEW = "={{ JSON.stringify(Object.fromEntries(Object.entries($json).filter(([k]) => !k.startsWith('_')))) }}"


def main():
    wf = n8n_api.get_workflow(WF_ID)
    patched = []
    for n in wf["nodes"]:
        if n["name"] in ANTHROPIC_NODES:
            jb = n["parameters"].get("jsonBody", "")
            if jb.strip() == OLD:
                n["parameters"]["jsonBody"] = NEW
                patched.append(n["name"])
            else:
                print(f"  ⚠️ {n['name']}: jsonBody inesperado, NÃO alterado -> {jb[:80]}")

    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    clean.setdefault("executionOrder", "v1")

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=clean)
    print("✓ Patched:", patched)


if __name__ == "__main__":
    main()
