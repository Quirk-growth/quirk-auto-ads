#!/usr/bin/env python3
"""
e_06 — Aplica o jsCode versionado em scripts/nodes/<nome>.js nos nós de mesmo
nome do workflow principal. Reusável: rode sempre que editar um .js lá.

Inclui o fix de formatação WhatsApp (2026-07-02): parse_onboarding_resp limpa
markdown e nunca deixa asterisco colado em link; build_onboarding_body reforça
no prompt.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "fBUin1UPt5xJEp6g"
NODES_DIR = os.path.join(os.path.dirname(__file__), "nodes")


def main():
    files = {f[:-3]: os.path.join(NODES_DIR, f)
             for f in os.listdir(NODES_DIR) if f.endswith(".js")}
    wf = n8n_api.get_workflow(WF_ID)
    done, missing = [], set(files)
    for n in wf["nodes"]:
        if n["name"] in files:
            n["parameters"]["jsCode"] = open(files[n["name"]]).read()
            done.append(n["name"])
            missing.discard(n["name"])

    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    clean.setdefault("executionOrder", "v1")

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=clean)
    print("✓ Aplicados:", done)
    if missing:
        print("⚠️ .js sem nó correspondente:", missing)


if __name__ == "__main__":
    main()
