# scripts/g_16_gate_subir_denovo.py
# Parte 1a: SUBIR_DENOVO so cria campanha se houver uma pronta pra subir (etapa_atual
# == 'pronta_pra_subir', tipico apos falha de upload). Se ja esta 'ativa' -> bloqueia
# (evita duplicar). Qualquer outra etapa -> pede os dados.
#
# Insere 3 nos SO na saida SUBIR_DENOVO (index 1) do switch_intent:
#   switch_intent[1] -> gate_subir_denovo -> if_pode_subir_denovo
#                         if true  -> build_extrator_body (fluxo normal de criacao)
#                         if false -> send_bloqueio_denovo -> respond_immediate
# A saida CONFIRMAR (index 0) -> build_extrator_body fica INTOCADA.
#
#   python3 g_16_gate_subir_denovo.py          -> dry-run (+ node --check)
#   python3 g_16_gate_subir_denovo.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

GATE_CODE = (
    "const etapa = $('load_estado').first().json.estado?.etapa_atual;\n"
    "const pode = etapa === 'pronta_pra_subir';\n"
    "let motivo = '';\n"
    "if (etapa === 'ativa') motivo = 'Sua última campanha já está no ar 🟢. Pra criar outra, manda *NOVA CAMPANHA*.';\n"
    "else if (!pode) motivo = 'Não tem nenhuma campanha pronta pra subir ainda. Me manda os dados do imóvel que a gente monta. 👍';\n"
    "return [{ json: { pode, motivo, telefone: $('normalize_phone').first().json.telefone_normalizado } }];"
)

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
conns = wf["connections"]

if "gate_subir_denovo" in N:
    print("gate ja existe — nada a fazer."); sys.exit(0)

# checagem sintaxe do gate
open("/tmp/_g16.js","w").write("function $(){return{first:()=>({json:{estado:{},telefone_normalizado:'x'}})}}\nfunction _w(){\n"+GATE_CODE+"\n}\n")
r = subprocess.run(["node","--check","/tmp/_g16.js"], capture_output=True, text=True)
print("SYNTAX gate:", "OK" if r.returncode==0 else "FALHOU")
if r.returncode: print(r.stderr[:500]); sys.exit(1)

# confirma que switch_intent saida[1] aponta hoje pra build_extrator_body
alvo = [c["node"] for c in conns["switch_intent"]["main"][1]]
print("switch_intent[1] (SUBIR_DENOVO) hoje ->", alvo)
if alvo != ["build_extrator_body"]:
    print("ABORTAR: esperava ['build_extrator_body']"); sys.exit(1)

# credencial do WhatsApp (mesma do send_gestao_msg)
cred = N["send_gestao_msg"]["credentials"]

gate = {
    "parameters": {"jsCode": GATE_CODE},
    "id": "gate_subir_denovo", "name": "gate_subir_denovo",
    "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2600, 180],
}
if_gate = {
    "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 1},
        "combinator": "and", "conditions": [{"leftValue": "={{ $json.pode }}", "rightValue": True,
        "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}, "options": {}},
    "id": "if_pode_subir_denovo", "name": "if_pode_subir_denovo",
    "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [2760, 180],
}
send_bloq = {
    "parameters": {"method": "POST", "url": "https://graph.facebook.com/v25.0/1320571937797802/messages",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={\n  \"messaging_product\": \"whatsapp\",\n  \"to\": \"{{ $json.telefone }}\",\n  \"type\": \"text\",\n  \"text\": { \"body\": {{ JSON.stringify($json.motivo) }}, \"preview_url\": true }\n}",
        "options": {}},
    "id": "send_bloqueio_denovo", "name": "send_bloqueio_denovo",
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [2960, 300],
    "credentials": cred,
}
wf["nodes"] += [gate, if_gate, send_bloq]

# rewire
conns["switch_intent"]["main"][1] = [{"node": "gate_subir_denovo", "type": "main", "index": 0}]
conns["gate_subir_denovo"] = {"main": [[{"node": "if_pode_subir_denovo", "type": "main", "index": 0}]]}
# IF: saida 0 = true -> build_extrator_body ; saida 1 = false -> send_bloqueio_denovo
conns["if_pode_subir_denovo"] = {"main": [
    [{"node": "build_extrator_body", "type": "main", "index": 0}],
    [{"node": "send_bloqueio_denovo", "type": "main", "index": 0}],
]}
conns["send_bloqueio_denovo"] = {"main": [[{"node": "respond_immediate", "type": "main", "index": 0}]]}

if not DEPLOY:
    print("[DRY-RUN] nos a criar: gate_subir_denovo, if_pode_subir_denovo, send_bloqueio_denovo")
    print("  switch_intent[1] -> gate ; if.true -> build_extrator_body ; if.false -> send_bloqueio_denovo -> respond_immediate")
    sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_gate_denovo.json","w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=conns,
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO. Backup: n8n_workflow/backup_main_pre_gate_denovo.json")
