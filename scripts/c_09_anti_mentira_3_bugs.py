#!/usr/bin/env python3
"""
3 bugs combinados causando bagunça grave (conversa real do Renan):

1. classify_intent v6 era muito estrito — regex /^reativar/ não casava
   com "Quero reativar a campanha". Cliente caía em OUTRO e ia pro
   agente_principal em vez de disparar o verbo.

2. agente_principal MENTIA quando intent=OUTRO. Inventava "vou
   consultar", "te aviso assim que tiver", "puxar a lista pra você" —
   mas o agente é INCAPAZ de executar ações. Sistema é REATIVO: só
   roda quando cliente manda gatilho. Agente sem gatilho não faz nada
   além de responder texto.

3. list_campanhas não filtrava por ad_account_id. Cliente tinha 32
   campanhas no DB (de várias contas antigas), só 3 estavam na conta
   Ignite atual. Lista mostrava tudo, cliente não achava o que queria.

Fixes:

1. classify_intent v7:
   - Regex permissivas (match em qualquer posição da msg):
     REATIVAR: /\\breativar\\b/i
     PAUSAR: /\\bpausar?\\b/i ou /\\bparar\\b/i
     ENCERRAR: /\\bencerrar\\b/i ou /\\barquivar\\b/i
     ALTERAR_*: /alterar.*verba/i, etc.
     STATUS: amplia pra "quais campanhas", "lista", "minhas campanhas",
       "me mande", "ver tudo", etc.

2. agente_principal.md: adiciona regra absoluta anti-mentira:
   - NUNCA prometa "vou consultar/buscar/puxar", "te aviso depois",
     "te mando assim que tiver", "vou reativar pra você"
   - SEMPRE diga o COMANDO exato pro cliente acionar a ação
     (STATUS, PAUSAR, REATIVAR, ENCERRAR, etc.)
   - Lembre: você é REATIVO. NUNCA volta com info sem o cliente pedir.

3. list_campanhas: filtra por ad_account_id da conta atual do cliente.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V7 = """const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();
const estado = $('load_estado').first().json?.estado || {};
const etapaAtual = estado.etapa_atual;

let intent = 'OUTRO';

