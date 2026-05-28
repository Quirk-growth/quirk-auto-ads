# Matriz Quirk → Interesses Reais do Meta — Mapeamento pra Aplicar no Prompt + Blueprint

**Data:** 2026-05-24
**Fontes cruzadas:**
1. Prompt-mestre v3.3 (Bloco 3.2 — matriz de públicos Quirk) embedado no cenário Make 4750002
2. `PUBLICOS_BM_QUIRK_2026-05-24.md` (22 contas reais com spend > R$5k em 90d)
3. Catálogo Detailed Targeting da Meta (interests + behaviors + demographics)

---

## ⚠️ Diagnóstico do Gap Crítico (ler antes)

Encontrei um problema sério no fluxo atual do Quirk Auto Ads:

**O prompt v3.3 define a matriz Pub Quirk 0-7 com interesses específicos** (Bloco 3.2). Exemplo: "Pub Quirk 3 = viajantes internacionais + produtos alto valor Brasil".

**Mas o body do D.2 (módulo 56 do blueprint) só envia:**
```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 25,
  "age_max": 60,
  "targeting_automation": {"advantage_audience": 0}
}
```

**Resultado:** o nome "Pub Quirk 3" vai só como rótulo do conjunto, mas a Meta sobe o anúncio com targeting praticamente aberto (Brasil inteiro, 25-60). Os interesses que justificam a matriz **não estão sendo aplicados**.

**Solução proposta neste documento:** adicionar `flexible_spec` (interests + behaviors + demographics) no body do D.2, com o conteúdo derivado do `publico_escolhido` extraído pelo Claude. Vou entregar:
1. Tabela de mapeamento Pub Quirk N → interests Meta
2. JSON pronto por público
3. Ajuste no prompt extrator (Claude) pra retornar o objeto `targeting_meta` em vez de só a string `publico_escolhido`
4. Ajuste no body do D.2

---

## 1. Mapeamento Pub Quirk N → Interesses Meta (Tabela Mestra)

### Pub Quirk 0 — Aberto

> "Aberto — 25-60. Usar com full form p/ ampliar base e qualificar via formulário."

- **Strategy:** sem interests, com Advantage+ Audience ativado (deixar algoritmo escolher)
- **Validação real:** observado em 4 das 22 contas (Quirk Azure, Casa Futuro com "[IG] [20-60] [Aberto]")

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 25,
  "age_max": 60,
  "targeting_automation": {"advantage_audience": 1}
}
```

---

### Pub Quirk 1 — Viajantes frequentes (base)

> "Viajantes frequentes 25-60"

**Interests Meta correspondentes:**
- Viagens (`Travel`)
- Viajante frequente (`Frequent flyer` / `Frequent travelers`)
- Aviação (`Aviation`)
- Aeroportos (`Airports`)
- Hotéis (`Hotels`)
- LATAM Pass / Smiles / TudoAzul (programas de milhagem brasileiros)

**Variações da matriz:**

| Sub | Adicionar a "Viajantes frequentes" |
|---|---|
| 1.1 | + Condomínio (`Gated community` ou `Condominium`) + Casa em condomínio (`Single-family detached home`) + filtro device: iPhone |
| 1.2 | + Bens de luxo (`Luxury goods`) + Condomínio + Investimento imobiliário + iPhone |
| 1.3 | + Investimento imobiliário (`Real estate investing`) + Portais imob. (`OLX Brasil`, `Zap Imóveis`, `VivaReal`) + iPhone |
| 1.4 | + Condomínio + Portais imob. + Investimento imobiliário |
| 1.5 | + Construtoras (`Real estate development`, `Construction`) |

**Validação real:** observado em Ademar (Floripa) - "viajante + internacionais + intermediário"; LOPES GOLD - "PUB- Quirk 1"

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 25,
  "age_max": 60,
  "flexible_spec": [
    {
      "interests": [
        {"name": "Travel"},
        {"name": "Frequent travelers"},
        {"name": "Hotels"}
      ]
    }
  ]
}
```

---

### Pub Quirk 2 — até R$ 700k (LIMITAR, médio/alto Brasil)

> "Viajantes freq. + produtos médio/alto Brasil"

