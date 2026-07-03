# Tutorial de uso no WhatsApp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o tutorial de uso do Auto Ads dentro do WhatsApp — sob demanda (cliente digita "tutorial" ou pede ajuda) e automaticamente quando o cliente vira `ativo`.

**Architecture:** Duas mudanças de baixo risco: (1) o agente conversacional (`agente_principal.md`) passa a responder o texto fixo do tutorial quando o cliente pede — sem tocar no `switch_intent`, porque "tutorial" já cai no agente via fallback `OUTRO`; (2) um nó de envio novo (`send_tutorial_act`) encadeado DEPOIS do `send_ativacao_msg` (que hoje é terminal) manda o tutorial na ativação. Nenhuma re-fiação de branches existentes.

**Tech Stack:** n8n (workflow principal `fBUin1UPt5xJEp6g` via `scripts/n8n_api.py`), prompt em Markdown, WhatsApp Cloud API (`graph.facebook.com/v25.0/1320571937797802/messages`).

**Spec:** `docs/superpowers/specs/2026-07-03-tutorial-whatsapp-design.md`

---

## Convenções

- Texto canônico do tutorial: está no spec (seção "Texto fixo do tutorial"). É a fonte da copy. Ele aparece em 2 lugares (prompt do agente + nó de ativação) — é uma string estática; se editar, editar nos dois.
- Envio Cloud API (padrão dos `send_*`): `POST https://graph.facebook.com/v25.0/1320571937797802/messages`, body `{messaging_product:"whatsapp", to:<tel>, type:"text", text:{body:<texto>, preview_url:true}}`, com a MESMA credencial/headers do `send_ativacao_msg` (copie do nó existente).
- Backup do workflow ANTES de qualquer alteração via API.
- Rode scripts de `/Users/renanreal/quirk_auto_ads/scripts`.

---

### Task 1: On-demand via `agente_principal.md`

**Files:**
- Modify: `/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md`

- [ ] **Step 1: Adicionar a seção de tutorial ao prompt do agente**

Acrescente ao `agente_principal.md` uma seção clara (perto das regras de comportamento, ex. após a "REGRA DE OURO"):

```markdown
## TUTORIAL / AJUDA

- Se o cliente enviar apenas "tutorial" (ou variações claras: "quero o tutorial", "como usar", "me ensina a usar"), responda EXATAMENTE com o texto abaixo, sem alterar nada, sem adicionar frases antes ou depois:

📱 *Como usar o Auto Ads*

*Pra criar um anúncio*, me manda numa mensagem:
• *Tipo* (apê, casa, sobrado, lote…)
• *Valor*
• *Bairro + cidade*
• *Objetivo*: morar, investir ou veraneio

Ex: _"Apartamento de R$ 650 mil no Batel, Curitiba, pra investidor."_
Faltou algo, eu te pergunto. Pode mandar *fotos/book* junto.

*Depois:* eu confirmo o público e a verba (começa em R$30/dia) → você diz *"confirma"* → o anúncio sobe. Te aviso quando estiver no ar.

*Comandos do dia a dia:*
• *status* — como estão seus anúncios
• *pausar* (diz qual) — pausa um anúncio
• *ativar* (diz qual) — religa um pausado
• *muda a verba pra R$X/dia* — altera o investimento diário
• *listar* — ver todos os seus anúncios
• *cancelar* (diz qual) — encerra um anúncio

💡 A verba começa no piso seguro (R$30/dia) — você aumenta quando quiser. A Meta leva de minutos a algumas horas pra aprovar.

Qualquer dúvida, é só me chamar ou digitar *tutorial*. 💬

- Se o cliente tiver uma dúvida PONTUAL (ex.: "como pauso?", "não entendi a verba"), responda de forma curta e direta a dúvida dele — NÃO despeje o tutorial inteiro — e termine lembrando: "Se quiser ver tudo, é só digitar *tutorial*."
```

- [ ] **Step 2: Verificar que o prompt do agente é lido de arquivo ou está embutido no nó**

Run:
```bash
cd scripts && python3 -c "import n8n_api,json; wf=n8n_api.get_workflow('fBUin1UPt5xJEp6g'); N={n['name']:n for n in wf['nodes']}; b=json.dumps(N.get('build_agente_body',{}).get('parameters',{}),ensure_ascii=False); print('prompt embutido no nó?', 'Como usar o Auto Ads' in b or 'REGRA DE OURO' in b); print('trecho:', b[:300])"
```
Expected: mostra se o `agente_principal.md` está **embutido** no nó `build_agente_body` (provável) ou lido de fora.
- Se estiver **embutido no nó**: a edição do `.md` NÃO basta — é preciso portar a nova seção pro `jsCode`/prompt do nó `build_agente_body` também (via um pequeno script `update_workflow`, com backup antes). Faça isso no Step 3.
- Se for lido de arquivo: a edição do `.md` já vale.