// Confirmar (sub-projeto A)
if (/^(confirmar|confirmado|confirma)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^(sim,?\\s*subir|pode\\s*subir|sobe\\s*ai)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';

// Subir denovo
else if (/^subir\\s+denovo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^subir\\s+de\\s+novo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/sub(ir|a)\\s+novamente/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/tent(e|a)r?\\s+(de\\s*novo|novamente)/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^repetir$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^refazer$/i.test(msg)) intent = 'SUBIR_DENOVO';

// Nova campanha
else if (/^nova\\s+campanha$/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/come[çc]ar\\s+(uma\\s+)?nova/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/quero\\s+(criar\\s+)?(uma\\s+)?(outra|nova)\\s+campanha/i.test(msg)) intent = 'NOVA_CAMPANHA';

// CANCELAR (prioridade alta — antes de PAUSAR pra evitar "cancela isso" virar pausa)
else if (/^(cancelar|cancela)[!.?]*$/i.test(msg)) intent = 'CANCELAR';
else if (/^deixa\\s+pra\\s+l[áa]/i.test(msg)) intent = 'CANCELAR';

// Gestão B — regex permissivas (palavra em qualquer posição)
else if (/\\bpausar?\\b/i.test(msg) || /\\bparar\\b/i.test(msg)) intent = 'PAUSAR';
else if (/\\breativar?\\b/i.test(msg) || /\\bativar\\b/i.test(msg)) intent = 'REATIVAR';
else if (/voltar\\s+(a\\s+)?(rodar|funcionar)/i.test(msg)) intent = 'REATIVAR';
else if (/retomar/i.test(msg)) intent = 'REATIVAR';
else if (/\\bencerrar\\b/i.test(msg) || /\\barquivar\\b/i.test(msg)) intent = 'ENCERRAR';
else if (/finalizar\\s+campanha/i.test(msg)) intent = 'ENCERRAR';
else if (/(alterar|mudar|trocar|aumentar|diminuir|reduzir)\\s+.{0,15}\\bverba\\b/i.test(msg)) intent = 'ALTERAR_VERBA';
else if (/\\b(alterar|mudar|trocar)\\s+.{0,15}p[uú]blico\\b/i.test(msg)) intent = 'ALTERAR_PUBLICO';
else if (/\\b(alterar|mudar|trocar)\\s+.{0,15}\\bgeo\\b/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/mudar\\s+(de\\s+)?(regi[aã]o|cidade|bairro)/i.test(msg)) intent = 'ALTERAR_GEO';

// STATUS — bem permissivo (cobre 'quais', 'lista', 'minhas', 'me mande')
else if (/^status$/i.test(msg)) intent = 'STATUS';
else if (/ver\\s+(o\\s+)?status/i.test(msg)) intent = 'STATUS';
else if (/como\\s+(est[áa]|vai|t[áa])\\s+.{0,30}campanha/i.test(msg)) intent = 'STATUS';
else if (/^relat[óo]rio$/i.test(msg)) intent = 'STATUS';
else if (/m[ée]tricas?\\s+(da\\s+)?(minha\\s+)?campanha/i.test(msg)) intent = 'STATUS';
else if (/quais?\\s+(s[aã]o\\s+)?.{0,15}campanhas?/i.test(msg)) intent = 'STATUS';
else if (/\\blista\\b.{0,30}campanhas?/i.test(msg)) intent = 'STATUS';
else if (/me\\s+(manda|mande|mostra|envia)\\s+.{0,30}campanhas?/i.test(msg)) intent = 'STATUS';
else if (/^(minhas?\\s+campanhas?|todas\\s+campanhas?|ver\\s+campanhas?)/i.test(msg)) intent = 'STATUS';
else if (/que\\s+campanhas?\\s+(temos|tenho|estao)/i.test(msg)) intent = 'STATUS';

// Auto-NOVA_CAMPANHA quando estado=ativa + msg parece brief
if (intent === 'OUTRO' && etapaAtual === 'ativa') {
  const temImovel = /(apartamento|cobertura|casa|sobrado|terreno|lote|condom[íi]nio|ap\\s*\\d|kitnet|studio)/i.test(msg);
  const temValor = /(r\\$|reais|milh[ãa]o|mil\\b|k\\b|\\d{2,}\\s*mil)/i.test(msg);
  const temRegiao = /(bairro|regi[ãa]o|cidade|setor|jardim|vila|centro)/i.test(msg);
  const sinais = [temImovel, temValor, temRegiao].filter(Boolean).length;
  if (sinais >= 2) intent = 'NOVA_CAMPANHA';
}

return [{ json: { intent, mensagem_texto: msg } }];
"""


LIST_CAMPANHAS_QUERY_V3 = """SELECT
  id AS campanha_id_db,
  nome_campanha AS nome,
  ad_account_id,
  campaign_id AS campaign_id_meta,
  adset_id AS adset_id_meta,
  status,
  json_extrator,
  ultima_alteracao
FROM auto_ads.campanhas
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'
  AND ad_account_id = '{{ $('select_cliente').item.json.ad_account_id }}'
  AND status = ANY(CASE
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'PAUSAR' THEN ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'REATIVAR' THEN ARRAY['PAUSED','CREATED_PAUSED']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'ENCERRAR' THEN ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
    WHEN '{{ $('classify_intent').item.json.intent }}' IN ('ALTERAR_VERBA','ALTERAR_PUBLICO','ALTERAR_GEO') THEN ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
    ELSE ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
  END)
ORDER BY criada_em DESC
LIMIT 10"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V7
    print('  ↻ classify_intent v7: regex permissivas (REATIVAR/PAUSAR em qualquer posição, STATUS amplo)')

    nb['list_campanhas']['parameters']['query'] = LIST_CAMPANHAS_QUERY_V3
    print('  ↻ list_campanhas: filtra por ad_account_id da conta atual')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ classify_intent v7 + list_campanhas filtrado')


if __name__ == '__main__':
    main()
