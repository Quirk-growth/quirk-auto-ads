"""
c_21_resolve_geo_criacao.py

Replica os fixes do ALTERAR_GEO (c_14/c_15/c_19) no fluxo de CRIAÇÃO.

Problema antes do c_21:
  - build_extrator_body (LLM) tem tabela hardcoded de ~80 capitais
  - Bairros, distritos, regiões fora da tabela caem no fallback {countries:['BR']}
  - validate rejeita corretamente (c_13) → cliente vê erro de geo
  - Consequência: cliente novo pedindo "Brasilândia, SP, 5km" na CRIAÇÃO não consegue subir campanha
  - ALTERAR_GEO já cobre esse caso, mas isso é UX ruim — força criar errado pra depois alterar

Fix do c_21:
  - Cria nó `load_meta_token_criacao` (cópia do load_meta_token) ANTES do validate
  - Cria nó `resolve_geo_criacao` (Code) que pós-processa o targeting_meta:
    * Lê conjunto.geo_cidade, conjunto.geo_estado (novo campo), conjunto.geo_raio_km
    * Roda Meta Search + Nominatim (mesma lógica do build_targeting_atualizado)
    * Sobrescreve targeting_meta.geo_locations com a melhor representação
    * Atualiza brief/estado com o resultado
  - Reordena fluxo: parse_extrator → merge_brief → persist_brief
                    → load_meta_token_criacao → resolve_geo_criacao → validate → if_valid

  - Atualiza prompt do build_extrator_body pra:
    * Aceitar raio 1-80
    * Extrair conjunto.geo_estado quando mencionado
    * Não exigir cidade na tabela hardcoded — pode preencher conjunto.geo_cidade
      com bairro/distrito que o resolve_geo_criacao resolve depois
"""

import sys, json, copy
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# A — Criar load_meta_token_criacao (cópia do load_meta_token)
# ─────────────────────────────────────────────────────────────

# Verifica se já existe
exists_load_token_criacao = any(n['name'] == 'load_meta_token_criacao' for n in wf['nodes'])
exists_resolve_geo = any(n['name'] == 'resolve_geo_criacao' for n in wf['nodes'])

original_token_node = next((n for n in wf['nodes'] if n['name'] == 'load_meta_token'), None)
if not original_token_node:
    print("❌ load_meta_token não encontrado — abortando")
    sys.exit(1)

if not exists_load_token_criacao:
    load_token_criacao = copy.deepcopy(original_token_node)
    load_token_criacao['name'] = 'load_meta_token_criacao'
    load_token_criacao['id'] = 'load_meta_token_criacao'
    # Coloca lá embaixo da faixa 0 do layout (faixa entry ~y=0)
    load_token_criacao['position'] = [3200, 0]
    wf['nodes'].append(load_token_criacao)
    fixes_applied.append('criado nó load_meta_token_criacao')

# ─────────────────────────────────────────────────────────────
# B — Criar resolve_geo_criacao (Code/JS)
# ─────────────────────────────────────────────────────────────

