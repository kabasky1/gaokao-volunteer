"""导入2025浙江XLS到SQLite"""
import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'schools.db')

try:
    import xlrd
except:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'xlrd', '-q'])
    import xlrd

def init_tables(conn):
    c = conn.cursor()
    # 浙江投档数据表
    c.execute('''CREATE TABLE IF NOT EXISTS zj_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER,
        school_code TEXT,
        school_name TEXT,
        major_code TEXT,
        major_name TEXT,
        plan_num INTEGER,
        score REAL,
        rank TEXT,
        tag TEXT,
        city TEXT,
        UNIQUE(year, school_code, major_code)
    )''')
    conn.commit()

def import_xls(conn, filepath, year):
    wb = xlrd.open_workbook(filepath)
    sheet = wb.sheet_by_index(0)
    c = conn.cursor()
    count = 0
    errors = 0
    
    for r in range(1, sheet.nrows):  # 跳过表头
        try:
            school_code = str(int(sheet.cell_value(r, 0))) if sheet.cell_value(r, 0) else ''
            school_name = str(sheet.cell_value(r, 1)).strip()
            major_code = str(int(sheet.cell_value(r, 2))) if sheet.cell_value(r, 2) else ''
            major_name = str(sheet.cell_value(r, 3)).strip()
            plan_num = int(sheet.cell_value(r, 4)) if sheet.cell_value(r, 4) else 0
            score = float(sheet.cell_value(r, 5)) if sheet.cell_value(r, 5) else 0
            rank_val = str(int(sheet.cell_value(r, 6))) if sheet.cell_value(r, 6) else ''
            tag = str(sheet.cell_value(r, 7)).strip() if r < 8 else ''
            city = str(sheet.cell_value(r, 8)).strip() if r < 9 else ''
            
            if not school_code or not school_name:
                continue
                
            c.execute('''INSERT OR REPLACE INTO zj_scores 
                (year, school_code, school_name, major_code, major_name, plan_num, score, rank, tag, city)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (year, school_code, school_name, major_code, major_name, plan_num, score, rank_val, tag, city))
            count += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f'  行{r}错误: {e}')
    
    conn.commit()
    return count

if __name__ == '__main__':
    conn = sqlite3.connect(DB_PATH)
    init_tables(conn)
    
    xls_path = '/Users/kabasky/Desktop/浙江省2025年普通高校招生普通类第一段平行投档分数线表.xls'
    if not os.path.exists(xls_path):
        print(f'文件不存在: {xls_path}')
        sys.exit(1)
    
    print('导入2025年浙江投档数据...')
    count = import_xls(conn, xls_path, 2025)
    print(f'成功导入{count}条记录')
    
    # 验证
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM zj_scores WHERE year=2025')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(DISTINCT school_name) FROM zj_scores WHERE year=2025')
    schools = c.fetchone()[0]
    c.execute('SELECT MIN(score), MAX(score) FROM zj_scores WHERE year=2025 AND score>0')
    score_range = c.fetchone()
    print(f'共{total}条, {schools}所学校, 分数范围{score_range[0]}-{score_range[1]}')
    
    conn.close()
