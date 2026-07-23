# scripts/h_03_trigger.py
# Task 3 (gatilho): (1) revisao_meta checa "afirmativo" pela MENSAGEM ATUAL (normalize_phone),
# nao pelo historico; (2) bypass: no caminho em_onboarding, se estado=aguardando_confirmacao,
# a mensagem vai direto pra revisao (que ativa se confirmou / re-pergunta se nao).
#   python3 h_03_trigger.py          -> dry-run (+ syntax)
#   python3 h_03_trigger.py deploy   -> aplica (backup antes)
import json, re, subprocess, sys, n8n_api, config
WF="fBUin1UPt5xJEp6g"; DEPLOY=len(sys.argv)>1 and sys.argv[1]=="deploy"
wf=n8n_api.get_workflow(WF); N={n['name']:n for n in wf['nodes']}; C=wf['connections']; PG=config.POSTGRES_CRED

# (1) revisao_meta: _lt vem da mensagem atual
jc=N['revisao_meta']['parameters']['jsCode']
new_lt="let _lt=''; try{ _lt=String($('normalize_phone').first().json.mensagem_texto||'').toLowerCase(); }catch(e){}"
jc2=re.sub(r"const _lt=String\(_lu\?.*?toLowerCase\(\);", new_lt, jc, count=1, flags=re.S)
if jc2==jc and "mensagem_texto||'').toLowerCase()" not in jc:
    print("ABORTAR: não achei a linha _lt pra substituir"); sys.exit(1)
N['revisao_meta']['parameters']['jsCode']=jc2

# (2) bypass no em_onboarding: load_estado_onb -> if_aguardando -> [true] trigger_revisao / [false] build_onboarding_body
if 'if_aguardando' not in N:
    pos=N['build_onboarding_body']['position']
    le={"id":"load_estado_onb","name":"load_estado_onb","type":"n8n-nodes-base.postgres","typeVersion":2.6,
        "position":[pos[0]-360,pos[1]],"alwaysOutputData":True,
        "parameters":{"operation":"executeQuery","query":
          "SELECT estado_json->>'etapa_atual' AS etapa FROM auto_ads.conversas WHERE telefone = '{{ $('classify_status').first().json.cliente.telefone }}' LIMIT 1"},
        "credentials":{"postgres":PG}}
    ifa={"id":"if_aguardando","name":"if_aguardando","type":"n8n-nodes-base.if","typeVersion":1,
         "position":[pos[0]-180,pos[1]],
         "parameters":{"conditions":{"string":[{"value1":"={{ $json.etapa }}","value2":"aguardando_confirmacao"}]}}}
    wf['nodes'] += [le,ifa]
    # switch_status[2] (em_onboarding) atualmente -> build_onboarding_body ; passa a -> load_estado_onb
    for br in C.get('switch_status',{}).get('main',[]):
        for c in (br or []):
            if c['node']=='build_onboarding_body': c['node']='load_estado_onb'
    C['load_estado_onb']={"main":[[{"node":"if_aguardando","type":"main","index":0}]]}
    C['if_aguardando']={"main":[
        [{"node":"trigger_revisao","type":"main","index":0}],       # true: aguardando -> revisao
        [{"node":"build_onboarding_body","type":"main","index":0}]]} # false: agente normal

out=N['revisao_meta']['parameters']['jsCode']
open("/tmp/_h03.js","w").write("async function _w(){\n"+out+"\n}\n")
r=subprocess.run(["node","--check","/tmp/_h03.js"],capture_output=True,text=True)
print("SYNTAX:", "OK" if r.returncode==0 else "FALHOU")
if r.returncode: print(r.stderr[:800]); sys.exit(1)
print("_lt usa mensagem atual?", "mensagem_texto||'').toLowerCase()" in out)
print("nós bypass:", [n['name'] for n in wf['nodes'] if n['name'] in ('load_estado_onb','if_aguardando')])
if not DEPLOY: print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_trigger.json","w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C, settings={"executionOrder": wf.get('settings',{}).get('executionOrder','v1')})
print("DEPLOYADO.")
