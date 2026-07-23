# scripts/g_09_um_por_vez.py
# Adiciona a regra "UM POR VEZ" no prompt vivo do agente (build_agente_body):
# quando o cliente manda varias fotos ou varios imoveis de uma vez, explicar de forma
# clara e amigavel que sobe 1 campanha por vez, 1 imovel por vez, 1 criativo (foto OU video).
#   python3 g_09_um_por_vez.py          -> dry-run (+ syntax check)
#   python3 g_09_um_por_vez.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
ANCHOR = "Bloco 5.1 — Verificação do criativo"

BLOCO = '''Bloco 5.1B — UM POR VEZ (regra dura)
Cada campanha = UM imóvel + UM criativo (1 foto OU 1 vídeo). NÃO existe carrossel, nem juntar várias fotos num anúncio só. NUNCA prometa isso.
- Se o cliente mandar VÁRIAS FOTOS de uma vez: explique de forma amigável que cada anúncio roda com 1 foto ou 1 vídeo (o que para o scroll e traz mais contato) e peça pra ele escolher qual usar neste anúncio. Ex de tom: "Cada anúncio roda com 1 foto ou 1 vídeo — a que mostra melhor o imóvel. Me diz qual dessas você quer usar nesse aqui que eu sigo com ela. 🙂"
- Se o cliente mandar VÁRIOS IMÓVEIS ou várias descrições ao mesmo tempo: explique que você sobe uma campanha por vez, um imóvel por vez (assim cada anúncio fica focado e performa melhor). Peça os dados de UM imóvel + a foto/vídeo dele; quando esse subir, faz o próximo. Ex de tom: "Eu subo uma campanha por vez, um imóvel por vez — assim cada anúncio fica focado e rende mais. Bora começar por um: me manda os dados de um imóvel (tipo, valor, metragem, cômodos, bairro, objetivo, diferencial, verba) + a foto ou vídeo dele. Quando esse subir, a gente faz o próximo. 🚀"
Tom sempre amigável e explicando o porquê (foco = anúncio mais forte), nunca robótico.

'''

def to_js(s):
    return json.dumps(s, ensure_ascii=True)[1:-1]

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
jc = N["build_agente_body"]["parameters"]["jsCode"]

a = to_js(ANCHOR)
cnt = jc.count(a)
if cnt != 1:
    print(f"ABORTAR: âncora apareceu {cnt}x"); sys.exit(1)

new_jc = jc.replace(a, to_js(BLOCO) + a, 1)

open("/tmp/_g09.js", "w").write("async function _w(){\n" + new_jc + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g09.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode:
    print(r.stderr[:800]); sys.exit(1)
print("len:", len(jc), "->", len(new_jc), "(delta", len(new_jc) - len(jc), ")")

if not DEPLOY:
    print("[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_umporvez.json", "w"), ensure_ascii=False, indent=2)
N["build_agente_body"]["parameters"]["jsCode"] = new_jc
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO.")
