#!/usr/bin/env python3
"""Builders de extrator parcial (publico/geo) + build_targeting_atualizado."""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


SYS_PROMPT_PUBLICO = """Você é um classificador de público de marketing imobiliário. Você lê uma descrição em texto livre de um cliente e devolve APENAS o nome do Pub Quirk que melhor mapeia, em uma única linha sem aspas, sem nada além.

Tabela de Pubs Quirk disponíveis:
- Pub Quirk 0 (broad)
- Pub Quirk 1 (BR 25-60 broad)
- Pub Quirk 1.1 (Condomínio fechado + Casa unifamiliar)
- Pub Quirk 1.2 (Bens de luxo + Investimento + Condomínio)
- Pub Quirk 1.3 (Investimento + OLX + Zap Imóveis)
- Pub Quirk 1.4 (Condomínio + OLX + Zap + Investimento)
- Pub Quirk 1.5 (Desenvolvimento imobiliário)
- Pub Quirk 2 (Real Estate + Investment)
- Pub Quirk 3 (Bens de luxo 30-60)
- Pub Quirk 4 (Bens de luxo + Viajantes 30-64)
- Pub Quirk 5 (Bens de luxo + Viajantes — variante)
- Pub Quirk 6 (capitais grandes + Bens de luxo)
- Pub Quirk 7 (Bens de luxo + Piscina)
- Pub Quirk Invest (Investment + Renda passiva + Finanças)
- Pub Quirk Invest + Intermediário
- Pub Quirk Invest + Alto valor
- Pub Quirk Profissões (Lawyer, Dentist, Judge)
- Pub Quirk Profissões + Intermediário
- Pub Quirk Profissões + Alto valor
- Pub Corretores #1

Devolva APENAS o nome exato de um item da lista. Sem explicação."""


SYS_PROMPT_GEO = """Você é um extrator de geo pra marketing. Lê descrição em texto livre e devolve APENAS um JSON na forma {"cidade":"<nome>","raio_km":<int>} em uma única linha sem nada antes ou depois.

Regras:
- cidade = nome canônico da cidade brasileira (ex: "São Paulo", "Goiânia", "Rio de Janeiro")
- raio_km = inteiro entre 17 e 80 (clamp se necessário)
- Se não houver raio mencionado, use 17 (mínimo Meta)

Responda SOMENTE o JSON."""


def build_publico_body_code():
    sys_q = json.dumps(SYS_PROMPT_PUBLICO)
    return f"""const system = {sys_q};
const desc = String($('process_gestao_step').first().json.gestao.novo_valor.descricao || '').trim();
return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 50,
    temperature: 0,
    system,
    messages: [{{ role: "user", content: desc }}]
  }}
}}];
"""


def build_geo_body_code():
    sys_q = json.dumps(SYS_PROMPT_GEO)
    return f"""const system = {sys_q};
const desc = String($('process_gestao_step').first().json.gestao.novo_valor.descricao || '').trim();
return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 100,
    temperature: 0,
    system,
    messages: [{{ role: "user", content: desc }}]
  }}
}}];
"""


BUILD_TARGETING_ATUALIZADO_CODE = """// Merge do novo público/geo no targeting_meta atual
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

const CIDADES = {"São Paulo":"269969","Rio de Janeiro":"267027","Brasília":"245683","Belo Horizonte":"244661","Salvador":"267730","Fortaleza":"253370","Curitiba":"250457","Manaus":"259014","Recife":"266284","Goiânia":"254063","Porto Alegre":"264859","Belém":"244580","Guarulhos":"254529","Campinas":"247071","Maceió":"258670","Natal":"261132","Florianópolis":"253249","Cuiabá":"250332","João Pessoa":"256863","Aracaju":"242415","Teresina":"272278","Campo Grande":"247184","São Luís":"269788","Macapá":"258622","Vitória":"274425","Porto Velho":"265452","Boa Vista":"245039","Palmas":"262281"};

let publico_label = null;

if (verbo === 'ALTERAR_PUBLICO') {
  if (nv.tipo === 'publico_estruturado') {
    publico_label = PUBS_LIST[nv.numero - 1] || 'Pub Quirk 0';
  } else if (nv.tipo === 'publico_livre') {
    publico_label = String($('extrator_partial').first().json?.content?.[0]?.text || 'Pub Quirk 0').trim();
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
    try {
      const parsed = JSON.parse(String($('extrator_partial').first().json?.content?.[0]?.text || '{}').trim());
      cidade = parsed.cidade;
      raio_km = parsed.raio_km;
    } catch(e) { cidade = null; raio_km = null; }
  }
  if (typeof raio_km === 'number' && raio_km < 17) raio_km = 17;
  if (typeof raio_km === 'number' && raio_km > 80) raio_km = 80;
  const key = CIDADES[cidade] || null;
  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada', cidade, raio_km } }];
  }
  targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
  return [{ json: { targeting, cidade_label_novo: cidade, raio_km_novo: raio_km } }];
}

return [{ json: { targeting } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'build_extrator_partial_publico_body' not in nb:
        wf['nodes'].append({
            'id': 'build_extrator_partial_publico_body', 'name': 'build_extrator_partial_publico_body',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2550, 250],
            'parameters': {'language': 'javaScript', 'jsCode': build_publico_body_code()}
        })
        print('  + build_extrator_partial_publico_body adicionado')

    if 'build_extrator_partial_geo_body' not in nb:
        wf['nodes'].append({
            'id': 'build_extrator_partial_geo_body', 'name': 'build_extrator_partial_geo_body',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2550, 400],
            'parameters': {'language': 'javaScript', 'jsCode': build_geo_body_code()}
        })
        print('  + build_extrator_partial_geo_body adicionado')

    if 'build_targeting_atualizado' not in nb:
        wf['nodes'].append({
            'id': 'build_targeting_atualizado', 'name': 'build_targeting_atualizado',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2800, 325],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_TARGETING_ATUALIZADO_CODE}
        })
        print('  + build_targeting_atualizado adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 6 aplicada')


if __name__ == '__main__':
    main()