**Interests Meta:**
- Viagens
- Viajante frequente
- Estilo de vida (`Lifestyle`)
- Compras (`Shopping`)
- Casa e jardim (`Home and garden`)
- Investimento (`Investment`)
- Produtos premium/médio porte (interpretar: NÃO incluir interests de luxo extremo)

**Validação real:** Quirk Growth Hunter usa "Pub Interesses Imob" + base de leads Quirk

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 25,
  "age_max": 60,
  "flexible_spec": [
    {
      "interests": [
        {"name": "Travel"},
        {"name": "Frequent travelers"}
      ],
      "behaviors": [
        {"name": "Engaged shoppers"}
      ]
    },
    {
      "interests": [
        {"name": "Investment"},
        {"name": "Real estate"}
      ]
    }
  ]
}
```

> ⚠️ Estrutura com 2 objetos dentro de `flexible_spec` = lógica **AND** entre os blocos (precisa estar nos dois). Dentro de cada bloco, `interests` é **OR** (qualquer um conta).

---

### Pub Quirk 3 — R$ 700k a 1mi (LIMITAR, high ticket)

> "Viajantes internacionais + produtos alto valor Brasil"

**Interests Meta:**
- Viagem internacional (`International travel`)
- Viajante internacional frequente (`Frequent international travelers` - é behavior)
- Hotéis 5 estrelas (`Five-star hotels`, `Luxury hotels`)
- Companhias aéreas premium (`LATAM Premium`, `Emirates`, `Lufthansa First Class`)
- Bens de luxo (`Luxury goods`)
- Carros premium (`BMW`, `Mercedes-Benz`, `Audi`)
- Restaurantes finos (`Fine dining`)

**Validação real:** Inv. Imob. Gestores - "PUB QUIRK [AGRO + VIAJANTES INTERNACIONAIS]"; Classe A - "Viajantes e Reforma"; Ademar - "viajante + internacionais"

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 30,
  "age_max": 60,
  "flexible_spec": [
    {
      "interests": [
        {"name": "International travel"},
        {"name": "Luxury hotels"}
      ],
      "behaviors": [
        {"name": "Frequent international travelers"}
      ]
    },
    {
      "interests": [
        {"name": "Luxury goods"},
        {"name": "Luxury vehicles"},
        {"name": "Fine dining"}
      ]
    }
  ]
}
```

---

### Pub Quirk 4 — R$ 1mi+ (LIMITAR + iPhone 13+)

> "Viaj. internac. + viaj. freq. + alto valor + iPhone 13+"

**Estrutura Pub 3 + filtro de device iPhone 13+:**

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 30,
  "age_max": 64,
  "flexible_spec": [
    {
      "behaviors": [
        {"name": "Frequent international travelers"},
        {"name": "Frequent travelers"}
      ]
    },
    {
      "interests": [
        {"name": "Luxury goods"},
        {"name": "Luxury hotels"},
        {"name": "Luxury vehicles"}
      ]
    }
  ],
  "user_device": ["iPhone 13", "iPhone 13 Pro", "iPhone 13 Pro Max", "iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max", "iPhone 15", "iPhone 15 Plus", "iPhone 15 Pro", "iPhone 15 Pro Max"],
  "user_os": ["iOS"]
}
```

**Validação real:** muito comum nas contas — Casa Futuro, Vinicius Modal, Quirk Azure, todas com "[IPHONE 14+]"

---

### Pub Quirk 5 — Pub 4 + iPad Pro

> "+iPad Pro"

Adicionar ao `user_device` do Pub 4: `"iPad Pro"`, `"iPad Pro 11-inch"`, `"iPad Pro 12.9-inch"`.

---

### Pub Quirk 6 — Pub 5 + Capitais brasileiras

> "= 5 + capitais brasileiras"

Trocar `geo_locations.countries: ["BR"]` por capitais específicas:

```json
"geo_locations": {
  "cities": [
    {"key": "2240449"}, // São Paulo
    {"key": "2240388"}, // Rio de Janeiro
    {"key": "2241455"}, // Brasília
    {"key": "2241355"}, // Belo Horizonte
    {"key": "2241449"}, // Salvador
    {"key": "2241430"}, // Curitiba
    {"key": "2240429"}, // Porto Alegre
    {"key": "2241464"}, // Fortaleza
    {"key": "2241458"}, // Recife
    {"key": "2241413"}  // Manaus
  ]
}
```

> ⚠️ As `key` acima são placeholders ilustrativos. Os IDs reais das cidades devem ser resolvidos via Graph API (`/search?type=adgeolocation&q=São Paulo&country_code=BR`) — incluí instrução na seção 4.

---

### Pub Quirk 7 — Pub 6 + Nicho do cliente

> "= 6 + interesses do nicho do cliente (lancha/golfe/piscina/helicóptero)"

Adicionar bloco extra de `flexible_spec` com o nicho:

| Nicho | Interests Meta |
|---|---|
| Lancha / Iates | `Boating`, `Yachts`, `Sailing` |
| Golfe | `Golf`, `Professional Golfers' Association` |
| Piscina | `Swimming pools`, `Pool design` |
| Helicóptero / Aviação privada | `Helicopters`, `Private aviation`, `Aviation` |
| Equitação / Cavalos | `Horseback riding`, `Equestrianism` |
| Vinhos / Enologia | `Wine`, `Wine tasting`, `Sommelier` |

