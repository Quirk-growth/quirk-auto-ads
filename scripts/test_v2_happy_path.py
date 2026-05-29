#!/usr/bin/env python3
"""Smoke test v2: brief → criativo → CONFIRMAR → estado final."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, n8n_api

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset_conversa():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    conn.commit(); conn.close()
    print(f'reset conversa pra {PHONE}')


def send_text(text):
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


def assert_etapa(esperada, lista_aceitavel=None):
    estado = get_estado()
    atual = estado['etapa_atual'] if estado else 'sem_conversa'
    if lista_aceitavel:
        assert atual in lista_aceitavel, f"etapa={atual} (esperava uma de {lista_aceitavel})"
    else:
        assert atual == esperada, f"etapa={atual} (esperada={esperada})"
    print(f'  ✓ etapa={atual}')


def main():
    reset_conversa()

    print('\n[msg 1: oi]')
    send_text('Oi, quero subir uma campanha')
    time.sleep(12)
    assert_etapa('coletando_info')

    print('\n[msg 2: brief curto]')
    send_text('Apartamento 2 quartos em Setor Bueno Goiânia, R$ 450 mil, perfil investidor, casado 30-50, R$ 50/dia 15 dias, alcance')
    time.sleep(15)
    estado = get_estado()
    brief = estado.get('brief') or {}
    print(f"  brief_campos={list(brief.keys())}")
    print(f"  etapa={estado['etapa_atual']}")

    print('\n[seta criativo direto via DB]')
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"""
      UPDATE auto_ads.conversas
      SET estado_json = jsonb_set(estado_json, '{{criativo}}', '{{"recebido":true,"url":"https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1080","mimetype":"image/jpeg","recebido_em":"now"}}'::jsonb),
          criativo_url = 'https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1080'
      WHERE telefone = '{PHONE}'
    """)
    conn.commit(); conn.close()
    print('  ✓ criativo seteado')

    print('\n[msg 3: CONFIRMAR]')
    send_text('CONFIRMAR')
    time.sleep(75)
    estado = get_estado()
    ult = estado.get('ultima_tentativa') or {}
    print(f"  etapa final={estado['etapa_atual']}")
    print(f"  ultima_tentativa: resultado={ult.get('resultado')} campaign_id={ult.get('campaign_id')} motivo={(ult.get('motivo') or '')[:200]}")

    assert estado['etapa_atual'] in ['ativa', 'falhou_dado', 'falhou_infra'], f"etapa inesperada: {estado['etapa_atual']}"
    print(f'\n✓ Happy path terminou em: {estado["etapa_atual"]}')


if __name__ == '__main__':
    main()
