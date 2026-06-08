#!/usr/bin/env python3
"""
Resolve cidades/bairros desconhecidos via Meta Targeting Search API.

Bug 1: build_targeting_atualizado fazia JSON.parse direto na resposta
do extrator_partial. Mas o LLM retorna ```json ... ``` (markdown).
Parse falhava → cidade=null → 'cidade não encontrada' mesmo pra
'São Paulo'.

Bug 2: tabela de cidades hardcoded só tem ~30 cidades. Bairros
(Freguesia do Ó, Barra Funda), cidades menores e qualquer lugar fora
dessa lista falhava. Cliente tinha que reescrever.

Fix:
1. build_targeting_atualizado parse robusto (extrai JSON de markdown)
2. Se cidade NÃO está na tabela hardcoded, faz HTTP Meta Targeting
   Search API via helpers.httpRequest dentro do próprio Code node.
   API: GET /search?type=adgeolocation&q={cidade}&country_code=BR
   Retorna key + tipo (city, neighborhood, region, zip).
3. Tabela hardcoded continua sendo fallback rápido (capitais)
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


BUILD_TARGETING_ATUALIZADO_V2 = """// Merge do novo público/geo no targeting_meta atual (com search Meta API pra cidades desconhecidas)
const sel = $('process_gestao_step').first().json.gestao.selecionada;
const nv = $('process_gestao_step').first().json.gestao.novo_valor;
const verbo = $('process_gestao_step').first().json.gestao.verbo;
const json_ext = sel.json_extrator_completo;
const targeting = JSON.parse(JSON.stringify(json_ext.targeting_meta || {}));

