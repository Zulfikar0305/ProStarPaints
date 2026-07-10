#!/usr/bin/env python3
import os, sys, sqlite3, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cur_db = os.path.join(ROOT, 'db.sqlite3')
backup_db = os.path.join(ROOT, 'backup', 'db_before_rc1_reset.sqlite3')
PKS = [157, 159]

def fetch_rows(db_path):
    if not os.path.exists(db_path):
        return {'error': f'db not found: {db_path}'}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Get columns for table
    try:
        cur.execute("PRAGMA table_info(quotation_quotationlineitem);")
        cols = [r[1] for r in cur.fetchall()]
    except Exception as e:
        return {'error': str(e), 'db': db_path}
    # Build query
    try:
        q = f"SELECT {', '.join(cols)} FROM quotation_quotationlineitem WHERE id IN ({','.join('?' for _ in PKS)})"
        cur.execute(q, PKS)
        rows = cur.fetchall()
        out = []
        for r in rows:
            d = {cols[i]: r[i] for i in range(len(cols))}
            out.append(d)
        return {'db': db_path, 'rows': out}
    except Exception as e:
        return {'error': str(e), 'db': db_path}

print('Current DB:', cur_db)
res_cur = fetch_rows(cur_db)
print(json.dumps(res_cur, indent=2, default=str))
print('\nBackup DB:', backup_db)
res_bak = fetch_rows(backup_db)
print(json.dumps(res_bak, indent=2, default=str))
