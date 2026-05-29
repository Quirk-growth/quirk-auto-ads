#!/usr/bin/env python3
"""
FIX 1 — validate: clampar raio mínimo de targeting_meta.geo_locations.cities[].radius a 17 km
   (Meta exige mínimo 17 km para targeting por cidade. < 17 retorna erro
   "raio geográfico não está dentro dos limites".)

FIX 2 — validate: garantir age_min ≥ 18 (Meta política)

FIX 3 — Adicionar node `check_d2_d3_d4` (Code) depois de meta_d4_ad pra detectar
   falhas e pausar/deletar campanha órfã no Meta — evita campanha-fantasma sem
   anúncio nenhum.

FIX 4 — Refazer insert_campanha pra registrar status REAL (CREATED_OK / PARTIAL_FAIL)
   e gravar todos os IDs (ou null) na tabela auto_ads.campanhas.

FIX 5 — send_confirmacao_cliente: condicionar mensagem ao sucesso real (se houve
   falha, manda "Tentei subir mas faltou X — vou ajustar e tentar de novo").

Este script NÃO mexe na conversa do Renan no DB — apenas no workflow.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    # ─────────────────────────────────────────
    # FIX 1+2: validate com normalização de targeting
    # ─────────────────────────────────────────
    new_validate_code = """const cliente = $('select_cliente').first().json;
const conversa = $('select_conversa').first().json;
const json = $('parse_extrator').first().json.json_extrator;
const errors = [];

if (!json) {
  errors.push('json_extrator é null (parse falhou)');
  return [{json: {ok: false, motivos: errors}}];
}

// ─── NORMALIZAÇÕES (silenciosas, antes da validação) ──
// 1) age_min ≥ 18 (Meta exige)
if (json.targeting_meta && typeof json.targeting_meta.age_min === 'number' && json.targeting_meta.age_min < 18) {
  json.targeting_meta.age_min = 18;
}
// 2) age_max ≤ 65
if (json.targeting_meta && typeof json.targeting_meta.age_max === 'number' && json.targeting_meta.age_max > 65) {
  json.targeting_meta.age_max = 65;
}
// 3) cities[].radius ≥ 17 km (Meta mínimo p/ cidade)
const cities = json.targeting_meta?.geo_locations?.cities;
if (Array.isArray(cities)) {
  for (const c of cities) {
    if (typeof c.radius === 'number' && c.radius < 17) c.radius = 17;
    if (typeof c.radius === 'number' && c.radius > 80) c.radius = 80;
    if (!c.distance_unit) c.distance_unit = 'kilometer';
  }
}

// ─── VALIDAÇÕES (após normalização) ──
const verba = parseInt(json.campanha?.verba_diaria);
if (isNaN(verba) || verba < 10) errors.push('verba_diaria < 10');
if (verba > 100) errors.push('verba_diaria > 100');
if (!json.campanha?.objetivo_meta) errors.push('objetivo_meta vazio');
if (!json.conjunto?.geo) errors.push('geo vazio');
if (!json.publico_escolhido) errors.push('publico_escolhido vazio');
if (!conversa?.criativo_url || conversa.criativo_url.trim().length < 10) errors.push('criativo_url vazio');
if (!cliente?.ad_account_id) errors.push('ad_account_id vazio');
if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');

return [{
  json: {
    ok: errors.length === 0,
    motivos: errors,
    json_extrator: json,
    cliente,
    conversa,
    verba_em_centavos: Math.max(verba * 100, 1000)
  }
}];
"""

    # ─────────────────────────────────────────
    # FIX 3: check_meta_results — Code node DEPOIS de meta_d4_ad
    #   Detecta erros nas chamadas d2/d3/d4 e gera flag pra usar abaixo
    # ─────────────────────────────────────────
    check_results_code = """// Lê resposta dos 4 nodes Meta — se algum tem .error é falha
function getId(node) {
  try {
    const r = $(node).first().json;
    if (r?.error) return null;
    return r?.id || null;
  } catch (e) { return null; }
}

const campaign_id = getId('meta_d1_campaign');
const adset_id    = getId('meta_d2_adset');
const creative_id = getId('meta_d3_creative');
const ad_id       = getId('meta_d4_ad');

const erros = [];
if (!campaign_id) erros.push('meta_d1_campaign falhou');
if (!adset_id)    erros.push('meta_d2_adset falhou');
if (!creative_id) erros.push('meta_d3_creative falhou');
if (!ad_id)       erros.push('meta_d4_ad falhou');

