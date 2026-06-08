"""
c_14_custom_locations_small_radius.py

Suporte a raios < 17km no ALTERAR_GEO usando geo_locations.custom_locations (lat/lng).

Problema:
  - geo_locations.cities tem raio mínimo de 17km (limitação do Meta)
  - geo_locations.custom_locations com lat/lng suporta raio mínimo de 1km
  - O código anterior clampeava qualquer raio < 17km para 17km silenciosamente

Solução:
  1. build_targeting_atualizado:
     - resolveGeoViaMetaSearch agora pede campos latitude+longitude
     - Se raio < 17km E coordenadas disponíveis → custom_locations (raio exato)
     - Se raio < 17km E sem coordenadas → cities com 17km (aviso)
     - Se raio >= 17km → cities como antes
     - Retorna geo_metodo ('custom_locations' | 'cities' | 'cities_clamped') e raio_km_pedido

  2. build_gestao_response (confirmação antes do SIM):
     - Remove aviso falso de "Meta não aceita < 17km"
     - Mostra raio solicitado sem distorção

  3. build_gestao_confirmation_msg (resultado após execução):
     - Se geo_metodo == 'cities_clamped': mostra aviso de ajuste
     - Se geo_metodo == 'custom_locations': confirma raio exato aplicado
"""

import sys, json, re
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'

wf = get_workflow(WF_ID)
nodes = wf['nodes']

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# FIX 1 — build_targeting_atualizado: raio < 17km via custom_locations
# ─────────────────────────────────────────────────────────────

TARGET_NODE_1 = 'build_targeting_atualizado'

# 1a. resolveGeoViaMetaSearch: adicionar fields=...latitude,longitude
OLD_RESOLVE_URL = (
    "    const url = 'https://graph.facebook.com/v25.0/search?type=adgeolocation"
    "&location_types=[\"city\",\"neighborhood\",\"region\",\"subcity\",\"medium_geo_area\",\"small_geo_area\",\"metro_area\"]"
    "&country_code=BR&limit=5&q=' + encodeURIComponent(query) + '&access_token=' + encodeURIComponent(accessToken);"
)
NEW_RESOLVE_URL = (
    "    const url = 'https://graph.facebook.com/v25.0/search?type=adgeolocation"
    "&location_types=[\"city\",\"neighborhood\",\"region\",\"subcity\",\"medium_geo_area\",\"small_geo_area\",\"metro_area\"]"
    "&country_code=BR&limit=5&fields=key,name,type,country_code,region_id,latitude,longitude&q=' "
    "+ encodeURIComponent(query) + '&access_token=' + encodeURIComponent(accessToken);"
)

# 1b. Substituir o bloco completo do ALTERAR_GEO (do início ao return)
# Identifica pelo início claro
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
}"""

NEW_GEO_BLOCK = """\
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


# ─────────────────────────────────────────────────────────────
# FIX 2 — build_gestao_response: remover aviso falso de "< 17km"
# ─────────────────────────────────────────────────────────────

TARGET_NODE_2 = 'build_gestao_response'

OLD_GEO_CONFIRMACAO = """\
  else if (verbo === 'ALTERAR_GEO') {
    const raio_pedido = nv?.raio_km;
    const raio_final = (typeof raio_pedido !== 'number') ? 17 : Math.min(80, Math.max(17, raio_pedido));
    const nova_loc = nv?.cidade || nv?.descricao || 'nova localização';
    const raio_aviso = (typeof raio_pedido === 'number' && raio_pedido < 17)
      ? ` ⚠️ Meta não aceita raio < 17km — será usado ${raio_final}km.`
      : '';
    resumo = `trocar geo de "${sel.nome}" → ${nova_loc}, raio ${raio_final}km${raio_aviso}`;
  }"""

NEW_GEO_CONFIRMACAO = """\
  else if (verbo === 'ALTERAR_GEO') {
    const raio_pedido = nv?.raio_km;
    const nova_loc = nv?.cidade || nv?.descricao || 'nova localização';
    const raio_display = (typeof raio_pedido !== 'number') ? 17 : Math.max(1, Math.min(80, raio_pedido));
    resumo = `trocar geo de "${sel.nome}" → ${nova_loc}, raio ${raio_display}km`;
  }"""


