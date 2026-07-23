# scripts/h_02b_confirma_ativa.py
# Task 2b: revisao_meta passa a ATIVAR quando estado=aguardando_confirmacao + candidatos
# guardados + ultima msg do cliente afirmativa. Adiciona load_estado_revisao (le candidatos)
# antes do revisao_meta, e prefixa o jsCode com o bloco de confirmacao-ativacao (valida
# acesso aos candidatos + atribui System User + retorna ok:true -> caminho de ativacao existente).
#   python3 h_02b_confirma_ativa.py          -> dry-run (+ syntax)
#   python3 h_02b_confirma_ativa.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api, config
WF="fBUin1UPt5xJEp6g"; DEPLOY=len(sys.argv)>1 and sys.argv[1]=="deploy"
wf=n8n_api.get_workflow(WF); N={n['name']:n for n in wf['nodes']}; C=wf['connections']; PG=config.POSTGRES_CRED

# 1) load_estado_revisao (PG) entre load_assigned_assets e revisao_meta
if 'load_estado_revisao' not in N:
    pos=N['revisao_meta']['position']
    q=("SELECT estado_json->'candidatos' AS candidatos, estado_json->>'etapa_atual' AS etapa "
       "FROM auto_ads.conversas WHERE telefone = '{{ $('classify_status').first().json.cliente.telefone }}' LIMIT 1")
    node={"id":"load_estado_revisao","name":"load_estado_revisao","type":"n8n-nodes-base.postgres","typeVersion":2.6,
          "position":[pos[0]-110,pos[1]-140],"alwaysOutputData":True,
          "parameters":{"operation":"executeQuery","query":q},"credentials":{"postgres":PG}}
    wf['nodes'].append(node)
    # rewire: load_assigned_assets -> load_estado_revisao -> revisao_meta
    prev=[s for s,d in C.items() for br in d.get('main',[]) for c in (br or []) if c['node']=='revisao_meta']
    prev=prev[0] if prev else 'load_assigned_assets'
    for br in C.get(prev,{}).get('main',[]):
        for c in (br or []):
            if c['node']=='revisao_meta': c['node']='load_estado_revisao'
    C['load_estado_revisao']={"main":[[{"node":"revisao_meta","type":"main","index":0}]]}

# 2) prefixo confirma-ativa no revisao_meta
jc=N['revisao_meta']['parameters']['jsCode']
PREFIX = r'''
// === CONFIRMA-ATIVA: se aguardando_confirmacao + candidatos + ultima msg afirmativa -> ativa ===
{
  const _cli=$('classify_status').first().json.cliente; const _tel=_cli.telefone;
  let _hist=[]; try{_hist=JSON.parse($('parse_onboarding_resp').first().json.novo_historico||_cli.historico_onboarding||'[]');}catch(e){try{_hist=JSON.parse(_cli.historico_onboarding||'[]');}catch(e2){_hist=[];}}
  let _etapa='',_cand=null;
  try{ const e=$('load_estado_revisao').first().json; _etapa=e.etapa||''; _cand=(typeof e.candidatos==='string'?JSON.parse(e.candidatos):e.candidatos); }catch(e){}
  const _lu=_hist.filter(h=>h.role==='user').slice(-1)[0];
  const _lt=String(_lu? (typeof _lu.content==='string'?_lu.content:(Array.isArray(_lu.content)?_lu.content.map(c=>c.text||'').join(' '):'')) : '').toLowerCase();
  const _sim=/\b(sim|isso|confirmo|confirmado|s[aã]o essas|s[aã]o elas|pode|correto|exato|isso mesmo|perfeito|ok)\b/.test(_lt);
  if(_etapa==='aguardando_confirmacao' && _cand && _cand.ad_id && _cand.page_id && _sim){
    let _tok=''; try{_tok=$('load_meta_token_revisao').first().json.valor;}catch(e){}
    const _BM='1612905538806887', _api='https://graph.facebook.com/v25.0', _SYS='122093025345347834';
    async function _post(path,params){ const b=Object.entries(params).map(([k,v])=>`${k}=${encodeURIComponent(v)}`).join('&'); const r=await this.helpers.httpRequest({method:'POST',url:`${_api}/${path}`,body:b,headers:{'Content-Type':'application/x-www-form-urlencoded'},returnFullResponse:false}); return (typeof r==='string')?JSON.parse(r):r; }
    async function _get(url){ const r=await this.helpers.httpRequest({method:'GET',url,returnFullResponse:false}); return (typeof r==='string')?JSON.parse(r):r; }
    let assign_ad=false,assign_page=false,assign_err='';
    try{ const r=await _post.call(this,`act_${_cand.ad_id}/assigned_users`,{user:_SYS,tasks:'["MANAGE","ADVERTISE","ANALYZE"]',access_token:_tok}); assign_ad=!!(r&&r.success); }catch(e){ assign_err+='ad:'+String(e).slice(0,100)+' '; }
    try{ const r=await _post.call(this,`${_cand.page_id}/assigned_users`,{user:_SYS,tasks:'["ADVERTISE","ANALYZE","CREATE_CONTENT"]',access_token:_tok}); assign_page=!!(r&&r.success); }catch(e){ assign_err+='page:'+String(e).slice(0,100); }
    try{ await _get.call(this,`${_api}/act_${_cand.ad_id}/campaigns?fields=id&limit=1&access_token=${encodeURIComponent(_tok)}`); }
    catch(e){ return [{json:{ok:false,motivo:'sem_permissao_campanhas',telefone:_tel,mensagem:'Tô vendo a Conta compartilhada, mas não consigo gerenciar campanhas dela. A permissão precisa ser "Gerenciar campanhas". Ajusta e me chama.'}}]; }
    const _pn=(_cli.nome_cliente||'').split(' ')[0]||'';
    return [{json:{ ok:true, telefone:_tel, ad_account_id:String(_cand.ad_id), page_id:String(_cand.page_id), wa_link:'', assign_ad, assign_page, assign_err,
      mensagem:`✅ Tudo certo, ${_pn}! Tua conta tá ativa na Quirk:\n\n📊 Conta: ${_cand.ad_name||_cand.ad_id}\n📄 Página: ${_cand.page_name||_cand.page_id}\n\nPode subir campanhas! É só me mandar os dados de um imóvel + a foto ou vídeo dele. 🚀`}}];
  }
}
// === fim CONFIRMA-ATIVA (se nao confirmou, segue pra deteccao normal abaixo) ===
'''
if 'CONFIRMA-ATIVA' not in jc:
    N['revisao_meta']['parameters']['jsCode'] = PREFIX + jc

new=N['revisao_meta']['parameters']['jsCode']
open("/tmp/_h02b.js","w").write("async function _w(){\n"+new+"\n}\n")
r=subprocess.run(["node","--check","/tmp/_h02b.js"],capture_output=True,text=True)
print("SYNTAX:", "OK" if r.returncode==0 else "FALHOU")
if r.returncode: print(r.stderr[:800]); sys.exit(1)
print("load_estado_revisao no wf?", 'load_estado_revisao' in {n['name'] for n in wf['nodes']})
if not DEPLOY: print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_conf2b.json","w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C, settings={"executionOrder": wf.get('settings',{}).get('executionOrder','v1')})
print("DEPLOYADO.")
