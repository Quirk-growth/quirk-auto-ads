# Aplicar no Make — Prompt Extrator + Body D.2 (prontos pra colar)

**Data:** 2026-05-24
**Pré-requisito:** ter lido `PUBLICOS_META_MAPEADOS_PARA_PROMPT.md`
**Cenário:** Make 4750002 (Auto Ads - test (copy))

---

## ⚠️ Ordem de aplicação (importante)

1. **Primeiro** atualizar o prompt extrator (Claude) — sem isso, `targeting_meta` não vai existir e o D.2 vai quebrar.
2. **Segundo** atualizar o body do D.2 (módulo 56).
3. **Terceiro** rodar 1 teste end-to-end com você como cliente antes de liberar pra cliente real.

---

## PARTE 1 — Prompt Extrator (substituir inteiro)

**Onde:** módulo Claude do EXTRATOR (o que tem `textPrompt: "Você é um EXTRATOR de dados de campanha..."`). É o que alimenta o módulo 49 (Parse JSON).

**Ação:** apagar o `textPrompt` atual e colar o bloco abaixo INTEIRO.

```
Você é um EXTRATOR de dados de campanha. Sua única função é ler a conversa completa abaixo entre o agente de tráfego da Quirk e o cliente, e extrair a estrutura final da campanha que o cliente confirmou.

CONVERSA COMPLETA:
>>>{{13.`histórico`}}<<<

REGRAS GERAIS:
- Responda APENAS com um objeto JSON válido. Nada antes, nada depois. Sem marcadores de código (sem crase tripla), sem explicação, sem comentário.
- Preencha cada campo com o dado REAL extraído da conversa.
- Se um dado não aparece claramente na conversa, use null. NUNCA invente.
- Verba diária e valor do imóvel: devolva apenas o número, sem "R$", sem pontos de milhar.

REGRA DE TARGETING_META (CRÍTICA):
O campo "targeting_meta" deve ser preenchido conforme a TABELA DE PÚBLICOS abaixo, usando o valor de "publico_escolhido" como chave. Copie o objeto JSON da tabela EXATAMENTE como está, depois ajuste age_min/age_max e geo_locations se o cliente confirmou valores diferentes na conversa.

Se o cliente mencionou cidade específica (ex: "Curitiba", "São Paulo"), substitua:
  "geo_locations": {"countries": ["BR"]}
por:
  "geo_locations": {"cities": [{"name": "Curitiba, BR"}]}

Se o cliente mencionou raio (ex: "30km da Gleba Palhano"), adicione "radius": 30 e "distance_unit": "kilometer" dentro do objeto da cidade.

TABELA DE PÚBLICOS (use como referência absoluta — não invente fora dela):

[Pub Quirk 0]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"targeting_automation":{"advantage_audience":1}}

[Pub Quirk 1]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Travel"},{"name":"Frequent travelers"},{"name":"Hotels"}]}]}

[Pub Quirk 1.1]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Travel"},{"name":"Frequent travelers"}]},{"interests":[{"name":"Gated community"},{"name":"Single-family detached home"}]}],"user_os":["iOS"]}

[Pub Quirk 1.2]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Luxury goods"}]},{"interests":[{"name":"Real estate investing"},{"name":"Gated community"}]}],"user_os":["iOS"]}

[Pub Quirk 1.3]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Real estate investing"}]},{"interests":[{"name":"OLX Brasil"},{"name":"Zap Imóveis"},{"name":"VivaReal"}]}],"user_os":["iOS"]}

[Pub Quirk 1.4]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Gated community"}]},{"interests":[{"name":"OLX Brasil"},{"name":"Zap Imóveis"}]},{"interests":[{"name":"Real estate investing"}]}]}

[Pub Quirk 1.5]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Frequent travelers"}]},{"interests":[{"name":"Real estate development"},{"name":"Construction"}]}]}

[Pub Quirk 2]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Travel"},{"name":"Frequent travelers"}],"behaviors":[{"name":"Engaged shoppers"}]},{"interests":[{"name":"Real estate"},{"name":"Investment"}]}]}

[Pub Quirk 3]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"name":"International travel"},{"name":"Luxury hotels"}]},{"interests":[{"name":"Luxury goods"},{"name":"Luxury vehicles"},{"name":"Fine dining"}]}]}

[Pub Quirk 4]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"behaviors":[{"name":"Frequent international travelers"},{"name":"Frequent travelers"}]},{"interests":[{"name":"Luxury goods"},{"name":"Luxury hotels"},{"name":"Luxury vehicles"}]}],"user_os":["iOS"]}

[Pub Quirk 5]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"behaviors":[{"name":"Frequent international travelers"},{"name":"Frequent travelers"}]},{"interests":[{"name":"Luxury goods"},{"name":"Luxury hotels"},{"name":"Luxury vehicles"}]}],"user_os":["iOS"],"user_device":["iPhone 13","iPhone 13 Pro","iPhone 13 Pro Max","iPhone 14","iPhone 14 Pro","iPhone 14 Pro Max","iPhone 15","iPhone 15 Pro","iPhone 15 Pro Max","iPad Pro"]}

[Pub Quirk 6]
{"geo_locations":{"cities":[{"name":"São Paulo, BR"},{"name":"Rio de Janeiro, BR"},{"name":"Brasília, BR"},{"name":"Belo Horizonte, BR"},{"name":"Curitiba, BR"},{"name":"Porto Alegre, BR"},{"name":"Salvador, BR"},{"name":"Fortaleza, BR"},{"name":"Recife, BR"},{"name":"Manaus, BR"}]},"age_min":30,"age_max":64,"flexible_spec":[{"behaviors":[{"name":"Frequent international travelers"}]},{"interests":[{"name":"Luxury goods"},{"name":"Luxury hotels"}]}],"user_os":["iOS"]}

[Pub Quirk 7]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"behaviors":[{"name":"Frequent international travelers"}]},{"interests":[{"name":"Luxury goods"}]},{"interests":[{"name":"Boating"},{"name":"Golf"},{"name":"Swimming pools"},{"name":"Helicopters"}]}],"user_os":["iOS"]}

[Pub Quirk Invest]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"name":"Investment"},{"name":"Real estate investing"},{"name":"Stock market"},{"name":"Passive income"},{"name":"Personal finance"}]}]}

[Pub Quirk Invest + Intermediário]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"name":"Investment"},{"name":"Real estate investing"},{"name":"Stock market"}]},{"work_positions":[{"name":"Manager"},{"name":"Business owner"}]}]}

[Pub Quirk Invest + Alto valor]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"name":"Real estate investing"},{"name":"Stock market"}]},{"interests":[{"name":"Luxury goods"},{"name":"Luxury hotels"}]}],"user_os":["iOS"]}

[Pub Quirk Profissões]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"name":"Physician"},{"name":"Lawyer"},{"name":"Dentist"},{"name":"Judge"},{"name":"Civil servant"}]}]}

[Pub Quirk Profissões + Intermediário]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"name":"Physician"},{"name":"Lawyer"},{"name":"Dentist"},{"name":"Engineer"},{"name":"Architect"}]}]}

[Pub Quirk Profissões + Alto valor]
{"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"work_positions":[{"name":"Physician"},{"name":"Lawyer"},{"name":"Judge"}]},{"interests":[{"name":"Luxury goods"}]}],"user_os":["iOS"]}

[Pub Corretores #1]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Real estate"},{"name":"Real estate broker"}],"work_positions":[{"name":"Real estate agent"},{"name":"Real estate broker"}]}]}

[Pub Corretores #2]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Real estate"},{"name":"Real estate broker"},{"name":"Real estate agency"}]}]}

[Pub Corretores #3]
{"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"work_positions":[{"name":"Real estate agent"},{"name":"Real estate broker"}]}]}

ESTRUTURA DO JSON (responda exatamente neste formato, preenchido):
{
  "objetivo": "moradia ou veraneio ou investimento",
  "faixa_valor": "ate_700k ou 700k_1mi ou acima_1mi ou investidor",
  "trilho_escolhido": "alcance ou precisao",
  "publico_escolhido": "nome do público que o cliente confirmou (ex: Pub Quirk 2)",
  "campanha": {
    "nome": "nome curto e descritivo da campanha",
    "objetivo_meta": "OUTCOME_LEADS",
    "verba_diaria": 0,
    "periodo": "período acordado para a campanha"
  },
  "conjunto": {
    "idade_min": 25,
    "idade_max": 60,
    "geo": "cidade, bairro ou região do imóvel",
    "limitar": true
  },
  "anuncio": {
    "tipo_imovel": "casa ou apartamento ou sobrado ou lote etc",
    "valor_imovel": 0,
    "copy": "o texto do anúncio acordado na conversa"
  },
  "targeting_meta": {}
}

REGRA FINAL:
- "targeting_meta" deve ser preenchido com o OBJETO da tabela acima correspondente ao "publico_escolhido".
- Se houver ajustes do cliente (idade, geo), aplique sobre o objeto base ANTES de colocar no JSON.
- Se "publico_escolhido" não bater com nenhum item da tabela, use o objeto de [Pub Quirk 0] e marque "publico_escolhido" como "Pub Quirk 0" (fallback seguro).

Responda SOMENTE com o JSON preenchido, mais nada.
```

