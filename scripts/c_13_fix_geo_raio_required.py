#!/usr/bin/env python3
"""
Dois problemas críticos:

1. Raio clamped sem avisar
   Meta exige mínimo 17km. Se o cliente pede 5km, o sistema aplicava 17km
   silenciosamente. O cliente via "geo atualizado" sem saber do ajuste.
   Fix: avisa ANTES (confirmação gestão) e DEPOIS (mensagem final).

2. Região e faixa etária não verificadas antes do CONFIRMAR
   O agente podia chegar em pronta_pra_subir sem região definida →
   extrator cai em fallback {"countries":["BR"]} → campanha no Brasil todo.
   Fix A: validate bloqueia geo_locations countries-only (sem cidade)
   Fix B: build_agente_body expõe região+faixa etária no estadoBlock e
          exige ambos no resumo do Bloco 8 antes de pedir CONFIRMAR
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


# ─── 1. VALIDATE — bloquear geo sem cidade ──────────────────────────────────

VALIDATE_OLD = """if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');"""

VALIDATE_NEW = """if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');

// Segurança anti-Brasil-total: bloqueia se geo_locations só tem countries (sem cidade)
if (json.targeting_meta?.geo_locations) {
  const gLoc = json.targeting_meta.geo_locations;
  const semCidade = !gLoc.cities?.length && !gLoc.regions?.length;
  if (gLoc.countries && semCidade) {
    errors.push('localização não definida — campanha cobriria o Brasil inteiro. Informe o bairro/cidade/região exata do imóvel.');
  }
}"""


# ─── 2. BUILD_AGENTE_BODY — 3 mudanças no prompt ────────────────────────────

# 2a: etapa_atual = pronta_pra_subir → checar região e criativo antes de CONFIRMAR
AGENTE_OLD_PRONTA = ('- etapa_atual = pronta_pra_subir → peça confirmação ("Tudo pronto. Manda CONFIRMAR pra subir.").')
AGENTE_NEW_PRONTA = ('- etapa_atual = pronta_pra_subir → ANTES de exibir o resumo e pedir CONFIRMAR, verifique no estado: '
                     '(1) Região ≠ "(não informado)" e (2) Criativo recebido = sim. '
                     'Se QUALQUER um faltar — peça o dado AGORA e não mostre o resumo. '
                     'Só quando ambos estiverem presentes: gere o resumo (Bloco 8) e peça CONFIRMAR.')

# 2b: Bloco 5 — adicionar região à lista de itens bloqueantes
AGENTE_OLD_B5 = ('Faltou item essencial (principalmente valor ou criativo)? Pergunte — de forma curta — antes de prosseguir.')
AGENTE_NEW_B5  = ('ITENS QUE BLOQUEIAM AVANÇAR (não siga sem eles): valor do imóvel, BAIRRO/REGIÃO EXATA e criativo recebido. '
                  'Sem região confirmada = campanha no Brasil todo (erro grave). '
                  'Faltou algum? Pergunte de forma curta antes de prosseguir.')

# 2c: Bloco 8 item 2 — incluir região e faixa etária no resumo obrigatório
AGENTE_OLD_B8 = ('2. Faça um resumo CURTO da campanha (objetivo, público, região, VERBA DIÁRIA COMO NÚMERO FECHADO) — em poucas linhas, não um relatório.')
AGENTE_NEW_B8 = ('2. Faça um resumo CURTO incluindo OBRIGATORIAMENTE: nome da campanha, objetivo, BAIRRO/CIDADE/REGIÃO EXATA do imóvel, '
                 'público (rótulo Quirk), FAIXA ETÁRIA (ex: 30–64 anos), VERBA DIÁRIA COMO NÚMERO FECHADO. '
                 'Em poucas linhas, não um relatório. Sem região ou faixa etária no resumo = NÃO mostre CONFIRMAR.')

# 2d: estadoBlock — expor geo e faixa etária explicitamente
AGENTE_OLD_ESTADO = ("let estadoBlock = `Etapa atual: ${etapa_efetiva}\nCriativo recebido: ${criativo?.recebido ? 'sim (' + (criativo.url || '') + ')' : 'não'}\nBrief preenchido: ${preenchidos.join(', ') || '(nada)'}\nBrief faltante: ${faltantes.join(', ') || '(nada)'}\nÚltima tentativa: ${ult ? (ult.resultado + (ult.motivo ? ': ' + ult.motivo : '')) : 'nenhuma'}\nTentativas count: ${ult?.tentativas_count || 0}\nIntent detectado (msg atual): ${intent}`;")
AGENTE_NEW_ESTADO = (
    "const geoInfo = brief?.conjunto?.geo || brief?.conjunto?.geo_cidade || '(não informado)';\n"
    "const idadeMin = brief?.conjunto?.idade_min ?? brief?.targeting_meta?.age_min ?? '?';\n"
    "const idadeMax = brief?.conjunto?.idade_max ?? brief?.targeting_meta?.age_max ?? '?';\n"
    "let estadoBlock = `Etapa atual: ${etapa_efetiva}\n"
    "Criativo recebido: ${criativo?.recebido ? 'sim (' + (criativo.url || '') + ')' : 'não'}\n"
    "Região do imóvel: ${geoInfo}\n"
    "Faixa etária: ${idadeMin}–${idadeMax}\n"
    "Brief preenchido: ${preenchidos.join(', ') || '(nada)'}\n"
    "Brief faltante: ${faltantes.join(', ') || '(nada)'}\n"
    "Última tentativa: ${ult ? (ult.resultado + (ult.motivo ? ': ' + ult.motivo : '')) : 'nenhuma'}\n"
    "Tentativas count: ${ult?.tentativas_count || 0}\n"
    "Intent detectado (msg atual): ${intent}`;"
)