- [ ] **Step 3 (se embutido): portar a seção pro nó `build_agente_body`**

```python
# scripts/g_01_agente_tutorial.py
import json, n8n_api
WF="fBUin1UPt5xJEp6g"
wf=n8n_api.get_workflow(WF)
json.dump(wf, open("../n8n_workflow/backup_main_pre_tutorial.json","w"), ensure_ascii=False, indent=2)
N={n['name']:n for n in wf['nodes']}
node=N['build_agente_body']
# achar o campo que contém o prompt (jsCode) e injetar a seção do tutorial
key='jsCode' if 'jsCode' in node['parameters'] else None
assert key, "ajustar: o prompt pode estar em outro campo do nó"
SECTION = open('/dev/stdin').read()  # cole a seção ## TUTORIAL / AJUDA aqui, ou embuta como string
# ancore a inserção num marcador estável do prompt (ex.: 'REGRA DE OURO' ou fim do prompt)
code=node['parameters'][key]
assert 'REGRA DE OURO' in code, "achar outra âncora"
node['parameters'][key]=code.replace('REGRA DE OURO', 'REGRA DE OURO', 1)  # inserir SECTION no ponto certo do texto do prompt
# (implementador: inserir SECTION dentro da string do prompt, no local adequado)
n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=wf['connections'])
print("build_agente_body atualizado (backup salvo)")
```
> Nota ao implementador: o mecanismo exato depende de como o prompt está montado no nó. Inspecione, injete a seção do tutorial no corpo do prompt do sistema, com backup antes.

- [ ] **Step 4: Teste ao vivo (humano) — sob demanda**

Peça ao Renan pra, do número de teste (`5511980838409`, cliente `ativo`), enviar **`tutorial`** pro bot. Confirme que a resposta é o texto do tutorial. (Alternativa técnica: replay de um inbound simulado no webhook do workflow principal com `type:text` e corpo "tutorial", e checar a execução chegando em `build_agente_body` + a resposta enviada.)
Expected: cliente recebe o tutorial; dúvida pontual (ex.: "como pauso?") recebe resposta curta + lembrete de digitar "tutorial".

- [ ] **Step 5: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add prompts/agente_principal.md scripts/g_01_agente_tutorial.py n8n_workflow/backup_main_pre_tutorial.json 2>/dev/null
git commit -m "feat(tutorial): agente responde tutorial sob demanda (digitar 'tutorial'/pedir ajuda)"
```

---

### Task 2: Auto-envio do tutorial na ativação

**Files:**
- Modify: workflow `fBUin1UPt5xJEp6g` (adiciona nó `send_tutorial_act` após `send_ativacao_msg`)
- Create: `scripts/g_02_tutorial_ativacao.py`

- [ ] **Step 1: Confirmar que `send_ativacao_msg` é terminal (nada depois)**

Run:
```bash
cd scripts && python3 -c "import n8n_api; wf=n8n_api.get_workflow('fBUin1UPt5xJEp6g'); C=wf['connections']; print('downstream de send_ativacao_msg:', [c['node'] for br in C.get('send_ativacao_msg',{}).get('main',[]) for c in (br or [])])"
```
Expected: `downstream de send_ativacao_msg: []` (terminal — seguro encadear depois).

- [ ] **Step 2: Escrever `g_02_tutorial_ativacao.py` (adiciona o nó + fio, com backup)**

```python
# scripts/g_02_tutorial_ativacao.py
import json, n8n_api
WF="fBUin1UPt5xJEp6g"
wf=n8n_api.get_workflow(WF)
json.dump(wf, open("../n8n_workflow/backup_main_pre_tutorial_ativacao.json","w"), ensure_ascii=False, indent=2)
N={n['name']:n for n in wf['nodes']}; C=wf['connections']

# copiar headers/credenciais/typeVersion do send_ativacao_msg pra manter idêntico
base=N['send_ativacao_msg']
TUT = ("📱 *Como usar o Auto Ads*\n\n"
"*Pra criar um anúncio*, me manda numa mensagem:\n"
"• *Tipo* (apê, casa, sobrado, lote…)\n• *Valor*\n• *Bairro + cidade*\n• *Objetivo*: morar, investir ou veraneio\n\n"
"Ex: _\"Apartamento de R$ 650 mil no Batel, Curitiba, pra investidor.\"_\n"
"Faltou algo, eu te pergunto. Pode mandar *fotos/book* junto.\n\n"
"*Depois:* eu confirmo o público e a verba (começa em R$30/dia) → você diz *\"confirma\"* → o anúncio sobe. Te aviso quando estiver no ar.\n\n"
"*Comandos do dia a dia:*\n"
"• *status* — como estão seus anúncios\n• *pausar* (diz qual) — pausa um anúncio\n• *ativar* (diz qual) — religa um pausado\n"
"• *muda a verba pra R$X/dia* — altera o investimento diário\n• *listar* — ver todos os seus anúncios\n• *cancelar* (diz qual) — encerra um anúncio\n\n"
"💡 A verba começa no piso seguro (R$30/dia) — você aumenta quando quiser. A Meta leva de minutos a algumas horas pra aprovar.\n\n"
"Qualquer dúvida, é só me chamar ou digitar *tutorial*. 💬")

