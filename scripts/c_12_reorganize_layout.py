#!/usr/bin/env python3
"""
Reorganiza os 95 nodes do workflow n8n em swimlanes visuais claras.

Layout em 5 faixas horizontais:

  ┌──────────────────────────────────────────────────────────────────────────┐
  │ FAIXA 0 (y≈0)   ENTRADA + ROTEAMENTO + SUB-A EXTRATOR + SHARED AUTH    │
  │ FAIXA A (y≈400) AGENTE PRINCIPAL (loop de conversação)                  │
  │ FAIXA B (y≈760) SUB-B GESTÃO (pausar/reativar/encerrar/alterar)         │
  │ FAIXA C (y≈1400) SUB-C STATUS (métricas)                                │
  │ FAIXA M (y≈1800) BRANCH MEDIA (foto/vídeo do criativo)                  │
  └──────────────────────────────────────────────────────────────────────────┘

Nodes de erro/aux ficam 260px abaixo do nó pai.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config

S = 260   # step horizontal entre nós
Y0  = 0      # faixa 0: trunk + extrator + shared precheck + meta criação
YA  = 400    # faixa A: agente principal
YB  = 800    # faixa B: gestão
YB2 = 1060   # faixa B sub: ações / cancelar / publico+geo
YB3 = 1200   # faixa B sub3: extrator parcial publico/geo
YC  = 1600   # faixa C: status
YM  = 2000   # faixa M: media

POSITIONS = {
    # ═══════════════════════════════════════════════════════════════════
    # FAIXA 0 — Entrada e tronco principal
    # ═══════════════════════════════════════════════════════════════════
    'webhook':                      [100,   Y0],
    'switch_type':                  [360,   Y0],
    'normalize_phone':              [620,   Y0],
    'select_cliente':               [880,   Y0],
    'if_cadastrado':                [1140,  Y0],
    'select_conversa':              [1400,  Y0],
    'load_estado':                  [1660,  Y0],
    'em_gestao_valido':             [1920,  Y0],
    'if_em_gestao':                 [2180,  Y0],

    # ── Erros da entrada
    'respond_immediate':            [100,   Y0 + S],
    'send_nao_cadastrado':          [1140,  Y0 + S],

    # ─── Roteamento de intenção
    'classify_intent':              [2440,  Y0],
    'switch_intent':                [2700,  Y0],
    'reset_estado_nova':            [2700,  Y0 + S],   # NOVA_CAMPANHA

    # ─── Sub-A: Extrator
    'build_extrator_body':          [2960,  Y0],
    'extrator':                     [3220,  Y0],
    'parse_extrator':               [3480,  Y0],
    'merge_brief':                  [3740,  Y0],
    'persist_brief':                [4000,  Y0],
    'validate':                     [4260,  Y0],
    'if_valid':                     [4520,  Y0],
    'audit_validacao_falhou':       [4520,  Y0 + S],  # erro de validação

    # ─── Shared: token + precheck + rota status
    'load_meta_token':              [4780,  Y0],
    'switch_status_ou_normal':      [5040,  Y0],
    'if_status_route':              [5300,  Y0],
    'precheck_meta_account':        [5560,  Y0],
    'eval_precheck':                [5820,  Y0],
    'if_precheck_ok':               [6080,  Y0],
    'audit_precheck':               [6080,  Y0 + S],
    'build_precheck_error_msg':     [6340,  Y0 + S],

    # ─── Sub-A: Meta criação
    'switch_a_ou_b':                [6340,  Y0],
    'meta_d1_campaign':             [6600,  Y0],
    'meta_d2_adset':                [6860,  Y0],
    'meta_d3_creative':             [7120,  Y0],
    'meta_d4_ad':                   [7380,  Y0],
    'check_meta_results':           [7640,  Y0],
    'if_pode_retry_infra':          [7900,  Y0],
    'wait_30s':                     [7900,  Y0 + S],   # retry loop
    'persist_estado_apos_meta':     [8160,  Y0],
    'insert_campanha':              [8420,  Y0],
    'audit_campanha_criada':        [8680,  Y0],
    'switch_resposta_meta':         [8940,  Y0],
    'build_resposta_ativa':         [9200,  Y0],
    'send_confirmacao_cliente':     [8420,  Y0 - S],   # orphan (não conectado)

    # ═══════════════════════════════════════════════════════════════════
    # FAIXA A — Agente principal (loop de conversação)
    # ═══════════════════════════════════════════════════════════════════
    'build_agente_body':            [2960,  YA],
    'agente_principal':             [3220,  YA],
    'update_estado_etapa':          [3480,  YA],
    'persist_estado_etapa':         [3740,  YA],
    'build_historico':              [4000,  YA],
    'upsert_conversa':              [4260,  YA],
    'send_resposta':                [4520,  YA],
    'if_confirmado':                [4780,  YA],

    # ═══════════════════════════════════════════════════════════════════
    # FAIXA B — Gestão (sub-projeto B)
    # ═══════════════════════════════════════════════════════════════════

    # ── Init / seleção de campanha (vem de switch_intent e de if_em_gestao)
    'process_gestao_step':          [2180,  YB],
    'switch_acao_gestao':           [2440,  YB],
    'list_campanhas':               [2700,  YB],
    'init_gestao':                  [2960,  YB],

    # ── Persistir estado resposta
    'prep_persist_gestao':          [3220,  YB],
    'persist_estado_gestao':        [3480,  YB],
    'build_gestao_response':        [3740,  YB],

    # ── CANCELAR (linha de baixo)
    'reset_gestao_simples':         [2440,  YB2],
    'build_gestao_msg_cancelado':   [2700,  YB2],

    # ── Rota para Meta API (switch_b_ou_c → load_meta_token na faixa 0)
    'switch_b_ou_c':                [3480,  YB2],

    # ── Executar ação na Meta
    'execute_gestao_action':        [4000,  YB],
    'meta_update_status':           [4260,  YB],       # PAUSAR/REATIVAR/ENCERRAR
    'meta_update_adset_budget':     [4260,  YB2],      # ALTERAR_VERBA

    # ── ALTERAR_PUBLICO / ALTERAR_GEO (extrator parcial)
    'switch_publico_geo_livre':     [4520,  YB2],
    'build_extrator_partial_publico_body': [4780, YB2 - 80],
    'build_extrator_partial_geo_body':     [4780, YB2 + 80],
    'extrator_partial':             [5040,  YB2],
    'build_targeting_atualizado':   [5300,  YB2],
    'meta_update_adset_targeting':  [5560,  YB2],

    # ── Resultado + DB + audit
    'check_gestao_result':          [5820,  YB],
    'prep_update_db':               [6080,  YB],
    'update_db_campanha':           [6340,  YB],
    'audit_gestao':                 [6600,  YB],
    'reset_gestao':                 [6860,  YB],
    'build_gestao_confirmation_msg': [7120, YB],

    # ── Terminal compartilhado B + C
    'send_gestao_msg':              [7380,  YB],

    # ═══════════════════════════════════════════════════════════════════
    # FAIXA C — Status (sub-projeto C)
    # ═══════════════════════════════════════════════════════════════════
    'meta_insights_today':          [5300,  YC],
    'meta_insights_yesterday':      [5560,  YC],
    'meta_insights_7d':             [5820,  YC],
    'meta_insights_30d':            [6080,  YC],
    'merge_insights':               [6340,  YC],
    'format_status_response':       [6600,  YC],
    'audit_status':                 [6860,  YC],
    'reset_gestao_status':          [7120,  YC],
    # reset_gestao_status → send_gestao_msg (faixa B, mesma coluna)

    # ═══════════════════════════════════════════════════════════════════
    # FAIXA M — Media (branch de foto/vídeo)
    # ═══════════════════════════════════════════════════════════════════
    'media_normalize_phone':        [620,   YM],
    'media_select_cliente':         [880,   YM],
    'media_if_cadastrado':          [1140,  YM],
    'media_select_conversa':        [1400,  YM],
    'media_download':               [1660,  YM],
    'media_upsert_criativo':        [1920,  YM],
    'decide_acao_media':            [2180,  YM],
    'build_media_response':         [2440,  YM],
    'media_send_confirma':          [2700,  YM],
}


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    # Aplicar posições
    not_mapped = []
    for node in wf['nodes']:
        name = node['name']
        if name in POSITIONS:
            node['position'] = POSITIONS[name]
        else:
            not_mapped.append(name)

    if not_mapped:
        print(f'⚠️  Nodes sem posição definida ({len(not_mapped)}): {not_mapped}')

    mapped = len(POSITIONS) - len(not_mapped)
    print(f'  ↻ {len(POSITIONS)} nodes reposicionados')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(
        WF_ID,
        name=wf['name'],
        nodes=wf['nodes'],
        connections=wf['connections'],
        settings=clean_settings
    )

    print()
    print('✓ Layout reorganizado em swimlanes:')
    print('  FAIXA 0  (y=   0): Entrada → Extrator → Shared Auth → Meta Criação')
    print('  FAIXA A  (y= 400): Agente Principal (loop de conversação)')
    print('  FAIXA B  (y= 800): Gestão (pausar/reativar/encerrar/alterar)')
    print('  FAIXA C  (y=1600): Status (métricas)')
    print('  FAIXA M  (y=2000): Media (criativos)')


if __name__ == '__main__':
    main()