const PUBS = {
  'Pub Quirk 0': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.1': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003077334693","name":"Condomínio fechado"},{"id":"6003382467537","name":"Casa unifamiliar"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.2': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"},{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003077334693","name":"Condomínio fechado"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.3': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6002965402168","name":"OLX Brasil"},{"id":"6014552641654","name":"Zap Imóveis"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.4': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003077334693","name":"Condomínio fechado"},{"id":"6002965402168","name":"OLX Brasil"},{"id":"6014552641654","name":"Zap Imóveis"},{"id":"6003446239080","name":"Investimento imobiliário"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.5': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003332796032","name":"Desenvolvimento imobiliário"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 2': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6002979192120","name":"Real Estate"},{"id":"6003392721577","name":"Investment"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 3': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 4': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]},{"behaviors":[{"id":"6002714895372","name":"Viajantes frequentes"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 5': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]},{"behaviors":[{"id":"6002714895372","name":"Viajantes frequentes"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 6': {"geo_locations":{"cities":[{"name":"São Paulo, BR"},{"name":"Rio de Janeiro, BR"},{"name":"Brasília, BR"},{"name":"Belo Horizonte, BR"},{"name":"Curitiba, BR"},{"name":"Porto Alegre, BR"}]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 7': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]},{"interests":[{"id":"6003221189867","name":"Piscina"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Invest': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003392721577","name":"Investment"},{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003287729076","name":"Renda passiva"},{"id":"6003143720966","name":"Finanças pessoais"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Invest + Intermediário': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003392721577","name":"Investment"},{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003143720966","name":"Finanças pessoais"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Invest + Alto valor': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003392721577","name":"Investment"}]},{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Profissões': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"id":"112696438745118","name":"Lawyer"},{"id":"108768179146852","name":"Dentist"},{"id":"106215529409578","name":"Judge"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Profissões + Intermediário': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"id":"112696438745118","name":"Lawyer"},{"id":"108768179146852","name":"Dentist"},{"id":"403013926540061","name":"Resident Physician"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Profissões + Alto valor': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"work_positions":[{"id":"112696438745118","name":"Lawyer"},{"id":"106215529409578","name":"Judge"}]},{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Corretores #1': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6002979192120","name":"Real Estate"},{"id":"6778210171187","name":"Corretagem de imóveis"}],"work_positions":[{"id":"171815889531702","name":"Real Estate Agent"},{"id":"111867022164671","name":"Real estate broker"}]}],"targeting_automation":{"advantage_audience":0}}
};
const PUBS_LIST = Object.keys(PUBS);

const CIDADES_HARDCODED = {"São Paulo":"269969","Rio de Janeiro":"267027","Brasília":"245683","Belo Horizonte":"244661","Salvador":"267730","Fortaleza":"253370","Curitiba":"250457","Manaus":"259014","Recife":"266284","Goiânia":"254063","Porto Alegre":"264859","Belém":"244580","Guarulhos":"254529","Campinas":"247071","Maceió":"258670","Natal":"261132","Florianópolis":"253249","Cuiabá":"250332","João Pessoa":"256863","Aracaju":"242415","Teresina":"272278","Campo Grande":"247184","São Luís":"269788","Macapá":"258622","Vitória":"274425","Porto Velho":"265452","Boa Vista":"245039","Palmas":"262281"};

// Parse JSON robusto: extrai do markdown ```json ... ``` se necessário
function parseLLMJson(raw) {
  if (!raw) return null;
  let txt = String(raw).trim();
  txt = txt.replace(/^```(?:json)?\\s*/i, '').replace(/```\\s*$/, '').trim();
  const first = txt.indexOf('{');
  const last = txt.lastIndexOf('}');
  if (first >= 0 && last > first) {
    txt = txt.substring(first, last + 1);
  }
  try { return JSON.parse(txt); } catch(e) { return null; }
}

// Resolve cidade/bairro via Meta Targeting Search API
async function resolveGeoViaMetaSearch(query, accessToken) {
  try {
    const url = 'https://graph.facebook.com/v25.0/search?type=adgeolocation&location_types=[\"city\",\"neighborhood\",\"region\",\"subcity\",\"medium_geo_area\",\"small_geo_area\",\"metro_area\"]&country_code=BR&limit=5&q=' + encodeURIComponent(query) + '&access_token=' + encodeURIComponent(accessToken);
    const resp = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
    const data = (typeof resp === 'string' ? JSON.parse(resp) : resp).data || [];
    if (!data.length) return null;
    // Prioriza city > subcity > neighborhood > region
    const priority = ['city', 'subcity', 'neighborhood', 'medium_geo_area', 'small_geo_area', 'metro_area', 'region'];
    data.sort((a, b) => priority.indexOf(a.type) - priority.indexOf(b.type));
    return data[0];  // {key, name, type, country_code, ...}
  } catch (e) { return null; }
}

let publico_label = null;
let token = '';
try { token = $('load_meta_token').first().json.valor; } catch(e) {}

if (verbo === 'ALTERAR_PUBLICO') {
  if (nv.tipo === 'publico_estruturado') {
    publico_label = PUBS_LIST[nv.numero - 1] || 'Pub Quirk 0';
  } else if (nv.tipo === 'publico_livre') {
    let raw = '';
    try { raw = $('extrator_partial').first().json?.content?.[0]?.text || ''; } catch(e) {}
    publico_label = String(raw).trim();
    // Limpa markdown se vier
    publico_label = publico_label.replace(/^```\\s*/i, '').replace(/```\\s*$/, '').trim();
    if (!PUBS[publico_label]) publico_label = 'Pub Quirk 0';
  }
  const novoTargetingBase = JSON.parse(JSON.stringify(PUBS[publico_label]));
  if (targeting.geo_locations?.cities && targeting.geo_locations.cities.length) {
    novoTargetingBase.geo_locations = targeting.geo_locations;
  }
  if (json_ext.conjunto?.idade_min) novoTargetingBase.age_min = json_ext.conjunto.idade_min;
  if (json_ext.conjunto?.idade_max) novoTargetingBase.age_max = json_ext.conjunto.idade_max;
  novoTargetingBase.targeting_automation = { advantage_audience: 0 };
  return [{ json: { targeting: novoTargetingBase, publico_label_novo: publico_label } }];
}

if (verbo === 'ALTERAR_GEO') {
  let cidade, raio_km;
  if (nv.tipo === 'geo_estruturado') {
    cidade = nv.cidade;
    raio_km = nv.raio_km;
  } else if (nv.tipo === 'geo_livre') {
    let raw = '';
    try { raw = $('extrator_partial').first().json?.content?.[0]?.text || ''; } catch(e) {}
    const parsed = parseLLMJson(raw);
    if (parsed) {
      cidade = parsed.cidade;
      raio_km = parsed.raio_km;
    }
  }

  // Clamp raio
  if (typeof raio_km !== 'number') raio_km = 17;
  if (raio_km < 17) raio_km = 17;
  if (raio_km > 80) raio_km = 80;

  if (!cidade) {
    return [{ json: { error: 'cidade_nao_identificada', cidade, raio_km } }];
  }

  // 1ª tentativa: tabela hardcoded (rápido, sem custo)
  let key = CIDADES_HARDCODED[cidade];
  let resolvedType = key ? 'city_hardcoded' : null;
  let resolvedName = cidade;

  // 2ª tentativa: Meta Targeting Search API
  if (!key && token) {
    const found = await resolveGeoViaMetaSearch.call(this, cidade, token);
    if (found) {
      key = found.key;
      resolvedType = found.type;
      resolvedName = found.name;
    }
  }

  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', cidade, raio_km } }];
  }

  // Bairro/subcity → location_types pode precisar ser ['custom_locations'] mas pra simplicidade
  // usa cities mesmo (Meta aceita key de neighborhoods em geo_locations.cities pra alguns países)
  targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
  return [{ json: { targeting, cidade_label_novo: resolvedName, raio_km_novo: raio_km, geo_tipo: resolvedType } }];
}

return [{ json: { targeting } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['build_targeting_atualizado']['parameters']['jsCode'] = BUILD_TARGETING_ATUALIZADO_V2
    print('  ↻ build_targeting_atualizado v2:')
    print('    - parse robusto (extrai JSON de markdown)')
    print('    - fallback Meta Targeting Search API pra cidades fora da tabela')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Geo dinâmico via Meta Search')


if __name__ == '__main__':
    main()
