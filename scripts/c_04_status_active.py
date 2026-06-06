#!/usr/bin/env python3
"""
Sai da fase de teste: campanhas criadas vão pra ACTIVE direto (não PAUSED).

Mudanças:
1. meta_d1_campaign body: status PAUSED → ACTIVE
2. meta_d2_adset body: status PAUSED → ACTIVE
3. meta_d4_ad body: status PAUSED → ACTIVE
4. build_resposta_ativa: msg deixa de mencionar "PAUSED no Meta" e
   "ativa manualmente no Ads Manager" — agora confirma que está rodando
5. insert_campanha: status_db = CREATED_ACTIVE em vez de CREATED_PAUSED

Importante:
- Tudo que rolar a partir de agora começa entregando imediatamente
- O precheck_meta_account (item 2 hardening) continua barrando se
  spend_cap esgotado, então segurança contra gastar mais que o
  permitido na conta continua valendo
- Verbos PAUSAR/REATIVAR/ENCERRAR continuam funcionando pra controlar
  campanhas vivas
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


NEW_D1_BODY = """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "objective": "OUTCOME_LEADS",
  "status": "ACTIVE",
  "special_ad_categories": [],
  "is_adset_budget_sharing_enabled": false,
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""


NEW_D2_BODY = """={
  "name": "{{ $('validate').item.json.json_extrator.publico_escolhido }}",
  "campaign_id": "{{ $('meta_d1_campaign').item.json.id }}",
  "daily_budget": {{ $('validate').item.json.verba_em_centavos }},
  "billing_event": "IMPRESSIONS",
  "optimization_goal": "CONVERSATIONS",
  "destination_type": "WHATSAPP",
  "promoted_object": {"page_id": "{{ $('validate').item.json.cliente.page_id }}"},
  "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
  "targeting": {{ JSON.stringify($('validate').item.json.json_extrator.targeting_meta) }},
  "dsa_beneficiary": "{{ $('validate').item.json.cliente.nome_cliente || 'Quirk Growth' }}",
  "dsa_payor": "Quirk Growth",
  "status": "ACTIVE",
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""


NEW_D4_BODY = """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "adset_id": "{{ $('meta_d2_adset').item.json.id }}",
  "creative": {"creative_id": "{{ $('meta_d3_creative').item.json.id }}"},
  "status": "ACTIVE",
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""


BUILD_RESPOSTA_ATIVA_V2 = """// Resposta determinística — campanha JÁ está rodando (sem fase paused)
const r = $('check_meta_results').first().json;
const nome = r.json_extrator?.campanha?.nome || 'sua campanha';

const text = `✅ Campanha *${nome}* no ar!\\n\\n` +
  `📋 IDs:\\n` +
  `• Campaign: ${r.campaign_id}\\n` +
  `• Adset: ${r.adset_id}\\n` +
  `• Creative: ${r.creative_id}\\n` +
  `• Ad: ${r.ad_id}\\n\\n` +
  `🚀 Status: ACTIVE — começou a entregar agora.\\n\\n` +
  `Acompanhe com STATUS · ajuste com PAUSAR / REATIVAR / ALTERAR VERBA / ALTERAR PUBLICO / ALTERAR GEO · ou ENCERRAR quando quiser.`;

return [{
  json: {
    content: [{type: 'text', text}]
  }
}];
"""


# insert_campanha: status_db vira CREATED_ACTIVE
INSERT_CAMPANHA_QUERY = """INSERT INTO auto_ads.campanhas (telefone, nome_campanha, ad_account_id, campaign_id, adset_id, creative_id, ad_id, status, json_extrator)
VALUES (
  '{{ $('check_meta_results').item.json.telefone }}',
  '{{ ($('check_meta_results').item.json.json_extrator.campanha.nome || '').replace(/'/g, "''") }}',
  '{{ $('validate').item.json.cliente.ad_account_id }}',
  {{ $('check_meta_results').item.json.campaign_id ? "'" + $('check_meta_results').item.json.campaign_id + "'" : 'NULL' }},
  {{ $('check_meta_results').item.json.adset_id ? "'" + $('check_meta_results').item.json.adset_id + "'" : 'NULL' }},
  {{ $('check_meta_results').item.json.creative_id ? "'" + $('check_meta_results').item.json.creative_id + "'" : 'NULL' }},
  {{ $('check_meta_results').item.json.ad_id ? "'" + $('check_meta_results').item.json.ad_id + "'" : 'NULL' }},
  '{{ $('check_meta_results').item.json.ok ? "CREATED_ACTIVE" : "PARTIAL_FAIL" }}',
  '{{ JSON.stringify($('check_meta_results').item.json.json_extrator).replace(/'/g, "''") }}'::jsonb
)"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['meta_d1_campaign']['parameters']['jsonBody'] = NEW_D1_BODY
    print('  ↻ meta_d1_campaign: status ACTIVE')

    nb['meta_d2_adset']['parameters']['jsonBody'] = NEW_D2_BODY
    print('  ↻ meta_d2_adset: status ACTIVE')

    nb['meta_d4_ad']['parameters']['jsonBody'] = NEW_D4_BODY
    print('  ↻ meta_d4_ad: status ACTIVE')

    nb['build_resposta_ativa']['parameters']['jsCode'] = BUILD_RESPOSTA_ATIVA_V2
    print('  ↻ build_resposta_ativa: msg sem menção a PAUSED')

    nb['insert_campanha']['parameters']['query'] = INSERT_CAMPANHA_QUERY
    print('  ↻ insert_campanha: status_db = CREATED_ACTIVE')

    # Atualizar lista de campanhas no PAUSAR (precisa cobrir ACTIVE também)
    # Já cobre ('CREATED_PAUSED','ACTIVE'). Adicionar 'CREATED_ACTIVE' explicitamente
    # pra futuro multi-cliente. Não estritamente necessário (Meta status real é ACTIVE).

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Sai da fase teste — próximo CONFIRMAR sobe campanha ACTIVE')


if __name__ == '__main__':
    main()
