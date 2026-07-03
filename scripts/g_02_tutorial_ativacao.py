# scripts/g_02_tutorial_ativacao.py
# Adiciona o no send_tutorial_act (clone do send_ativacao_msg) encadeado DEPOIS do
# send_ativacao_msg, mandando o texto fixo do tutorial na ativacao do cliente.
#   python3 g_02_tutorial_ativacao.py          -> dry-run (monta + preview, sem deploy)
#   python3 g_02_tutorial_ativacao.py deploy    -> aplica (backup antes)
import json, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

TUT = ("📱 *Como usar o Auto Ads*\n\n"
"*Pra criar um anúncio*, me manda numa mensagem:\n"
"• *Tipo* (apê, casa, sobrado, lote…)\n"
"• *Valor*\n"
"• *Bairro + cidade*\n"
"• *Objetivo*: morar, investir ou veraneio\n\n"
"Ex: _\"Apartamento de R$ 650 mil no Batel, Curitiba, pra investidor.\"_\n"
"Faltou algo, eu te pergunto. Pode mandar *fotos/book* junto.\n\n"
"*Depois:* eu confirmo o público e a verba (começa em R$30/dia) → você diz *\"confirma\"* → o anúncio sobe. Te aviso quando estiver no ar.\n\n"
"*Comandos do dia a dia:*\n"
"• *status* — como estão seus anúncios\n"
"• *pausar* (diz qual) — pausa um anúncio\n"
"• *ativar* (diz qual) — religa um pausado\n"
"• *muda a verba pra R$X/dia* — altera o investimento diário\n"
"• *listar* — ver todos os seus anúncios\n"
"• *cancelar* (diz qual) — encerra um anúncio\n\n"
"💡 A verba começa no piso seguro (R$30/dia) — você aumenta quando quiser. A Meta leva de minutos a algumas horas pra aprovar.\n\n"
"Qualquer dúvida, é só me chamar ou digitar *tutorial*. 💬")

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
C = wf["connections"]

if any(n["name"] == "send_tutorial_act" for n in wf["nodes"]):
    print("send_tutorial_act JÁ existe — nada a fazer."); sys.exit(0)

base = N["send_ativacao_msg"]
send_tut = json.loads(json.dumps(base))   # clona: mesma cred/headers/typeVersion/url
send_tut["id"] = "send_tutorial_act"
send_tut["name"] = "send_tutorial_act"
send_tut["position"] = [base["position"][0] + 240, base["position"][1] + 140]
send_tut["parameters"]["jsonBody"] = (
    '={\n'
    '  "messaging_product": "whatsapp",\n'
    '  "to": "{{ $(\'revisao_meta\').first().json.telefone }}",\n'
    '  "type": "text",\n'
    '  "text": { "body": ' + json.dumps(TUT, ensure_ascii=False) + ', "preview_url": true }\n'
    '}'
)

# valida que o jsonBody (fora a parte {{ }}) é JSON coerente — checa o bloco text
preview = send_tut["parameters"]["jsonBody"]
print("--- jsonBody do send_tutorial_act (preview) ---")
print(preview[:400], "...")
print("URL:", send_tut["parameters"].get("url"))
print("tem credentials clonadas?", "credentials" in send_tut)

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado.]"); sys.exit(0)

# backup + adiciona nó + fio + deploy
json.dump(wf, open("../n8n_workflow/backup_main_pre_tutorial_ativacao.json", "w"), ensure_ascii=False, indent=2)
wf["nodes"].append(send_tut)
C.setdefault("send_ativacao_msg", {"main": [[]]})
if not C["send_ativacao_msg"].get("main"):
    C["send_ativacao_msg"]["main"] = [[]]
if not C["send_ativacao_msg"]["main"]:
    C["send_ativacao_msg"]["main"].append([])
C["send_ativacao_msg"]["main"][0].append({"node": "send_tutorial_act", "type": "main", "index": 0})

clean_settings = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=C, settings=clean_settings)
print("\nDEPLOYADO. send_tutorial_act encadeado após send_ativacao_msg. Backup salvo.")