**Validação real:** Plinio tattoo usa essa lógica com "PET + tattoo + highticket" (nicho pet) — fora do imobiliário mas mesma estrutura

---

### Pub Quirk Invest

> "Mercado financeiro, renda passiva, investimento imobiliário, investidor, ROI (+ Intermediário / + Alto valor)"

**Interests Meta:**
- Investimento (`Investment`)
- Investimento imobiliário (`Real estate investing`)
- Mercado financeiro (`Stock market`, `Financial market`)
- Bolsa de valores (`Stock exchange`, `Bovespa`)
- Renda passiva (`Passive income`)
- Fundos imobiliários / REITs (`Real estate investment trust`)
- Educação financeira (`Financial literacy`, `Personal finance`)
- Empreendedor (`Entrepreneur`)

**Validação real:** 14 das 22 contas usam variação de "Invest" — é o público mais frequente

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 30,
  "age_max": 60,
  "flexible_spec": [
    {
      "interests": [
        {"name": "Investment"},
        {"name": "Real estate investing"},
        {"name": "Stock market"},
        {"name": "Passive income"},
        {"name": "Personal finance"}
      ]
    }
  ]
}
```

**Variações:**
- `Pub Quirk Invest + Intermediário` → adicionar bloco de Profissões intermediárias
- `Pub Quirk Invest + Alto valor` → adicionar bloco de Luxury goods + device iPhone 14+

---

### Pub Quirk Profissões

> "Médicos, juízes, advogados sócios, servidor público, dentistas"

**ATENÇÃO:** Job titles na Meta são **demographics**, não interests. Estrutura diferente:

```json
"targeting": {
  "geo_locations": {"countries": ["BR"]},
  "age_min": 30,
  "age_max": 60,
  "flexible_spec": [
    {
      "work_positions": [
        {"name": "Physician"},
        {"name": "Lawyer"},
        {"name": "Judge"},
        {"name": "Dentist"},
        {"name": "Civil servant"}
      ]
    },
    {
      "interests": [
        {"name": "Medicine"},
        {"name": "Law"},
        {"name": "Healthcare"}
      ]
    }
  ]
}
```

**Validação real:** 12 das 22 contas usam "Profissões" — segundo público mais frequente.
LOPES GOLD usa muito ("PUB- Quirk Profissões"); Inv. Imob. Gestores ("PUB QUIRK - PROFISSÕES")

---

### Pub Corretores

> "#1 completo | #2 intermediário | #3 só cargo de corretor"

**#1 Completo:**
```json
"flexible_spec": [
  {
    "interests": [
      {"name": "Real estate"},
      {"name": "Real estate broker"},
      {"name": "Real estate agency"}
    ],
    "work_positions": [
      {"name": "Real estate agent"},
      {"name": "Real estate broker"}
    ]
  }
]
```

**#2 Intermediário:** só `interests` (sem work_positions, mais aberto)

**#3 Só cargo:** só `work_positions` (mais restrito e qualificado)

**Validação real:** não observado explicitamente nas 22 contas dessa amostra, mas faz parte da matriz oficial.

---

## 2. Públicos que estão nas 22 contas mas NÃO estão no catálogo Quirk

Encontrei na BM padrões que rodam com bom volume mas **não existem na matriz v3.3**. Vale considerar adicionar:

| Público observado | Contas que usam | Sugestão |
|---|---|---|
| **AGRO / Agronegócio** | PB Boutique (Londrina), Casa Futuro, Amanda Iglesias, Inv. Imob. Gestores | Adicionar `Pub Quirk Agro` à matriz: `Agribusiness`, `Agriculture`, `John Deere`, `Soybean`, `Cattle`. Filtro device opcional. |
| **Decoração / Interior Premium** | Residencia Automações (automação), Complexo Tag Guedala ("Decorado") | Adicionar `Pub Quirk Decoração`: `Interior design`, `Home improvement`, `Smart home`. Sobreposição com Pub 7 (nicho) — talvez consolidar. |
| **Reforma + Arquitetos** | Classe A (marcenaria) | Adicionar `Pub Quirk Reforma`: `Home renovation`, `Architecture`, `Carpentry`. Job title: `Architect`. |
| **Compradores Alto Padrão (Lookalike)** | Casa Futuro | Não é interesse — é Custom/Lookalike Audience. Documentar como audience separada. |

---

## 3. JSON Templates Prontos pra Encaixar no Body do D.2

Substituir o body atual do D.2 (módulo 56) por algo do tipo:

```json
{
  "name": "{{49.publico_escolhido}}",
  "campaign_id": "{{52.data.id}}",
  "daily_budget": {{if(49.campanha.verba_diaria > 0; 49.campanha.verba_diaria * 100; 1000)}},
  "billing_event": "IMPRESSIONS",
  "optimization_goal": "CONVERSATIONS",
  "destination_type": "WHATSAPP",
  "promoted_object": {"page_id": "{{13.page_id}}"},
  "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
  "targeting": {{49.targeting_meta}},
  "status": "PAUSED",
  "access_token": "{{13.access_token}}"
}
```

Onde `{{49.targeting_meta}}` é um **objeto JSON inteiro** vindo do Claude extrator. Pra isso funcionar, o prompt extrator precisa devolver o objeto pronto. Próxima seção.

---

## 4. Ajuste no Prompt EXTRATOR (Claude — módulo 49)

**Hoje** o extrator devolve:
```json
{
  "publico_escolhido": "Pub Quirk 4",
  "conjunto": {"idade_min": 25, "idade_max": 60, "geo": "...", "limitar": true}
}
```

**Proposta** — adicionar campo `targeting_meta` com o objeto pronto:

```json
{
  "publico_escolhido": "Pub Quirk 4",
  "conjunto": {"idade_min": 30, "idade_max": 64, "geo": "São Paulo", "limitar": true},
  "targeting_meta": {
    "geo_locations": {"countries": ["BR"]},
    "age_min": 30,
    "age_max": 64,
    "flexible_spec": [
      {"behaviors": [{"name": "Frequent international travelers"}]},
      {"interests": [{"name": "Luxury goods"}, {"name": "Luxury hotels"}]}
    ],
    "user_os": ["iOS"]
  }
}
```

**Como instruir o Claude pra gerar isso:** adicionar uma seção ao prompt extrator com a tabela de mapeamento deste documento, dizendo: "use a tabela X pra preencher `targeting_meta` conforme o `publico_escolhido`".

### Trecho exato a adicionar no prompt extrator:

```
ADIÇÃO AO PROMPT EXTRATOR — preencher targeting_meta

