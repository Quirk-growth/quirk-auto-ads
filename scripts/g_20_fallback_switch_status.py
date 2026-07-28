# scripts/g_20_fallback_switch_status.py
# Blindagem do roteador universal: classify_status faz rota = cliente.status (valor cru
# da coluna). switch_status so trata 6 valores e NAO tem fallback -> um cliente com
# status inesperado (ex: editado no banco, 'cancelado', status futuro) e dropado sem
# resposta em TODA mensagem, pra sempre.
# Fix: fallbackOutput='extra' -> nova saida -> send_status_desconhecido (mensagem
# honesta em vez de silencio) -> respond_immediate.
#   python3 g_20_fallback_switch_status.py          -> dry-run
#   python3 g_20_fallback_switch_status.py deploy   -> aplica (backup antes)
import json, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

MSG = ("⚠️ Opa! Tem uma pendência no seu cadastro e não consegui seguir automaticamente. "
       "Já avisei a equipe da Quirk e a gente te responde rapidinho. 🙏")

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
conns = wf["connections"]

if "send_status_desconhecido" in N:
    print("já existe — nada a fazer."); sys.exit(0)

n_rules = len(N["switch_status"]["parameters"]["rules"]["values"])
print(f"switch_status tem {n_rules} regras -> saída extra (fallback) no índice {n_rules}")

# 1) liga fallbackOutput=extra
N["switch_status"]["parameters"].setdefault("options", {})["fallbackOutput"] = "extra"

# 2) novo nó de mensagem
send_node = {
    "parameters": {"method": "POST", "url": "https://graph.facebook.com/v25.0/1320571937797802/messages",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
        "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={\n  \"messaging_product\": \"whatsapp\",\n  \"to\": \"{{ $json.telefone }}\",\n  \"type\": \"text\",\n  \"text\": { \"body\": " + json.dumps(MSG, ensure_ascii=False) + ", \"preview_url\": false }\n}",
        "options": {}},
    "id": "send_status_desconhecido", "name": "send_status_desconhecido",
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1480, 2360],
    "credentials": N["send_gestao_msg"]["credentials"],
}
wf["nodes"].append(send_node)

# 3) wiring: garante que main tenha índice do fallback -> send -> respond_immediate
main = conns.setdefault("switch_status", {}).setdefault("main", [])
while len(main) <= n_rules:
    main.append([])
main[n_rules] = [{"node": "send_status_desconhecido", "type": "main", "index": 0}]
conns["send_status_desconhecido"] = {"main": [[{"node": "respond_immediate", "type": "main", "index": 0}]]}

if not DEPLOY:
    print("[DRY-RUN] criaria send_status_desconhecido; switch_status.main[%d] -> ele -> respond_immediate" % n_rules)
    sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_fallback_status.json", "w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=conns,
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO. Backup: n8n_workflow/backup_main_pre_fallback_status.json")
