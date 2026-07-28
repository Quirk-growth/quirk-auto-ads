# scripts/g_15_status_legivel.py
# Parte 4: o relatorio de status mostra "no ar / pausada / encerrada" em vez do
# status cru do banco (CREATED_ACTIVE etc).
#   python3 g_15_status_legivel.py          -> dry-run (+ node --check)
#   python3 g_15_status_legivel.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

ANCHOR = """const p = d.periodos;
const linhas = [
  '📊 ' + d.campanha_nome,
  'Status no Meta: ' + d.status_atual,"""

NEW = """const MAPA_STATUS = { CREATED_ACTIVE:'🟢 No ar', ACTIVE:'🟢 No ar', CREATED_PAUSED:'⏸️ Pausada', PAUSED:'⏸️ Pausada', ARCHIVED:'📁 Encerrada', PARTIAL_FAIL:'⚠️ Subiu com pendência — me chama' };
const status_legivel = MAPA_STATUS[d.status_atual] || d.status_atual;
const p = d.periodos;
const linhas = [
  '📊 ' + d.campanha_nome,
  'Status: ' + status_legivel,"""

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
jc = N["format_status_response"]["parameters"]["jsCode"]

cnt = jc.count(ANCHOR)
print("ancora encontrada", cnt, "x")
if cnt != 1:
    print("ABORTAR: esperava 1"); sys.exit(1)

new_jc = jc.replace(ANCHOR, NEW, 1)
open("/tmp/_g15.js", "w").write("function $(){return{first:()=>({json:{periodos:{}}})}}\nfunction _w(){\n" + new_jc + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g15.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode:
    print(r.stderr[:600]); sys.exit(1)

if not DEPLOY:
    print("[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_status_legivel.json", "w"), ensure_ascii=False, indent=2)
N["format_status_response"]["parameters"]["jsCode"] = new_jc
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO. Backup: n8n_workflow/backup_main_pre_status_legivel.json")
