# Tutorial de uso no WhatsApp — design

**Data:** 2026-07-03
**Status:** Aprovado (design)
**Supersede:** o design anterior de página web (`como-usar-page`) foi descartado — o tutorial vai **dentro do WhatsApp**, não numa página.

## Objetivo

Ensinar o cliente já `ativo` a usar o Auto Ads, **dentro da própria conversa do WhatsApp** — sem sair pra um site. Entregue de duas formas: (1) automaticamente na ativação e (2) sob demanda quando o cliente pede ajuda ou digita `tutorial`. E deixar sempre claro que ajuda está a um pedido de distância.

## Princípio de conteúdo (regra do Renan)

**Simples e direto. Nada de textão.** O tutorial é **uma mensagem única**, escaneável: tópicos, negrito do WhatsApp (`*bold*`), 1 exemplo. Cobre todos os detalhes de uso, enxuto.

## Não-objetivos (YAGNI)

- Sem página web (descartado).
- Sem vídeo.
- Não mexe no onboarding de conexão da conta (já existe).
- Não gera o tutorial via LLM a cada vez — é **texto fixo canônico** (consistência + zero risco de o modelo improvisar).

## Como funciona

**Fonte única:** um **texto fixo do tutorial** (abaixo), usado nos dois gatilhos.

**Gatilho 1 — Automático na ativação:** quando o cliente vira `ativo`, a mensagem de liberação já inclui/segue com o texto do tutorial (primeiras coordenadas) + a frase "digite *tutorial* quando quiser".

**Gatilho 2 — Sob demanda:** o cliente digita `tutorial` (ou variações claras) → o bot responde com o mesmo texto fixo. Pedidos de ajuda em linguagem natural sobre um ponto específico ("como pauso?", "não entendi a verba") continuam sendo respondidos **conversacionalmente pelo agente**, que ao fim lembra: "quer ver tudo? é só digitar *tutorial*."

## Onde mexe (os "motores")

1. **`prompts/classifier.md`** — novo intent **`TUTORIAL`**. Gatilhos: a palavra "tutorial"/"tutoria", "como usar/como funciona a ferramenta", "quero o tutorial", "me ensina a usar". (Dúvidas pontuais NÃO viram TUTORIAL — continuam `OUTRO`/conversa.)
2. **Workflow principal n8n (`fBUin1UPt5xJEp6g`)** — no switch de intent, nova saída `TUTORIAL` → nó `send_tutorial` que envia o texto fixo. (Segue o padrão dos outros `send_*`.)
3. **`prompts/agente_principal.md`** — instrução: sempre que o cliente demonstrar dúvida, explicar de forma simples E lembrar que pode digitar `tutorial` pra ver tudo. Guardar o texto canônico como referência.
4. **Mensagem de ativação** (transição p/ `ativo`, no sub-fluxo de revisão) — incluir o texto do tutorial + "digite *tutorial* quando quiser". Ajuste mínimo na mensagem existente (não criar fluxo novo).

## Texto fixo do tutorial (canônico)

Uma mensagem, formatação WhatsApp:

```
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
```

> **Fidelidade:** campos (tipo, valor, bairro/cidade, objetivo) e comandos (status, pausar, ativar, alterar verba, listar, cancelar) refletem o que o bot aceita (`agente_principal.md` ~linha 120 + intents do classificador). Na implementação, conferir o fraseado dos comandos contra `classifier.md`.

## Testes

1. **Sob demanda:** mandar `tutorial` pro bot de teste → recebe o texto fixo, uma mensagem, formatação ok. Variações ("quero o tutorial") também caem no intent.
2. **Não-regressão do classificador:** "como pauso o anúncio do Batel?" NÃO vira `TUTORIAL` (continua conversa/`PAUSAR` conforme o caso). "status", "pausar", "listar" etc. seguem funcionando.
3. **Ativação:** simular transição de um cliente de teste p/ `ativo` → a mensagem de liberação chega com o tutorial + o lembrete de digitar `tutorial`. Restaurar o estado do cliente de teste depois.
4. **Consistência:** o texto na ativação e o texto sob demanda são idênticos (fonte única).

## Deploy

- Alterações via API do n8n (com **backup** do workflow antes) + edição dos prompts no repo.
- Versionar prompts atualizados + este spec no repo (branch `main`).
- Testar no número/instância de teste antes de considerar pronto.
