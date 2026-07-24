# scripts/g_11_gateway_canon9.py
# Parte A: o gateway (parse_payment) canonicaliza o telefone vindo do Asaas para a forma
# BR canonica (55 + DDD + 9 + 8) ANTES de gravar, fechando o furo da escrita.
#   python3 g_11_gateway_canon9.py          -> dry-run (+ syntax)
#   python3 g_11_gateway_canon9.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "2ZnZqb4wFous4uEs"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

ANCHOR = "if (telefone.length >= 10 && !telefone.startsWith('55')) telefone = '55' + telefone;"
ADD = ("\n// Canonicaliza BR: 55 + DDD + [9] + 8 digitos -> SEMPRE com o 9 "
       "(bate com a entrada e com a CHECK do banco)\n"
       "if (telefone.startsWith('55')) { const _r = telefone.slice(2); "
       "if (_r.length === 10) telefone = '55' + _r.slice(0, 2) + '9' + _r.slice(2); }")

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
jc = N["parse_payment"]["parameters"]["jsCode"]

if "Canonicaliza BR" in jc:
    print("já canonicaliza — nada a fazer."); sys.exit(0)

cnt = jc.count(ANCHOR)
print(f"âncora encontrada {cnt}x")
if cnt != 1:
    print("ABORTAR: esperava exatamente 1"); sys.exit(1)

new_jc = jc.replace(ANCHOR, ANCHOR + ADD, 1)

open("/tmp/_g11.js", "w").write("async function _w(){\n" + new_jc + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g11.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode:
    print(r.stderr[:800]); sys.exit(1)

if not DEPLOY:
    print("[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_gateway_pre_canon9.json", "w"), ensure_ascii=False, indent=2)
N["parse_payment"]["parameters"]["jsCode"] = new_jc
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO: gateway canonicaliza o telefone na escrita.")
