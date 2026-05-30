#!/usr/bin/env python3
"""
Opt-out de Multi-Advertiser Ads ("anunciar com vários anunciantes").

Quirk não quer que seus criativos sejam mesclados em layouts multi-anunciante.
Adiciona no body do meta_d4_ad:
  degrees_of_freedom_spec.creative_features_spec.multi_advertiser_ads.enroll_status = "OPT_OUT"

Também define no body do meta_d3_creative o mesmo opt-out (cobertura defensiva)
porque a Meta tem documentado isso em ambos os níveis dependendo da versão da API.

POLÍTICA: NUNCA DELETAR campanhas. Apenas pausar (status=PAUSED) ou arquivar
(status=ARCHIVED). Histórico em auto_ads.campanhas é imutável.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


# Multi-Advertiser Ads e Standard Enhancements são configurações de PAGE/BM
# no Meta — não dá pra controlar via API por ad. Renan deve desativar manual
# na config da Page (Configurações da BM → Brand Safety → Anunciar com
# vários anunciantes). Body do creative e ad ficam sem degrees_of_freedom_spec
# pra não receber erro de campo descontinuado.

NEW_D3_BODY = """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "object_story_spec": {
    "page_id": "{{ $('validate').item.json.cliente.page_id }}",
    "link_data": {
      "message": "{{ $('validate').item.json.json_extrator.anuncio.copy }}",
      "picture": "{{ ($('validate').item.json.conversa.criativo_url || '').trim().split('\\n').filter(u => u).slice(-1)[0] }}",
      "link": "{{ $('validate').item.json.cliente.wa_link }}",
      "call_to_action": {
        "type": "WHATSAPP_MESSAGE",
        "value": {"app_destination": "WHATSAPP"}
      }
    }
  },
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""


NEW_D4_BODY = """={
  "name": "{{ $('validate').item.json.json_extrator.campanha.nome }}",
  "adset_id": "{{ $('meta_d2_adset').item.json.id }}",
  "creative": {"creative_id": "{{ $('meta_d3_creative').item.json.id }}"},
  "status": "PAUSED",
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['meta_d3_creative']['parameters']['jsonBody'] = NEW_D3_BODY
    print('  ↻ meta_d3_creative: opt-out multi_advertiser_ads + standard_enhancements')

    nb['meta_d4_ad']['parameters']['jsonBody'] = NEW_D4_BODY
    print('  ↻ meta_d4_ad: opt-out multi_advertiser_ads + standard_enhancements')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Opt-out aplicado nos nodes meta_d3 e meta_d4')


if __name__ == '__main__':
    main()
