# scripts/g_19_blinda_lookups_vazios.py
# Blindagem do padrao "no vazio estanca a cadeia em silencio" — 2 riscos reais:
#   A) list_campanhas: cliente com 0 campanhas -> init_gestao nao dispara -> morte muda.
#      Fix: alwaysOutputData=true (emite 1 item vazio) + init_gestao filtra o vazio
#           -> cai no ramo sem_campanhas ("voce nao tem campanhas").
#   B) load_meta_token / _criacao / _revisao: se a chave sumir do config, 0 linhas ->
#      estanca tudo. Fix: alwaysOutputData=true -> valor vem undefined -> a chamada Meta
#      falha e agora e classificada/mensageada (nao morre em silencio).
#
#   python3 g_19_blinda_lookups_vazios.py          -> dry-run (+ node --check)
#   python3 g_19_blinda_lookups_vazios.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

ALWAYS_ON = ["list_campanhas", "load_meta_token", "load_meta_token_criacao", "load_meta_token_revisao"]

# init_gestao: filtra o item-sentinela vazio antes do length===0
IG_ANCHOR = "const linhas = $('list_campanhas').all().map(r => r.json);"
IG_NEW = "const linhas = $('list_campanhas').all().map(r => r.json).filter(r => r && r.campanha_id_db != null);"

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

# --- A/B: liga alwaysOutputData ---
mudou = []
for nome in ALWAYS_ON:
    if N[nome].get("alwaysOutputData") is True:
        print(f"  {nome}: já tinha alwaysOutputData")
    else:
        N[nome]["alwaysOutputData"] = True
        mudou.append(nome)
print("alwaysOutputData ligado em:", mudou or "(nenhum — já estavam)")

# --- init_gestao filtro ---
jc = N["init_gestao"]["parameters"]["jsCode"]
c = jc.count(IG_ANCHOR)
if c != 1 and "filter(r => r && r.campanha_id_db" not in jc:
    print(f"ABORTAR init_gestao: âncora {c}x (esperava 1)"); sys.exit(1)
if "filter(r => r && r.campanha_id_db" in jc:
    print("  init_gestao: já filtra o vazio")
    jc_new = jc
else:
    jc_new = jc.replace(IG_ANCHOR, IG_NEW, 1)
    open("/tmp/_g19.js","w").write("function $(){return{all:()=>[],first:()=>({json:{}})}}\nfunction _w(){\n"+jc_new+"\n}\n")
    r = subprocess.run(["node","--check","/tmp/_g19.js"], capture_output=True, text=True)
    print("init_gestao syntax:", "OK" if r.returncode==0 else "FALHOU")
    if r.returncode: print(r.stderr[:400]); sys.exit(1)

if not DEPLOY:
    print("\n[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_blinda_lookups.json","w"), ensure_ascii=False, indent=2)
N["init_gestao"]["parameters"]["jsCode"] = jc_new
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("\nDEPLOYADO. Backup: n8n_workflow/backup_main_pre_blinda_lookups.json")
