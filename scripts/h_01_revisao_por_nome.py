# scripts/h_01_revisao_por_nome.py
# Task 1: detecta conta+pagina por NOME entre ativos SEM DONO; retorna precisa_confirmar (nao ativa).
import json, subprocess, sys, n8n_api, config
WF = "fBUin1UPt5xJEp6g"; DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
wf = n8n_api.get_workflow(WF); N = {n['name']: n for n in wf['nodes']}; C = wf['connections']
PG = config.POSTGRES_CRED

if 'load_assigned_assets' not in N:
    prev = [s for s, d in C.items() for br in d.get('main', []) for c in (br or []) if c['node'] == 'revisao_meta']
    prev = prev[0] if prev else 'load_meta_token_revisao'
    pos = N['revisao_meta']['position']
    node = {"id": "load_assigned_assets", "name": "load_assigned_assets", "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.6, "position": [pos[0] - 220, pos[1] + 120],
            "parameters": {"operation": "executeQuery", "query":
                "SELECT COALESCE(json_agg(ad_account_id) FILTER (WHERE ad_account_id IS NOT NULL),'[]') AS ad_ids, "
                "COALESCE(json_agg(page_id) FILTER (WHERE page_id IS NOT NULL),'[]') AS page_ids FROM auto_ads.clientes"},
            "credentials": {"postgres": PG}}
    wf['nodes'].append(node)
    C.setdefault(prev, {"main": [[]]})
    for br in C[prev]['main']:
        for c in (br or []):
            if c['node'] == 'revisao_meta':
                c['node'] = 'load_assigned_assets'
    C['load_assigned_assets'] = {"main": [[{"node": "revisao_meta", "type": "main", "index": 0}]]}

NEW = r'''
const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
let historico=[];
try { historico=JSON.parse($('parse_onboarding_resp').first().json.novo_historico || cliente.historico_onboarding || '[]'); }
catch(e){ try{historico=JSON.parse(cliente.historico_onboarding||'[]');}catch(e2){historico=[];} }
const userText = historico.filter(h=>h.role==='user').map(h=> typeof h.content==='string'?h.content:(Array.isArray(h.content)?h.content.map(c=>c.text||'').join(' '):'')).join('\n');

let token=''; try{ token=$('load_meta_token_revisao').first().json.valor; }catch(e){}
if(!token) return [{json:{ok:false,motivo:'sem_token_meta',telefone,mensagem:'Deu um errinho interno aqui — já te chamo de volta.'}}];

let assignedAd=[], assignedPage=[];
try{ const a=$('load_assigned_assets').first().json; assignedAd=(typeof a.ad_ids==='string'?JSON.parse(a.ad_ids):a.ad_ids)||[]; assignedPage=(typeof a.page_ids==='string'?JSON.parse(a.page_ids):a.page_ids)||[]; }catch(e){}
const assignedAdSet=new Set(assignedAd.map(String));
const assignedPageSet=new Set(assignedPage.map(String));

const BM='1612905538806887', apiBase='https://graph.facebook.com/v25.0';
async function getJson(url){ const r=await this.helpers.httpRequest({method:'GET',url,returnFullResponse:false}); return (typeof r==='string')?JSON.parse(r):r; }
const norm=s=>String(s||'').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');
const nomeCad=norm(cliente.nome_cliente);
const userNorm=norm(userText);
const termosCad=nomeCad.split(/\s+/).filter(t=>t.length>=3);

function candidatos(lista, idField, assignedSet){
  const semDono=lista.filter(x=>!assignedSet.has(String(x[idField])));
  const byUser=semDono.filter(x=>x.name && norm(x.name).length>=3 && userNorm.includes(norm(x.name)));
  const byCad =semDono.filter(x=> x.name && termosCad.some(t=>norm(x.name).includes(t)));
  const uniq=new Map(); [...byUser,...byCad].forEach(x=>uniq.set(String(x[idField]),x));
  return {semDono, matches:[...uniq.values()].sort((a,b)=>norm(b.name).length-norm(a.name).length)};
}

let adAll=[]; try{ adAll=(await getJson.call(this,`${apiBase}/${BM}/client_ad_accounts?fields=id,account_id,name&limit=500&access_token=${encodeURIComponent(token)}`)).data||[]; }
catch(e){ return [{json:{ok:false,motivo:'erro_meta_api',telefone,mensagem:'Não consegui consultar a Meta agora. Tenta de novo daqui a 1 minutinho.'}}]; }
const ad=candidatos(adAll,'account_id',assignedAdSet);
let pgAll=[]; try{ const [cp,op]=await Promise.all([ getJson.call(this,`${apiBase}/${BM}/client_pages?fields=id,name&limit=500&access_token=${encodeURIComponent(token)}`), getJson.call(this,`${apiBase}/${BM}/owned_pages?fields=id,name&limit=500&access_token=${encodeURIComponent(token)}`) ]); pgAll=[...(cp.data||[]),...(op.data||[])]; }
catch(e){ return [{json:{ok:false,motivo:'erro_meta_api',telefone,mensagem:'Não consegui consultar a Meta agora. Tenta de novo daqui a 1 minutinho.'}}]; }
const pg=candidatos(pgAll,'id',assignedPageSet);

function lista(nomes){ return nomes.map(n=>`• ${n}`).join('\n'); }
if(ad.matches.length===0) return [{json:{ok:false,motivo:'ad_nao_encontrada',telefone,mensagem:`Ainda não localizei a sua *Conta de Anúncios* compartilhada com a Quirk.\nConfere: compartilhou a Conta de Anúncios (não o Business inteiro) com a permissão "Gerenciar campanhas"? ID da Quirk: ${BM}.\nDepois é só me chamar. 🙂`}}];
if(ad.matches.length>1) return [{json:{ok:false,motivo:'ad_ambigua',telefone,mensagem:`Achei mais de uma conta. Qual é a sua?\n${lista(ad.matches.map(a=>a.name))}\nMe diz o nome exato.`}}];
if(pg.matches.length===0) return [{json:{ok:false,motivo:'pagina_nao_encontrada',telefone,mensagem:`Achei tua conta, mas ainda não localizei a *Página* compartilhada. Me manda o *nome exato* da tua Página (igual aparece no Facebook), ou confere se compartilhou com a Quirk.`}}];
if(pg.matches.length>1) return [{json:{ok:false,motivo:'pagina_ambigua',telefone,mensagem:`Achei mais de uma página. Qual é a sua?\n${lista(pg.matches.map(p=>p.name))}\nMe diz o nome exato.`}}];

const adC=ad.matches[0], pgC=pg.matches[0];
return [{json:{
  precisa_confirmar:true, telefone,
  ad_candidate:{id:String(adC.account_id), name:adC.name},
  page_candidate:{id:String(pgC.id), name:pgC.name},
  mensagem:`Achei aqui:\n📊 Conta: *${adC.name}*\n📄 Página: *${pgC.name}*\n\nConfirma que são essas? Responde *SIM* que eu ativo tua conta. 🚀`
}}];
'''
N['revisao_meta']['parameters']['jsCode'] = NEW

open("/tmp/_h01.js", "w").write("async function _w(){\n" + NEW + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_h01.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode:
    print(r.stderr[:800]); sys.exit(1)
print("load_assigned_assets no wf?", 'load_assigned_assets' in {n['name'] for n in wf['nodes']})
if not DEPLOY:
    print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_revisao_nome.json", "w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C, settings={"executionOrder": wf.get('settings', {}).get('executionOrder', 'v1')})
print("DEPLOYADO.")
