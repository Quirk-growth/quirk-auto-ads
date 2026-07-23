# Onboarding — auto-detecção de conta/página — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover o passo "digite o ID da conta de anúncios" do onboarding: detectar a conta por NOME (como a página já é), entre os ativos SEM DONO compartilhados com a BM Quirk, com confirmação sempre e escape pra humano.

**Architecture:** Mudanças no workflow principal n8n `fBUin1UPt5xJEp6g`, sub-fluxo de onboarding (`revisao_meta` e vizinhos). Detecção por nome + filtro "sem dono" (anti-troca), estado de confirmação via marcador `<REVISAO_CONFIRMADA/>` (mesmo padrão do `<REVISAO_REQUEST/>` que já existe), e contador de falhas → alerta no WhatsApp do Renan.

**Tech Stack:** n8n (via `scripts/n8n_api.py`), Meta Graph API v25.0, Postgres/Supabase. Testes = aplicar via script + **replay** de payloads no webhook + checagem no banco.

## Global Constraints

- **Workflow:** `fBUin1UPt5xJEp6g` (principal). BM Quirk: `1612905538806887`. System User: `122093025345347834`. Token: config `meta_access_token` (nó `load_meta_token_revisao`).
- **PUT do n8n só aceita `executionOrder` em settings** → sempre `update_workflow(..., settings={"executionOrder": wf.get("settings",{}).get("executionOrder","v1")})`.
- **Backup ANTES de cada mudança:** `json.dump(wf, open("../n8n_workflow/backup_main_pre_<x>.json","w"), ...)`.
- **Prompt vivo do agente** está embutido nos nós (não no `.md`); use `scripts/_dump_prompt_vivo.py` como referência de leitura.
- Rodar scripts de `/Users/renanreal/quirk_auto_ads/scripts`. Dry-run + syntax-check (`node --check` envelopando o jsCode em `async function _w(){...}`) antes de deployar.
- **Segurança (inviolável):** só considerar ativos SEM DONO (não presentes em `auto_ads.clientes.ad_account_id`/`page_id`); nunca atribuir por tempo; na dúvida (0 ou 2+), perguntar.

---

### Task 1: Detecção da conta por nome + filtro "sem dono" (não ativa ainda)

Troca a extração do ID (14-17 dígitos) por match por nome entre as contas SEM DONO; aplica o mesmo filtro à página; quando acha 1+1, retorna `precisa_confirmar` (não ativa).

**Files:**
- Create: `scripts/h_01_revisao_por_nome.py`
- Modify (via script): nó `revisao_meta` (jsCode) + novo nó `load_assigned_assets` (Postgres) antes dele.

**Interfaces:**
- Produz (retorno do `revisao_meta`): objetos com um destes formatos:
  - `{ precisa_confirmar:true, telefone, ad_candidate:{id,name}, page_candidate:{id,name}, mensagem }`
  - `{ ok:false, motivo, telefone, mensagem }` (0 candidatos, ambíguo, erro_meta, sem_token)
  - (a ativação de fato passa a acontecer na Task 2, após confirmação)

- [ ] **Step 1: Descobrir o que alimenta `revisao_meta` e criar o nó de ativos atribuídos**

Run (inspeção):
```bash
cd scripts && python3 -c "import n8n_api,json; wf=n8n_api.get_workflow('fBUin1UPt5xJEp6g'); C=wf['connections']; print('quem aponta pra revisao_meta:', [s for s,d in C.items() for br in d.get('main',[]) for c in (br or []) if c['node']=='revisao_meta'])"
```
Expected: mostra o nó anterior ao `revisao_meta` (ex.: `trigger_revisao`). Anote — o novo `load_assigned_assets` entra ENTRE esse nó e o `revisao_meta`.

- [ ] **Step 2: Escrever `h_01_revisao_por_nome.py`** — adiciona `load_assigned_assets` (Postgres) e substitui o jsCode do `revisao_meta`

