"""补充学校详细信息（仅浙江录取数据中出现的学校）"""
import sqlite3, urllib.request, json, ssl, os, time
ssl._create_default_https_context = ssl._create_unverified_context

DB = os.path.join(os.path.dirname(__file__), 'schools.db')

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def update():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    # 确保列存在
    for col in ['num_master','num_doctor','ruanke_rank','xueke_rank','subject_arr','special_arr','dualclass_arr','master_arr','doctor_arr']:
        try: c.execute(f'ALTER TABLE schools ADD COLUMN {col} TEXT DEFAULT ""')
        except: pass
    conn.commit()
    
    # 获取浙江数据中出现的学校，且有school_id但未更新过的
    c.execute('''SELECT DISTINCT s.school_id, s.name FROM schools s 
        INNER JOIN (SELECT school_name FROM zj_pdf_scores UNION SELECT school_name FROM zj_scores) z 
        ON s.name = z.school_name
        WHERE s.school_id > 0 AND s.num_master = ""''')
    schools = c.fetchall()
    print(f'需要更新的学校: {len(schools)}所')
    
    for i, (sid, name) in enumerate(schools):
        try:
            data = fetch(f'https://static-data.gaokao.cn/www/2.0/school/{sid}/info.json?a=www.gaokao.cn').get('data', {})
            
            specials = [s['special_name'] for s in data.get('special', []) if s.get('nation_feature')=='1']
            duals = [d['class'] for d in data.get('dualclass', [])]
            
            c.execute('''UPDATE schools SET 
                num_master=?, num_doctor=?, ruanke_rank=?,
                xueke_rank=?, subject_arr=?, special_arr=?,
                dualclass_arr=?, master_arr=?, doctor_arr=?
                WHERE school_id=?''', (
                str(data.get('num_master','')), str(data.get('num_doctor','')),
                str(data.get('ruanke_rank','')),
                json.dumps(data.get('xueke_rank',{}), ensure_ascii=False),
                json.dumps(data.get('subject_arr',[]), ensure_ascii=False),
                json.dumps(specials, ensure_ascii=False),
                json.dumps(duals, ensure_ascii=False),
                json.dumps(data.get('master_arr',[]), ensure_ascii=False),
                json.dumps(data.get('doctor_arr',[]), ensure_ascii=False),
                sid
            ))
            
            if (i+1) % 50 == 0:
                conn.commit()
                print(f'  {i+1}/{len(schools)}')
            time.sleep(0.15)
        except Exception as e:
            print(f'  [{sid}] {e}')
    
    conn.commit()
    conn.close()
    print(f'完成! 共更新{len(schools)}所学校')

if __name__ == '__main__':
    update()
