# Blindagem do 9º dígito — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantir uma única forma canônica de telefone (`55 + DDD + 9 + 8 dígitos`) em todo o produto — canonicalizando também na **escrita** (gateway Asaas) e tornando o invariante **obrigatório no banco**, para que qualquer desvio futuro falhe visivelmente em vez de criar cliente fantasma.

**Architecture:** Duas mudanças independentes e pequenas: (A) o nó `parse_payment` do workflow Gateway aplica `com9()` ao telefone vindo do Asaas antes de gravar; (B) uma CHECK constraint em `auto_ads.clientes.telefone` exige o formato canônico para números BR — `conversas` e `campanhas` herdam via FK.

**Tech Stack:** n8n (via `scripts/n8n_api.py`), Postgres/Supabase (psycopg2), Node (`node --check` para validar o jsCode).

**Spec:** `docs/superpowers/specs/2026-07-23-blindagem-9digito-design.md`

## Global Constraints

- **Regra canônica BR:** `55 + DDD(2) + 9 + 8 dígitos` (13 dígitos). Números que **não** começam com `55` ficam livres.
- **Workflow Gateway:** `2ZnZqb4wFous4uEs` (nó `parse_payment`). **Workflow principal:** `fBUin1UPt5xJEp6g` (não é alterado neste plano).
- **PUT do n8n só aceita `executionOrder` em settings** → sempre `update_workflow(..., settings={"executionOrder": wf.get("settings",{}).get("executionOrder","v1")})`.
- **Backup ANTES de alterar workflow:** `json.dump(wf, open("../n8n_workflow/backup_<x>.json","w"), ensure_ascii=False, indent=2)`.
- **Syntax check obrigatório** antes de deployar jsCode: envelopar em `async function _w(){ ... }` e rodar `node --check`.
- Rodar scripts de `/Users/renanreal/quirk_auto_ads/scripts`. DB via `psycopg2.connect(open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-'))`.

---

### Task 1: Gateway canonicaliza o telefone antes de gravar

**Files:**
- Create: `scripts/g_11_gateway_canon9.py`
- Modify (via script): nó `parse_payment` do workflow `2ZnZqb4wFous4uEs`

**Interfaces:**
- Produz: o campo `telefone` retornado pelo `parse_payment` passa a estar **sempre canônico** (BR com o 9). O `upsert_cliente` consome esse campo sem alteração.

- [ ] **Step 1: Testar a regra `com9()` isolada (antes de tocar em produção)**

Run:
```bash
node -e "
function com9(n){ if(n&&n.startsWith('55')){const r=n.slice(2); if(r.length===10) return '55'+r.slice(0,2)+'9'+r.slice(2);} return n; }
console.log('sem 9  554198443588 ->', com9('554198443588'));
console.log('com 9  5541998443588 ->', com9('5541998443588'));
console.log('intl   14155552671   ->', com9('14155552671'));
"
```
Expected:
```
sem 9  554198443588 -> 5541998443588
com 9  5541998443588 -> 5541998443588
intl   14155552671   -> 14155552671
```

- [ ] **Step 2: Escrever `scripts/g_11_gateway_canon9.py`**