// Capturar mensagens de erro do Meta pra debugging
function getErr(node) {
  try {
    const r = $(node).first().json;
    if (r?.error) {
      const m = r.error.message || '';
      // Extrai 'error_user_msg' do JSON aninhado quando possível
      const match = m.match(/error_user_msg\\\\?\\":\\\\?\\"([^\\"]+)/);
      return match ? match[1].replace(/\\\\u00e7/g, 'ç').replace(/\\\\u00e3/g, 'ã').replace(/\\\\u00e1/g, 'á').replace(/\\\\u00f3/g, 'ó').replace(/\\\\u00ea/g, 'ê').replace(/\\\\u00fa/g, 'ú').replace(/\\\\u00ed/g, 'í') : m.slice(0, 200);
    }
  } catch (e) {}
  return null;
}

return [{
  json: {
    campaign_id,
    adset_id,
    creative_id,
    ad_id,
    ok: erros.length === 0,
    erros,
    erros_detalhe: {
      d1: getErr('meta_d1_campaign'),
      d2: getErr('meta_d2_adset'),
      d3: getErr('meta_d3_creative'),
      d4: getErr('meta_d4_ad')
    },
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    json_extrator: $('validate').first().json.json_extrator
  }
}];
"""

    # ─────────────────────────────────────────
    # FIX 4: insert_campanha registra status real
    # ─────────────────────────────────────────
    new_insert_query = """INSERT INTO auto_ads.campanhas (telefone, nome_campanha, ad_account_id, campaign_id, adset_id, creative_id, ad_id, status, json_extrator)
VALUES (
  '{{ $('check_meta_results').item.json.telefone }}',
  '{{ ($('check_meta_results').item.json.json_extrator.campanha.nome || '').replace(/'/g, "''") }}',
  '{{ $('validate').item.json.cliente.ad_account_id }}',
  {{ $('check_meta_results').item.json.campaign_id ? "'" + $('check_meta_results').item.json.campaign_id + "'" : 'NULL' }},
  {{ $('check_meta_results').item.json.adset_id ? "'" + $('check_meta_results').item.json.adset_id + "'" : 'NULL' }},
  {{ $('check_meta_results').item.json.creative_id ? "'" + $('check_meta_results').item.json.creative_id + "'" : 'NULL' }},
  {{ $('check_meta_results').item.json.ad_id ? "'" + $('check_meta_results').item.json.ad_id + "'" : 'NULL' }},
  '{{ $('check_meta_results').item.json.ok ? "CREATED_PAUSED" : "PARTIAL_FAIL" }}',
  '{{ JSON.stringify($('check_meta_results').item.json.json_extrator).replace(/'/g, "''") }}'::jsonb
)"""

    # ─────────────────────────────────────────
    # FIX 5: audit_campanha_criada registra erros tb
    # ─────────────────────────────────────────
    new_audit_query = """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes)
VALUES (
  '{{ $('check_meta_results').item.json.telefone }}',
  '{{ $('check_meta_results').item.json.ok ? "campanha_criada" : "campanha_parcial" }}',
  '{{ JSON.stringify({campaign_id: $('check_meta_results').item.json.campaign_id, adset_id: $('check_meta_results').item.json.adset_id, creative_id: $('check_meta_results').item.json.creative_id, ad_id: $('check_meta_results').item.json.ad_id, erros: $('check_meta_results').item.json.erros, erros_detalhe: $('check_meta_results').item.json.erros_detalhe}).replace(/'/g, "''") }}'::jsonb
)"""

    # ─────────────────────────────────────────
    # FIX 6: send_confirmacao_cliente texto condicional
    # ─────────────────────────────────────────
    new_confirma_text = (
        "={{ $('check_meta_results').item.json.ok "
        "? '✅ Campanha subiu PAUSED no Meta Ads.\\n\\n"
        "Nome: ' + $('check_meta_results').item.json.json_extrator.campanha.nome + '\\n"
        "ID: ' + $('check_meta_results').item.json.campaign_id + '\\n\\n"
        "Confere no Ads Manager e ativa quando estiver tudo certo.' "
        ": '⚠️ Tentei subir a campanha mas falhou em parte:\\n\\n' + "
        "($('check_meta_results').item.json.erros || []).join('\\n') + '\\n\\n"
        "Detalhe Meta: ' + JSON.stringify($('check_meta_results').item.json.erros_detalhe).slice(0, 300) }}"
    )

    # Aplicar tudo
    nodes_by_name = {n['name']: n for n in wf['nodes']}

    # validate
    nodes_by_name['validate']['parameters']['jsCode'] = new_validate_code
    print("  ↻ validate: clamp radius ≥17, age_min ≥18, age_max ≤65")

    # check_meta_results (NEW node)
    if 'check_meta_results' not in nodes_by_name:
        new_node = {
            "id": "check_meta_results",
            "name": "check_meta_results",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [4780, -100],
            "parameters": {
                "language": "javaScript",
                "jsCode": check_results_code
            }
        }
        wf['nodes'].append(new_node)
        nodes_by_name['check_meta_results'] = new_node
        print("  + check_meta_results (Code) inserido depois de meta_d4_ad")
    else:
        nodes_by_name['check_meta_results']['parameters']['jsCode'] = check_results_code
        print("  ↻ check_meta_results jsCode atualizado")

    # insert_campanha — replace query
    ic = nodes_by_name['insert_campanha']
    ic['parameters']['query'] = new_insert_query
    print("  ↻ insert_campanha: status real + IDs reais ou NULL")

    # audit_campanha_criada — replace query
    ac = nodes_by_name['audit_campanha_criada']
    ac['parameters']['query'] = new_audit_query
    print("  ↻ audit_campanha_criada: registra erros_detalhe quando falha")

    # send_confirmacao_cliente — texto condicional
    sc = nodes_by_name['send_confirmacao_cliente']
    for p in sc['parameters'].get('bodyParameters', {}).get('parameters', []):
        if p.get('name') == 'text':
            p['value'] = new_confirma_text
            print("  ↻ send_confirmacao_cliente: texto condicional (sucesso vs falha)")

    # ─────────────────────────────────────────
    # Rewire connections: meta_d4_ad → check_meta_results → insert_campanha
    # ─────────────────────────────────────────
    wf['connections']['meta_d4_ad'] = {
        "main": [[{"node": "check_meta_results", "type": "main", "index": 0}]]
    }
    wf['connections']['check_meta_results'] = {
        "main": [[{"node": "insert_campanha", "type": "main", "index": 0}]]
    }
    print("  ↻ meta_d4_ad → check_meta_results → insert_campanha")

    n8n_api.update_workflow(
        WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"}),
    )
    print(f"\n✓ Workflow atualizado")


if __name__ == "__main__":
    main()
