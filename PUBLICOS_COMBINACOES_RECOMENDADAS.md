# Combinações de Públicos Recomendadas — Quirk Auto Ads

**Base:** análise dos 22 ad accounts com spend > R$5k em 90 dias (snapshot 2026-05-24)
**Documento-fonte:** `PUBLICOS_BM_QUIRK_2026-05-24.md`

---

## ⚠️ Como esse documento foi construído (importante ler)

O Meta Ads MCP **não expõe o objeto `targeting`** dos ad sets. O que fiz:

1. **Extraí dos nomes** dos ad sets os interesses e temas que os gestores Quirk explicitamente mencionaram (ex: ad set chamado "PUB QUIRK [AGRO + VIAJANTES INTERNACIONAIS]" → interesses: agronegócio + viajantes internacionais).
2. **Crucei a frequência** entre as 22 contas pra identificar o que se repete.
3. **Mapeei pros interesses oficiais do Meta** (Detailed Targeting) que correspondem a esses temas — isso é inferência baseada em conhecimento do catálogo Meta, não dado extraído.

**Limitação real:** alguns ad sets têm nomes genéricos ("Pub Quirk 0", "Pub Quirk 12") que não revelam interesses — esses são playbook interno da Quirk e estão fora desta análise.

**Pra validar com dados reais:** rodar script Python na Graph API extraindo o campo `targeting.flexible_spec.interests` de cada ad set. Esse documento é a **hipótese de partida**, não a verdade.

---

## 1. Mapa de Interesses Recorrentes na BM

Frequência observada nos nomes dos ad sets das 22 contas:

### A) Padrão Imobiliário (15 das 22 contas — alta convergência)

| Tema | Contas que usam | Interesse Meta correspondente (sugestão) |
|---|---|---|
| **Investidor / Investimento Imobiliário** | 14 contas | "Investimento imobiliário", "Investidor", "Bolsa de valores", "Fundos imobiliários", "Renda passiva" |
| **Profissões high-ticket / Cargos** | 12 contas | "CEO", "Diretor", "Empresário", "Empreendedor", "Médico", "Advogado", "Engenheiro" |
| **Alto Padrão / Alto Valor / High Ticket** | 10 contas | "Bens de luxo", "Estilo de vida luxuoso", "Imóveis de luxo", "Casas de alto padrão" |
| **Viajantes Internacionais** | 6 contas | "Viagem internacional", "Viagens (interesse)", "Aeroportos", "Companhias aéreas premium" |
| **Agronegócio / AGRO** | 4 contas (PB Boutique, Casa Futuro, Amanda Iglesias, Inv. Imob. Gestores) | "Agronegócio", "Agricultura", "Pecuária", "John Deere", "Tratores" |
| **Empreendedor Lifestyle** | 3 contas | "Empreendedorismo", "Negócios e indústria", "Pequenas empresas" |
| **Decoração / Interior Premium** | 2 contas (Residencia Automações, Complexo Tag Guedala) | "Decoração de interiores", "Arquitetura", "Design de interiores", "Casa & lar" |
| **Reforma** | 1 conta (Classe A) | "Reforma residencial", "Marcenaria", "Móveis sob medida" |

### B) Padrão por Estratégia de Audiência (não-interesse)

| Tipo | Contas que usam |
|---|---|
| **Lookalike 1% Lista de clientes** | 11 contas |
| **Lookalike Seguidores IG** | 4 contas (Casa Futuro, Suits, etc) |
| **Engajamento 7D / 14D / 365D** | 18 contas (quase universal) |
| **Remarketing 60D / 365D** | 5 contas |
| **Advantage+ Audience (ADV)** | 9 contas |
| **Aberto (sem targeting)** | 4 contas (Azure INFLUENCER, Complexo) |

### C) Padrão de Filtro Geo/Demo recorrente

| Filtro | Padrão dominante |
|---|---|
| **Idade** | 25-55 (mais comum), 30-64 (alto padrão), 23-50 (clínica) |
| **Gênero** | "H M" padrão; "M" só clínica estética e moda plus size; "H" só Plinio (pet+tattoo) |
| **Geo** | Raio em km da loja/imóvel: 5km, 10km, 16km, 25km, 30km, 35km — quase nunca estado inteiro |
| **Dispositivo** | iPhone (especialmente iPhone 14+) usado como filtro de renda em 17 das 22 contas |

