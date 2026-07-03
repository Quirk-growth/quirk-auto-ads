# scripts/g_01_agente_tutorial.py
# Injeta a REGRA TUTORIAL/AJUDA no prompt estável (estavelBlock) do nó build_agente_body
# do workflow principal. Dry-run por padrão; passe "deploy" pra aplicar.
#   python3 g_01_agente_tutorial.py          -> dry-run (build + syntax check + preview)
#   python3 g_01_agente_tutorial.py deploy   -> aplica (com backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
ANCHOR = "TEXTO BASE COMPLETO (v3.3)"   # ASCII, sem em-dash

RAW = '''REGRA TUTORIAL / AJUDA: se o cliente enviar apenas "tutorial" (ou pedir claramente o tutorial, "como usar", "me ensina a usar"), responda EXATAMENTE com o texto entre <<< e >>> abaixo, sem escrever nada antes nem depois:
<<<
📱 *Como usar o Auto Ads*

*Pra criar um anúncio*, me manda numa mensagem:
• *Tipo* (apê, casa, sobrado, lote…)
• *Valor*
• *Bairro + cidade*
• *Objetivo*: morar, investir ou veraneio

Ex: _"Apartamento de R$ 650 mil no Batel, Curitiba, pra investidor."_
Faltou algo, eu te pergunto. Pode mandar *fotos/book* junto.

*Depois:* eu confirmo o público e a verba (começa em R$30/dia) → você diz *"confirma"* → o anúncio sobe. Te aviso quando estiver no ar.

*Comandos do dia a dia:*
• *status* — como estão seus anúncios
• *pausar* (diz qual) — pausa um anúncio
• *ativar* (diz qual) — religa um pausado
• *muda a verba pra R$X/dia* — altera o investimento diário
• *listar* — ver todos os seus anúncios
• *cancelar* (diz qual) — encerra um anúncio

💡 A verba começa no piso seguro (R$30/dia) — você aumenta quando quiser. A Meta leva de minutos a algumas horas pra aprovar.

Qualquer dúvida, é só me chamar ou digitar *tutorial*. 💬
>>>
Se a dúvida for PONTUAL (ex.: "como pauso?", "não entendi a verba"), responda curto e direto e termine com: "Se quiser ver tudo, é só digitar *tutorial*."
'''

def to_js(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
jc = N["build_agente_body"]["parameters"]["jsCode"]

cnt = jc.count(ANCHOR)
if cnt != 1:
    print(f"ABORTAR: âncora '{ANCHOR}' apareceu {cnt}x"); sys.exit(1)

inj = to_js(RAW)
new_jc = jc.replace(ANCHOR, ANCHOR + "\\n \\n" + inj + "\\n \\n", 1)

# checagem de sintaxe: envelopa em função async e roda node --check
open("/tmp/_agentcheck.js", "w").write("async function _wrap(){\n" + new_jc + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_agentcheck.js"], capture_output=True, text=True)
print("SYNTAX CHECK:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode != 0:
    print(r.stderr[:1000]); sys.exit(1)
print("len antes:", len(jc), "| depois:", len(new_jc), "| delta:", len(new_jc) - len(jc))

i = new_jc.find("REGRA TUTORIAL")
print("\n--- preview do trecho injetado (no jsCode) ---")
print(new_jc[i:i + 160])
print("--- fim preview ---")

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado. Rode com 'deploy' pra aplicar.]")
    sys.exit(0)

# backup + deploy
json.dump(wf, open("../n8n_workflow/backup_main_pre_tutorial.json", "w"), ensure_ascii=False, indent=2)
N["build_agente_body"]["parameters"]["jsCode"] = new_jc
# o PUT publico do n8n so aceita 'executionOrder' (recusa callerPolicy/availableInMCP/binaryMode).
# callerPolicy default == valor atual; binaryMode e governado pela config da instancia. Backup salvo acima.
clean_settings = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"], settings=clean_settings)
print("\nDEPLOYADO. Backup em n8n_workflow/backup_main_pre_tutorial.json | settings enviado:", clean_settings)
