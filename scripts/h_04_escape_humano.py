# scripts/h_04_escape_humano.py
# Task 4: escape pra humano. Conta falhas de revisao (estado_json.revisao_falhas);
# ao chegar a 3: marca travado_onboarding, alerta o Renan e avisa o cliente que o time
# vai olhar (em vez de repetir a mesma pergunta). Reset do contador ao achar candidatos.
import json, sys, n8n_api, config
WF="fBUin1UPt5xJEp6g"; DEPLOY=len(sys.argv)>1 and sys.argv[1]=="deploy"
ALERTA_TEL="5511980838409"  # numero do Renan (operador). Mudar aqui se precisar.
wf=n8n_api.get_workflow(WF); N={n['name']:n for n in wf['nodes']}; C=wf['connections']; PG=config.POSTGRES_CRED

def down(n): return C.get(n,{}).get('main',[[]])

if 'if_escape' not in N:
    pos=N['send_falha_msg']['position']
    tel="{{ $('revisao_meta').first().json.telefone }}"
    # incr_falhas: +1 e retorna o total
    incr={"id":"incr_falhas","name":"incr_falhas","type":"n8n-nodes-base.postgres","typeVersion":2.6,
          "position":[pos[0]-360,pos[1]],
          "parameters":{"operation":"executeQuery","query":
            "UPDATE auto_ads.conversas SET estado_json = jsonb_set(COALESCE(estado_json,'{}'::jsonb),'{revisao_falhas}',"
            "to_jsonb(COALESCE((estado_json->>'revisao_falhas')::int,0)+1)) WHERE telefone='"+tel+"' "
            "RETURNING (estado_json->>'revisao_falhas')::int AS falhas"},"credentials":{"postgres":PG}}
    ife={"id":"if_escape","name":"if_escape","type":"n8n-nodes-base.if","typeVersion":1,
         "position":[pos[0]-180,pos[1]],
         "parameters":{"conditions":{"number":[{"value1":"={{ $json.falhas }}","operation":"largerEqual","value2":3}]}}}
    # marca travado
    mark={"id":"mark_travado","name":"mark_travado","type":"n8n-nodes-base.postgres","typeVersion":2.6,
          "position":[pos[0]-40,pos[1]-120],
          "parameters":{"operation":"executeQuery","query":
            "UPDATE auto_ads.conversas SET estado_json = jsonb_set(COALESCE(estado_json,'{}'::jsonb),'{travado_onboarding}','true'::jsonb) WHERE telefone='"+tel+"'"},
          "credentials":{"postgres":PG}}
    # alerta pro Renan (clone do send_falha_msg, to fixo + corpo de alerta)
    al=json.loads(json.dumps(N['send_falha_msg'])); al['id']='send_alerta_humano'; al['name']='send_alerta_humano'; al['position']=[pos[0]+160,pos[1]-120]
    al['parameters']['jsonBody']=('={\n  "messaging_product": "whatsapp",\n  "to": "'+ALERTA_TEL+'",\n  "type": "text",\n'
      '  "text": { "body": '+json.dumps("⚠️ Cliente preso no onboarding — não detectei os ativos após 3 tentativas. Telefone: ", ensure_ascii=False)[:-1]+' + {{ JSON.stringify($(\'revisao_meta\').first().json.telefone) }} + ". Dá uma olhada no painel." }\n}')
    # avisa o cliente (clone, to=cliente)
    cl=json.loads(json.dumps(N['send_falha_msg'])); cl['id']='send_time_cliente'; cl['name']='send_time_cliente'; cl['position']=[pos[0]+340,pos[1]-120]
    cl['parameters']['jsonBody']=('={\n  "messaging_product": "whatsapp",\n  "to": "'+tel+'",\n  "type": "text",\n'
      '  "text": { "body": '+json.dumps("Deixa que eu peço pro nosso time dar uma olhada na tua conexão e já te retorno, tá? 🙌", ensure_ascii=False)+' }\n}')
    wf['nodes'] += [incr,ife,mark,al,cl]
    # rewire: update_cliente_falhou -> incr_falhas -> if_escape ; [false]->send_falha_msg ; [true]->mark->alerta->cliente
    C['update_cliente_falhou']={"main":[[{"node":"incr_falhas","type":"main","index":0}]]}
    C['incr_falhas']={"main":[[{"node":"if_escape","type":"main","index":0}]]}
    C['if_escape']={"main":[
        [{"node":"mark_travado","type":"main","index":0}],       # true (>=3)
        [{"node":"send_falha_msg","type":"main","index":0}]]}     # false
    C['mark_travado']={"main":[[{"node":"send_alerta_humano","type":"main","index":0}]]}
    C['send_alerta_humano']={"main":[[{"node":"send_time_cliente","type":"main","index":0}]]}
    # reset do contador ao achar candidatos: acrescenta revisao_falhas=0 no persist_candidatos
    pc=N['persist_candidatos']['parameters']['query']
    if 'revisao_falhas' not in pc:
        pc2=pc.replace("SET estado_json = jsonb_set(", "SET estado_json = jsonb_set(jsonb_set(",1)
        pc2=pc2.replace("WHERE telefone", "'{revisao_falhas}','0'::jsonb) WHERE telefone",1)
        N['persist_candidatos']['parameters']['query']=pc2

print("nós escape:", [n['name'] for n in wf['nodes'] if n['name'] in ('incr_falhas','if_escape','mark_travado','send_alerta_humano','send_time_cliente')])
print("persist_candidatos reseta falhas?", 'revisao_falhas' in N['persist_candidatos']['parameters']['query'])
if not DEPLOY: print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_escape.json","w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C, settings={"executionOrder": wf.get('settings',{}).get('executionOrder','v1')})
print("DEPLOYADO.")