```python
# scripts/h_01_revisao_por_nome.py
import json, subprocess, sys, n8n_api, config
WF="fBUin1UPt5xJEp6g"; DEPLOY = len(sys.argv)>1 and sys.argv[1]=="deploy"
wf=n8n_api.get_workflow(WF); N={n['name']:n for n in wf['nodes']}; C=wf['connections']

# 1) nó Postgres que carrega os ativos JÁ atribuídos (pra filtrar "sem dono")
PG=config.POSTGRES_CRED
if 'load_assigned_assets' not in N:
    prev=[s for s,d in C.items() for br in d.get('main',[]) for c in (br or []) if c['node']=='revisao_meta']
    prev=prev[0] if prev else 'trigger_revisao'
    node={"id":"load_assigned_assets","name":"load_assigned_assets","type":"n8n-nodes-base.postgres","typeVersion":2.6,
      "position": (N['revisao_meta']['position'][0]-220, N['revisao_meta']['position'][1]),
      "parameters":{"operation":"executeQuery","query":
        "SELECT COALESCE(json_agg(ad_account_id) FILTER (WHERE ad_account_id IS NOT NULL),'[]') AS ad_ids, "
        "COALESCE(json_agg(page_id) FILTER (WHERE page_id IS NOT NULL),'[]') AS page_ids FROM auto_ads.clientes"},
      "credentials":{"postgres":PG}}
    wf['nodes'].append(node)
    # rewire: prev -> load_assigned_assets -> revisao_meta
    C.setdefault(prev,{"main":[[]]});
    for br in C[prev]['main']:
        for c in (br or []):
            if c['node']=='revisao_meta': c['node']='load_assigned_assets'
    C['load_assigned_assets']={"main":[[{"node":"revisao_meta","type":"main","index":0}]]}

# 2) novo jsCode do revisao_meta: detecta conta+pagina por NOME entre SEM DONO; retorna precisa_confirmar
NEW = r'''
const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
let historico=[];
try { historico=JSON.parse($('parse_onboarding_resp').first().json.novo_historico || cliente.historico_onboarding || '[]'); }
catch(e){ try{historico=JSON.parse(cliente.historico_onboarding||'[]');}catch(e2){historico=[];} }
const userText = historico.filter(h=>h.role==='user').map(h=> typeof h.content==='string'?h.content:(Array.isArray(h.content)?h.content.map(c=>c.text||'').join(' '):'')).join('\n');

let token=''; try{ token=$('load_meta_token_revisao').first().json.valor; }catch(e){}
if(!token) return [{json:{ok:false,motivo:'sem_token_meta',telefone,mensagem:'Deu um errinho interno aqui — já te chamo de volta.'}}];

// ativos JA atribuidos (pra considerar so os SEM DONO)
let assignedAd=[], assignedPage=[];
try{ const a=$('load_assigned_assets').first().json; assignedAd=(typeof a.ad_ids==='string'?JSON.parse(a.ad_ids):a.ad_ids)||[]; assignedPage=(typeof a.page_ids==='string'?JSON.parse(a.page_ids):a.page_ids)||[]; }catch(e){}
const assignedAdSet=new Set(assignedAd.map(String));
const assignedPageSet=new Set(assignedPage.map(String));

const BM='1612905538806887', apiBase='https://graph.facebook.com/v25.0';
async function getJson(url){ const r=await this.helpers.httpRequest({method:'GET',url,returnFullResponse:false}); return (typeof r==='string')?JSON.parse(r):r; }
const norm=s=>String(s||'').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');
const nomeCad=norm(cliente.nome_cliente);
const userNorm=norm(userText);
// termos do nome do cadastro (>=3 chars) pra casar por nome
const termosCad=nomeCad.split(/\s+/).filter(t=>t.length>=3);

function candidatos(lista, idField, assignedSet){
  const semDono=lista.filter(x=>!assignedSet.has(String(x[idField])));
  // (a) nome do ativo contido no que o cliente falou  OU  (b) nome do ativo contem termo do cadastro
  const byUser=semDono.filter(x=>x.name && norm(x.name).length>=3 && userNorm.includes(norm(x.name)));
  const byCad =semDono.filter(x=> x.name && termosCad.some(t=>norm(x.name).includes(t)));
  // uniao, priorizando quem casou pelos dois; ordena por nome mais longo
  const uniq=new Map(); [...byUser,...byCad].forEach(x=>uniq.set(String(x[idField]),x));
  return {semDono, matches:[...uniq.values()].sort((a,b)=>norm(b.name).length-norm(a.name).length)};
}

// contas
let adAll=[]; try{ adAll=(await getJson.call(this,`${apiBase}/${BM}/client_ad_accounts?fields=id,account_id,name&limit=500&access_token=${encodeURIComponent(token)}`)).data||[]; }
catch(e){ return [{json:{ok:false,motivo:'erro_meta_api',telefone,mensagem:'Não consegui consultar a Meta agora. Tenta de novo daqui a 1 minutinho.'}}]; }
const ad=candidatos(adAll,'account_id',assignedAdSet);
// paginas
let pgAll=[]; try{ const [cp,op]=await Promise.all([ getJson.call(this,`${apiBase}/${BM}/client_pages?fields=id,name&limit=500&access_token=${encodeURIComponent(token)}`), getJson.call(this,`${apiBase}/${BM}/owned_pages?fields=id,name&limit=500&access_token=${encodeURIComponent(token)}`) ]); pgAll=[...(cp.data||[]),...(op.data||[])]; }
catch(e){ return [{json:{ok:false,motivo:'erro_meta_api',telefone,mensagem:'Não consegui consultar a Meta agora. Tenta de novo daqui a 1 minutinho.'}}]; }
const pg=candidatos(pgAll,'id',assignedPageSet);

// decisao (nunca adivinha)
function lista(nomes){ return nomes.map(n=>`• ${n}`).join('\n'); }
if(ad.matches.length===0) return [{json:{ok:false,motivo:'ad_nao_encontrada',telefone,mensagem:`Ainda não localizei a sua *Conta de Anúncios* compartilhada com a Quirk.\nConfere: compartilhou a Conta de Anúncios (não o Business inteiro) com a permissão "Gerenciar campanhas"? ID da Quirk: ${BM}.\nDepois é só me chamar. 🙂`}}];
if(ad.matches.length>1) return [{json:{ok:false,motivo:'ad_ambigua',telefone,mensagem:`Achei mais de uma conta. Qual é a sua?\n${lista(ad.matches.map(a=>a.name))}\nMe diz o nome exato.`}}];
if(pg.matches.length===0) return [{json:{ok:false,motivo:'pagina_nao_encontrada',telefone,mensagem:`Achei tua conta, mas ainda não localizei a *Página* compartilhada. Me manda o *nome exato* da tua Página (igual aparece no Facebook), ou confere se compartilhou com a Quirk.`}}];
if(pg.matches.length>1) return [{json:{ok:false,motivo:'pagina_ambigua',telefone,mensagem:`Achei mais de uma página. Qual é a sua?\n${lista(pg.matches.map(p=>p.name))}\nMe diz o nome exato.`}}];

// 1 conta + 1 pagina -> PEDE CONFIRMACAO (nao ativa)
const adC=ad.matches[0], pgC=pg.matches[0];
return [{json:{
  precisa_confirmar:true, telefone,
  ad_candidate:{id:String(adC.account_id), name:adC.name},
  page_candidate:{id:String(pgC.id), name:pgC.name},
  mensagem:`Achei aqui:\n📊 Conta: *${adC.name}*\n📄 Página: *${pgC.name}*\n\nConfirma que são essas? Responde *SIM* que eu ativo tua conta. 🚀`
}}];
'''
N['revisao_meta']['parameters']['jsCode']=NEW

open("/tmp/_h01.js","w").write("async function _w(){\n"+NEW+"\n}\n")
r=subprocess.run(["node","--check","/tmp/_h01.js"],capture_output=True,text=True)
print("SYNTAX:", "OK" if r.returncode==0 else "FALHOU");
if r.returncode: print(r.stderr[:800]); sys.exit(1)
print("load_assigned_assets criado?", 'load_assigned_assets' in {n['name'] for n in wf['nodes']})
if not DEPLOY: print("[DRY-RUN]"); sys.exit(0)
json.dump(wf, open("../n8n_workflow/backup_main_pre_revisao_nome.json","w"), ensure_ascii=False, indent=2)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C, settings={"executionOrder": wf.get('settings',{}).get('executionOrder','v1')})
print("DEPLOYADO.")
```