```python
# scripts/g_11_gateway_canon9.py
# Parte A: o gateway (parse_payment) canonicaliza o telefone vindo do Asaas para a forma
# BR canonica (55 + DDD + 9 + 8) ANTES de gravar, fechando o furo da escrita.
#   python3 g_11_gateway_canon9.py          -> dry-run (+ syntax)
#   python3 g_11_gateway_canon9.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "2ZnZqb4wFous4uEs"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

ANCHOR = "if (telefone.length >= 10 && !telefone.startsWith('55')) telefone = '55' + telefone;"
ADD = ("\n// Canonicaliza BR: 55 + DDD + [9] + 8 digitos -> SEMPRE com o 9 "
       "(bate com a entrada e com a CHECK do banco)\n"
       "if (telefone.startsWith('55')) { const _r = telefone.slice(2); "
       "if (_r.length === 10) telefone = '55' + _r.slice(0, 2) + '9' + _r.slice(2); }")

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
jc = N["parse_payment"]["parameters"]["jsCode"]

if "Canonicaliza BR" in jc:
    print("já canonicaliza — nada a fazer."); sys.exit(0)

cnt = jc.count(ANCHOR)
print(f"âncora encontrada {cnt}x")
if cnt != 1:
    print("ABORTAR: esperava exatamente 1"); sys.exit(1)

new_jc = jc.replace(ANCHOR, ANCHOR + ADD, 1)

open("/tmp/_g11.js", "w").write("async function _w(){\n" + new_jc + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g11.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode:
    print(r.stderr[:800]); sys.exit(1)

if not DEPLOY:
    print("[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_gateway_pre_canon9.json", "w"), ensure_ascii=False, indent=2)
N["parse_payment"]["parameters"]["jsCode"] = new_jc
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO: gateway canonicaliza o telefone na escrita.")
```

- [ ] **Step 3: Dry-run**

Run: `cd scripts && python3 g_11_gateway_canon9.py`
Expected: `âncora encontrada 1x` + `SYNTAX: OK` + `[DRY-RUN]`

- [ ] **Step 4: Deploy**

Run: `cd scripts && python3 g_11_gateway_canon9.py deploy`
Expected: `DEPLOYADO: gateway canonicaliza o telefone na escrita.`

- [ ] **Step 5: Verificar que ficou no nó vivo**

Run:
```bash
cd scripts && python3 -c "
import n8n_api
jc={n['name']:n for n in n8n_api.get_workflow('2ZnZqb4wFous4uEs')['nodes']}['parse_payment']['parameters']['jsCode']
print('canonicaliza?', 'Canonicaliza BR' in jc)
wf=n8n_api.get_workflow('2ZnZqb4wFous4uEs'); print('ativo?', wf.get('active'), '| nós:', len(wf['nodes']))
"
```
Expected: `canonicaliza? True` e `ativo? True`

- [ ] **Step 6: Não-regressão — replay de um webhook de pagamento real**

Reenvia um payload de pagamento já capturado (execução 21500 do gateway) e confirma que o fluxo segue funcionando e o telefone sai canônico:
```bash
cd scripts && python3 -c "
import json, n8n_api, urllib.request, time
ex=n8n_api._request('GET','/executions/21500?includeData=true')
rd=ex['data']['resultData']['runData']
def fj(o):
    if isinstance(o,dict):
        if 'body' in o and isinstance(o['body'],dict) and 'event' in o['body']: return o
        for v in o.values():
            r=fj(v)
            if r: return r
    elif isinstance(o,list):
        for v in o:
            r=fj(v)
            if r: return r
w=fj(rd['webhook']); body=w['body']; tok=w['headers'].get('asaas-access-token','')
req=urllib.request.Request('https://n8n.quirkgrowth.online/webhook/quirk-auto-ads-payment',
    data=json.dumps(body).encode(), method='POST',
    headers={'Content-Type':'application/json','asaas-access-token':tok})
print('replay ->', urllib.request.urlopen(req,timeout=30).status)
time.sleep(4)
r=n8n_api._request('GET','/executions?workflowId=2ZnZqb4wFous4uEs&limit=1&includeData=false')
d=n8n_api._request('GET',f\"/executions/{r['data'][0]['id']}?includeData=true\")['data']['resultData']['runData']
print('telefone do parse_payment:', d['parse_payment'][0]['data']['main'][0][0]['json'].get('telefone'))
"
```
Expected: `replay -> 200` e o telefone impresso com **13 dígitos** (canônico, ex.: `5541998443588`).