Use a tabela abaixo pra preencher o campo "targeting_meta" do JSON conforme o publico_escolhido:

| publico_escolhido       | targeting_meta (copiar como está)                                                                                                                                                                            |
|-------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Pub Quirk 0             | {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"targeting_automation":{"advantage_audience":1}}                                                                                              |
| Pub Quirk 1             | {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Travel"},{"name":"Frequent travelers"},{"name":"Hotels"}]}]}                                          |
| Pub Quirk 2             | {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Travel"}],"behaviors":[{"name":"Engaged shoppers"}]},{"interests":[{"name":"Real estate"}]}]}        |
| Pub Quirk 3             | {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"name":"International travel"},{"name":"Luxury hotels"}]},{"interests":[{"name":"Luxury goods"}]}]}          |
| Pub Quirk 4             | {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"behaviors":[{"name":"Frequent international travelers"}]},{"interests":[{"name":"Luxury goods"},{"name":"Luxury hotels"}]}],"user_os":["iOS"]} |
| Pub Quirk Invest        | {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"name":"Investment"},{"name":"Real estate investing"},{"name":"Stock market"},{"name":"Passive income"}]}]}  |
| Pub Quirk Profissões    | {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"name":"Physician"},{"name":"Lawyer"},{"name":"Dentist"},{"name":"Judge"}]}]}                            |
| Pub Corretores #1       | {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"name":"Real estate"}],"work_positions":[{"name":"Real estate agent"}]}]}                                     |

