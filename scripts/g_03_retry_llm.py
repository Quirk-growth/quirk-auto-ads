# scripts/g_03_retry_llm.py
# Endurece o retry dos nos que chamam a API da Anthropic no workflow principal.
# Causa raiz: Anthropic devolve 529 "Overloaded" em janelas de sobrecarga; com
# maxTries=2 / wait=2s o no esgota em ~4s e a execucao morre (cliente sem resposta).
# 5 tentativas x 5000ms e o maximo que o n8n suporta nativamente (~20s de janela).
#   python3 g_03_retry_llm.py          -> dry-run
#   python3 g_03_retry_llm.py deploy   -> aplica (backup antes)
import json, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
MAX_TRIES = 5
WAIT_MS = 5000

wf = n8n_api.get_workflow(WF)
alvos = []
for n in wf["nodes"]:
    url = (n.get("parameters", {}) or {}).get("url", "")
    if isinstance(url, str) and "api.anthropic.com" in url:
        alvos.append(n)

print(f"Nós que chamam a Anthropic: {len(alvos)}\n")
for n in alvos:
    print(f"- {n['name']:<26} antes: retry={n.get('retryOnFail', False)} "
          f"maxTries={n.get('maxTries')} wait={n.get('waitBetweenTries')}")

if not alvos:
    print("ABORTAR: nenhum nó encontrado"); sys.exit(1)

if not DEPLOY:
    print(f"\n[DRY-RUN] Aplicaria: retryOnFail=True, maxTries={MAX_TRIES}, waitBetweenTries={WAIT_MS}")
    sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_retry.json", "w"), ensure_ascii=False, indent=2)
for n in alvos:
    n["retryOnFail"] = True
    n["maxTries"] = MAX_TRIES
    n["waitBetweenTries"] = WAIT_MS

clean_settings = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"], settings=clean_settings)
print(f"\nDEPLOYADO em {len(alvos)} nós: maxTries={MAX_TRIES}, wait={WAIT_MS}ms. Backup salvo.")
