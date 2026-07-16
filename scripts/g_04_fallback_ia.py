# scripts/g_04_fallback_ia.py
# Fallback de IA: se os nos da Anthropic esgotarem as 5 tentativas (Overloaded 529),
# em vez de a execucao morrer em silencio, o cliente recebe um aviso pedindo pra repetir.
# Implementacao: onError=continueErrorOutput nos 4 nos de IA + saida de erro (main[1])
# ligada a um unico no send_fallback_ia (clone do send_resposta).
#   python3 g_04_fallback_ia.py          -> dry-run
#   python3 g_04_fallback_ia.py deploy   -> aplica (backup antes)
import json, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
ALVOS = ["agente_principal", "extrator", "extrator_partial", "onboarding_agent"]
MSG = "Tive uma instabilidade momentânea aqui 😅\n\nPode repetir sua última mensagem, por favor?"

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
C = wf["connections"]

if "send_fallback_ia" in N:
    print("send_fallback_ia JÁ existe — nada a fazer."); sys.exit(0)

base = N["send_resposta"]
fb = json.loads(json.dumps(base))   # clona: credencial, url, typeVersion
fb["id"] = "send_fallback_ia"; fb["name"] = "send_fallback_ia"
fb["position"] = [base["position"][0], base["position"][1] + 260]
fb.pop("retryOnFail", None); fb.pop("maxTries", None); fb.pop("waitBetweenTries", None)
fb["parameters"]["jsonBody"] = (
    '={\n'
    '  "messaging_product": "whatsapp",\n'
    '  "to": "{{ $(\'normalize_phone\').first().json.telefone_normalizado }}",\n'
    '  "type": "text",\n'
    '  "text": { "body": ' + json.dumps(MSG, ensure_ascii=False) + ', "preview_url": false }\n'
    '}'
)

print("--- send_fallback_ia ---")
print("url:", fb["parameters"].get("url"), "| credentials?", "credentials" in fb)
print("body:", fb["parameters"]["jsonBody"][:220], "...\n")

plano = []
for name in ALVOS:
    n = N[name]
    outs = C.get(name, {}).get("main", [])
    plano.append(f"  {name}: onError -> continueErrorOutput | main[1] (erro) -> send_fallback_ia (main[0] atual preservado: {[c['node'] for c in (outs[0] or [])] if outs else []})")
print("\n".join(plano))

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado.]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_fallback.json", "w"), ensure_ascii=False, indent=2)
wf["nodes"].append(fb)
for name in ALVOS:
    N[name]["onError"] = "continueErrorOutput"
    C.setdefault(name, {"main": [[]]})
    m = C[name].setdefault("main", [[]])
    while len(m) < 1: m.append([])
    if len(m) < 2: m.append([])          # main[1] = saída de erro
    m[1] = [{"node": "send_fallback_ia", "type": "main", "index": 0}]

clean_settings = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=C, settings=clean_settings)
print("\nDEPLOYADO: fallback ligado nas saídas de erro dos 4 nós de IA. Backup salvo.")