---

## 2. Combinações Recomendadas (Templates do Quirk Auto Ads)

Estruturei em **6 templates** baseados nos padrões mais convergentes. Cada template combina:
- Interesses do Meta (Detailed Targeting)
- Faixa etária
- Filtro geo
- Filtro de dispositivo (proxy de renda)

### TEMPLATE 1 — Investidor Imobiliário Premium (10 das 22 contas)

**Quando usar:** lançamentos, imóveis acima de R$ 800k, investimento

**Interesses (combinar com "qualquer um"):**
- Investimento imobiliário
- Mercado financeiro
- Bolsa de valores
- Fundos de investimento
- Renda passiva
- Educação financeira

**Filtros:**
- Idade: 30-64
- Gênero: H M
- Geo: raio 20km do imóvel/cidade-alvo
- Dispositivo: iOS 14+ (filtro de renda)

**Frequência na BM:** Quirk Growth Hunter, LOPES GOLD, Complexo Tag Guedala, Quirk Azure, Inv. Imobiliários PA, Inv. Imob. Gestores, Vinicius Modal, Casa Futuro, Thiago Westim, Amanda Iglesias

---

### TEMPLATE 2 — Profissões High-Ticket (12 contas)

**Quando usar:** público B2C de poder aquisitivo alto, sem nicho específico

**Interesses (cargos):**
- CEO
- Diretor executivo
- Empresário
- Médico
- Engenheiro
- Advogado
- Arquiteto
- Empreendedor

**Filtros:**
- Idade: 30-60
- Gênero: H M
- Geo: capital + região metropolitana (raio 30km)
- Dispositivo: iOS 14+ OU Galaxy S (linha premium Samsung)

**Variação:** "Profissões + Agro" (PB Boutique, Casa Futuro) — adicionar interesses agro pra mercados de interior

---

### TEMPLATE 3 — Alto Padrão / Lifestyle Luxo (10 contas)

**Quando usar:** imóveis acima de R$ 1.5M, joias high-ticket, bens de luxo

**Interesses:**
- Bens de luxo
- Carros de luxo (BMW, Mercedes-Benz, Audi, Porsche)
- Hotéis 5 estrelas
- Restaurantes finos
- Jantares de gala
- Iates / náutica
- Joias finas
- Moda de luxo (Louis Vuitton, Gucci, Prada)

**Filtros:**
- Idade: 35-64
- Gênero: H M
- Geo: bairros nobres específicos (raio 5-10km de bairro alvo)
- Dispositivo: iPhone 14+ obrigatório

**Frequência:** Suits Joias, Complexo Tag Guedala (decorado), LOPES GOLD, Residencia Automações, Quirk Azure, Inv. Imob. Gestores

---

### TEMPLATE 4 — Viajantes Internacionais + Investidor (6 contas)

**Quando usar:** imóveis para investimento ou segunda residência, perfil cosmopolita

**Interesses (combinar AND entre os dois grupos):**

Grupo A (viagem):
- Viagem internacional
- Aeroportos internacionais (Guarulhos, Galeão, Confins)
- Companhias aéreas premium (LATAM Premium, Emirates, Lufthansa)
- Hotéis Marriott / Hilton / Hyatt

Grupo B (investimento):
- Investimento imobiliário
- Bolsa de valores
- Educação financeira

**Filtros:**
- Idade: 30-64
- Gênero: H M
- Geo: capitais
- Dispositivo: iOS 14+

**Frequência:** Inv. Imobiliários PA, Inv. Imob. Gestores, Ademar (Floripa), Classe A, Casa Futuro, LOPES GOLD

---

### TEMPLATE 5 — Agronegócio + Profissões (4 contas)

**Quando usar:** cidades do interior agrícola (Londrina, Sinop, Cuiabá, Rondonópolis)

**Interesses (Grupo A AND Grupo B):**

Grupo A (agro):
- Agronegócio
- Agricultura
- Pecuária
- Soja / Milho / Café
- John Deere / Case / New Holland
- Caminhonetes (Ranger, Hilux, S10)

Grupo B (poder aquisitivo):
- CEO / Diretor / Empresário
- Pequenas e médias empresas
- Investimento

