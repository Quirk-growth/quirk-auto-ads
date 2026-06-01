#!/usr/bin/env python3
"""
Fix: special_ad_categories=HOUSING obrigatório pra anúncios imobiliários.

Bug observado: adset rodava (em conta velha sem compliance) mas Meta agora
exige declaração de categoria. Sem HOUSING declarado, anúncios imobiliários
disparam compliance review e podem ser rejeitados ou pausados pela Meta.

ALERTA: este fix sozinho NÃO resolve o erro "O anunciante está ausente"
(subcode 3858634). Esse erro vem de Advertiser Identity ausente na conta
de Ads — precisa preencher no BM (Configurações → Conta → Identidade do
anunciante → Razão social + CNPJ + endereço). Sem isso, anúncios com geo
específica (cidade + raio) são bloqueados.

Mudanças:
1. meta_d1_campaign: special_ad_categories=["HOUSING"] + special_ad_category_country=["BR"]
2. merge_brief: remove age_min/age_max/flexible_spec/user_os do targeting
   — Meta HOUSING REJEITA segmentação demográfica fina. Mantém só geo.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


NEW_D1_BODY = """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "objective": "OUTCOME_LEADS",
  "status": "PAUSED",
  "special_ad_categories": ["HOUSING"],
  "special_ad_category_country": ["BR"],
  "is_adset_budget_sharing_enabled": false,
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""


MERGE_BRIEF_HOUSING = """const estado = $('load_estado').first().json.estado;
const parsed = $('parse_extrator').first().json.json_extrator;

if (!parsed) return [{ json: { estado, parse_ok: false } }];

if (parsed.targeting_meta && typeof parsed.targeting_meta.age_min === 'number' && parsed.targeting_meta.age_min < 18) parsed.targeting_meta.age_min = 18;
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_max === 'number' && parsed.targeting_meta.age_max > 65) parsed.targeting_meta.age_max = 65;

const cities = parsed.targeting_meta?.geo_locations?.cities;
if (Array.isArray(cities)) {
  for (const c of cities) {
    if (typeof c.radius === 'number' && c.radius < 17) c.radius = 17;
    if (typeof c.radius === 'number' && c.radius > 80) c.radius = 80;
    if (!c.distance_unit) c.distance_unit = 'kilometer';
  }
}

if (parsed.targeting_meta) {
  parsed.targeting_meta.targeting_automation = { advantage_audience: 0 };
  if (parsed.targeting_meta.custom_audiences) delete parsed.targeting_meta.custom_audiences;

  // HOUSING REJEITA segmentação demográfica — remove age/interests/work_positions/etc
  delete parsed.targeting_meta.age_min;
  delete parsed.targeting_meta.age_max;
  delete parsed.targeting_meta.flexible_spec;
  delete parsed.targeting_meta.user_os;
  delete parsed.targeting_meta.exclusions;
}

estado.brief = { ...estado.brief, ...parsed };
return [{ json: { estado, parse_ok: true } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['meta_d1_campaign']['parameters']['jsonBody'] = NEW_D1_BODY
    print('  ↻ meta_d1_campaign: special_ad_categories=HOUSING + BR')

    nb['merge_brief']['parameters']['jsCode'] = MERGE_BRIEF_HOUSING
    print('  ↻ merge_brief: remove age/interests/etc (HOUSING não aceita)')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ HOUSING category aplicado')


if __name__ == '__main__':
    main()
