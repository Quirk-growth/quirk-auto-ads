"""
c_19_nominatim_geocoding.py

Adiciona geocoding via OpenStreetMap Nominatim no build_targeting_atualizado
como fallback de lat/lng quando a Meta Search não retorna coordenadas (caso
de neighborhood/subcity — confirmado por teste empírico em 2026-06-12).

Antes do c_19:
  - Meta Search → key, name, region ✓
  - latitude/longitude: vem null pra neighborhoods → cai em cities_clamped → raio 17

Depois do c_19:
  - Meta Search → key, name, region
  - Nominatim fallback → latitude, longitude
  - precisaCoordenadas + coords reais → custom_locations com raio exato (1-80km)

Nominatim:
  - URL: https://nominatim.openstreetmap.org/search
  - Grátis, sem chave, requer User-Agent identificador
  - Acceptable use: ~1 req/seg, ok pro volume Quirk
  - Boa cobertura BR (bairros, distritos, regiões)
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# FIX A — Adicionar geocodeViaNominatim ao build_targeting_atualizado
# ─────────────────────────────────────────────────────────────

# Insere a função Nominatim logo após o fim da resolveGeoViaMetaSearch.
# Marcador: final daquela função (return data[0]; } catch...} } )

OLD_AFTER_RESOLVE_FN = """\
    return data[0];
  } catch (e) { return null; }
}

let publico_label = null;"""

NEW_AFTER_RESOLVE_FN = """\
    return data[0];
  } catch (e) { return null; }
}

// Geocoding via OpenStreetMap Nominatim — fallback de lat/lng quando Meta
// não retorna coordenadas (caso comum em neighborhood/subcity).
// API grátis, sem chave, requer User-Agent. Rate ~1 req/seg (suficiente).
async function geocodeViaNominatim(query, estadoHint) {
  try {
    const UF_TO_NOME = {
      AC:'Acre', AL:'Alagoas', AP:'Amapá', AM:'Amazonas', BA:'Bahia', CE:'Ceará',
      DF:'Distrito Federal', ES:'Espírito Santo', GO:'Goiás', MA:'Maranhão',
      MT:'Mato Grosso', MS:'Mato Grosso do Sul', MG:'Minas Gerais', PA:'Pará',
      PB:'Paraíba', PR:'Paraná', PE:'Pernambuco', PI:'Piauí', RJ:'Rio de Janeiro',
      RN:'Rio Grande do Norte', RS:'Rio Grande do Sul', RO:'Rondônia', RR:'Roraima',
      SC:'Santa Catarina', SP:'São Paulo', SE:'Sergipe', TO:'Tocantins'
    };
    let q = String(query || '').trim();
    if (!q) return null;
    if (estadoHint) {
      const hint = String(estadoHint).trim().toUpperCase();
      const nome = UF_TO_NOME[hint] || estadoHint;
      // Evita duplicar estado se já está no nome
      if (!q.toLowerCase().includes(String(nome).toLowerCase())) {
        q = q + ', ' + nome;
      }
    }
    const url = 'https://nominatim.openstreetmap.org/search?format=json&countrycodes=br&limit=3&q=' + encodeURIComponent(q);
    const resp = await this.helpers.httpRequest({
      method: 'GET',
      url,
      headers: { 'User-Agent': 'QuirkAutoAds/1.0 (contato@quirkgrowth.com.br)' },
      returnFullResponse: false,
    });
    const data = (typeof resp === 'string' ? JSON.parse(resp) : resp);
    if (!Array.isArray(data) || !data.length) return null;
    const first = data[0];
    if (first.lat == null || first.lon == null) return null;
    return {
      latitude: Number(first.lat),
      longitude: Number(first.lon),
      display_name: first.display_name || null,
      osm_type: first.osm_type || null
    };
  } catch (e) { return null; }
}

let publico_label = null;"""

# ─────────────────────────────────────────────────────────────
# FIX B — Adicionar fallback Nominatim no fluxo ALTERAR_GEO
# ─────────────────────────────────────────────────────────────

# Insere o bloco Nominatim entre o Meta Search e a decisão branch.
OLD_BEFORE_BRANCH = """\
  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', cidade, estado, raio_km } }];
  }

  let geo_metodo;

  if (precisaCoordenadas && lat != null && lng != null) {"""

NEW_BEFORE_BRANCH = """\
  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', cidade, estado, raio_km } }];
  }

  // Fallback Nominatim: precisamos de coords mas Meta não retornou
  // (caso comum: neighborhood, subcity, e até city às vezes).
  let geo_coords_source = null;
  if (lat != null && lng != null) {
    geo_coords_source = 'meta';
  } else if (precisaCoordenadas) {
    const geo = await geocodeViaNominatim.call(this, cidade, estado);
    if (geo) {
      lat = geo.latitude;
      lng = geo.longitude;
      geo_coords_source = 'nominatim';
      // Não sobrescreve resolvedName — manter o nome do Meta (que é o usado em UI)
    }
  }

  let geo_metodo;

  if (precisaCoordenadas && lat != null && lng != null) {"""

# ─────────────────────────────────────────────────────────────
# FIX C — Incluir geo_coords_source no retorno
# ─────────────────────────────────────────────────────────────

OLD_RETURN = (
    "  return [{ json: { targeting, cidade_label_novo: resolvedName, "
    "raio_km_novo: raio_km, raio_km_pedido, geo_tipo: resolvedType, "
    "geo_metodo, estado_resolvido: resolvedRegion, estado_pedido: estado } }];"
)
NEW_RETURN = (
    "  return [{ json: { targeting, cidade_label_novo: resolvedName, "
    "raio_km_novo: raio_km, raio_km_pedido, geo_tipo: resolvedType, "
    "geo_metodo, geo_coords_source, estado_resolvido: resolvedRegion, "
    "estado_pedido: estado } }];"
)


for node in wf['nodes']:
    if node['name'] != 'build_targeting_atualizado':
        continue
    code = node['parameters']['jsCode']

    if OLD_AFTER_RESOLVE_FN in code:
        code = code.replace(OLD_AFTER_RESOLVE_FN, NEW_AFTER_RESOLVE_FN)
        fixes_applied.append('build_targeting_atualizado: helper geocodeViaNominatim injetado')
    else:
        fixes_failed.append('build_targeting_atualizado: ponto de inserção da helper não encontrado')

    if OLD_BEFORE_BRANCH in code:
        code = code.replace(OLD_BEFORE_BRANCH, NEW_BEFORE_BRANCH)
        fixes_applied.append('build_targeting_atualizado: fallback Nominatim no fluxo ALTERAR_GEO')
    else:
        fixes_failed.append('build_targeting_atualizado: ponto de inserção do fallback não encontrado')

    if OLD_RETURN in code:
        code = code.replace(OLD_RETURN, NEW_RETURN)
        fixes_applied.append('build_targeting_atualizado: retorno inclui geo_coords_source')
    else:
        fixes_failed.append('build_targeting_atualizado: linha de retorno não encontrada')

    node['parameters']['jsCode'] = code
    break


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
    print(f"\n✅ Workflow '{WF_ID}' atualizado.")
else:
    sys.exit(1)
