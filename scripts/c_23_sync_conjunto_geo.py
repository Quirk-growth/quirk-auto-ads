"""
c_23_sync_conjunto_geo.py

Bug colateral detectado no teste E2E (12/06/2026):

A campanha id=34 ("Casa 2 quartos - Limão SP - 400mil") teve ALTERAR_GEO
para "Brasilândia SP 5km". Resultado no DB:
  - json_extrator.targeting_meta.geo_locations.custom_locations: Brasilândia ✓
  - json_extrator.conjunto.geo_cidade: "São Paulo" ← DESATUALIZADO
  - json_extrator.conjunto.geo_raio_km: 5 (acertou por coincidência)
  - json_extrator.conjunto.geo: "Limão, São Paulo, raio 5km" ← DESATUALIZADO

Causa: o update_db_campanha só faz jsonb_set em targeting_meta. O
conjunto.geo_cidade/geo_raio_km/geo_estado nunca são atualizados.
Consequência prática: lista_candidatas exibe `sel.geo_cidade_atual` que
lê de `json_extrator.conjunto.geo_cidade` — então a próxima vez o user vê
info errada do que ele acabou de alterar.

Fix em 2 partes:

  A. prep_update_db: expõe novo_cidade + novo_raio_km + novo_estado
     (extraídos de build_targeting_atualizado).

  B. update_db_campanha (SQL): além de atualizar targeting_meta,
     também atualiza conjunto.geo_cidade, conjunto.geo_raio_km,
     conjunto.geo_estado, e conjunto.geo (string descritiva).
     Usa jsonb_set encadeado pra cada chave.
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# A — prep_update_db: expor novo_cidade/raio/estado
# ─────────────────────────────────────────────────────────────

OLD_PREP = """\
else if (['ALTERAR_PUBLICO', 'ALTERAR_GEO'].includes(v)) {
  try {
    novo_targeting = $('build_targeting_atualizado').first().json.targeting;
  } catch(e) { novo_targeting = null; }
}

return [{
  json: {
    campanha_id_db: r.selecionada.campanha_id_db,
    telefone: r.telefone,
    verbo: v,
    ok: r.ok,
    classe: r.classe || '',
    motivo: r.motivo || '',
    selecionada: r.selecionada,
    novo_status,
    novo_verba,
    novo_targeting_json: novo_targeting ? JSON.stringify(novo_targeting) : null,
    novo_valor: r.novo_valor
  }
}];"""

NEW_PREP = """\
else if (['ALTERAR_PUBLICO', 'ALTERAR_GEO'].includes(v)) {
  try {
    novo_targeting = $('build_targeting_atualizado').first().json.targeting;
  } catch(e) { novo_targeting = null; }
}

// Extrai metadados da resolução de geo pra sincronizar conjunto.* no DB
let novo_geo_cidade = null;
let novo_geo_raio_km = null;
let novo_geo_estado = null;
let novo_geo_descritivo = null;
if (v === 'ALTERAR_GEO') {
  try {
    const g = $('build_targeting_atualizado').first().json;
    novo_geo_cidade = g.cidade_label_novo || null;
    novo_geo_raio_km = (typeof g.raio_km_novo === 'number') ? g.raio_km_novo : null;
    novo_geo_estado = g.estado_pedido || (g.estado_resolvido ? String(g.estado_resolvido).replace(/\\s*\\(state\\)$/i,'') : null) || null;
    if (novo_geo_cidade && novo_geo_raio_km) {
      novo_geo_descritivo = novo_geo_estado
        ? `${novo_geo_cidade}, ${novo_geo_estado}, raio ${novo_geo_raio_km}km`
        : `${novo_geo_cidade}, raio ${novo_geo_raio_km}km`;
    }
  } catch(e) {}
}

