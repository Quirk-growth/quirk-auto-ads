#!/usr/bin/env python3
"""Testa branch de mídia state-aware — msg condicional baseada em estado anterior."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, n8n_api

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def set_estado(estado):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute("""INSERT INTO auto_ads.conversas (telefone, historico, estado_json, criativo_url)
                   VALUES (%s, '', %s, '')
                   ON CONFLICT (telefone) DO UPDATE SET estado_json = EXCLUDED.estado_json""",
                (PHONE, json.dumps(estado)))
    conn.commit(); conn.close()


def send_media():
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'id': 'fake-media-id', 'type': 'media', 'from': f'{PHONE}@s.whatsapp.net', 'mediaType': 'image'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=30).read()


def get_last_media_response():
    execs = n8n_api.list_executions(limit=1)
    eid = execs['data'][0]['id']
    ex = n8n_api._request('GET', f'/executions/{eid}?includeData=true')
    rd = ex['data'].get('resultData', {}).get('runData', {})
    if 'build_media_response' in rd:
        return rd['build_media_response'][0]['data']['main'][0][0]['json'].get('text', '')
    return ''


def test(name, estado, espera):
    print(f'\n[{name}]')
    set_estado(estado)
    send_media()
    time.sleep(8)
    msg = get_last_media_response()
    print(f'  msg: "{msg[:150]}"')
    assert espera.lower() in msg.lower(), f"esperava '{espera}', msg foi '{msg}'"
    print(f'  ✓ contém "{espera}"')


def main():
    test(
        'coletando_info + brief vazio',
        {'etapa_atual': 'coletando_info', 'criativo': {'recebido': False}, 'brief': {}, 'ultima_tentativa': None},
        'ainda preciso'
    )

    brief_completo = {'campanha': {'nome': 'x', 'verba_diaria': 30}, 'objetivo': 'morar', 'faixa_valor': 'ate_700k',
                      'conjunto': {'geo': 'X'}, 'anuncio': {'copy': 'x'}, 'targeting_meta': {'geo_locations': {}}}

    test(
        'aguardando_criativo + brief completo',
        {'etapa_atual': 'aguardando_criativo', 'criativo': {'recebido': False}, 'brief': brief_completo, 'ultima_tentativa': None},
        'CONFIRMAR'
    )

    test(
        'falhou_dado (motivo criativo) → trigger RETRY',
        {'etapa_atual': 'falhou_dado', 'criativo': {'recebido': True, 'url': 'old'}, 'brief': brief_completo,
         'ultima_tentativa': {'resultado': 'erro_dado', 'motivo': 'imagem rejeitada pela Meta', 'tentativas_count': 1}},
        'RETRY'
    )

    test(
        'ativa → sugere NOVA CAMPANHA',
        {'etapa_atual': 'ativa', 'criativo': {'recebido': True, 'url': 'x'}, 'brief': brief_completo,
         'ultima_tentativa': {'resultado': 'ok', 'campaign_id': '123', 'tentativas_count': 1}},
        'NOVA'
    )

    print('\n✓ Todas as transições do branch de mídia OK')


if __name__ == '__main__':
    main()