---

## PARTE 2 — Body do D.2 (módulo 56, substituir inteiro)

**Onde:** módulo HTTP id **56** (D.2 — Conjunto de Anúncios), campo "Request content".

**Ação:** apagar o body atual e colar o bloco abaixo. Depois confirmar que **TODAS** as bolhas viraram coloridas.

```json
{"name":"{{49.publico_escolhido}}","campaign_id":"{{52.data.id}}","daily_budget":{{if(49.campanha.verba_diaria > 0; 49.campanha.verba_diaria * 100; 1000)}},"billing_event":"IMPRESSIONS","optimization_goal":"CONVERSATIONS","destination_type":"WHATSAPP","promoted_object":{"page_id":"{{13.page_id}}"},"bid_strategy":"LOWEST_COST_WITHOUT_CAP","targeting":{{49.targeting_meta}},"status":"PAUSED","access_token":"{{13.access_token}}"}
```

**Diferença vs. body atual:**
- Antes: `"targeting":{"geo_locations":{"countries":["BR"]},"age_min":{{49.conjunto.idade_min}},"age_max":{{49.conjunto.idade_max}},"targeting_automation":{"advantage_audience":0}}`
- Agora: `"targeting":{{49.targeting_meta}}` — o objeto inteiro vem do extrator.

