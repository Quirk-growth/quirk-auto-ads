# Quirk Auto Ads — Execução Multi-Cliente

**Documento único de aplicação.** Siga na ordem. Cada seção tem o exato passo a passo.

---

## Resumo do que vai mudar

| Camada | Mudança |
|---|---|
| **Data Store** | +4 campos novos por cliente (`ad_account_id`, `page_id`, `access_token`, `wa_link`) |
| **D.1, D.2, D.3, D.4** | Bodies usam variáveis do Data Store em vez de hardcode |
| **Headers D.1 e D.2** | Remover header lixo antigo |
| **Validação (Router 51)** | +1 condição: `ad_account_id Exists` (bloqueia cliente não cadastrado) |
| **Bug do criativo no D.3** | Corrigido com `last(split(...; newline))` para pegar o último link |
| **Cadastro do primeiro cliente** | Você cadastra seu próprio número manualmente pra testar |

---

## PARTE 1 — Estender o Data Store

No Make → Data stores → `Memoria Conversas Quirk` → editar Data structure.

**Adicionar 4 campos (todos type `text`, não obrigatórios):**

| Nome do campo | Tipo | Pra quê serve |
|---|---|---|
| `ad_account_id` | text | ID da conta de anúncios do cliente (sem `act_`, só os números) |
| `page_id` | text | ID da página Facebook do cliente |
| `access_token` | text | Token do System User com acesso à conta do cliente |
| `wa_link` | text | Link `https://wa.me/NUMERO` do WhatsApp conectado à página do cliente |

**Salvar.**

**⚠️ Detalhe do `wa_link`:** o D.3 (criativo) exige um campo `link` no `link_data`. Hoje está hardcoded como `https://wa.me/5511952136200` (Quirk). Pra cada cliente ter o anúncio mandando pro WhatsApp dele, esse link tem que vir do registro do cliente. O `call_to_action: WHATSAPP_MESSAGE` continua sendo o que de fato abre a conversa, mas o `link` é estrutural e a Meta exige.

---

## PARTE 2 — Cadastrar você mesmo como primeiro cliente de teste

Ainda no Data Store `Memoria Conversas Quirk` → clica em **Browse** → **Add record**.

Preencher:

| Campo | Valor |
|---|---|
| Key | `5511980838409` *(seu telefone do payload, sem `+`)* |
| historico | *(deixar vazio — vai ser preenchido nas conversas)* |
| criativo_url | *(deixar vazio)* |
| ad_account_id | `3771507593117364` |
| page_id | `687786881077238` |
| access_token | `EAAqtFmgGCYkBRu50affAwjZBbqg0FvqDH85mfvGkY77wQmSoJ4QAxKuaUqmPQ7b5YX7uJsjlcI80GHFspdQLZCuX7vrPhaplzd1WKBJwlmxpnhrM0JH7ESYpglLqdfDsgzgUu0mMZBKfJAepmpeLZBTKnsxNYS0Wv8yCJicNUen6iI28QWZC2Diald11ak7i99QZDZD` |
| wa_link | `https://wa.me/5511952136200` *(o número conectado à página da Quirk)* |

**Save.**

> Pra adicionar clientes reais depois, é o mesmo processo: cria registro novo com a Key sendo o telefone do cliente (formato `5511999999999`, sem `+`).

---

## PARTE 3 — Atualizar D.1 (Campanha)

Módulo HTTP id **52** no cenário.

### URL (campo URL do módulo)

```
https://graph.facebook.com/v25.0/act_{{13.ad_account_id}}/campaigns
```

> ⚠️ A parte `{{13.ad_account_id}}` precisa virar **bolha de variável** (do módulo Get a record). Cola o texto, depois apaga o `{{13.ad_account_id}}` e insere a variável pelo painel.

### Headers

**REMOVER** o header existente (aquele com `name: {{49.campanha.nome}}` e value=token). Era lixo, não atrapalhava mas é sujeira.

Deixar **sem nenhum header**. O token vai no body.

### Body (campo Request content, JSON string)