RESOLVE_GEO_CRIACAO_CODE = r"""// Pós-processamento de geo no fluxo de CRIAÇÃO
// Espelha a lógica de build_targeting_atualizado (Meta Search + Nominatim + custom_locations)
// Lê o brief do persist_brief, resolve geo dinâmico, devolve estado/brief atualizados.

const estadoIn = $('persist_brief').first().json.estado;
const brief = estadoIn.brief || {};
const conjunto = brief.conjunto || {};
const targeting = JSON.parse(JSON.stringify(brief.targeting_meta || {}));

const cidade = conjunto.geo_cidade || '';
const estado_hint = conjunto.geo_estado || '';
let raio_km = conjunto.geo_raio_km;

let token = '';
try { token = $('load_meta_token_criacao').first().json.valor; } catch(e) {}

const CIDADES_HARDCODED = {"São Paulo":"269969","Rio de Janeiro":"267027","Brasília":"245683","Belo Horizonte":"244661","Salvador":"267730","Fortaleza":"253370","Curitiba":"250457","Manaus":"259014","Recife":"266284","Goiânia":"254063","Porto Alegre":"264859","Belém":"244580","Guarulhos":"254529","Campinas":"247071","Maceió":"258670","Natal":"261132","Florianópolis":"253249","Cuiabá":"250332","João Pessoa":"256863","Aracaju":"242415","Teresina":"272278","Campo Grande":"247184","São Luís":"269788","Macapá":"258622","Vitória":"274425","Porto Velho":"265452","Boa Vista":"245039","Palmas":"262281"};

async function resolveGeoViaMetaSearch(query, accessToken, estadoHint, preferirComCoordenadas) {
  try {
    const url = 'https://graph.facebook.com/v25.0/search?type=adgeolocation&location_types=["city","neighborhood","region","subcity","medium_geo_area","small_geo_area","metro_area"]&country_code=BR&limit=20&fields=key,name,type,country_code,region,region_id,latitude,longitude&q=' + encodeURIComponent(query) + '&access_token=' + encodeURIComponent(accessToken);
    const resp = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
    let data = (typeof resp === 'string' ? JSON.parse(resp) : resp).data || [];
    if (!data.length) return null;
    const UF_TO_NOME = {AC:'Acre',AL:'Alagoas',AP:'Amapá',AM:'Amazonas',BA:'Bahia',CE:'Ceará',DF:'Distrito Federal',ES:'Espírito Santo',GO:'Goiás',MA:'Maranhão',MT:'Mato Grosso',MS:'Mato Grosso do Sul',MG:'Minas Gerais',PA:'Pará',PB:'Paraíba',PR:'Paraná',PE:'Pernambuco',PI:'Piauí',RJ:'Rio de Janeiro',RN:'Rio Grande do Norte',RS:'Rio Grande do Sul',RO:'Rondônia',RR:'Roraima',SC:'Santa Catarina',SP:'São Paulo',SE:'Sergipe',TO:'Tocantins'};
    const norm = s => String(s||'').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');
    if (estadoHint) {
      const hint = String(estadoHint).trim().toUpperCase();
      const nomeEsperado = UF_TO_NOME[hint] || estadoHint;
      const nomeNorm = norm(nomeEsperado);
      const filtered = data.filter(r => r.region && norm(r.region) === nomeNorm);
      if (filtered.length) data = filtered;
    }
    const tipoOrder = preferirComCoordenadas
      ? ['neighborhood', 'subcity', 'small_geo_area', 'medium_geo_area', 'city', 'metro_area', 'region']
      : ['city', 'subcity', 'neighborhood', 'medium_geo_area', 'small_geo_area', 'metro_area', 'region'];
    data.sort((a, b) => {
      if (preferirComCoordenadas) {
        const aC = (a.latitude != null && a.longitude != null) ? 0 : 1;
        const bC = (b.latitude != null && b.longitude != null) ? 0 : 1;
        if (aC !== bC) return aC - bC;
      }
      return tipoOrder.indexOf(a.type) - tipoOrder.indexOf(b.type);
    });
    return data[0];
  } catch (e) { return null; }
}

async function geocodeViaNominatim(query, estadoHint) {
  try {
    const UF_TO_NOME = {AC:'Acre',AL:'Alagoas',AP:'Amapá',AM:'Amazonas',BA:'Bahia',CE:'Ceará',DF:'Distrito Federal',ES:'Espírito Santo',GO:'Goiás',MA:'Maranhão',MT:'Mato Grosso',MS:'Mato Grosso do Sul',MG:'Minas Gerais',PA:'Pará',PB:'Paraíba',PR:'Paraná',PE:'Pernambuco',PI:'Piauí',RJ:'Rio de Janeiro',RN:'Rio Grande do Norte',RS:'Rio Grande do Sul',RO:'Rondônia',RR:'Roraima',SC:'Santa Catarina',SP:'São Paulo',SE:'Sergipe',TO:'Tocantins'};
    let q = String(query || '').trim();
    if (!q) return null;
    if (estadoHint) {
      const hint = String(estadoHint).trim().toUpperCase();
      const nome = UF_TO_NOME[hint] || estadoHint;
      if (!q.toLowerCase().includes(String(nome).toLowerCase())) q = q + ', ' + nome;
    }
    const url = 'https://nominatim.openstreetmap.org/search?format=json&countrycodes=br&limit=3&q=' + encodeURIComponent(q);
    const resp = await this.helpers.httpRequest({ method:'GET', url, headers:{'User-Agent':'QuirkAutoAds/1.0 (contato@quirkgrowth.com.br)'}, returnFullResponse:false });
    const data = (typeof resp === 'string' ? JSON.parse(resp) : resp);
    if (!Array.isArray(data) || !data.length) return null;
    const first = data[0];
    if (first.lat == null || first.lon == null) return null;
    return { latitude: Number(first.lat), longitude: Number(first.lon), display_name: first.display_name || null };
  } catch (e) { return null; }
}

// Se não houver cidade no brief, deixa passar como está — o validate vai pegar
if (!cidade) {
  return [{ json: { estado: estadoIn, geo_resolvido: false, motivo: 'sem_cidade' } }];
}

if (typeof raio_km !== 'number') raio_km = 17;
if (raio_km < 1) raio_km = 1;
if (raio_km > 80) raio_km = 80;
const raio_km_pedido = raio_km;
const precisaCoordenadas = raio_km < 17;

let key = null;
let lat = null;
let lng = null;
let resolvedType = null;
let resolvedName = cidade;

// Hardcoded só pra raio >= 17 sem estado
if (!precisaCoordenadas && !estado_hint) {
  const h = CIDADES_HARDCODED[cidade];
  if (h) { key = h; resolvedType = 'city_hardcoded'; }
}

// Meta Search
if ((!key || precisaCoordenadas) && token) {
  const found = await resolveGeoViaMetaSearch.call(this, cidade, token, estado_hint, precisaCoordenadas);
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
  return [{ json: { estado: estadoIn, geo_resolvido: false, motivo: 'cidade_nao_encontrada_meta', cidade, estado_hint } }];
}

// Nominatim fallback
let geo_coords_source = null;
if (lat != null && lng != null) {
  geo_coords_source = 'meta';
} else if (precisaCoordenadas) {
  const geo = await geocodeViaNominatim.call(this, cidade, estado_hint);
  if (geo) { lat = geo.latitude; lng = geo.longitude; geo_coords_source = 'nominatim'; }
}

let geo_metodo;
if (precisaCoordenadas && lat != null && lng != null) {
  targeting.geo_locations = {
    custom_locations: [{ latitude: lat, longitude: lng, radius: raio_km, distance_unit: 'kilometer', name: resolvedName }]
  };
  geo_metodo = 'custom_locations';
} else if (precisaCoordenadas) {
  raio_km = 17;
  targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
  geo_metodo = 'cities_clamped';
} else {
  targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
  geo_metodo = 'cities';
}

// Atualiza brief in-place
const novoEstado = JSON.parse(JSON.stringify(estadoIn));
novoEstado.brief.targeting_meta = targeting;
novoEstado.brief.conjunto = novoEstado.brief.conjunto || {};
novoEstado.brief.conjunto.geo_cidade = resolvedName;
novoEstado.brief.conjunto.geo_raio_km = raio_km;
if (geo_metodo === 'custom_locations') {
  novoEstado.brief.conjunto.geo_lat = lat;
  novoEstado.brief.conjunto.geo_lng = lng;
}

return [{
  json: {
    estado: novoEstado,
    geo_resolvido: true,
    geo_metodo,
    geo_coords_source,
    raio_km_pedido,
    raio_km_aplicado: raio_km,
    cidade_label: resolvedName,
    geo_tipo: resolvedType
  }
}];
"""

