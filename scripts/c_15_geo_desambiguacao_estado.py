"""
c_15_geo_desambiguacao_estado.py

Dois bugs reportados pelo usuário:

  1. "Brasilândia" → Meta retornou Brasilândia/MT (city) em vez de Brasilândia/SP
     (bairro). O extrator não preservava o estado mencionado, e o
     resolveGeoViaMetaSearch priorizava 'city' > 'neighborhood'.

  2. "Raio de 5km" → virou 17km mesmo com o fix anterior de custom_locations.
     CAUSA RAIZ: o prompt do extrator LLM mandava "raio_km = inteiro entre
     17 e 80 (clamp se necessário)". O LLM clampava ANTES do código JS ver.
     O fix de custom_locations nunca recebia 5km, sempre 17.

Fixes:

  A. build_extrator_partial_geo_body:
     - prompt aceita raio 1–80 (não mais 17 mín)
     - extrai 'estado' separado quando mencionado (ex: "Brasilândia em SP")
     - JSON novo: {cidade, estado, raio_km}

  B. build_targeting_atualizado / resolveGeoViaMetaSearch:
     - pede campo 'region' (nome do estado) da Meta API
     - se 'estado' fornecido: filtra resultados pelo região correspondente
       (aceita UF "SP" ou nome "São Paulo", case-insensitive)
     - quando precisaCoordenadas: prioriza tipos COM lat/lng
       (neighborhood/subcity geralmente têm; city pode não ter)

  C. build_targeting_atualizado ALTERAR_GEO:
     - extrai 'estado' do nv.estado (geo_estruturado) ou parsed.estado (geo_livre)
     - passa pra resolveGeoViaMetaSearch como segundo arg de contexto
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# FIX A — build_extrator_partial_geo_body (prompt LLM)
# ─────────────────────────────────────────────────────────────

# O prompt está armazenado como string JS com escapes unicode.
# Vou substituir o conteúdo do `const system = "..."` inteiro.

OLD_SYSTEM_PROMPT = (
    'const system = "Voc\\u00ea \\u00e9 um extrator de localiza\\u00e7\\u00e3o pra Meta Ads. '
    'L\\u00ea uma descri\\u00e7\\u00e3o em texto livre e devolve APENAS um JSON na forma '
    '{\\"cidade\\":\\"<nome>\\",\\"raio_km\\":<int>} em uma \\u00fanica linha sem nada antes ou depois.'
    '\\n\\nRegras:'
    '\\n- cidade = nome EXATO mencionado pelo cliente (cidade, bairro, regi\\u00e3o, distrito). '
    'N\\u00e3o troque por cidade pai. Ex: \\"Freguesia do \\u00d3\\" \\u2192 \\"Freguesia do \\u00d3\\" '
    '(n\\u00e3o \\"S\\u00e3o Paulo\\"). \\"Setor Bueno\\" \\u2192 \\"Setor Bueno\\" '
    '(n\\u00e3o \\"Goi\\u00e2nia\\"). \\"Barra Funda\\" \\u2192 \\"Barra Funda\\".'
    '\\n- raio_km = inteiro entre 17 e 80 (clamp se necess\\u00e1rio)'
    '\\n- Se n\\u00e3o houver raio mencionado, use 17 (m\\u00ednimo Meta)'
    '\\n- Preserve acentos e capitaliza\\u00e7\\u00e3o correta'
    '\\n\\nResponda SOMENTE o JSON, sem markdown, sem ```.";'
)

NEW_SYSTEM_PROMPT = (
    'const system = "Voc\\u00ea \\u00e9 um extrator de localiza\\u00e7\\u00e3o pra Meta Ads. '
    'L\\u00ea uma descri\\u00e7\\u00e3o em texto livre e devolve APENAS um JSON na forma '
    '{\\"cidade\\":\\"<nome>\\",\\"estado\\":\\"<UF ou nome ou vazio>\\",\\"raio_km\\":<int>} '
    'em uma \\u00fanica linha sem nada antes ou depois.'
    '\\n\\nRegras:'
    '\\n- cidade = nome EXATO mencionado pelo cliente (cidade, bairro, regi\\u00e3o, distrito). '
    'N\\u00e3o troque por cidade pai. Ex: \\"Freguesia do \\u00d3\\" \\u2192 \\"Freguesia do \\u00d3\\" '
    '(n\\u00e3o \\"S\\u00e3o Paulo\\"). \\"Setor Bueno\\" \\u2192 \\"Setor Bueno\\" '
    '(n\\u00e3o \\"Goi\\u00e2nia\\"). \\"Barra Funda\\" \\u2192 \\"Barra Funda\\".'
    '\\n- estado = UF (\\"SP\\", \\"RJ\\", \\"MG\\"...) OU nome do estado se mencionado '
    '(ex: \\"Brasil\\u00e2ndia em SP\\" \\u2192 \\"SP\\"; \\"bairro Santa Cec\\u00edlia, S\\u00e3o Paulo\\" \\u2192 \\"S\\u00e3o Paulo\\"). '
    'Se n\\u00e3o mencionado, devolva string vazia \\"\\".'
    '\\n- raio_km = inteiro entre 1 e 80 (Meta aceita raio m\\u00ednimo 1km via custom_locations '
    'com lat/lng \\u2014 N\\u00c3O clampe para 17). Se cliente disser 5km, devolva 5. Se 0.5km, devolva 1.'
    '\\n- Se n\\u00e3o houver raio mencionado, use 17 (default)'
    '\\n- Preserve acentos e capitaliza\\u00e7\\u00e3o correta'
    '\\n\\nResponda SOMENTE o JSON, sem markdown, sem ```.";'
)

# ─────────────────────────────────────────────────────────────
# FIX B + C — build_targeting_atualizado
# ─────────────────────────────────────────────────────────────

# B1: Substituir resolveGeoViaMetaSearch — aceita estado + filtra + prioriza lat/lng
OLD_RESOLVE_FN = """\
// Resolve cidade/bairro via Meta Targeting Search API
async function resolveGeoViaMetaSearch(query, accessToken) {
  try {
    const url = 'https://graph.facebook.com/v25.0/search?type=adgeolocation&location_types=["city","neighborhood","region","subcity","medium_geo_area","small_geo_area","metro_area"]&country_code=BR&limit=5&fields=key,name,type,country_code,region_id,latitude,longitude&q=' + encodeURIComponent(query) + '&access_token=' + encodeURIComponent(accessToken);
    const resp = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
    const data = (typeof resp === 'string' ? JSON.parse(resp) : resp).data || [];
    if (!data.length) return null;
    // Prioriza city > subcity > neighborhood > region
    const priority = ['city', 'subcity', 'neighborhood', 'medium_geo_area', 'small_geo_area', 'metro_area', 'region'];
    data.sort((a, b) => priority.indexOf(a.type) - priority.indexOf(b.type));
    return data[0];  // {key, name, type, country_code, ...}
  } catch (e) { return null; }
}"""

NEW_RESOLVE_FN = """\
// Resolve cidade/bairro via Meta Targeting Search API
// estadoHint: UF ("SP") ou nome ("São Paulo") opcional — filtra resultados pela região
// preferirComCoordenadas: quando true, prioriza resultados que tenham lat/lng
async function resolveGeoViaMetaSearch(query, accessToken, estadoHint, preferirComCoordenadas) {
  try {
    const url = 'https://graph.facebook.com/v25.0/search?type=adgeolocation&location_types=["city","neighborhood","region","subcity","medium_geo_area","small_geo_area","metro_area"]&country_code=BR&limit=20&fields=key,name,type,country_code,region,region_id,latitude,longitude&q=' + encodeURIComponent(query) + '&access_token=' + encodeURIComponent(accessToken);
    const resp = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
    let data = (typeof resp === 'string' ? JSON.parse(resp) : resp).data || [];
    if (!data.length) return null;

    // UF → nome do estado (Meta retorna nome completo em result.region)
    const UF_TO_NOME = {
      AC:'Acre', AL:'Alagoas', AP:'Amapá', AM:'Amazonas', BA:'Bahia', CE:'Ceará',
      DF:'Distrito Federal', ES:'Espírito Santo', GO:'Goiás', MA:'Maranhão',
      MT:'Mato Grosso', MS:'Mato Grosso do Sul', MG:'Minas Gerais', PA:'Pará',
      PB:'Paraíba', PR:'Paraná', PE:'Pernambuco', PI:'Piauí', RJ:'Rio de Janeiro',
      RN:'Rio Grande do Norte', RS:'Rio Grande do Sul', RO:'Rondônia', RR:'Roraima',
      SC:'Santa Catarina', SP:'São Paulo', SE:'Sergipe', TO:'Tocantins'
    };
    const norm = s => String(s||'').trim().toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');

    // Filtro por estado quando fornecido
    if (estadoHint) {
      const hint = String(estadoHint).trim().toUpperCase();
      const nomeEsperado = UF_TO_NOME[hint] || estadoHint;
      const nomeNorm = norm(nomeEsperado);
      const filtered = data.filter(r => r.region && norm(r.region) === nomeNorm);
      if (filtered.length) data = filtered;
    }

    // Ordenação por prioridade
    // - Default: city > subcity > neighborhood > ...
    // - preferirComCoordenadas (raio<17km): coords primeiro, depois neighborhood/subcity > city
    const tipoOrder = preferirComCoordenadas
      ? ['neighborhood', 'subcity', 'small_geo_area', 'medium_geo_area', 'city', 'metro_area', 'region']
      : ['city', 'subcity', 'neighborhood', 'medium_geo_area', 'small_geo_area', 'metro_area', 'region'];

    data.sort((a, b) => {
      if (preferirComCoordenadas) {
        const aCoords = (a.latitude != null && a.longitude != null) ? 0 : 1;
        const bCoords = (b.latitude != null && b.longitude != null) ? 0 : 1;
        if (aCoords !== bCoords) return aCoords - bCoords;
      }
      return tipoOrder.indexOf(a.type) - tipoOrder.indexOf(b.type);
    });

    return data[0];
  } catch (e) { return null; }
}"""

# B2: Substituir bloco ALTERAR_GEO — passa estado + flag pra função
OLD_GEO_BLOCK = """\
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

  // Salva raio original antes de qualquer ajuste
  const raio_km_pedido = raio_km;

  if (!cidade) {
    return [{ json: { error: 'cidade_nao_identificada', cidade, raio_km } }];
  }

  // Clamp: mínimo 1km (custom_locations), máximo 80km
  if (typeof raio_km !== 'number') raio_km = 17;
  if (raio_km < 1) raio_km = 1;
  if (raio_km > 80) raio_km = 80;

  const precisaCoordenadas = raio_km < 17;

  let key = null;
  let lat = null;
  let lng = null;
  let resolvedType = null;
  let resolvedName = cidade;

  // Para raio >= 17km: tenta tabela hardcoded primeiro (rápido, sem custo)
  // Para raio < 17km: pula hardcoded (não tem coords) e vai direto pro Meta Search
  if (!precisaCoordenadas) {
    const hardcodedKey = CIDADES_HARDCODED[cidade];
    if (hardcodedKey) {
      key = hardcodedKey;
      resolvedType = 'city_hardcoded';
    }
  }

  // Meta Targeting Search API — obrigatório quando precisaCoordenadas ou key ainda null
  if ((!key || precisaCoordenadas) && token) {
    const found = await resolveGeoViaMetaSearch.call(this, cidade, token);
    if (found) {
      key = found.key;
      resolvedType = found.type;
      resolvedName = found.name;
      if (found.latitude != null && found.longitude != null) {
        lat = Number(found.latitude);
        lng = Number(found.longitude);
      }
    }
  }

  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', cidade, raio_km } }];
  }

  let geo_metodo;

  if (precisaCoordenadas && lat != null && lng != null) {
    // ✅ Raio < 17km + coordenadas → custom_locations (mín 1km, raio exato)
    targeting.geo_locations = {
      custom_locations: [{
        latitude: lat,
        longitude: lng,
        radius: raio_km,
        distance_unit: 'kilometer',
        name: resolvedName
      }]
    };
    geo_metodo = 'custom_locations';
  } else if (precisaCoordenadas) {
    // ⚠️ Raio < 17km mas sem coordenadas → ajusta para 17km com cities
    raio_km = 17;
    targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
    geo_metodo = 'cities_clamped';
  } else {
    // Raio >= 17km → cities normalmente
    targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
    geo_metodo = 'cities';
  }

  return [{ json: { targeting, cidade_label_novo: resolvedName, raio_km_novo: raio_km, raio_km_pedido, geo_tipo: resolvedType, geo_metodo } }];
}"""

NEW_GEO_BLOCK = """\
if (verbo === 'ALTERAR_GEO') {
  let cidade, estado, raio_km;
  if (nv.tipo === 'geo_estruturado') {
    cidade = nv.cidade;
    estado = nv.estado || '';
    raio_km = nv.raio_km;
  } else if (nv.tipo === 'geo_livre') {
    let raw = '';
    try { raw = $('extrator_partial').first().json?.content?.[0]?.text || ''; } catch(e) {}
    const parsed = parseLLMJson(raw);
    if (parsed) {
      cidade = parsed.cidade;
      estado = parsed.estado || '';
      raio_km = parsed.raio_km;
    }
  }

  // Salva raio original antes de qualquer ajuste
  const raio_km_pedido = raio_km;

  if (!cidade) {
    return [{ json: { error: 'cidade_nao_identificada', cidade, raio_km } }];
  }

  // Clamp: mínimo 1km (custom_locations), máximo 80km
  if (typeof raio_km !== 'number') raio_km = 17;
  if (raio_km < 1) raio_km = 1;
  if (raio_km > 80) raio_km = 80;

  const precisaCoordenadas = raio_km < 17;

  let key = null;
  let lat = null;
  let lng = null;
  let resolvedType = null;
  let resolvedName = cidade;
  let resolvedRegion = null;

  // Para raio >= 17km E sem estado especificado: tenta tabela hardcoded (rápido, sem custo)
  // Quando estado foi mencionado, sempre vai pra Meta Search pra desambiguar.
  // Para raio < 17km: pula hardcoded (não tem coords) e vai direto pro Meta Search.
  if (!precisaCoordenadas && !estado) {
    const hardcodedKey = CIDADES_HARDCODED[cidade];
    if (hardcodedKey) {
      key = hardcodedKey;
      resolvedType = 'city_hardcoded';
    }
  }

  // Meta Targeting Search API — obrigatório quando precisaCoordenadas, estado fornecido, ou key null
  if ((!key || precisaCoordenadas) && token) {
    const found = await resolveGeoViaMetaSearch.call(this, cidade, token, estado, precisaCoordenadas);
    if (found) {
      key = found.key;
      resolvedType = found.type;
      resolvedName = found.name;
      resolvedRegion = found.region || null;
      if (found.latitude != null && found.longitude != null) {
        lat = Number(found.latitude);
        lng = Number(found.longitude);
      }
    }
  }

  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', cidade, estado, raio_km } }];
  }

  let geo_metodo;

  if (precisaCoordenadas && lat != null && lng != null) {
    // ✅ Raio < 17km + coordenadas → custom_locations (mín 1km, raio exato)
    targeting.geo_locations = {
      custom_locations: [{
        latitude: lat,
        longitude: lng,
        radius: raio_km,
        distance_unit: 'kilometer',
        name: resolvedName
      }]
    };
    geo_metodo = 'custom_locations';
  } else if (precisaCoordenadas) {
    // ⚠️ Raio < 17km mas sem coordenadas → ajusta para 17km com cities
    raio_km = 17;
    targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
    geo_metodo = 'cities_clamped';
  } else {
    // Raio >= 17km → cities normalmente
    targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
    geo_metodo = 'cities';
  }

  return [{ json: { targeting, cidade_label_novo: resolvedName, raio_km_novo: raio_km, raio_km_pedido, geo_tipo: resolvedType, geo_metodo, estado_resolvido: resolvedRegion, estado_pedido: estado } }];
}"""


# ─────────────────────────────────────────────────────────────
# Aplica
# ─────────────────────────────────────────────────────────────

for node in wf['nodes']:
    name = node['name']

    if name == 'build_extrator_partial_geo_body':
        code = node['parameters']['jsCode']
        if OLD_SYSTEM_PROMPT in code:
            code = code.replace(OLD_SYSTEM_PROMPT, NEW_SYSTEM_PROMPT)
            node['parameters']['jsCode'] = code
            fixes_applied.append(f'{name}: prompt LLM aceita raio 1-80 + extrai estado')
        else:
            fixes_failed.append(f'{name}: system prompt original não encontrado')

    elif name == 'build_targeting_atualizado':
        code = node['parameters']['jsCode']

        if OLD_RESOLVE_FN in code:
            code = code.replace(OLD_RESOLVE_FN, NEW_RESOLVE_FN)
            fixes_applied.append(f'{name}: resolveGeoViaMetaSearch filtra por estado + prioriza coords')
        else:
            fixes_failed.append(f'{name}: resolveGeoViaMetaSearch não encontrada')

        if OLD_GEO_BLOCK in code:
            code = code.replace(OLD_GEO_BLOCK, NEW_GEO_BLOCK)
            fixes_applied.append(f'{name}: ALTERAR_GEO passa estado + preferência por coords')
        else:
            fixes_failed.append(f'{name}: bloco ALTERAR_GEO não encontrado')

        node['parameters']['jsCode'] = code


# ─────────────────────────────────────────────────────────────
# Salva
# ─────────────────────────────────────────────────────────────

print("=== FIXES APLICADOS ===")
for f in fixes_applied:
    print(f"  ✅ {f}")

print("\n=== FIXES FALHADOS ===")
for f in fixes_failed:
    print(f"  ❌ {f}")

if not fixes_failed:
    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean_settings)
    print(f"\n✅ Workflow '{WF_ID}' atualizado com sucesso.")
else:
    print(f"\n⚠️  {len(fixes_failed)} fix(es) falharam — workflow NÃO salvo.")
    sys.exit(1)
