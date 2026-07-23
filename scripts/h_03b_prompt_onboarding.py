# scripts/h_03b_prompt_onboarding.py
# Task 3 (prompt): o agente de onboarding para de pedir o ID da Conta de Anuncios;
# passa a pedir so pra avisar quando terminar de compartilhar, e dispara <REVISAO_REQUEST/>
# nisso (a deteccao da conta+pagina e por nome, automatica).
import json, subprocess, sys, n8n_api
WF="fBUin1UPt5xJEp6g"; DEPLOY=len(sys.argv)>1 and sys.argv[1]=="deploy"

REPLACES=[
 ("4. No fim, reportar só 2 dados: Nome da Página + ID da Conta de Anúncios",
  "4. No fim, é só me avisar que terminou (ex: \"já compartilhei tudo\", \"terminei\"). NÃO precisa do ID da Conta de Anúncios — eu detecto sua Conta e Página automaticamente e te peço só pra confirmar o nome."),
 ("Quando os 2 dados (Nome da Página + ID da Conta de Anúncios numérico) já tiverem aparecido na conversa: responde APENAS com a tag <REVISAO_REQUEST/> e mais nada.",
  "Quando o cliente disser que TERMINOU de compartilhar a Conta de Anúncios e a Página com a Quirk (ex: \"já compartilhei tudo\", \"terminei\", \"pode revisar\"): responde APENAS com a tag <REVISAO_REQUEST/> e mais nada. NÃO exija o ID — a detecção é automática."),
]

# build_onboarding_body guarda acentos como UTF-8 literal; aspas internas ficam \"
def esc(s): return s.replace('\\', '\\\\').replace('"', '\\"')

wf=n8n_api.get_workflow(WF); N={n['name']:n for n in wf['nodes']}
jc=N['build_onboarding_body']['parameters']['jsCode']
for i,(old,new) in enumerate(REPLACES,1):
    o=esc(old); c=jc.count(o)
    print(f"[{i}] âncora {c}x — {old[:50]}...")
    if c!=1: print(f"   ABORTAR: esperava 1, achei {c}"); sys.exit(1)
    jc=jc.replace(o,esc(new),1)

open("/tmp/_h03b.js","w").write("async function _w(){\n"+jc+"\n}\n")
r=subprocess.run(["node","--check","/tmp/_h03b.js"],capture_output=True,text=True)
print("SYNTAX:", "OK" if r.returncode==0 else "FALHOU")
if r.returncode: print(r.stderr[:600]); sys.exit(1)
if not DEPLOY: print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_prompt_onb.json","w"), ensure_ascii=False, indent=2)
N['build_onboarding_body']['parameters']['jsCode']=jc
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=wf['connections'], settings={"executionOrder": wf.get('settings',{}).get('executionOrder','v1')})
print("DEPLOYADO.")