- [ ] **Step 3: Dry-run (syntax)**

Run: `cd scripts && python3 h_01_revisao_por_nome.py`
Expected: `SYNTAX: OK` + `load_assigned_assets criado? True` + `[DRY-RUN]`.

- [ ] **Step 4: Deploy**

Run: `cd scripts && python3 h_01_revisao_por_nome.py deploy`
Expected: `DEPLOYADO.`

- [ ] **Step 5: Teste — cliente de teste em onboarding sinaliza que terminou**

Coloque um cliente de teste em `em_onboarding` cujo nome case com um ativo SEM DONO real da BM (ou use um cujo ativo você conhece), com o `<REVISAO_REQUEST/>` (o `onboarding_agent` emite quando o cliente diz que terminou — na Task 3 ajustamos o prompt; por ora dispare replicando um payload que leve o `parse_onboarding_resp` a `solicita_revisao=true`). Depois:
```bash
cd scripts && python3 -c "import n8n_api,json; r=n8n_api._request('GET','/executions?workflowId=fBUin1UPt5xJEp6g&limit=1&includeData=false'); d=n8n_api._request('GET',f\"/executions/{r['data'][0]['id']}?includeData=true\")['data']['resultData']['runData']; print(json.dumps(d['revisao_meta'][0]['data']['main'][0][0]['json'],ensure_ascii=False)[:400])"
```
Expected: retorno com `precisa_confirmar: true`, `ad_candidate`, `page_candidate` e a mensagem "Confirma? …" — **e NÃO** ativou o cliente (status ainda `em_onboarding`).