# ─────────────────────────────────────────────────────────────
# FIX 3 — build_gestao_confirmation_msg: mostrar aviso só se clamped
# ─────────────────────────────────────────────────────────────

TARGET_NODE_3 = 'build_gestao_confirmation_msg'

OLD_GEO_RESULTADO = """\
  else if (v === 'ALTERAR_GEO') {
    let raio_nota = '';
    try {
      const raio_pedido = r.novo_valor?.raio_km;
      const raio_final = $('build_targeting_atualizado').first().json?.raio_km_novo;
      if (typeof raio_pedido === 'number' && raio_final && raio_pedido < raio_final) {
        raio_nota = `\\n⚠️ Raio ajustado de ${raio_pedido}km → ${raio_final}km (mínimo permitido pelo Meta).`;
      }
    } catch(e) {}
    text = `✓ Geo de "${sel.nome}" atualizado.${raio_nota}`;
  }"""

NEW_GEO_RESULTADO = """\
  else if (v === 'ALTERAR_GEO') {
    let raio_nota = '';
    try {
      const tgt = $('build_targeting_atualizado').first().json;
      const raio_pedido = tgt?.raio_km_pedido;
      const raio_final  = tgt?.raio_km_novo;
      const geo_metodo  = tgt?.geo_metodo;
      if (geo_metodo === 'cities_clamped' && typeof raio_pedido === 'number' && raio_final) {
        raio_nota = `\\n⚠️ Geo sem coordenadas precisas — raio ajustado de ${raio_pedido}km → ${raio_final}km.`;
      } else if (geo_metodo === 'custom_locations' && typeof raio_pedido === 'number' && raio_final) {
        raio_nota = `\\n📍 Raio exato de ${raio_final}km aplicado via coordenadas (lat/lng).`;
      }
    } catch(e) {}
    text = `✓ Geo de "${sel.nome}" atualizado.${raio_nota}`;
  }"""


# ─────────────────────────────────────────────────────────────
# Aplicar os fixes
# ─────────────────────────────────────────────────────────────

for node in nodes:
    name = node['name']

    if name == TARGET_NODE_1:
        code = node['parameters']['jsCode']

        # Fix 1a: URL com latitude/longitude
        if OLD_RESOLVE_URL in code:
            code = code.replace(OLD_RESOLVE_URL, NEW_RESOLVE_URL)
            fixes_applied.append(f'{name}: resolveGeoViaMetaSearch URL com campos lat/lng')
        else:
            fixes_failed.append(f'{name}: URL resolveGeoViaMetaSearch não encontrada')

        # Fix 1b: bloco ALTERAR_GEO completo
        if OLD_GEO_BLOCK in code:
            code = code.replace(OLD_GEO_BLOCK, NEW_GEO_BLOCK)
            fixes_applied.append(f'{name}: bloco ALTERAR_GEO reescrito para custom_locations')
        else:
            fixes_failed.append(f'{name}: bloco ALTERAR_GEO não encontrado')

        node['parameters']['jsCode'] = code

    elif name == TARGET_NODE_2:
        code = node['parameters']['jsCode']

        if OLD_GEO_CONFIRMACAO in code:
            code = code.replace(OLD_GEO_CONFIRMACAO, NEW_GEO_CONFIRMACAO)
            fixes_applied.append(f'{name}: aviso falso de 17km removido')
        else:
            fixes_failed.append(f'{name}: bloco confirmação ALTERAR_GEO não encontrado')

        node['parameters']['jsCode'] = code

    elif name == TARGET_NODE_3:
        code = node['parameters']['jsCode']

        if OLD_GEO_RESULTADO in code:
            code = code.replace(OLD_GEO_RESULTADO, NEW_GEO_RESULTADO)
            fixes_applied.append(f'{name}: resultado ALTERAR_GEO atualizado (custom_locations vs clamped)')
        else:
            fixes_failed.append(f'{name}: bloco resultado ALTERAR_GEO não encontrado')

        node['parameters']['jsCode'] = code


# ─────────────────────────────────────────────────────────────
# Salvar
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
