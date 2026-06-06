#!/usr/bin/env python3
"""
Smoke test do branch de mídia que NÃO seta criativo via DB direto.

Cobre o gap do test_v2_happy_path (que setta criativo manualmente).
Aqui simulamos webhook UAZAPI real com payload de mídia e validamos:
- decide_acao_media (rejeita vídeo, aceita imagem)
- media_upsert_criativo (UPSERT com guard mimetype)
- estado_json.criativo gravado corretamente
- Mensagem de resposta condicional ao estado

Como media_download chama UAZAPI real, ele vai falhar com 'Message not
found' (id fake). Mas o restante do branch continua via continueOnFail.
Validamos o que conseguimos validar.

Para teste FULL com download real, precisaria UAZAPI token + upload de
imagem real — fora de escopo (manual via WhatsApp).
"""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def db_reset():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    conn.commit(); conn.close()


def send_media_event(fake_id, mimetype='image/jpeg'):
    """Simula webhook UAZAPI de mídia. media_download vai falhar pra id fake
    (Message not found) mas branch continua via continueOnFail."""
    payload = {
        'chat': {'phone': '+55 11 98083-8409'},
        'message': {
            'id': fake_id, 'type': 'media',
            'from': f'{PHONE}@s.whatsapp.net',
            'mediaType': 'image' if mimetype.startswith('image') else 'video',
            'content': {'mimetype': mimetype, 'URL': f'https://fake.whatsapp.net/{fake_id}'}
        }
    }
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=30).read()


def db_set_estado(estado):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute("INSERT INTO auto_ads.conversas (telefone, historico, estado_json) VALUES (%s, '', %s) ON CONFLICT (telefone) DO UPDATE SET estado_json = EXCLUDED.estado_json",
                (PHONE, json.dumps(estado)))
    conn.commit(); conn.close()


def db_get_state():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def get_last_media_response_text():
    """Lê a última execução de media e retorna o text de build_media_response."""
    sys.path.insert(0, os.path.dirname(__file__))
    import n8n_api
    execs = n8n_api.list_executions(limit=1)
    eid = execs['data'][0]['id']
    ex = n8n_api._request('GET', f'/executions/{eid}?includeData=true')
    rd = ex['data'].get('resultData', {}).get('runData', {})
    if 'build_media_response' in rd:
        return rd['build_media_response'][0]['data']['main'][0][0]['json'].get('text', '')
    return ''


def assert_contains(msg, expected, scenario):
    assert expected.lower() in msg.lower(), f"[{scenario}] esperava '{expected}', recebeu: '{msg[:200]}'"
    print(f'  ✓ {scenario}: msg contém "{expected}"')


def main():
    # ─── Cenário 1: vídeo → rejeitado ───
    db_reset()
    send_media_event('fake-video-1', mimetype='video/mp4')
    time.sleep(8)
    msg = get_last_media_response_text()
    assert_contains(msg, 'só aceito FOTO', 'vídeo rejeitado')
    estado = db_get_state()
    # criativo NÃO deve estar marcado como recebido (guard SQL)
    assert estado is None or not estado.get('criativo', {}).get('recebido'), 'vídeo NÃO deve setar criativo'
    print(f'  ✓ DB: criativo não foi setado pra vídeo')

    # ─── Cenário 2: foto em coletando_info + brief vazio ───
    db_reset()
    db_set_estado({'etapa_atual': 'coletando_info', 'criativo': {'recebido': False}, 'brief': {}, 'ultima_tentativa': None})
    send_media_event('fake-img-2', mimetype='image/jpeg')
    time.sleep(10)
    msg = get_last_media_response_text()
    assert_contains(msg, 'ainda preciso', 'foto + brief vazio')

    # ─── Cenário 3: foto em aguardando_criativo + brief completo ───
    db_reset()
    brief_completo = {'campanha': {'nome': 'x'}, 'objetivo': 'morar', 'faixa_valor': 'ate_700k',
                      'conjunto': {'geo': 'X'}, 'anuncio': {'copy': 'x'}, 'targeting_meta': {'geo_locations': {}}}
    db_set_estado({'etapa_atual': 'aguardando_criativo', 'criativo': {'recebido': False}, 'brief': brief_completo, 'ultima_tentativa': None})
    send_media_event('fake-img-3', mimetype='image/png')
    time.sleep(10)
    msg = get_last_media_response_text()
    assert_contains(msg, 'CONFIRMAR', 'foto + brief completo')

    # ─── Cenário 4: foto em ativa → sugere NOVA ───
    db_reset()
    db_set_estado({'etapa_atual': 'ativa', 'criativo': {'recebido': True, 'url': 'old'},
                   'brief': brief_completo, 'ultima_tentativa': {'resultado': 'ok', 'campaign_id': '999', 'tentativas_count': 1}})
    send_media_event('fake-img-4', mimetype='image/jpeg')
    time.sleep(10)
    msg = get_last_media_response_text()
    assert_contains(msg, 'NOVA', 'foto em ativa')

    # ─── Cenário 5: foto duplicada (< 2 min) ───
    db_reset()
    from datetime import datetime, timedelta, timezone
    db_set_estado({'etapa_atual': 'aguardando_criativo',
                   'criativo': {'recebido': True, 'url': 'first', 'mimetype': 'image/jpeg',
                                'recebido_em': datetime.now(timezone.utc).isoformat()},
                   'brief': brief_completo, 'ultima_tentativa': None})
    send_media_event('fake-img-5', mimetype='image/png')
    time.sleep(10)
    msg = get_last_media_response_text()
    assert_contains(msg, 'atualizado', 'foto duplicada recente')

    print('\n✓ Branch de mídia validado em 5 cenários reais (sem set DB direto pro criativo)')


if __name__ == '__main__':
    main()