if not exists_resolve_geo:
    resolve_geo_node = {
        'parameters': {'jsCode': RESOLVE_GEO_CRIACAO_CODE},
        'id': 'resolve_geo_criacao',
        'name': 'resolve_geo_criacao',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [3460, 0],
    }
    wf['nodes'].append(resolve_geo_node)
    fixes_applied.append('criado nó resolve_geo_criacao')

# ─────────────────────────────────────────────────────────────
# C — Reorganizar conexões
#   Antes:  persist_brief → validate
#   Depois: persist_brief → load_meta_token_criacao → resolve_geo_criacao → validate
# ─────────────────────────────────────────────────────────────

conns = wf.get('connections', {})

# 1. persist_brief deixa de apontar pra validate, aponta pra load_meta_token_criacao
if 'persist_brief' in conns:
    for branch in conns['persist_brief'].get('main', []):
        for c in branch:
            if c.get('node') == 'validate':
                c['node'] = 'load_meta_token_criacao'
                fixes_applied.append('persist_brief → load_meta_token_criacao (era validate)')

# 2. load_meta_token_criacao → resolve_geo_criacao
conns['load_meta_token_criacao'] = {
    'main': [[{'node': 'resolve_geo_criacao', 'type': 'main', 'index': 0}]]
}
fixes_applied.append('load_meta_token_criacao → resolve_geo_criacao (nova)')

# 3. resolve_geo_criacao → validate
conns['resolve_geo_criacao'] = {
    'main': [[{'node': 'validate', 'type': 'main', 'index': 0}]]
}
fixes_applied.append('resolve_geo_criacao → validate (nova)')

# ─────────────────────────────────────────────────────────────
# D — Atualizar validate pra ler estado de resolve_geo_criacao em vez de merge_brief
# ─────────────────────────────────────────────────────────────

OLD_VALIDATE_SRC = "const estado = $('merge_brief').first().json.estado;"
NEW_VALIDATE_SRC = "const estado = $('resolve_geo_criacao').first().json.estado;"