- [ ] **Step 6: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/h_01_revisao_por_nome.py n8n_workflow/backup_main_pre_revisao_nome.json
git commit -m "feat(onboarding): detecta conta+página por nome entre ativos sem dono (pede confirmação)"
```

---

### Task 2: Estado de confirmação + ativação após "SIM"

Roteia o novo retorno: `precisa_confirmar` → guarda candidatos no estado + manda "confirma?"; e o marcador `<REVISAO_CONFIRMADA/>` → ativa com os candidatos guardados.

**Files:**
- Create: `scripts/h_02_confirmacao_ativacao.py`
- Modify: `if_revisao_ok` (roteia precisa_confirmar), `parse_onboarding_resp` (detecta REVISAO_CONFIRMADA), + novos nós `persist_candidatos` (Postgres: grava candidatos no estado_json) e `ativar_com_candidatos` (lê estado + chama update_cliente_ativo).

**Interfaces:**
- Consome (da Task 1): `{precisa_confirmar, ad_candidate:{id,name}, page_candidate:{id,name}, telefone, mensagem}`.
- Produz: ativação (`update_cliente_ativo`) usando `estado_json.candidatos.{ad_id,page_id}`.

- [ ] **Step 1: Inspecionar `if_revisao_ok` e `parse_onboarding_resp`**

Run:
```bash
cd scripts && python3 -c "import n8n_api,json; wf=n8n_api.get_workflow('fBUin1UPt5xJEp6g'); N={n['name']:n for n in wf['nodes']}; print('if_revisao_ok:', json.dumps(N['if_revisao_ok']['parameters'],ensure_ascii=False)[:300]); print('parse regex:', [l for l in N['parse_onboarding_resp']['parameters']['jsCode'].split(chr(10)) if 'REVISAO' in l])"
```
Expected: mostra a condição do `if_revisao_ok` (provavelmente `$json.ok === true`) e a regex do `REVISAO_REQUEST` — vamos espelhar pro `REVISAO_CONFIRMADA`.

- [ ] **Step 2: Escrever `h_02_confirmacao_ativacao.py`**

Implementa (com backup + syntax-check + `settings` limpo):
1. `parse_onboarding_resp`: adicionar, ao lado do `solicita_revisao`, `confirma_ativacao = /<REVISAO_CONFIRMADA\s*\/?>/i.test(txt)` e incluí-lo no `json` de saída.
2. `if_revisao_ok`: hoje ramifica `ok===true` → `update_cliente_ativo`, senão → manda a mensagem. Trocar por um **Switch** (ou IF encadeado) com 3 saídas: `precisa_confirmar===true` → `persist_candidatos` (grava `estado_json.candidatos` + `estado_json.etapa='aguardando_confirmacao'`) → manda a `mensagem`; `ok===true` → (fluxo antigo de ativação, mantido); senão → manda a `mensagem` de erro.
3. Novo caminho de confirmação: no `if_solicita_revisao` (ou logo após `parse_onboarding_resp`), quando `confirma_ativacao===true` **e** o estado do cliente é `aguardando_confirmacao`, rotear pra `ativar_com_candidatos` (lê `estado_json.candidatos.ad_id/page_id`, faz a validação de acesso + auto-atribuição do System User — reaproveitar os passos 2.5/3 do `revisao_meta` antigo — e chama `update_cliente_ativo` com esses IDs).

> Nota ao implementador: o código exato dos nós Postgres (`persist_candidatos`) e do `ativar_com_candidatos` deve seguir os padrões já usados (`persist_estado_etapa` pra gravar estado; o bloco de auto-atribuição+checagem de campanhas do `revisao_meta` linhas 99-122 do dump pra revalidar). Grave `estado_json` via `jsonb_set`. Use `telefone_normalizado` (agora canônico com o 9).

- [ ] **Step 3: Deploy + verificar wiring**

Run: `cd scripts && python3 h_02_confirmacao_ativacao.py deploy`
Then:
```bash
cd scripts && python3 -c "import n8n_api; wf=n8n_api.get_workflow('fBUin1UPt5xJEp6g'); print('nós novos:', [n['name'] for n in wf['nodes'] if n['name'] in ('persist_candidatos','ativar_com_candidatos')])"
```
Expected: os 2 nós novos existem; workflow ativo.

- [ ] **Step 4: Teste de ponta a ponta (confirmação → ativação)**

Com o cliente de teste que ficou em `precisa_confirmar` (Task 1, Step 5), simule a resposta "SIM" (payload de texto "sim") → o `onboarding_agent` (Task 3) emitirá `<REVISAO_CONFIRMADA/>`; por ora, pra testar isoladamente, injete um histórico que gere o marcador OU teste o nó `ativar_com_candidatos` com os candidatos gravados. Verifique no banco:
```bash
cd scripts && python3 -c "import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-'); c=psycopg2.connect(u).cursor(); c.execute(\"SELECT telefone,status,ad_account_id,page_id FROM auto_ads.clientes WHERE telefone=<TEST_TEL>\"); print(c.fetchone())"
```
Expected: após "SIM", status=`ativo` com os `ad_account_id`/`page_id` dos candidatos. **Restaure** o cliente de teste depois.

- [ ] **Step 5: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/h_02_confirmacao_ativacao.py n8n_workflow/backup_main_pre_confirmacao.json
git commit -m "feat(onboarding): estado aguardando_confirmacao + ativação após SIM (marcador REVISAO_CONFIRMADA)"
```