**⚠️ Atenção crítica:**
- A bolha `{{49.targeting_meta}}` **NÃO** pode ter aspas em volta. O Make vai serializar o objeto JSON automaticamente. Se você colocar aspas (`"{{49.targeting_meta}}"`), vira string e a Meta rejeita.
- Confira no painel direito do Make que `targeting_meta` aparece como **objeto** (com cadeado de chave) e não como string.

---

## PARTE 3 — Validação do Router 51 (adicionar 8ª condição)

**Onde:** Router 51, filtro da rota "Validação OK".

**Ação:** adicionar nova condição (AND com as existentes):

| Campo | Operador | Valor |
|---|---|---|
| `{{49.targeting_meta}}` | Exists | *(vazio)* |

E uma 9ª condição (defesa em profundidade):

| Campo | Operador | Valor |
|---|---|---|
| `{{49.targeting_meta.geo_locations}}` | Exists | *(vazio)* |

Isso garante que mesmo se o Claude esquecer de preencher `targeting_meta` por algum motivo, a campanha não sobe pela metade.

---

## PARTE 4 — Teste end-to-end (obrigatório antes de produção)

1. Pelo seu WhatsApp pessoal, manda:
   > "Quero subir campanha pra apartamento de 1.5 milhão na Gleba Palhano em Londrina, pra investimento. Nome: Teste Targeting Pub 4"

2. Responda as perguntas do agente conforme aparecerem. Quando ele perguntar o público, confirma "Pub Quirk 4".

3. Manda uma imagem como criativo.

4. Confirma com "sim" no final.

5. **Antes** do D.2 executar, abra a execução no Make e clica na bolha do módulo 49 → confirma que `targeting_meta` está preenchido com um objeto contendo `flexible_spec` com luxury goods/luxury hotels etc.

6. Depois que o D.2 rodar, abra no Gerenciador de Anúncios da Quirk a campanha "Teste Targeting Pub 4" → conjunto criado → aba "Público" → confirma que os interesses Luxury goods / Luxury hotels aparecem.

7. Se aparecer ✅, replicar com Pub Quirk Invest e Pub Quirk Profissões.

---

## PARTE 5 — Sinais de problema e como debugar

| Sintoma | Causa provável | Como corrigir |
|---|---|---|
| Erro 400 no D.2: "targeting_spec is invalid" | Bolha `{{49.targeting_meta}}` está com aspas em volta no body | Tirar as aspas, deixar `"targeting":{{49.targeting_meta}}` |
| Erro 400: "Unknown interest 'XXX'" | Nome do interest não existe no catálogo PT da Meta (foi traduzido) | Trocar pelo nome em inglês ou resolver pra ID (ver PARTE 6) |
| Conjunto sobe mas sem interesses (só geo+idade) | Extrator devolveu `targeting_meta: {}` ou null | Verificar resposta do Claude no painel → revisar o prompt extrator |
| Erro: "audience too small" | Combinação de interesses + geo muito restrita | Pub muito limitado pro mercado — sugerir Pub mais aberto (ex: trocar Pub 4 por Pub 3) |
| Router 51 bloqueou | Falha na 8ª/9ª condição | Logar `targeting_meta` no alerta de erro pra ver o que veio do Claude |

---

## PARTE 6 — Próximo passo: resolver IDs dos interests (recomendado pós-MVP)

Os nomes acima (`"Luxury goods"`, `"Real estate investing"`) funcionam na Meta API mas dependem do catálogo aceitar o nome literal. Pra robustez, depois que o MVP estiver rodando:

1. Rodar uma vez um script com `curl https://graph.facebook.com/v25.0/search?type=adinterest&q=Luxury%20goods&access_token=<TOKEN>` pra cada interesse da tabela.
2. Salvar o mapeamento `nome → id` em `interests_ids.json`.
3. Atualizar a tabela do prompt extrator pra usar IDs em vez de nomes:
   ```
   [Pub Quirk 4]
   {... "flexible_spec":[{"behaviors":[{"id":"6002714895372"}]}, {"interests":[{"id":"6003107902433","name":"Luxury goods"}]}]}
   ```

Avise quando quiser que eu monte esse script (`resolve_interests.sh` ou `.py`).

---

## Checklist de aplicação

- [ ] PARTE 1: prompt do extrator substituído
- [ ] PARTE 2: body do D.2 substituído
- [ ] PARTE 3: condições 8 e 9 adicionadas no Router 51
- [ ] PARTE 4: teste end-to-end com Pub Quirk 4 passou (interesses aparecem no Gerenciador)
- [ ] PARTE 4: teste com Pub Quirk Invest passou
- [ ] PARTE 4: teste com Pub Quirk Profissões passou
- [ ] PARTE 6 (opcional): IDs resolvidos via Graph API search
