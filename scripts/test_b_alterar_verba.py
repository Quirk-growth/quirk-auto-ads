#!/usr/bin/env python3
"""Smoke test ALTERAR_VERBA: 4 turnos, valida verba nova no DB."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def setup():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    cur.execute(f"""UPDATE auto_ads.campanhas
                    SET status='ACTIVE',
                        json_extrator = jsonb_set(json_extrator, '{{campanha,verba_diaria}}', '50'::jsonb)
                    WHERE id = 17""")
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_verba_camp17():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute("SELECT (json_extrator->'campanha'->>'verba_diaria')::int FROM auto_ads.campanhas WHERE id=17")
    v = cur.fetchone()[0]; conn.close()
    return v


def main():
    setup()
    print(f'verba inicial: R$ {get_verba_camp17()}/dia')

    send('alterar verba'); time.sleep(10)
    send('1'); time.sleep(10)
    send('80'); time.sleep(10)
    send('SIM'); time.sleep(25)

    final = get_verba_camp17()
    assert final == 80, f'verba esperada 80, tem {final}'
    print(f'  ✓ verba R$ 50 → R$ {final}/dia. Sucesso.')


if __name__ == '__main__':
    main()
