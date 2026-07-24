# scripts/g_13_tutorial_v2.py
# Reescreve o TUTORIAL nos DOIS lugares onde ele vive (a divergencia entre copias
# ja nos mordeu no caminho de midia):
#   1) send_tutorial_act  -> mensagem enviada na ativacao (jsonBody do httpRequest)
#   2) build_agente_body  -> bloco entre <<< e >>> no prompt (resposta a "tutorial")
# Corrige: campos obrigatorios que faltavam (metragem/comodos/diferencial),
# a promessa falsa de "fotos/book" (regra e 1 foto OU 1 video), a faixa de verba
# (R$10-R$100/dia, nao "comeca em R$30"), e os comandos que nao existem
# ("listar" sozinho) ou estavam descritos errado ("cancelar" != encerrar).
#   python3 g_13_tutorial_v2.py          -> dry-run
#   python3 g_13_tutorial_v2.py deploy   -> aplica (backup antes)
import json, re, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

NOVO = """📱 *Como usar o Auto Ads*

*1) Pra subir um anúncio*, me manda numa mensagem só:
• *Tipo* (apê, casa, sobrado, lote…) e *valor*
• *Metragem* e *quantos cômodos* (quartos/suítes/vagas)
• *Bairro + cidade*
• *Diferencial* — o que esse imóvel tem que os outros não têm
• *Objetivo*: morar, investir ou veraneio
• *Verba por dia* (de R$10 a R$100)

Ex: _"Apê de R$ 650 mil no Batel, Curitiba, 78m², 2 quartos com 1 suíte e 1 vaga. Diferencial: sacada com churrasqueira e 200m do metrô. Pra investidor, R$40 por dia."_

Faltou algo, eu te pergunto. Mas sem *diferencial, metragem e cômodos* eu não subo — é o que faz o anúncio render.

*2) O criativo:* me manda *1 foto OU 1 vídeo* — um só. Cada anúncio roda com uma peça e um imóvel; não existe carrossel aqui. Se mandar várias, eu peço pra você escolher a melhor.

*3) Eu te mostro o resumo completo* — nome da campanha, público, faixa etária, região, verba e qual criativo vai. Você confere e responde *CONFIRMADO*. Só aí sobe. Te aviso quando estiver no ar (a Meta leva de minutos a algumas horas pra aprovar).

*Comandos do dia a dia:*
• *status* — como estão seus anúncios
• *pausar* — pausa um anúncio
• *reativar* — religa um pausado
• *mudar a verba pra R$X por dia*
• *mudar o público* ou *mudar a região*
• *encerrar* — finaliza um anúncio de vez
• *nova campanha* — começa outro imóvel do zero

💡 Um imóvel por campanha. Quer anunciar 3 imóveis? São 3 campanhas — manda *nova campanha* pra cada uma.

Dúvida pontual é só perguntar. Pra ver tudo de novo, digita *tutorial*. 💬"""

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
mudou = []

# ---------- 1) send_tutorial_act (jsonBody) ----------
jb = N["send_tutorial_act"]["parameters"]["jsonBody"]
m = re.search(r'("body": ")(.*?)(", "preview_url")', jb, re.S)
if not m:
    print("ABORTAR: nao achei o campo body no send_tutorial_act"); sys.exit(1)
novo_esc = json.dumps(NOVO, ensure_ascii=False)[1:-1]
jb_new = jb[:m.start(2)] + novo_esc + jb[m.end(2):]
# valida que continua sendo JSON valido depois do prefixo "=" da expressao n8n
try:
    json.loads(jb_new[1:] if jb_new.startswith("=") else jb_new)
    print("[1] send_tutorial_act: JSON valido apos troca ✅")
except Exception as e:
    print("ABORTAR: JSON invalido:", e); sys.exit(1)
mudou.append(("send_tutorial_act", len(m.group(2)), len(novo_esc)))

# ---------- 2) build_agente_body (bloco entre <<< e >>>) ----------
jc = N["build_agente_body"]["parameters"]["jsCode"]
ini, fim = jc.find("<<<\\n"), jc.find("\\n>>>")
if ini < 0 or fim < 0 or fim < ini:
    print("ABORTAR: nao achei os marcadores <<< >>> no prompt"); sys.exit(1)
inline = NOVO.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
jc_new = jc[:ini + 5] + inline + jc[fim:]
open("/tmp/_g13.js", "w").write("async function _w(){\n" + jc_new + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g13.js"], capture_output=True, text=True)
print("[2] build_agente_body: syntax", "OK ✅" if r.returncode == 0 else "FALHOU ❌")
if r.returncode:
    print(r.stderr[:600]); sys.exit(1)
mudou.append(("build_agente_body", fim - ini, len(inline)))

for nome, antes, depois in mudou:
    print(f"    {nome:<22} {antes} -> {depois} chars")

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_tutorial_v2.json", "w"), ensure_ascii=False, indent=2)
N["send_tutorial_act"]["parameters"]["jsonBody"] = jb_new
N["build_agente_body"]["parameters"]["jsCode"] = jc_new
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("\nDEPLOYADO nos dois lugares. Backup: n8n_workflow/backup_main_pre_tutorial_v2.json")
