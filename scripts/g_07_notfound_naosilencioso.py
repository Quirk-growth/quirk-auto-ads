# scripts/g_07_notfound_naosilencioso.py
# Fix #2: quando select_cliente nao acha ninguem (numero desconhecido), o no Postgres
# sem itens estancava a cadeia e o fluxo morria em silencio (nem a msg de "nao cadastrado"
# saia). classify_status JA trata cliente vazio como rota='not_found' -> send_not_found;
# so faltava o select_cliente EMITIR um item vazio nesse caso. Fix: alwaysOutputData=True.
# Idempotente.
#   python3 g_07_notfound_naosilencioso.py deploy
import json, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
if len(sys.argv) < 2 or sys.argv[1] != "deploy":
    print("uso: python3 g_07_notfound_naosilencioso.py deploy"); sys.exit(0)

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
json.dump(wf, open("../n8n_workflow/backup_main_pre_notfound.json", "w"), ensure_ascii=False, indent=2)
N["select_cliente"]["alwaysOutputData"] = True
cs = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"], settings=cs)
print("DEPLOYADO: select_cliente.alwaysOutputData=True (numero desconhecido -> send_not_found).")