```json
{"name":"{{49.campanha.nome}}","objective":"OUTCOME_LEADS","status":"PAUSED","special_ad_categories":[],"is_adset_budget_sharing_enabled":false,"access_token":"{{13.access_token}}"}
```

> Após colar, confirma que `{{49.campanha.nome}}` e `{{13.access_token}}` viraram bolhas coloridas.

**Salvar.**

---

## PARTE 4 — Atualizar D.2 (Conjunto de Anúncios)

Módulo HTTP id **56**.

### URL

```
https://graph.facebook.com/v25.0/act_{{13.ad_account_id}}/adsets
```

### Headers

**REMOVER** o header lixo antigo.

### Body

```json
{"name":"{{49.publico_escolhido}}","campaign_id":"{{52.data.id}}","daily_budget":{{if(49.campanha.verba_diaria > 0; 49.campanha.verba_diaria * 100; 1000)}},"billing_event":"IMPRESSIONS","optimization_goal":"CONVERSATIONS","destination_type":"WHATSAPP","promoted_object":{"page_id":"{{13.page_id}}"},"bid_strategy":"LOWEST_COST_WITHOUT_CAP","targeting":{"geo_locations":{"countries":["BR"]},"age_min":{{49.conjunto.idade_min}},"age_max":{{49.conjunto.idade_max}},"targeting_automation":{"advantage_audience":0}},"status":"PAUSED","access_token":"{{13.access_token}}"}
```

> Após colar, confere que **TODAS** as bolhas viraram coloridas: `{{49.publico_escolhido}}`, `{{52.data.id}}`, a fórmula `if()`, `{{13.page_id}}`, `{{49.conjunto.idade_min}}`, `{{49.conjunto.idade_max}}`, `{{13.access_token}}`.

**Salvar.**

---

## PARTE 5 — Atualizar D.3 (Criativo)

Módulo HTTP id **62**.

### URL

```
https://graph.facebook.com/v25.0/act_{{13.ad_account_id}}/adcreatives
```

### Body

```json
{"name":"{{49.campanha.nome}}","object_story_spec":{"page_id":"{{13.page_id}}","link_data":{"message":"{{49.anuncio.copy}}","picture":"{{trim(last(split(13.criativo_url; newline)))}}","link":"{{13.wa_link}}","call_to_action":{"type":"WHATSAPP_MESSAGE","value":{"app_destination":"WHATSAPP"}}}},"access_token":"{{13.access_token}}"}
```

**O que mudou:**
- `name`: passou de `"Criativo CTWA"` (fixo) → variável `{{49.campanha.nome}}`
- `picture`: passou de `{{13.criativo_url}}<URL fixa de teste grudada>` → fórmula `{{trim(last(split(13.criativo_url; newline)))}}` que pega o **último link** da lista acumulada
- `link`: passou de `https://wa.me/5511952136200` (fixo Quirk) → variável `{{13.wa_link}}`
- `page_id`: passou de fixo → variável `{{13.page_id}}`
- `access_token`: variável

> ⚠️ **Sobre a fórmula `picture`**: ela usa `split(...; newline)` que separa a string `criativo_url` pelas quebras de linha (igual você implementou na gravação), pega o `last()` da lista (o link mais recente) e aplica `trim()` pra tirar espaços. Se o Make não aceitar `newline` como literal, troca por: `{{trim(last(split(13.criativo_url; "\n")))}}`. Se nenhum dos dois funcionar, me chama.

**Salvar.**

---

## PARTE 6 — Atualizar D.4 (Anúncio)

Módulo HTTP id **63**.

### URL

```
https://graph.facebook.com/v25.0/act_{{13.ad_account_id}}/ads
```

### Body

```json
{"name":"{{49.campanha.nome}}","adset_id":"{{56.data.id}}","creative":{"creative_id":"{{62.data.id}}"},"status":"PAUSED","access_token":"{{13.access_token}}"}
```

**O que mudou:**
- `name`: passou de `"Anuncio Teste CTWA"` (fixo) → variável `{{49.campanha.nome}}`
- `access_token`: variável

**Salvar.**

---

## PARTE 7 — Atualizar o Filtro de Validação (Fase C, Router 51)