- [ ] **Step 7: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/g_11_gateway_canon9.py n8n_workflow/backup_gateway_pre_canon9.json
git commit -m "fix(9digito): gateway canonicaliza telefone na escrita (fecha o furo da gravação)"
```

---

### Task 2: CHECK constraint no banco (invariante obrigatório)

**Files:**
- Create: `scripts/g_12_constraint_telefone.py`
- Modify: schema `auto_ads.clientes` (nova constraint `clientes_telefone_canonico`)

**Interfaces:**
- Consome: telefones já canônicos gravados pelo gateway (Task 1) e pelo fluxo principal.
- Produz: garantia de banco — qualquer `INSERT/UPDATE` de telefone BR fora do padrão falha com violação de constraint.

- [ ] **Step 1: Pré-condição — confirmar que TODAS as linhas atuais passam na regex**

Run:
```bash
cd scripts && python3 -c "
import psycopg2
u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u).cursor()
c.execute(\"SELECT telefone FROM auto_ads.clientes WHERE NOT (telefone !~ '^55' OR telefone ~ '^55[0-9]{2}9[0-9]{8}\$')\")
ruins=c.fetchall(); print('linhas que VIOLARIAM a constraint:', ruins if ruins else 'nenhuma ✅')
"
```
Expected: `nenhuma ✅` — se aparecer alguma, **PARE** e corrija esses telefones antes de criar a constraint.

- [ ] **Step 2: Escrever `scripts/g_12_constraint_telefone.py`**

```python
# scripts/g_12_constraint_telefone.py
# Parte B: CHECK constraint em auto_ads.clientes.telefone exigindo a forma canonica BR.
# conversas e campanhas herdam via FK -> nao precisam de constraint propria.
#   python3 g_12_constraint_telefone.py          -> so verifica a pre-condicao
#   python3 g_12_constraint_telefone.py deploy   -> cria a constraint
import sys, psycopg2

DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"
REGEX = r"^55[0-9]{2}9[0-9]{8}$"
u = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
conn = psycopg2.connect(u); cur = conn.cursor()

cur.execute("SELECT telefone FROM auto_ads.clientes WHERE NOT (telefone !~ '^55' OR telefone ~ %s)", [REGEX])
ruins = cur.fetchall()
print("linhas que violariam:", ruins if ruins else "nenhuma")
if ruins:
    print("ABORTAR: corrija esses telefones antes."); sys.exit(1)

if not DEPLOY:
    print("[DRY-RUN] pré-condição OK — rode com 'deploy' pra criar a constraint."); sys.exit(0)

cur.execute("""
ALTER TABLE auto_ads.clientes
  ADD CONSTRAINT clientes_telefone_canonico
  CHECK (telefone !~ '^55' OR telefone ~ '^55[0-9]{2}9[0-9]{8}$')
""")
conn.commit()
print("CONSTRAINT criada: clientes_telefone_canonico")
conn.close()
```

- [ ] **Step 3: Dry-run (só valida a pré-condição)**

Run: `cd scripts && python3 g_12_constraint_telefone.py`
Expected: `linhas que violariam: nenhuma` + `[DRY-RUN] pré-condição OK`

- [ ] **Step 4: Criar a constraint**

Run: `cd scripts && python3 g_12_constraint_telefone.py deploy`
Expected: `CONSTRAINT criada: clientes_telefone_canonico`

- [ ] **Step 5: Testar que a constraint REJEITA telefone BR sem o 9**

Run:
```bash
cd scripts && python3 -c "
import psycopg2
u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u); cur=c.cursor()
try:
    cur.execute(\"INSERT INTO auto_ads.clientes (telefone, nome_cliente, status) VALUES ('554198887777','Teste Sem9','em_onboarding')\")
    c.commit(); print('❌ FALHOU: a constraint NÃO barrou (limpar essa linha!)')
except Exception as e:
    c.rollback(); print('✅ REJEITADO como esperado:', str(e).split(chr(10))[0][:90])
c.close()
"
```
Expected: `✅ REJEITADO como esperado: new row for relation "clientes" violates check constraint ...`

- [ ] **Step 6: Testar que ACEITA canônico e internacional**

Run:
```bash
cd scripts && python3 -c "
import psycopg2
u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u); cur=c.cursor()
for tel,label in [('5541998887777','BR canônico'),('14155552671','internacional')]:
    try:
        cur.execute('INSERT INTO auto_ads.clientes (telefone, nome_cliente, status) VALUES (%s,%s,%s)',[tel,'Teste '+label,'em_onboarding'])
        cur.execute('DELETE FROM auto_ads.clientes WHERE telefone=%s',[tel]); c.commit()
        print('✅ aceitou e limpou:', label, tel)
    except Exception as e:
        c.rollback(); print('❌ rejeitou indevidamente:', label, str(e)[:80])
