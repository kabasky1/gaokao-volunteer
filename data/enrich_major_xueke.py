"""补充专业级的学科评估数据"""
import sqlite3, urllib.request, json, ssl, os, time
ssl._create_default_https_context = ssl._create_unverified_context

DB = os.path.join(os.path.dirname(__file__), 'schools.db')

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def update():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    try: c.execute('ALTER TABLE schools ADD COLUMN major_xueke TEXT DEFAULT ""')
    except: pass
    conn.commit()
    
    # 获取浙江数据中出现的学校
    c.execute('''SELECT DISTINCT s.school_id, s.name FROM schools s 
        INNER JOIN (SELECT school_name FROM zj_pdf_scores UNION SELECT school_name FROM zj_scores) z 
        ON s.name = z.school_name
        WHERE s.school_id > 0''')
    schools = c.fetchall()
    print(f'共{len(schools)}所学校')
    
    for i, (sid, name) in enumerate(schools):
        try:
            data = fetch(f'https://static-data.gaokao.cn/www/2.0/school/{sid}/info.json?a=www.gaokao.cn')
            specials = data.get('data', {}).get('special', [])
            
            # 整理专业→学科评估映射
            major_map = {}
            for s in specials:
                major_name = s.get('special_name', '')
                xueke_score = s.get('xueke_rank_score', '')
                ruanke_level = s.get('ruanke_level', '')
                if major_name:
                    major_map[major_name] = {'xueke': xueke_score, 'ruanke': ruanke_level}
            
            if major_map:
                c.execute('UPDATE schools SET major_xueke=? WHERE school_id=?', 
                         (json.dumps(major_map, ensure_ascii=False), sid))
            
            if (i+1) % 200 == 0:
                conn.commit()
                print(f'  {i+1}/{len(schools)}')
            time.sleep(0.15)
        except Exception as e:
            print(f'  [{sid}]{name}: {e}')
    
    conn.commit()
    conn.close()
    print('完成!')

if __name__ == '__main__':
    update()