No cenário, acha o Router 51 (validação determinística, fica depois do Parse JSON na rota de execução). Clica no filtro da rota **"Validação OK"**.

**Adicionar uma 7ª condição** (lógica AND com as outras):

| Campo | Operador | Valor |
|---|---|---|
| `{{13.ad_account_id}}` | Exists | *(deixar vazio — Exists não precisa valor)* |

Assim, se um cliente não cadastrado tentar criar campanha, cai automaticamente na rota fallback "Validação falhou" → envia alerta pra equipe Quirk.

**Opcionalmente** (recomendado), ajusta o texto do alerta da rota fallback pra incluir esse motivo. Algo como adicionar uma linha:

```
ATENCAO: Verificar se este telefone esta cadastrado no Data Store (campos ad_account_id, page_id, access_token, wa_link preenchidos).
```

---

## PARTE 8 — Teste end-to-end

Com tudo acima aplicado, rode um teste real:

1. Pelo seu WhatsApp pessoal, manda no número da Quirk: `quero subir campanha pra apartamento 2 quartos no setor bueno, 450 mil, pra morar. Nome da campanha: Teste Multi Cliente`
2. Responde as perguntas do agente conforme aparecerem
3. Manda uma imagem como criativo
4. Quando o agente perguntar a confirmação final, responde `sim`
5. Cenário deve disparar a rota de execução:
   - Get a record carrega TEU registro (ad_account_id 3771507593117364, page_id 687786881077238, token, wa_link)
   - Extrator gera JSON
   - Parse JSON
   - Validação passa (todas as condições + ad_account_id Exists)
   - D.1 cria campanha em `act_3771507593117364`
   - D.2 cria conjunto
   - D.3 cria criativo com a tua imagem
   - D.4 cria o anúncio em PAUSED

Confere no Gerenciador de Anúncios da Quirk → campanha nova aparece pausada.

---

## PARTE 9 — Como adicionar um cliente real depois

Quando um cliente novo entra na Quirk:

1. **Onboarding Meta** (você já documentou no `Quirk_onboarding_cliente_v1.docx`): cliente compartilha a conta de anúncio dele com a BM da Quirk via Partnership.
2. **Pega os IDs**:
   - `ad_account_id`: aparece em Configurações do Negócio → Contas de Anúncio compartilhadas
   - `page_id`: nas configurações da página dele
   - `wa_link`: o `https://wa.me/<numero>` do WhatsApp dele
3. **access_token**: continua sendo o mesmo da Quirk (do System User QuirkOps), porque ele tem acesso a todas as contas compartilhadas via Partnership.
4. **Cadastra no Data Store**: novo registro com Key = telefone do cliente + os 4 campos.
5. Pronto. Próxima mensagem que aquele número mandar, o sistema já carrega as credenciais certas.

---

## Notas finais

**Por que mudei o `name` do D.4 pra `{{49.campanha.nome}}`:** assim a campanha, o conjunto (que usa `publico_escolhido` como nome) e o anúncio ficam consistentes no Gerenciador. Se quiser diferenciar, pode usar `"name":"{{49.campanha.nome}} - Anuncio"` no D.4.

**Por que o token continua no body em vez de header:** porque foi o que funcionou nos testes e mantém consistência. Não vale mexer sem motivo.

**Sobre a Fase E (futuro):** quando for hora de centralizar manutenção, dá pra trocar essa estratégia de "token por cliente no Data Store" por "token único em variável de cenário do Make". Mas só faz sentido depois que o multi-cliente estiver rodando e você confirmar que vai usar um único System User pra todos. Pro MVP, deixa por cliente.

**Bugs antigos que esse documento corrige de uma vez:**
1. Headers lixo no D.1 e D.2 (limpos)
2. Bug do picture no D.3 (variável + URL fixa grudadas)
3. Nomes hardcoded no D.3 e D.4
4. Token duplicado em 6 lugares (agora centralizado por cliente)
5. Conta fixa em todos os módulos (agora por cliente)
6. Page_id fixo (agora por cliente)
7. wa_link fixo (agora por cliente)
8. Falta de validação de cliente cadastrado (agora bloqueia)