# ─── 3. BUILD_GESTAO_RESPONSE — aviso de raio na confirmação gestão ──────────

GR_OLD = """  else if (verbo === 'ALTERAR_GEO') resumo = `trocar geo de "${sel.nome}" (${sel.geo_cidade_atual} ${sel.geo_raio_atual}km → novo)`;"""
GR_NEW = (
    "  else if (verbo === 'ALTERAR_GEO') {\n"
    "    const raio_pedido = nv?.raio_km;\n"
    "    const raio_final = (typeof raio_pedido !== 'number') ? 17 : Math.min(80, Math.max(17, raio_pedido));\n"
    "    const nova_loc = nv?.cidade || nv?.descricao || 'nova localização';\n"
    "    const raio_aviso = (typeof raio_pedido === 'number' && raio_pedido < 17)\n"
    "      ? ` ⚠️ Meta não aceita raio < 17km — será usado ${raio_final}km.`\n"
    "      : '';\n"
    "    resumo = `trocar geo de \"${sel.nome}\" → ${nova_loc}, raio ${raio_final}km${raio_aviso}`;\n"
    "  }"
)


# ─── 4. BUILD_GESTAO_CONFIRMATION_MSG — nota raio ajustado ───────────────────

BGCM_OLD = "  else if (v === 'ALTERAR_GEO') text = `✓ Geo de \"${sel.nome}\" atualizado.`;"
BGCM_NEW = (
    "  else if (v === 'ALTERAR_GEO') {\n"
    "    let raio_nota = '';\n"
    "    try {\n"
    "      const raio_pedido = r.novo_valor?.raio_km;\n"
    "      const raio_final = $('build_targeting_atualizado').first().json?.raio_km_novo;\n"
    "      if (typeof raio_pedido === 'number' && raio_final && raio_pedido < raio_final) {\n"
    "        raio_nota = `\\n⚠️ Raio ajustado de ${raio_pedido}km → ${raio_final}km (mínimo permitido pelo Meta).`;\n"
    "      }\n"
    "    } catch(e) {}\n"
    "    text = `✓ Geo de \"${sel.nome}\" atualizado.${raio_nota}`;\n"
    "  }"
)


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    changed = []

    # 1. validate
    old = nb['validate']['parameters']['jsCode']
    if VALIDATE_OLD in old:
        nb['validate']['parameters']['jsCode'] = old.replace(VALIDATE_OLD, VALIDATE_NEW)
        changed.append('validate: bloqueio geo sem cidade')
    else:
        print('  ⚠️  validate: padrão antigo não encontrado')

    # 2. build_agente_body — 4 substituições
    bab = nb['build_agente_body']['parameters']['jsCode']

    if AGENTE_OLD_PRONTA in bab:
        bab = bab.replace(AGENTE_OLD_PRONTA, AGENTE_NEW_PRONTA)
        changed.append('build_agente_body: pronta_pra_subir exige região+criativo')
    else:
        print('  ⚠️  build_agente_body: padrão pronta_pra_subir não encontrado')

    if AGENTE_OLD_B5 in bab:
        bab = bab.replace(AGENTE_OLD_B5, AGENTE_NEW_B5)
        changed.append('build_agente_body: Bloco 5 — região obrigatória')
    else:
        print('  ⚠️  build_agente_body: padrão Bloco 5 não encontrado')

    if AGENTE_OLD_B8 in bab:
        bab = bab.replace(AGENTE_OLD_B8, AGENTE_NEW_B8)
        changed.append('build_agente_body: Bloco 8 — região+faixa etária no resumo')
    else:
        print('  ⚠️  build_agente_body: padrão Bloco 8 não encontrado')

    if AGENTE_OLD_ESTADO in bab:
        bab = bab.replace(AGENTE_OLD_ESTADO, AGENTE_NEW_ESTADO)
        changed.append('build_agente_body: estadoBlock expõe região e faixa etária')
    else:
        print('  ⚠️  build_agente_body: padrão estadoBlock não encontrado')

    nb['build_agente_body']['parameters']['jsCode'] = bab

    # 3. build_gestao_response — raio warning na confirmação
    gr = nb['build_gestao_response']['parameters']['jsCode']
    if GR_OLD in gr:
        nb['build_gestao_response']['parameters']['jsCode'] = gr.replace(GR_OLD, GR_NEW)
        changed.append('build_gestao_response: aviso raio clamped na confirmação')
    else:
        print('  ⚠️  build_gestao_response: padrão ALTERAR_GEO não encontrado')

    # 4. build_gestao_confirmation_msg — nota raio final
    bgcm = nb['build_gestao_confirmation_msg']['parameters']['jsCode']
    if BGCM_OLD in bgcm:
        nb['build_gestao_confirmation_msg']['parameters']['jsCode'] = bgcm.replace(BGCM_OLD, BGCM_NEW)
        changed.append('build_gestao_confirmation_msg: nota raio ajustado')
    else:
        print('  ⚠️  build_gestao_confirmation_msg: padrão ALTERAR_GEO não encontrado')

    for c in changed:
        print(f'  ↻ {c}')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                            connections=wf['connections'], settings=clean_settings)
    print(f'\n✓ {len(changed)}/5 correções aplicadas')


if __name__ == '__main__':
    main()