---

### Task 3: Prompt do `onboarding_agent` — parar de pedir ID; confirmar

**Files:**
- Create: `scripts/h_03_prompt_onboarding.py`
- Modify: prompt embutido no nó `build_onboarding_body` (jsCode).

- [ ] **Step 1: Ler o prompt vivo do onboarding**

Run:
```bash
cd scripts && python3 -c "import n8n_api; jc={n['name']:n for n in n8n_api.get_workflow('fBUin1UPt5xJEp6g')['nodes']}['build_onboarding_body']['parameters']['jsCode']; open('/tmp/onb.txt','w').write(jc); print('salvo /tmp/onb.txt', len(jc),'chars')"
```
Then read `/tmp/onb.txt` e ache: onde instrui a pedir o ID da conta, e onde/quando emite `<REVISAO_REQUEST/>`.

- [ ] **Step 2: Ajustar o prompt (via script com backup + syntax-check + `settings` limpo)**

Alterações no texto do prompt (string-replace com âncoras exatas do prompt vivo):
1. **Remover** a instrução de pedir o *ID da Conta de Anúncios*. Passar a pedir só: *"compartilhe a Conta de Anúncios e a Página com a Quirk (ID 1612905538806887, permissão Gerenciar campanhas) e me avise quando terminar"*.
2. Manter: quando o cliente sinaliza que terminou/compartilhou → emitir `<REVISAO_REQUEST/>`.
3. **Adicionar:** quando o estado for `aguardando_confirmacao` e o cliente confirmar (sim/isso/confirmo/são essas) → emitir `<REVISAO_CONFIRMADA/>`. Se ele disser que NÃO são essas → não emitir; pedir o nome exato ou orientar a conferir o compartilhamento.

- [ ] **Step 3: Deploy + verificar**

Run: `cd scripts && python3 h_03_prompt_onboarding.py deploy`
Then: `cd scripts && python3 _dump_prompt_vivo.py` (adaptar pro nó onboarding) OU grep no jsCode confirmando que `REVISAO_CONFIRMADA` está presente e o pedido de ID sumiu.
Expected: prompt sem "ID da Conta de Anúncios"; com instrução de `<REVISAO_CONFIRMADA/>`.

