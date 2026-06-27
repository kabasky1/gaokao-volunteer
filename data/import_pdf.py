"""导入PDF解析数据到SQLite"""
import sys, json, sqlite3, os
sys.path.insert(0, '/tmp')
from parse_zj_v4 import parse_pdf

DB = '/Users/kabasky/Desktop/项目/高考志愿填报助手/data/schools.db'

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS zj_pdf_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER, section TEXT,
        school_code TEXT, school_name TEXT,
        major_name TEXT, xk TEXT,
        plan TEXT, xuezhi TEXT, avg_score TEXT,
        min_score TEXT, rank TEXT,
        min_score2 TEXT, rank2 TEXT
    )''')
    conn.commit()
    return conn

def import_data(conn, rows):
    c = conn.cursor()
    c.execute('DELETE FROM zj_pdf_scores WHERE year=?', (rows[0]['year'],))
    count = 0
    for r in rows:
        c.execute('''INSERT INTO zj_pdf_scores 
            (year, section, school_code, school_name, major_name, xk,
             plan, xuezhi, avg_score, min_score, rank, min_score2, rank2)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (r['year'], r['section'], r['school_code'], r['school_name'],
             r['major_name'], r['xk'], r['plan'], r['xuezhi'], r['avg_score'],
             r['min_score'], r['rank'], r.get('min_score2',''), r.get('rank2','')))
        count += 1
    conn.commit()
    return count

if __name__ == '__main__':
    conn = init_db()
    for year in ['2023','2024','2025']:
        fpath = '/Users/kabasky/Desktop/浙江省普通高校招生投档及专业录取情况%s年.pdf' % year
        print('解析%s年...' % year, end=' ', flush=True)
        rows = parse_pdf(fpath, int(year))
        n = import_data(conn, rows)
        print('%d条' % n)
    
    # 验证
    c = conn.cursor()
    c.execute('SELECT year, COUNT(*) FROM zj_pdf_scores GROUP BY year ORDER BY year')
    for row in c.fetchall():
        print('  %s年: %d条' % row)
    
    # 跟XLS对比2025
    c.execute('SELECT COUNT(*) FROM zj_scores WHERE year=2025')
    xls_count = c.fetchone()[0]
    print('\n2025年XLS: %d条' % xls_count)
    
    conn.close()
