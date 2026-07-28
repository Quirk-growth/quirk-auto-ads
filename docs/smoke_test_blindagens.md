# Smoke test — validação das blindagens

**Como usar:** manda cada mensagem pelo número de teste (não uma conta de cliente — parte disso mexe em campanha de verdade). No fim, manda `encerrar` pra derrubar o que subiu na demo. ~5 min.

Cada bloco diz **o que mandar** e **o que tem que acontecer**.

---

## 1. Tutorial bate com o que o agente exige
- Manda: `tutorial`
- ✅ Deve listar os 7 dados (incluindo **metragem, cômodos, diferencial**), dizer **1 foto OU 1 vídeo** (sem carrossel), verba **R$10–100/dia**, e comandos `status/pausar/reativar/encerrar/nova campanha`.

## 2. Status legível (não mostra status cru)
- Manda: `status` → escolhe uma campanha pelo número
- ✅ Deve aparecer **🟢 No ar** ou **⏸️ Pausada** — nunca `CREATED_ACTIVE`.

## 3. Cliente com 0 campanhas não some (lookup vazio)
- Num número de teste **sem nenhuma campanha**, manda: `pausar`
- ✅ Deve responder **"você não tem campanhas ativas pra pausar"** — não pode ficar mudo.

## 4. Perguntar antes de trocar (estado travado)
- Manda: `pausar` → (ele lista as campanhas) → **não escolhe número**, manda: `alterar geo`
- ✅ Deve **perguntar**: *"Você tem pausar... em andamento. Quer CONTINUAR ou TROCAR?"*
- Manda: `trocar`
- ✅ Deve dizer *"deixei a alteração anterior de lado, manda de novo"*.
- (Bônus: repete e responde `continuar` → deve voltar pra lista de pausar.)

## 5. Lixo de verdade ainda reprompta (não é falso positivo)
- Manda: `pausar` → depois manda: `xyz`
- ✅ Deve dizer **"número inválido, manda entre 1 e N ou CANCELAR"** (não a pergunta de troca).

## 6. Geo: mesma localização, só o raio
- Manda: `alterar geo` → escolhe uma → manda: `mesma localização, raio de 8km`
- ✅ Deve confirmar a troca reaproveitando a cidade atual (não pode dar "erro desconhecido").

## 7. Retry seguro NÃO cria campanha (o bug que te assustou)
- Se em algum momento aparecer **"⚙️ engasgo no Meta, manda SIM de novo"**: manda `sim`
- ✅ Deve **repetir a mesma alteração** — nunca subir uma campanha nova.
- Teste do gate: com uma campanha já no ar, manda `subir denovo`
- ✅ Deve dizer **"sua última campanha já está no ar, manda NOVA CAMPANHA"** — não pode subir outra.

## 8. Review completo antes de subir
- Fluxo de nova campanha até o fim (usa o exemplo do apê do Batel do tutorial).
- ✅ Antes de subir, deve mostrar o **resumo completo** (nome, público, faixa etária, região, verba, criativo) e só aceitar **CONFIRMADO** (não "sim"/"ok").

---

## Não dá pra testar pelo WhatsApp (são trava de banco — validados por teste automatizado)
- **Status inesperado** de cliente → cai numa mensagem de pendência (fallback do roteador).
- **Isolamento multi-tenant** → dois clientes nunca seguram o mesmo asset (índice único, testado com rollback).

## Se algo falhar
Me manda o número de teste e o horário — eu puxo a execução exata no n8n e diagnostico. O guarda automatizado roda com:
```bash
cd ~/quirk_auto_ads/scripts && python3 _audit_erros_conversa.py
```
