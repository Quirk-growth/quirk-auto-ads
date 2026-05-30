#!/usr/bin/env python3
"""Smoke test PAUSAR: força 1 campanha ACTIVE, manda fluxo, valida PAUSED no DB."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def setup():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    # Force a campaign to ACTIVE
    cur.execute(f"""UPDATE auto_ads.campanhas SET status='ACTIVE'
                    WHERE id = (SELECT id FROM auto_ads.campanhas
                                WHERE telefone='{PHONE}' AND campaign_id IS NOT NULL
                                AND campaign_id != 'undefined'
                                ORDER BY criada_em DESC LIMIT 1)""")
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def count_status(s):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM auto_ads.campanhas WHERE telefone='{PHONE}' AND status=%s", (s,))
    n = cur.fetchone()[0]; conn.close()
    return n


def main():
    setup()
    before = count_status('ACTIVE')
    print(f'Antes: {before} ACTIVE')
    assert before >= 1, f'precisa de >=1 ACTIVE pra testar; tem {before}'

    paused_before = count_status('PAUSED')

    print('[pausar]')
    send('pausar')
    time.sleep(10)
    estado = get_estado()
    assert estado and estado.get('gestao'), f'esperava estado.gestao populado, é {estado}'
    assert estado['gestao']['passo'] == 'selecao', f"esperava passo=selecao, é {estado['gestao']['passo']}"
    print(f"  ✓ lista com {len(estado['gestao']['lista_candidatas'])} candidatas")

    print('[1]')
    send('1')
    time.sleep(10)
    estado = get_estado()
    assert estado['gestao']['passo'] == 'confirmacao', f"esperava passo=confirmacao, é {estado['gestao']['passo']}"
    print(f"  ✓ avançou pra confirmacao, selecionada: {estado['gestao']['selecionada']['nome']}")

    print('[SIM]')
    send('SIM')
    time.sleep(25)
    estado = get_estado()
    assert estado.get('gestao') is None, f"esperava gestao=null após execução, é {estado.get('gestao')}"
    paused_after = count_status('PAUSED')
    assert paused_after > paused_before, f'esperava +1 PAUSED; antes={paused_before} depois={paused_after}'
    print(f'  ✓ PAUSED no DB. {paused_before} → {paused_after}. Fluxo completo.')


if __name__ == '__main__':
    main()
