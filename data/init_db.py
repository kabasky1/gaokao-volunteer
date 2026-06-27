#!/usr/bin/env python3
"""导入学校数据到SQLite"""
import sqlite3, json, urllib.request, os, ssl

# macOS证书修复
ssl._create_default_https_context = ssl._create_unverified_context

DB_PATH = os.path.join(os.path.dirname(__file__), 'schools.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 省份表
    c.execute('''CREATE TABLE IF NOT EXISTS provinces (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        province_id TEXT UNIQUE
    )''')
    
    # 学校表
    c.execute('''CREATE TABLE IF NOT EXISTS schools (
        school_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        province_name TEXT,
        city_name TEXT,
        town_name TEXT,
        nature_name TEXT,
        type_name TEXT,
        level_name TEXT,
        belong TEXT,
        f985 INTEGER DEFAULT 0,
        f211 INTEGER DEFAULT 0,
        dual_class_name TEXT,
        zs_code TEXT,
        site TEXT,
        phone TEXT,
        content TEXT,
        school_special_num INTEGER DEFAULT 0,
        ruanke_rank INTEGER DEFAULT 0,
        xueke_rank TEXT,
        label_list TEXT,
        attr_list TEXT,
        updated INTEGER DEFAULT 0
    )''')
    
    # 学校投档线缓存
    c.execute('''CREATE TABLE IF NOT EXISTS school_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id INTEGER,
        province_id TEXT,
        year INTEGER,
        type TEXT,
        batch TEXT,
        zslx_name TEXT,
        local_batch_name TEXT,
        local_type_name TEXT,
        min_score INTEGER,
        min_section TEXT,
        max_score INTEGER,
        average_score INTEGER,
        filing TEXT,
        diff INTEGER,
        sg_info TEXT,
        updated INTEGER DEFAULT 0,
        UNIQUE(school_id, province_id, year, type)
    )''')
    
    # 专业录取线缓存
    c.execute('''CREATE TABLE IF NOT EXISTS major_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_id INTEGER,
        province_id TEXT,
        year INTEGER,
        type TEXT,
        special_id TEXT,
        sp_name TEXT,
        level2_name TEXT,
        level3_name TEXT,
        min_score INTEGER,
        min_section TEXT,
        max_score INTEGER,
        average_score INTEGER,
        lq_num TEXT,
        sp_info TEXT,
        sg_info TEXT,
        zslx_name TEXT,
        local_batch_name TEXT,
        info TEXT,
        updated INTEGER DEFAULT 0,
        UNIQUE(school_id, province_id, year, special_id, type)
    )''')
    
    conn.commit()
    return conn

def import_schools(conn):
    """从gaokao.cn API拉取学校列表"""
    c = conn.cursor()
    url = 'https://static-data.gaokao.cn/www/2.0/school/list.json?page=1&size=3000'
    print('正在下载学校列表...')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    items = [v for k,v in data.get('data',{}).items() if k.isdigit()]
    print(f'共{len(items)}所学校')
    
    count = 0
    for item in items:
        try:
            c.execute('''INSERT OR REPLACE INTO schools 
                (school_id, name, province_name, city_name, town_name, nature_name, type_name, level_name,
                 f985, f211, dual_class_name, zs_code, label_list, attr_list)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                int(item['school_id']), item['name'], item.get('pro',''), item.get('city',''),
                item.get('town',''), item.get('nature',''), item.get('type',''), item.get('level',''),
                1 if item.get('f985')=='1' else 0,
                1 if item.get('f211')=='1' else 0,
                '双一流' if item.get('dual_class')=='1' else '',
                item.get('zs_code',''), 
                json.dumps(item.get('label_list',[]), ensure_ascii=False),
                json.dumps(item.get('attr_list',[]), ensure_ascii=False)
            ))
            count += 1
        except Exception as e:
            print(f'  导入失败 [{item.get("school_id")}]: {e}')
    
    conn.commit()
    print(f'成功导入{count}所学校')

def import_provinces(conn):
    """省份映射表"""
    provinces = [
        (11,'北京'),(12,'天津'),(13,'河北'),(14,'山西'),(15,'内蒙古'),
        (21,'辽宁'),(22,'吉林'),(23,'黑龙江'),
        (31,'上海'),(32,'江苏'),(33,'浙江'),(34,'安徽'),(35,'福建'),(36,'江西'),(37,'山东'),
        (41,'河南'),(42,'湖北'),(43,'湖南'),(44,'广东'),(45,'广西'),(46,'海南'),
        (50,'重庆'),(51,'四川'),(52,'贵州'),(53,'云南'),(54,'西藏'),
        (61,'陕西'),(62,'甘肃'),(63,'青海'),(64,'宁夏'),(65,'新疆')
    ]
    c = conn.cursor()
    for pid, name in provinces:
        c.execute('INSERT OR REPLACE INTO provinces (id, name, province_id) VALUES (?,?,?)', (pid, name, str(pid)))
    conn.commit()
    print(f'导入{len(provinces)}个省份')

if __name__ == '__main__':
    conn = init_db()
    import_provinces(conn)
    import_schools(conn)
    conn.close()
    print('完成!')