return [{
  json: {
    campanha_id_db: r.selecionada.campanha_id_db,
    telefone: r.telefone,
    verbo: v,
    ok: r.ok,
    classe: r.classe || '',
    motivo: r.motivo || '',
    selecionada: r.selecionada,
    novo_status,
    novo_verba,
    novo_targeting_json: novo_targeting ? JSON.stringify(novo_targeting) : null,
    novo_geo_cidade,
    novo_geo_raio_km,
    novo_geo_estado,
    novo_geo_descritivo,
    novo_valor: r.novo_valor
  }
}];"""

# ─────────────────────────────────────────────────────────────
# B — update_db_campanha: SQL atualiza conjunto.* além de targeting_meta
# ─────────────────────────────────────────────────────────────

OLD_SQL = """\
UPDATE auto_ads.campanhas
SET status = COALESCE(NULLIF(NULLIF('{{ $json.novo_status }}'::text, 'null'), ''), status),
    json_extrator = CASE
      WHEN '{{ $json.verbo }}' = 'ALTERAR_VERBA' AND {{ $json.novo_verba || 'NULL' }} IS NOT NULL THEN
        jsonb_set(json_extrator, '{campanha,verba_diaria}', to_jsonb({{ $json.novo_verba || 0 }}))
      WHEN '{{ $json.verbo }}' IN ('ALTERAR_PUBLICO','ALTERAR_GEO') AND '{{ $json.novo_targeting_json || '' }}' != '' AND '{{ $json.novo_targeting_json || '' }}' != 'null' THEN
        jsonb_set(json_extrator, '{targeting_meta}', '{{ ($json.novo_targeting_json || '{}').replace(/'/g, "''") }}'::jsonb)
      ELSE json_extrator
    END,
    ultima_alteracao = NOW()
WHERE id = {{ $json.campanha_id_db }}"""

NEW_SQL = """\
UPDATE auto_ads.campanhas
SET status = COALESCE(NULLIF(NULLIF('{{ $json.novo_status }}'::text, 'null'), ''), status),
    json_extrator = CASE
      WHEN '{{ $json.verbo }}' = 'ALTERAR_VERBA' AND {{ $json.novo_verba || 'NULL' }} IS NOT NULL THEN
        jsonb_set(json_extrator, '{campanha,verba_diaria}', to_jsonb({{ $json.novo_verba || 0 }}))
      WHEN '{{ $json.verbo }}' = 'ALTERAR_GEO' AND '{{ $json.novo_targeting_json || '' }}' != '' AND '{{ $json.novo_targeting_json || '' }}' != 'null' THEN
        jsonb_set(
          jsonb_set(
            jsonb_set(
              jsonb_set(
                jsonb_set(
                  json_extrator,
                  '{targeting_meta}',
                  '{{ ($json.novo_targeting_json || '{}').replace(/'/g, "''") }}'::jsonb
                ),
                '{conjunto,geo_cidade}',
                to_jsonb(NULLIF('{{ ($json.novo_geo_cidade || '').replace(/'/g, "''") }}'::text, ''))
              ),
              '{conjunto,geo_raio_km}',
              to_jsonb({{ $json.novo_geo_raio_km || 'NULL' }}::int)
            ),
            '{conjunto,geo_estado}',
            to_jsonb(NULLIF('{{ ($json.novo_geo_estado || '').replace(/'/g, "''") }}'::text, ''))
          ),
          '{conjunto,geo}',
          to_jsonb(NULLIF('{{ ($json.novo_geo_descritivo || '').replace(/'/g, "''") }}'::text, ''))
        )
      WHEN '{{ $json.verbo }}' = 'ALTERAR_PUBLICO' AND '{{ $json.novo_targeting_json || '' }}' != '' AND '{{ $json.novo_targeting_json || '' }}' != 'null' THEN
        jsonb_set(json_extrator, '{targeting_meta}', '{{ ($json.novo_targeting_json || '{}').replace(/'/g, "''") }}'::jsonb)
      ELSE json_extrator
    END,
    ultima_alteracao = NOW()
WHERE id = {{ $json.campanha_id_db }}"""

# ─────────────────────────────────────────────────────────────
# Aplicar
# ─────────────────────────────────────────────────────────────

for node in wf['nodes']:
    name = node['name']
    if name == 'prep_update_db':
        code = node['parameters']['jsCode']
        if OLD_PREP in code:
            node['parameters']['jsCode'] = code.replace(OLD_PREP, NEW_PREP)
            fixes_applied.append('prep_update_db: expõe novo_cidade/raio/estado/descritivo')
        else:
            fixes_failed.append('prep_update_db: bloco antigo não encontrado')

    elif name == 'update_db_campanha':
        q = node['parameters'].get('query', '')
        if OLD_SQL in q:
            node['parameters']['query'] = q.replace(OLD_SQL, NEW_SQL)
            fixes_applied.append('update_db_campanha: SQL sincroniza conjunto.geo_* no ALTERAR_GEO')
        else:
            fixes_failed.append('update_db_campanha: SQL antigo não encontrado')


print("=== FIXES APLICADOS ===")
for f in fixes_applied: print(f"  ✅ {f}")
print("\n=== FIXES FALHADOS ===")
for f in fixes_failed: print(f"  ❌ {f}")

if not fixes_failed:
    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean_settings)
    print(f"\n✅ Workflow '{WF_ID}' atualizado.")
else:
    sys.exit(1)