send_tut = json.loads(json.dumps(base))       # clona o nó de envio (mesma cred/headers/versão)
send_tut['id']='send_tutorial_act'; send_tut['name']='send_tutorial_act'
send_tut['position']=[base['position'][0]+220, base['position'][1]+120]
send_tut['parameters']['jsonBody']=(
  '={\n  "messaging_product": "whatsapp",\n'
  '  "to": "{{ $(\'revisao_meta\').first().json.telefone }}",\n'
  '  "type": "text",\n'
  '  "text": { "body": ' + json.dumps(TUT, ensure_ascii=False) + ', "preview_url": true }\n}'
)
wf['nodes'].append(send_tut)
C.setdefault('send_ativacao_msg',{'main':[[]]})
if not C['send_ativacao_msg']['main']: C['send_ativacao_msg']['main']=[[]]
C['send_ativacao_msg']['main'][0].append({'node':'send_tutorial_act','type':'main','index':0})

n8n_api.update_workflow(WF, nodes=wf['nodes'], connections=C)
print("send_tutorial_act adicionado após send_ativacao_msg (backup salvo)")
```

- [ ] **Step 3: Deploy**

Run: `cd scripts && python3 g_02_tutorial_ativacao.py`
Expected: `send_tutorial_act adicionado após send_ativacao_msg (backup salvo)`

- [ ] **Step 4: Verificar wiring**

Run:
```bash
cd scripts && python3 -c "import n8n_api; wf=n8n_api.get_workflow('fBUin1UPt5xJEp6g'); C=wf['connections']; print('downstream de send_ativacao_msg:', [c['node'] for br in C.get('send_ativacao_msg',{}).get('main',[]) for c in (br or [])]); print('send_tutorial_act existe?', any(n['name']=='send_tutorial_act' for n in wf['nodes']))"
```
Expected: downstream inclui `send_tutorial_act`; nó existe.

- [ ] **Step 5: Teste da ativação (cuidadoso, com restore)**

Use um cliente de teste que dispare o caminho de ativação (ou peça ao Renan pra completar o onboarding de um número de teste). Ao virar `ativo`, confirme que chegam DUAS mensagens: a de liberação + o tutorial. Verifique a execução:
```bash
cd scripts && python3 -c "import n8n_api; [print(e) for e in n8n_api.list_executions('fBUin1UPt5xJEp6g',5).get('data',[])]"
```
Depois confira que `send_tutorial_act` executou sem erro (inspecione a execução mais recente da ativação). Se mexeu no estado de um cliente de teste, restaure.
Expected: cliente recebe liberação + tutorial; `send_tutorial_act` sem erro.

- [ ] **Step 6: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/g_02_tutorial_ativacao.py n8n_workflow/backup_main_pre_tutorial_ativacao.json
git commit -m "feat(tutorial): auto-envio do tutorial na ativação (send_tutorial_act)"
```

---

## Self-Review

**Cobertura do spec:**
- Sob demanda (digitar "tutorial" / pedir ajuda) → Task 1 (agente responde o texto fixo). ✓
- Auto na ativação → Task 2 (`send_tutorial_act` após `send_ativacao_msg`). ✓
- Dúvida pontual = conversa + lembrete → Task 1, Step 1 (instrução). ✓
- Texto fixo canônico → embutido no prompt e no nó de ativação (mesma string). ✓ (nota: 2 cópias da string — documentado.)
- "digite tutorial quando quiser" → está no fim do próprio texto. ✓

**Desvios conscientes vs. spec:**
- O spec citava novo intent no `classifier.md` + saída no `switch_intent`. Trocado por: agente responde (on-demand) — MENOR risco (o `switch_intent` tem amarração de fallback frágil). Mesma experiência pro cliente. `classifier.md` não é o roteador real (é o code node `classify_intent`); não precisa mudar.

**Riscos/validações ao vivo:**
1. Confirmar se o prompt do agente está embutido no nó `build_agente_body` (Task 1, Step 2) — muda onde editar.
2. `send_ativacao_msg` terminal (Task 2, Step 1) antes de encadear.
3. Testes on-demand e de ativação dependem de mensagem real/simulada — validar com o Renan no número de teste.