- [ ] **Step 4: Teste conversacional real**

Com um cliente de teste `em_onboarding`, mande "já compartilhei tudo" → deve vir a pergunta "confirma '{conta}' e '{página}'?"; responda "sim" → deve ativar. Cheque a execução e o status no banco. Restaure o teste.
Expected: fluxo conversacional completo sem pedir ID.

- [ ] **Step 5: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/h_03_prompt_onboarding.py n8n_workflow/backup_main_pre_prompt_onb.json
git commit -m "feat(onboarding): agente para de pedir ID da conta; confirma ativos por nome + emite REVISAO_CONFIRMADA"
```

---

### Task 4: Escape pra humano (3 falhas → alerta no WhatsApp do Renan)

**Files:**
- Create: `scripts/h_04_escape_humano.py`
- Modify: gravar contador em `estado_json.revisao_falhas`; ao chegar a 3, enviar alerta pro número interno + marcar `estado_json.travado_onboarding=true`.

- [ ] **Step 1: Definir o número interno de alerta**

Usar o telefone do Renan (config novo `alerta_humano_telefone`). Inserir no config:
```bash
cd scripts && python3 -c "import psycopg2; u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-'); c=psycopg2.connect(u); cur=c.cursor(); cur.execute(\"INSERT INTO auto_ads.config (chave,valor) VALUES ('alerta_humano_telefone','5511980838409') ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor\"); c.commit(); print('ok')"
```
Expected: `ok`. (Confirmar o número do Renan com ele antes.)

- [ ] **Step 2: Escrever `h_04_escape_humano.py`** — incrementa contador nos retornos `ok:false, motivo` de "não encontrado/ambíguo" do `revisao_meta`, e quando ≥3:
  1. Envia Cloud API pro `alerta_humano_telefone`: `⚠️ Cliente {nome} ({telefone}) preso no onboarding — não detectei os ativos após 3 tentativas. Dá uma olhada.`
  2. Marca `estado_json.travado_onboarding=true`.
  3. Manda ao cliente: "Vou pedir pro time dar uma olhada e já te retorno. 🙌" em vez de repetir a mesma pergunta.

> Implementação: o incremento do contador é um nó Postgres (jsonb_set em `estado_json.revisao_falhas`) no caminho de falha do `if_revisao_ok`; um IF `revisao_falhas>=3` roteia pro nó de alerta (clone de `send_resposta`, `to` do config) + a mensagem tranquilizadora.

- [ ] **Step 3: Deploy + teste**

Run: `cd scripts && python3 h_04_escape_humano.py deploy`
Teste: cliente de teste sem nada compartilhado sinaliza "terminei" 3× → na 3ª, o alerta chega no número interno e o cliente recebe a mensagem de "time vai olhar". Verifique `estado_json.travado_onboarding`.
Expected: alerta enviado + flag setada + cliente não fica em loop.

- [ ] **Step 4: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/h_04_escape_humano.py n8n_workflow/backup_main_pre_escape.json
git commit -m "feat(onboarding): escape pra humano após 3 falhas (alerta no WhatsApp + flag travado_onboarding)"
```

---

## Self-Review

**Cobertura do spec:**
- Detecção da conta por nome + filtro sem-dono → Task 1. ✓
- Filtro sem-dono na página → Task 1. ✓
- Confirmação sempre (estado `aguardando_confirmacao`) → Task 2 + Task 3. ✓
- 0/ambíguo → pergunta (nunca adivinha) → Task 1 (retornos ad_nao_encontrada/ad_ambigua/...). ✓
- Escape pra humano (3 falhas → alerta) → Task 4. ✓
- Prompt para de pedir ID → Task 3. ✓
- Admin "ativar+avisar" = follow-on **fora deste plano** (spec própria). ✓

**Pontos a validar ao vivo (n8n):**
1. `if_revisao_ok` vira switch de 3 vias — conferir shape do IF/Switch da instância (IF v1 `conditions.boolean`, Switch v3.2 `rules.values`) antes de montar.
2. `estado_json` — confirmar a coluna/estrutura (é em `auto_ads.conversas.estado_json`) e usar `jsonb_set` corretamente.
3. Contador de falhas: garantir reset quando o cliente finalmente ativa.
4. Todos os testes dependem de um cliente de teste com ativo real SEM DONO na BM — combinar com o Renan qual usar.