REGRAS:
- Se publico_escolhido tiver sub-variação (ex: "Pub Quirk 1.3"), use o JSON base do Pub Quirk 1 e adicione os interests/behaviors extras conforme a sub-variação (ver documento PUBLICOS_META_MAPEADOS_PARA_PROMPT.md).
- Geo: se o cliente mencionou cidade específica, substitua "countries":["BR"] por "cities":[{"name":"<nome da cidade>"}] (a Meta resolve o ID pelo nome).
- Idade: prevalece o que o cliente confirmou; só use os valores padrão da tabela se o cliente não pediu faixa específica.
- NÃO invente interesses fora da tabela.
```

---

## 5. Como resolver os IDs reais dos interesses (necessário antes de produção)

A Meta aceita `{"name": "Luxury goods"}` em alguns endpoints, mas o robusto é usar **IDs numéricos** do catálogo Detailed Targeting. Pra resolver os nomes pra IDs:

```bash
curl -X GET "https://graph.facebook.com/v25.0/search?type=adinterest&q=Luxury%20goods&access_token=SEU_TOKEN"
```

Retorna algo como:
```json
{
  "data": [
    {"id": "6003107902433", "name": "Luxury goods", "audience_size_lower_bound": 1500000000, ...}
  ]
}
```

**Recomendação:** rodar uma vez um script pra resolver os ~40 interesses listados neste documento, salvar o mapeamento `nome → id` num arquivo `interests_ids.json`, e ajustar os JSON templates pra usar IDs em vez de nomes:

```json
{"interests": [{"id": "6003107902433", "name": "Luxury goods"}]}
```

Avise se quer que eu escreva esse script de resolução.

---

## 6. Resumo de Ajustes Necessários

| Onde | O que mudar | Por quê |
|---|---|---|
| **Prompt extrator (módulo 49)** | Adicionar instrução pra gerar `targeting_meta` conforme tabela mestra deste doc | Hoje Claude só devolve o nome do público; precisa devolver o targeting estruturado |
| **Body do D.2 (módulo 56)** | Substituir bloco `"targeting": {...}` por `"targeting": {{49.targeting_meta}}` | Hoje envia só geo+idade; precisa enviar interests/behaviors/work_positions |
| **Prompt-mestre v3.3 (Bloco 3.2)** | (Opcional) atualizar a matriz pra incluir Pub Agro, Pub Decoração, Pub Reforma que aparecem nas contas reais mas não estão no catálogo | Cobertura de nichos observados na BM |
| **Novo arquivo `interests_ids.json`** | Resolver os IDs reais via Graph API search | Robustez (nome pode mudar/traduzir) |
| **Validação no Router 51** | Adicionar checagem: se `targeting_meta` não tiver `flexible_spec` E publico_escolhido ≠ "Pub Quirk 0", bloquear | Evitar subir campanha sem interesses por bug do extrator |

---

## 7. Próximos passos sugeridos (ordem de execução)

1. **Você revisa este mapeamento** e me diz se algum `Pub Quirk N` precisa ajuste de interesses (ex: gestor sênior pode dizer "Pub Quirk 3 também usa Yachts").
2. Decidimos se vamos com **nomes** (mais simples, menos robusto) ou **IDs** (precisa script de resolução).
3. Eu escrevo:
   - Trecho do prompt extrator atualizado
   - Body novo do D.2
   - Script de resolução de IDs (se for o caminho)
4. Você aplica no Make e testa end-to-end com um cliente de teste.

Pronto pra avançar?
