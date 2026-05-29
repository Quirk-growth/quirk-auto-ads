#!/usr/bin/env python3
"""Aplica sql/004_estado_json.sql via psycopg2 direto."""
import os, sys
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    sql_path = '/Users/renanreal/quirk_auto_ads/sql/004_estado_json.sql'
    with open(sql_path) as f:
        sql = f.read()

    db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip()
    db_url = db_url.replace('aws-0-', 'aws-1-')

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

    cur.execute("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_schema='auto_ads' AND table_name='conversas' AND column_name='estado_json'
    """)
    row = cur.fetchone()
    assert row is not None, "Coluna estado_json não foi criada"
    print(f'✓ Coluna criada: {row[0]} {row[1]}')

    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname='auto_ads' AND tablename='conversas' AND indexname='conversas_etapa_idx'
    """)
    assert cur.fetchone() is not None, "Index conversas_etapa_idx não foi criado"
    print('✓ Index conversas_etapa_idx criado')

    cur.execute("""
        SELECT count(*) FROM auto_ads.conversas
        WHERE (estado_json -> 'criativo' ->> 'recebido')::bool = true
    """)
    print(f'  linhas com criativo populado: {cur.fetchone()[0]}')

    conn.close()
    print('\n✓ Migration 004 aplicada')


if __name__ == '__main__':
    main()
