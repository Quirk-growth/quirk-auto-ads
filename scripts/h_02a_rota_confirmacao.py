# scripts/h_02a_rota_confirmacao.py
# Task 2a: quando revisao_meta retorna precisa_confirmar, gravar candidatos no estado
# (etapa=aguardando_confirmacao) e mandar a mensagem "confirma?" — em vez de cair na
# branch de falha. Insere if_precisa_confirmar ANTES do if_revisao_ok.
#   python3 h_02a_rota_confirmacao.py          -> dry-run
#   python3 h_02a_rota_confirmacao.py deploy   -> aplica (backup antes)
import json, sys, n8n_api, config
WF="fBUin1UPt5xJEp6g"; DEPLOY=len(sys.argv)>1 and sys.argv[1]=="deploy"
wf=n8n_api.get_workflow(WF); N={n['name']:n for n in wf['nodes']}; C=wf['connections']; PG=config.POSTGRES_CRED
pos=N['if_revisao_ok']['position']

if 'if_precisa_confirmar' not in N:
    # 1) IF: precisa_confirmar === true
    ifn={"id":"if_precisa_confirmar","name":"if_precisa_confirmar","type":"n8n-nodes-base.if","typeVersion":1,
         "position":[pos[0]-180,pos[1]],
         "parameters":{"conditions":{"boolean":[{"value1":"={{ $json.precisa_confirmar === true }}","value2":True}]}}}
    # 2) Postgres: grava candidatos + etapa aguardando_confirmacao
    cand=("{\"ad_id\":\"'||''||'\"}")  # placeholder; a query real usa expressao abaixo
    q=("UPDATE auto_ads.conversas SET estado_json = jsonb_set(jsonb_set(COALESCE(estado_json,'{}'::jsonb),"
       "'{etapa_atual}','\"aguardando_confirmacao\"'::jsonb),'{candidatos}',"
       "'{{ JSON.stringify({ad_id:$('revisao_meta').first().json.ad_candidate.id,ad_name:$('revisao_meta').first().json.ad_candidate.name,page_id:$('revisao_meta').first().json.page_candidate.id,page_name:$('revisao_meta').first().json.page_candidate.name}).replace(/'/g,\"''\") }}'::jsonb) "
       "WHERE telefone = '{{ $('revisao_meta').first().json.telefone }}'")
    persist={"id":"persist_candidatos","name":"persist_candidatos","type":"n8n-nodes-base.postgres","typeVersion":2.6,
             "position":[pos[0]+40,pos[1]+160],"parameters":{"operation":"executeQuery","query":q},"credentials":{"postgres":PG}}
    # 3) send_confirma_msg = clone do send_falha_msg (mesma cred/refs a $('revisao_meta'))
    sc=json.loads(json.dumps(N['send_falha_msg']))
    sc['id']='send_confirma_msg'; sc['name']='send_confirma_msg'; sc['position']=[pos[0]+240,pos[1]+160]
    wf['nodes'] += [ifn,persist,sc]
    # rewire: revisao_meta -> if_precisa_confirmar ; [false]-> if_revisao_ok ; [true]-> persist -> send_confirma
    C['revisao_meta']={"main":[[{"node":"if_precisa_confirmar","type":"main","index":0}]]}
    C['if_precisa_confirmar']={"main":[
        [{"node":"persist_candidatos","type":"main","index":0}],      # true
        [{"node":"if_revisao_ok","type":"main","index":0}] ]}          # false
    C['persist_candidatos']={"main":[[{"node":"send_confirma_msg","type":"main","index":0}]]}

print("nós novos:", [n['name'] for n in wf['nodes'] if n['name'] in ('if_precisa_confirmar','persist_candidatos','send_confirma_msg')])
if not DEPLOY: print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_conf2a.json","w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C, settings={"executionOrder": wf.get('settings',{}).get('executionOrder','v1')})
print("DEPLOYADO.")
