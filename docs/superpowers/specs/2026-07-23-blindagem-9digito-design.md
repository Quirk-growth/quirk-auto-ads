# Blindagem do 9º dígito — canonicalizar na escrita + trava no banco — design

**Data:** 2026-07-23
**Status:** Aprovado (design)

## Problema

O 9º dígito de celulares BR já causou **dois incidentes com cliente real** (Jimenne), em caminhos diferentes:

1. **Texto:** WhatsApp entrega `wa_id` sem o 9; `clientes` guarda com o 9 → cliente pago virava "desconhecido" e o fluxo morria em silêncio (corrigido, commits `95e945c`/`5ee5310`).
2. **Mídia:** o caminho de mídia tinha um `media_normalize_phone` **separado** que não foi corrigido junto → vídeo enviado sumia sem erro (corrigido, commit `52438ba`).

A causa raiz é sistêmica: **não existe uma forma canônica garantida** do telefone. Cada ponto normaliza (ou não) do seu jeito, e a divergência só aparece como falha silenciosa.

## Auditoria (estado atual, 2026-07-23)

**Banco — 100% consistente no formato canônico (com o 9):**

| Tabela | Total | Com o 9 (13) | Sem o 9 (12) |
|---|---|---|---|
| `clientes` | 5 | 5 | 0 |
| `conversas` | 3 | 3 | 0 |
| `campanhas` | 46 | 46 | 0 |

**Leitura (entrada) — já blindada nos dois caminhos:**
- `normalize_phone` (texto) e `media_normalize_phone` (mídia): canonicalizam para COM o 9 + geram `telefone_variantes`.
- `select_cliente` e `media_select_cliente`: casam qualquer variante (`telefone IN (...)`) + `alwaysOutputData`.
- Os demais ~30 nós apenas **consomem** `telefone_normalizado` (já canônico) ou `cliente.telefone` (do banco, canônico) — não são risco.

**Buraco remanescente — a ESCRITA:** o gateway do Asaas (`parse_payment` → `upsert_cliente`, workflow `2ZnZqb4wFous4uEs`) grava o telefone **como veio da API do Asaas**, sem canonicalizar. Se um cliente informar o número sem o 9 no checkout, ele entra fora do padrão → a entrada canonicaliza para com o 9 → nunca casa → cliente travado, em silêncio.

## Objetivo

Garantir **uma única forma canônica** do telefone em todo o produto: `55 + DDD(2) + 9 + 8 dígitos` para números brasileiros. Canonicalizar também na escrita e **tornar o invariante obrigatório no banco**, para que qualquer desvio futuro falhe de forma visível em vez de silenciosa.

## Parte A — Gateway canonicaliza antes de gravar

No nó `parse_payment` do workflow **Webhook Gateway** (`2ZnZqb4wFous4uEs`): depois de buscar o cliente na API do Asaas (`GET /v3/customers/{id}`), aplicar a mesma função `com9()` usada na entrada, antes de devolver o campo `telefone` que alimenta o `upsert_cliente`.

```js
function com9(n) {
  if (n && n.startsWith('55')) {
    const rest = n.slice(2);
    if (rest.length === 10) return '55' + rest.slice(0, 2) + '9' + rest.slice(2);
  }
  return n;
}
```

Aplicar sobre o telefone já limpo (só dígitos), exatamente como `normalize_phone` faz. Resultado: **todo cliente criado por pagamento entra canônico**, independente do que o Asaas devolver.

## Parte B — Trava no banco (CHECK constraint)

```sql
ALTER TABLE auto_ads.clientes
  ADD CONSTRAINT clientes_telefone_canonico
  CHECK (telefone !~ '^55' OR telefone ~ '^55[0-9]{2}9[0-9]{8}$');
```

- Números **brasileiros** (começam com `55`) precisam estar no formato canônico.
- Números **internacionais** ficam livres (à prova de futuro).
- `conversas` e `campanhas` têm **FK para `clientes.telefone`** → herdam a garantia automaticamente; **não precisam de constraint própria**.

**Efeito:** qualquer gravação fora do padrão falha imediatamente e de forma visível, em vez de criar um cliente que nunca casa.

## Trade-off aceito

Com a trava, um telefone genuinamente anômalo (que a canonicalização não consiga corrigir) faz o cadastro **falhar** — o cliente pagaria e não seria registrado. Isso é pior pontualmente, porém melhor no geral: falha **visível** que se conserta em minutos, em vez de cliente fantasma travado sem ninguém perceber. Com a Parte A no lugar, a trava não deve disparar no fluxo normal — ela é rede de segurança, não caminho feliz.

## Não-objetivos (YAGNI)

- Não blindar os lookups restantes contra "nó vazio estanca a cadeia" (`select_conversa`, `load_estado_*`, `media_select_conversa`) — fica registrado como próxima frente.
- Não migrar dados (o banco já está 100% canônico).
- Não mexer nos ~30 nós que apenas consomem o valor já canônico.

## Testes

1. **Pré-condição:** confirmar que os 5 clientes atuais **passam** na regex canônica ANTES de criar a constraint (senão o `ALTER TABLE` é rejeitado).
2. **Constraint rejeita:** tentar inserir/atualizar um telefone BR sem o 9 → deve **falhar** com violação de constraint.
3. **Constraint aceita:** telefone canônico (13 dígitos com o 9) → passa; número internacional (não começa com 55) → passa.
4. **Parte A:** simular o `com9()` do gateway com entrada sem o 9 (`554198443588`) → deve produzir `5541998443588`; com entrada já canônica → inalterada.
5. **Não-regressão:** o gateway continua criando/atualizando cliente normalmente (replay de um webhook de pagamento real já capturado).

## Deploy

- Parte A: alteração no `parse_payment` do gateway via API do n8n, com **backup antes** e checagem de sintaxe (`node --check`), padrão dos scripts `g_*`.
- Parte B: `ALTER TABLE` via psycopg2, após validar a pré-condição.
