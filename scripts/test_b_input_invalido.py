#!/usr/bin/env python3
"""Smoke test: inputs inválidos mantém passo."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    cur.execute("UPDATE auto_ads.campanhas SET status='ACTIVE' WHERE id=17")
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_passo():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json -> 'gestao' ->> 'passo' FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def main():
    # Teste 1: número fora de range
    reset()
    send('pausar'); time.sleep(8)
    send('99'); time.sleep(8)
    p = get_passo()
    assert p == 'selecao', f'esperava selecao após número fora, tem {p}'
    print(f'  ✓ número 99 (fora) mantém passo=selecao')

    # Teste 2: verba fora de faixa
    reset()
    send('alterar verba'); time.sleep(8)
    send('1'); time.sleep(8)
    send('200'); time.sleep(8)
    p = get_passo()
    assert p == 'coleta_valor', f'esperava coleta_valor após verba fora, tem {p}'
    print(f'  ✓ verba 200 (fora) mantém passo=coleta_valor')

    print('\n✓ inputs inválidos não corrompem estado')


if __name__ == '__main__':
    main()
