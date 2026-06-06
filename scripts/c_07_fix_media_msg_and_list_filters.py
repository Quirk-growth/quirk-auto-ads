#!/usr/bin/env python3
"""
2 fixes:

1. build_media_response: msg de criativo recebido era 'ainda preciso de
   campanha, objetivo, ...' quando estado.brief estava vazio. Mas o brief
   só é persistido no momento do CONFIRMAR (via extrator → merge_brief).
   Entre o brief no chat e o CONFIRMAR, estado.brief = {} mesmo o cliente
   tendo passado tudo. Mensagem mentia.

   Fix: msg vira agnóstica — não tenta listar campos que faltam (porque
   o branch de mídia não sabe). Diz só 'Recebi seu criativo ✓ — me passa
   o brief se ainda não passou OU manda CONFIRMAR pra subir.'

2. list_campanhas: filtros estão desatualizados. Depois que tiramos do
   modo teste (status_db virou CREATED_ACTIVE em vez de CREATED_PAUSED),
   o filtro PAUSAR ainda procurava por ['CREATED_PAUSED', 'ACTIVE'] e
   ignorava CREATED_ACTIVE. Por isso a campanha que acabou de subir não
   apareceu na lista do PAUSAR.

   Fix: filtros atualizados.
   - PAUSAR: ['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE']
   - REATIVAR: ['PAUSED','CREATED_PAUSED']
   - ENCERRAR: ['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
   - STATUS (default): mesma de ENCERRAR
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


BUILD_MEDIA_RESPONSE_V5 = """const d = $('decide_acao_media').first().json;
const estadoAntes = d.estadoAntes || {};

let text;

// vídeo rejeitado mantém prioridade
if (d.video_rejeitado) {
  text = '⚠️ Por enquanto só aceito FOTO no criativo (JPG ou PNG). Vídeo ainda não tá suportado. Manda uma imagem do imóvel.';
} else if (d.duplicado_recente) {
  text = '✓ Recebi seu criativo (atualizado).';
} else if (d.triggerRetry) {
  text = 'Recebi o novo criativo ✓ — manda SUBIR DENOVO pra tentar com ele.';
} else if (estadoAntes.etapa_atual === 'ativa') {
  text = 'Recebi o criativo ✓ — mas você já tem campanha ativa. Quer fazer NOVA CAMPANHA?';
} else if (estadoAntes.etapa_atual === 'falhou_dado') {
  const motivo = estadoAntes.ultima_tentativa?.motivo || 'algum problema';
  text = 'Recebi seu criativo ✓ — mas a última tentativa falhou por: ' + motivo + '. Corrige isso e manda SUBIR DENOVO.';
} else {
  // CASO GERAL: criativo recebido. Não tenta listar o que falta do brief,
  // porque o branch de mídia não tem visibilidade real do brief
  // (extrator só roda em CONFIRMAR/SUBIR_DENOVO).
  text = 'Recebi seu criativo ✓ — se você já me passou as informações da campanha, manda CONFIRMAR pra eu subir. Se ainda faltam detalhes (tipo, valor, região, perfil), me manda esses dados.';
}

return [{ json: { text, telefone: d.telefone } }];
"""


LIST_CAMPANHAS_QUERY_V2 = """SELECT
  id AS campanha_id_db,
  nome_campanha AS nome,
  ad_account_id,
  campaign_id AS campaign_id_meta,
  adset_id AS adset_id_meta,
  status,
  json_extrator,
  ultima_alteracao
FROM auto_ads.campanhas
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'
  AND status = ANY(CASE
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'PAUSAR' THEN ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'REATIVAR' THEN ARRAY['PAUSED','CREATED_PAUSED']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'ENCERRAR' THEN ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
    WHEN '{{ $('classify_intent').item.json.intent }}' IN ('ALTERAR_VERBA','ALTERAR_PUBLICO','ALTERAR_GEO') THEN ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
    ELSE ARRAY['CREATED_PAUSED','CREATED_ACTIVE','ACTIVE','PAUSED']
  END)
ORDER BY criada_em DESC
LIMIT 10"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['build_media_response']['parameters']['jsCode'] = BUILD_MEDIA_RESPONSE_V5
    print('  ↻ build_media_response v5: msg agnóstica de brief')

    nb['list_campanhas']['parameters']['query'] = LIST_CAMPANHAS_QUERY_V2
    print('  ↻ list_campanhas: filtros incluem CREATED_ACTIVE')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ 2 fixes aplicados')


if __name__ == '__main__':
    main()