for node in wf['nodes']:
    if node['name'] == 'validate':
        code = node['parameters']['jsCode']
        if OLD_VALIDATE_SRC in code:
            node['parameters']['jsCode'] = code.replace(OLD_VALIDATE_SRC, NEW_VALIDATE_SRC)
            fixes_applied.append('validate: lê estado de resolve_geo_criacao')
        else:
            fixes_failed.append(f'validate: linha "const estado = $({chr(39)}merge_brief{chr(39)})..." não encontrada')
        break

# ─────────────────────────────────────────────────────────────
# E — Atualizar prompt do build_extrator_body
#     - extrair conjunto.geo_estado
#     - aceitar raio 1-80
#     - aceitar bairros/distritos fora da tabela
# ─────────────────────────────────────────────────────────────

# Padrão antigo na seção "REGRA CRÍTICA DE GEO_LOCATIONS"
OLD_GEO_PROMPT_FRAG = (
    'REGRA CR\\u00cdTICA DE GEO_LOCATIONS:'
    '\\nO cliente DEVE ter informado uma cidade brasileira + raio em km. Extraia ambos pros campos:'
    '\\n- conjunto.geo (string descritiva: \\"Goi\\u00e2nia, raio 15km\\")'
    '\\n- conjunto.geo_cidade (nome literal da cidade)'
    '\\n- conjunto.geo_raio_km (inteiro)'
    '\\n\\nEm \\"targeting_meta.geo_locations\\", monte usando a TABELA DE CIDADES BR. Formato:'
    '\\n  \\"geo_locations\\": {\\"cities\\": [{\\"key\\": \\"<KEY>\\", \\"radius\\": <raio_km>, \\"distance_unit\\": \\"kilometer\\"}]}'
    '\\n\\nSe cidade n\\u00e3o na tabela, fallback: {\\"countries\\":[\\"BR\\"]} + alerta no campo \\"alertas\\".'
)
NEW_GEO_PROMPT_FRAG = (
    'REGRA CR\\u00cdTICA DE GEO_LOCATIONS:'
    '\\nO cliente DEVE ter informado uma localiza\\u00e7\\u00e3o brasileira (cidade, bairro, distrito ou regi\\u00e3o) + raio em km. Extraia:'
    '\\n- conjunto.geo (string descritiva: \\"Bras\\u00edl\\u00e2ndia, SP, raio 5km\\")'
    '\\n- conjunto.geo_cidade (nome EXATO mencionado pelo cliente — pode ser bairro/distrito)'
    '\\n- conjunto.geo_estado (UF \\"SP\\"/\\"RJ\\"/... OU nome \\"S\\u00e3o Paulo\\"; vazio se n\\u00e3o mencionado)'
    '\\n- conjunto.geo_raio_km (inteiro entre 1 e 80 — N\\u00c3O clampe pra 17; sistema p\\u00f3s-processa raios menores via lat/lng)'
    '\\n\\nEm \\"targeting_meta.geo_locations\\", monte um placeholder usando a TABELA DE CIDADES BR. O sistema vai sobrescrever depois com resolu\\u00e7\\u00e3o din\\u00e2mica via Meta Search + Nominatim, ent\\u00e3o esse campo \\u00e9 s\\u00f3 fallback inicial:'
    '\\n  \\"geo_locations\\": {\\"cities\\": [{\\"key\\": \\"<KEY>\\", \\"radius\\": <raio_km>, \\"distance_unit\\": \\"kilometer\\"}]}'
    '\\n\\nSe cidade n\\u00e3o estiver na tabela, use a CAPITAL do estado mencionado (ou \\"269969\\" S\\u00e3o Paulo se n\\u00e3o souber). NUNCA caia em {\\"countries\\":[\\"BR\\"]} — o p\\u00f3s-processador resolve a localiza\\u00e7\\u00e3o real depois.'
)

for node in wf['nodes']:
    if node['name'] == 'build_extrator_body':
        code = node['parameters']['jsCode']
        if OLD_GEO_PROMPT_FRAG in code:
            node['parameters']['jsCode'] = code.replace(OLD_GEO_PROMPT_FRAG, NEW_GEO_PROMPT_FRAG)
            fixes_applied.append('build_extrator_body: prompt aceita bairro + estado + raio 1-80')
        else:
            fixes_failed.append('build_extrator_body: fragmento de prompt de geo não encontrado')
        break

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
    print(f"\n✅ Workflow '{WF_ID}' atualizado.")
else:
    print(f"\n⚠️  {len(fixes_failed)} fix(es) falharam — workflow NÃO salvo.")
    sys.exit(1)
