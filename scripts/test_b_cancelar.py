#!/usr/bin/env python3
"""Smoke test CANCELAR em cada passo."""
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


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def cancel_at(steps):
    reset()
    send('pausar'); time.sleep(8)
    for s in steps:
        send(s); time.sleep(8)
    send('cancelar'); time.sleep(8)
    estado = get_estado()
    assert estado.get('gestao') is None, f'gestao não resetado após cancelar (steps={steps}): {estado.get("gestao")}'
    print(f'  ✓ CANCELAR após {steps} resetou gestao')


def main():
    cancel_at([])           # cancelar no selecao
    cancel_at(['1'])        # cancelar no confirmacao
    print('\n✓ CANCELAR validado em ambos passos')


if __name__ == '__main__':
    main()