c.close()
"
```
Expected: `✅ aceitou e limpou: BR canônico 5541998887777` e `✅ aceitou e limpou: internacional 14155552671`

- [ ] **Step 7: Confirmar que nenhuma linha de teste ficou no banco**

Run:
```bash
cd scripts && python3 -c "
import psycopg2
u=open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-','aws-1-')
c=psycopg2.connect(u).cursor(); c.execute(\"SELECT telefone,nome_cliente FROM auto_ads.clientes WHERE nome_cliente LIKE 'Teste %'\")
print('linhas de teste remanescentes:', c.fetchall() or 'nenhuma ✅')
"
```
Expected: `nenhuma ✅`

- [ ] **Step 8: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/g_12_constraint_telefone.py
git commit -m "feat(9digito): CHECK constraint garante telefone canônico em clientes (falha visível)"
```

---

### Task 3: Re-auditoria final

**Files:**
- Modify: nenhum (só verificação)

- [ ] **Step 1: Rodar a auditoria e confirmar que o furo da escrita fechou**

Run: `cd scripts && python3 _audit_9digito.py`
Expected: a seção "BANCO — formatos" mostra **SEM9=0** nas três tabelas; nenhuma regressão nos nós de entrada (`normalize_phone`, `media_normalize_phone`, `select_cliente`, `media_select_cliente` continuam com `canon=True`).

- [ ] **Step 2: Registrar o resultado no spec**

Acrescentar ao final de `docs/superpowers/specs/2026-07-23-blindagem-9digito-design.md` uma seção `## Resultado (pós-implementação)` com a data e o que a re-auditoria mostrou (escrita canonicalizada + constraint ativa + banco 100% canônico).

- [ ] **Step 3: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add docs/superpowers/specs/2026-07-23-blindagem-9digito-design.md
git commit -m "docs: resultado da re-auditoria do 9º dígito pós-blindagem"
```

---

## Self-Review

**Cobertura do spec:**
- Parte A (gateway canonicaliza na escrita) → Task 1. ✓
- Parte B (CHECK constraint, BR obrigatório / internacional livre) → Task 2. ✓
- `conversas`/`campanhas` herdam via FK (sem constraint própria) → documentado no spec e na Task 2. ✓
- Pré-condição (linhas atuais passam) → Task 2, Step 1 e Step 3. ✓
- Testes de rejeição e aceitação → Task 2, Steps 5 e 6 (+ Step 7 garante limpeza). ✓
- Trade-off aceito (falha visível) → materializado no teste de rejeição. ✓
- Não-objetivos (lookups silenciosos, migração de dados) → fora do plano, conforme spec. ✓

**Pontos de atenção ao executar:**
1. Task 2 insere e apaga linhas de teste em `clientes` — o Step 7 confirma que nada sobrou.
2. Se o Step 1 da Task 2 achar telefone fora do padrão, **parar** e corrigir antes (a constraint seria rejeitada).
3. O replay da Task 1 Step 6 reprocessa um pagamento real já processado — é idempotente (upsert), mas confirme que o cliente-alvo não muda de status inesperadamente.