**Filtros:**
- Idade: 30-65
- Gênero: H (predominante no agro, validar com cliente)
- Geo: cidade do interior + raio 50-100km
- Dispositivo: iPhone 14+ ou Galaxy S

**Frequência:** PB Boutique (Londrina), Casa Futuro, Amanda Iglesias, Inv. Imob. Gestores

---

### TEMPLATE 6 — Decoração + Interior Premium (2 contas + transversal)

**Quando usar:** apartamentos decorados, marcenaria de luxo, automação residencial

**Interesses:**
- Decoração de interiores
- Arquitetura residencial
- Design de interiores
- Casa & lar (categoria)
- Marcenaria
- Automação residencial / Smart home
- Móveis sob medida
- Revistas: Casa e Jardim, Arquitetura e Construção, Casa Vogue

**Filtros:**
- Idade: 30-60
- Gênero: M (predominante decoração, validar)
- Geo: capitais + bairros classe A/B (raio 10-15km)
- Dispositivo: iPhone 14+

**Frequência:** Residencia Automações, Complexo Tag Guedala ("Decorado"), Classe A (parcial)

---

## 3. Combinações de **Audiências** (não-interesse) que se repetem

Essas não são "interesses" mas são padrões de público que aparecem em quase todas as contas e devem fazer parte do playbook:

### Stack padrão Quirk (observado em 18 das 22 contas)

```
1. Custom Audience: Engajamento IG 7D + Engajamento IG 14D  ←  warm
2. Custom Audience: Lista CRM (clientes + leads históricos)   ←  hot
3. Lookalike 1%: da Lista CRM acima                           ←  cold qualificado
4. Lookalike 1%: dos Seguidores IG                            ←  cold qualificado
5. Interesses (Templates 1-6 acima)                            ←  cold genérico
6. Advantage+ Audience (ADV)                                  ←  algoritmo
```

Esse stack é o "playbook Quirk" implícito. **Recomendação pro Quirk Auto Ads:** automatizar a criação desses 6 conjuntos por cliente novo, com o template de interesse variando conforme o tipo de negócio.

---

## 4. Recomendação de Estrutura de Campanha (default)

Baseado no que rodou com R$5k+ em 90d:

**Campanha tipo 1 — Conversão de Leads (Forms)**
- 1 ad set Advantage+ Audience (sem interesse fixo, deixa o algoritmo escolher)
- 1 ad set Interesses do Template apropriado
- 1 ad set Lookalike 1% Lista CRM
- 1 ad set Engajamento 7D + 14D (warm/remarketing)

**Campanha tipo 2 — Mensagens WhatsApp (CTWA)**
- 1 ad set "QUENTE": Engaj 7D + visitantes
- 1 ad set "FRIO": Interesses + LAL 1% Lista
- Filtros: WhatsApp + iPhone (pra renda)

**Campanha tipo 3 — Tráfego/Awareness (raro nas contas grandes — só 2 das 22 usavam)**
- Geralmente não recomendar como padrão Quirk

---

## 5. Sinais de alerta encontrados

Coisas que vi e que valem mencionar:

- **Quirk Azure INFLUENCER** roda 30+ ad sets idênticos "[IG] [20-60] [SP] [Aberto]" — possível duplicação/lixo, não padrão
- **LOPES GOLD** tem 200+ ad sets ativos no período — sinal de falta de consolidação, oportunidade pra usar Auto Ads pra padronizar
- **Públicos "Aberto" (sem targeting)** aparecem em 4 contas — quando o ADV+ funciona, é o melhor caminho; quando não, é desperdício
- **Faixa etária 20-60** muito ampla aparece em algumas contas — geralmente performa pior que 30-60 (validar caso a caso)

---

## 6. Próximo passo crítico

Esse documento é a **hipótese de partida pro Quirk Auto Ads**. Pra fechar com dados reais:

1. **Validar interesses inferidos** via Graph API (`/{adset_id}?fields=targeting`)
2. **Cruzar com performance** (CPL, CTR, ROAS) dos ad sets que usam cada combinação — isso o MCP me dá direto, posso fazer numa segunda rodada
3. **Eliminar interesses que aparecem nos nomes mas performam mal** (ex: se "Viajantes Internacionais" tem CPL 3x maior que "Investidor", talvez não entre no template default)

Avise se quer que eu rode a análise de performance (passo 2) — isso eu consigo agora pelo MCP.
