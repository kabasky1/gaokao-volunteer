"""高考志愿填报助手 - 浙江版 v2.1（三年综合+高级筛选）"""
import sqlite3, os, re
from flask import Flask, render_template, request, jsonify, session
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.urandom(16).hex()
ACCESS_PASSWORD = '123456'  # 密码，可自行修改
DB = os.path.join(os.path.dirname(__file__), 'data/schools.db')
YEARS = [2025, 2024, 2023]

# 地区分类映射（两类：经济区域 + 地理大区，互斥单选）
REGION_MAP = {
    # 经济区域
    '沿海城市': ['辽宁','河北','天津','山东','江苏','上海','浙江','福建','广东','广西','海南'],
    '内陆省份': ['北京','山西','内蒙古','吉林','黑龙江','安徽','江西','河南','湖北','湖南','重庆','四川','贵州','云南','西藏','陕西','甘肃','青海','宁夏','新疆'],
    '江浙沪': ['上海','江苏','浙江'],
    '京津冀': ['北京','天津','河北'],
    '长三角': ['上海','江苏','浙江','安徽'],
    '大湾区': ['广东','香港','澳门'],
    '成渝': ['四川','重庆'],
    # 地理大区
    '华北': ['北京','天津','河北','山西','内蒙古'],
    '东北': ['辽宁','吉林','黑龙江'],
    '华东': ['上海','江苏','浙江','安徽','福建','江西','山东'],
    '华中': ['河南','湖北','湖南'],
    '华南': ['广东','广西','海南'],
    '西南': ['重庆','四川','贵州','云南','西藏'],
    '西北': ['陕西','甘肃','青海','宁夏','新疆']
}

# 行业标签学校映射
TRADE_GROUPS = {
    '🚀国防七子': ['哈尔滨工业大学','哈尔滨工程大学','北京航空航天大学','北京理工大学','南京航空航天大学','南京理工大学','西北工业大学'],
    '📡两电一邮': ['电子科技大学','西安电子科技大学','北京邮电大学'],
    '💰两财一贸': ['中央财经大学','上海财经大学','对外经济贸易大学'],
    '⚖️五院四系': ['中国政法大学','西南政法大学','华东政法大学','中南财经政法大学','西北政法大学','北京大学','中国人民大学','武汉大学','吉林大学'],
    '🏗️建筑老八校': ['清华大学','东南大学','天津大学','同济大学','华南理工大学','哈尔滨工业大学','重庆大学','西安建筑科技大学'],
    '🏥四大医学院': ['北京协和医学院','北京大学医学部','复旦大学上海医学院','上海交通大学医学院'],
    '🚀卓越E9联盟': ['北京理工大学','重庆大学','大连理工大学','东南大学','华南理工大学','哈尔滨工业大学','天津大学','同济大学','西北工业大学']
}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ── 专业名归一化：去掉括号后缀、常见尾缀，用于跨年匹配 ──
def normalize_major(name):
    """归一化专业名，让不同写法能匹配上"""
    if not name: return ''
    n = name
    # 去掉英文括号及内容：(五年制), (5+3一体化) 等
    n = re.sub(r'\([^)]*\)', '', n)
    # 去掉中文括号及内容：（5＋3一体化）等
    n = re.sub(r'（[^）]*）', '', n)
    # 去掉方括号及内容：[含英语...] 等
    n = re.sub(r'\[[^\]]*\]', '', n)
    # 去掉常见尾缀
    for suffix in ['类', '班', '方向', '（师范）', '(师范)', '（实验班）', '(实验班)']:
        if n.endswith(suffix):
            n = n[:-len(suffix)]
            break
    return n.strip()

# ── 分数-位次一致性校验 ──
# 用2025年可靠数据构建 分数→正常位次范围 的映射
def build_score_rank_model(c):
    """从2025年官方数据建立分数到位次的映射表"""
    model = {}
    c.execute('SELECT CAST(score AS INTEGER) as sc, CAST(rank AS INTEGER) as rk FROM zj_scores WHERE rank!=\'\' AND CAST(rank AS INTEGER) BETWEEN 1 AND 300000')
    rows = c.fetchall()
    groups = {}
    for row in rows:
        sc = row['sc']
        rk = row['rk']
        if sc not in groups:
            groups[sc] = []
        groups[sc].append(rk)
    # 对每个分数，计算中位数和允许范围
    for sc, ranks in groups.items():
        ranks.sort()
        median = ranks[len(ranks)//2]
        # 允许范围：0.3倍~3倍中位数，同时放宽边界
        lo = max(1, int(median * 0.3))
        hi = min(300000, int(median * 3))
        model[sc] = (lo, hi, median)
    return model

def validate_score_rank(score, rank, model):
    """校验分数-位次是否合理，返回True=合理"""
    if not rank or rank <= 0:
        return False
    # 用最接近的分数查模型
    best = None
    for s in range(max(200, score-2), min(751, score+3)):
        if s in model:
            best = model[s]
            break
    if best is None:
        # 没有参考数据，用宽松阈值
        return 150 <= score <= 750 and 1 <= rank <= 300000
    lo, hi, med = best
    # 位次在合理范围内（0.3x~3x中位数）
    if lo <= rank <= hi:
        return True
    # 极端异常：偏差超过10倍
    if rank < med // 10 or rank > med * 10:
        return False
    # 中等偏差：根据学校类型放宽判断（这里保守返回True）
    return True

def get_school_info(c, name):
    """从学校库查学校标签"""
    c.execute('SELECT f985, f211, dual_class_name, nature_name, level_name, province_name, city_name, belong FROM schools WHERE name=?', (name,))
    return c.fetchone()

def query_year(c, year, lo, hi, filters=None):
    """查单年数据，支持筛选"""
    base_cols = 'a.school_name, a.major_name, a.school_code'
    score_col = 'CAST(a.score AS INTEGER)' if year == 2025 else 'CAST(a.min_score AS INTEGER)'
    rank_col = 'a.rank'
    plan_col = 'plan_num as plan' if year == 2025 else 'plan'
    table = 'zj_scores' if year == 2025 else 'zj_pdf_scores'
    year_filter = f'a.year=2025 AND CAST(a.score AS INTEGER) BETWEEN 200 AND 750' if year == 2025 else f'a.year={year} AND CAST(a.min_score AS INTEGER) BETWEEN 200 AND 750'
    major_code_col = ', a.major_code' if year == 2025 else ', \'\' as major_code'
    
    # 筛选条件
    where_extra = ''
    joins = ''
    if filters:
        if filters.get('level_985'): where_extra += ' AND s.f985=1'
        if filters.get('level_c9'):
            c9_list = "','".join(['清华大学','北京大学','浙江大学','复旦大学','上海交通大学','南京大学','西安交通大学','哈尔滨工业大学','中国科学技术大学'])
            where_extra += f" AND s.name IN ('{c9_list}')"
        if filters.get('level_shuangyiliu'): where_extra += " AND s.dual_class_name='双一流'"
        if filters.get('level_211'): where_extra += ' AND s.f211=1'
        if filters.get('level_province_key'): where_extra += " AND s.f985=0 AND s.f211=0 AND s.nature_name='公办' AND s.level_name='普通本科'"
        if filters.get('type_name'): where_extra += f" AND s.type_name='{filters['type_name']}'"
        if filters.get('trade_group'):
            schools = TRADE_GROUPS.get(filters['trade_group'], [])
            if schools:
                s_list = "','".join(schools)
                where_extra += f" AND s.name IN ('{s_list}')"
        if filters.get('nature'): where_extra += f" AND s.nature_name='{filters['nature']}'"
        if filters.get('province'): where_extra += f" AND s.province_name='{filters['province']}'"
        if filters.get('region'):
            provinces = REGION_MAP.get(filters['region'], [])
            if provinces:
                p_list = "','".join(provinces)
                where_extra += f" AND s.province_name IN ('{p_list}')"
        if where_extra:
            joins = 'LEFT JOIN schools s ON a.school_name=s.name'
    
    query = f'''
        SELECT {base_cols}, {score_col} as sc, {rank_col}, {plan_col} {major_code_col}
        FROM {table} a {joins}
        WHERE {year_filter} AND {score_col} BETWEEN ? AND ?
        {where_extra}
        ORDER BY sc DESC
    '''
    c.execute(query, (lo, hi))
    return [dict(r) for r in c.fetchall()]

def recommend(score, rank, filters=None, top_chong=15, top_wen=15, top_bao=15):
    """三年综合推荐"""
    conn = get_db()
    c = conn.cursor()
    
    margin = 35
    all_data = []
    
    # 构建分数-位次校验模型
    score_rank_model = build_score_rank_model(c)
    
    for year in YEARS:
        rows = query_year(c, year, score - margin, score + margin, filters)
        for r in rows:
            # 分数-位次一致性校验
            sc = r['sc']
            rk = int(r['rank']) if r['rank'] and r['rank'].strip() else 0
            if not validate_score_rank(sc, rk, score_rank_model):
                continue  # 跳过异常数据
            r['year'] = year
            all_data.append(r)
    
    # 补充查询：2025年PDF数据（部分专业名被截断，在zj_scores中找不到）
    c.execute('''
        SELECT a.school_name, a.major_name, a.school_code,
               CAST(a.min_score AS INTEGER) as sc, a.rank, a.plan
        FROM zj_pdf_scores a
        WHERE a.year=2025 AND CAST(a.min_score AS INTEGER) BETWEEN ? AND ?
    ''', (score - margin, score + margin))
    pdf2025 = c.fetchall()
    existing_keys = set()
    for r in all_data:
        if r['year'] == 2025:
            existing_keys.add((r['school_name'], normalize_major(r['major_name'])))
    for r in pdf2025:
        key = (r['school_name'], normalize_major(r['major_name']))
        if key not in existing_keys:
            rk = int(r['rank']) if r['rank'] and r['rank'].strip() else 0
            if validate_score_rank(r['sc'], rk, score_rank_model):
                all_data.append({'school_name': r['school_name'], 'major_name': r['major_name'],
                                 'school_code': r['school_code'], 'sc': r['sc'], 'rank': r['rank'],
                                 'plan': r['plan'], 'year': 2025})
    
    # 补充查询：2024年放宽范围（部分专业年度分数波动大±25不够）
    c.execute('''
        SELECT a.school_name, a.major_name, a.school_code,
               CAST(a.min_score AS INTEGER) as sc, a.rank, a.plan
        FROM zj_pdf_scores a
        WHERE a.year=2024 AND CAST(a.min_score AS INTEGER) BETWEEN ? AND ?
    ''', (score - 40, score + 40))
    pdf2024_wide = c.fetchall()
    existing_2024_keys = set()
    for r in all_data:
        if r['year'] == 2024:
            existing_2024_keys.add(normalize_major(r['major_name']))
    # 只针对已有2023/2025但缺2024的学校补充
    schools_with_2024_gap = set()
    for r in all_data:
        if r['year'] in (2023, 2025):
            schools_with_2024_gap.add(r['school_name'])
    for r in pdf2024_wide:
        norm = normalize_major(r['major_name'])
        if norm not in existing_2024_keys and r['school_name'] in schools_with_2024_gap:
            rk = int(r['rank']) if r['rank'] and r['rank'].strip() else 0
            valid = validate_score_rank(r['sc'], rk, score_rank_model)
            if valid:
                all_data.append({'school_name': r['school_name'], 'major_name': r['major_name'],
                                 'school_code': r['school_code'], 'sc': r['sc'], 'rank': r['rank'],
                                 'plan': r['plan'], 'year': 2024})
    
    # 批量查学校详细信息
    school_ids = {}
    c.execute('SELECT school_id, name, type_name, num_master, num_doctor, ruanke_rank, xueke_rank, special_arr, dualclass_arr, major_xueke, f985, f211, dual_class_name, nature_name, level_name, province_name, belong FROM schools')
    for row in c.fetchall():
        school_ids[row['name']] = dict(row)
    
    conn.close()
    
    # 按学校+归一化专业名聚合（跨年匹配不同写法）
    groups = defaultdict(lambda: {'school':'', 'major':'', 'school_code':'', 'major_code':'', 'years': {}, 'major_variants': []})
    for r in all_data:
        norm = normalize_major(r['major_name'])
        key = (r['school_name'], norm)
        g = groups[key]
        g['school'] = r['school_name']
        g['major'] = g['major'] or r['major_name']  # 保留第一个出现的名称
        g['school_code'] = g['school_code'] or (r.get('school_code') or '')
        g['major_code'] = g['major_code'] or (r.get('major_code') or '')
        # 记录所有专业名变体，去重
        if r['major_name'] not in g['major_variants']:
            g['major_variants'].append(r['major_name'])
        # rank可能含前导0（如"08222"），转int处理
        g['years'][r['year']] = {'score': r['sc'], 'rank': int(r['rank']) if r['rank'] and r['rank'].strip() else 999999, 'plan': r.get('plan','')}
    
    items = list(groups.values())
    
    # 计算平均分和平均位次
    for item in items:
        # 剔除明显异常的分数
        item['years'] = {y: v for y, v in item['years'].items() if 150 <= v['score'] <= 750 and 1 <= v['rank'] <= 300000}
        scores = [v['score'] for v in item['years'].values()]
        ranks = [v['rank'] for v in item['years'].values()]
        if not scores or not ranks: continue
        item['avg_score'] = round(sum(scores) / len(scores))
        item['avg_rank'] = round(sum(ranks) / len(ranks))
        item['year_count'] = len(item['years'])
    
    items = [i for i in items if i['year_count'] >= 2]
    
    # 第二轮过滤：用学校信息修正异常位次
    for item in items:
        si = school_ids.get(item['school'], {})
        nature = si.get('nature_name', '')
        level = si.get('level_name', '')
        # 民办/独立学院 位次 < 30000 → 数据异常，舍弃
        if (nature in ('民办','独立学院') or '专科' in level):
            item['years'] = {y: v for y, v in item['years'].items() if v['rank'] >= 30000}
            ranks2 = [v['rank'] for v in item['years'].values()]
            scores2 = [v['score'] for v in item['years'].values()]
            if not ranks2 or not scores2: item['year_count'] = 0; continue
            item['avg_rank'] = round(sum(ranks2) / len(ranks2))
            item['avg_score'] = round(sum(scores2) / len(scores2))
            item['year_count'] = len(item['years'])
    
    items = [i for i in items if i['year_count'] >= 2]
    items.sort(key=lambda x: x['avg_rank'])
    
    # 动态位次阈值
    if rank < 10000: threshold = 2000
    elif rank < 30000: threshold = 5000
    elif rank < 80000: threshold = 10000
    else: threshold = 15000
    
    # 分档
    results = {'冲': [], '稳': [], '保': []}
    seen = set()
    
    # 构建各校2025年专业名索引（用于判断缺失原因）
    school_2025_norms = {}
    for r in all_data:
        if r['year'] == 2025:
            sn = r['school_name']
            if sn not in school_2025_norms:
                school_2025_norms[sn] = set()
            school_2025_norms[sn].add(normalize_major(r['major_name']))
    
    for item in items:
        rank_diff = item['avg_rank'] - rank  # 正数=你的位次更好→保底, 负数=你的位次更差→冲刺
        score_diff = score - item['avg_score']  # 正数=你的分数更高→保底, 负数=你的分数更低→冲刺
        key = item['school'] + '|' + item['major']
        if key in seen: continue
        seen.add(key)
        
        # 趋势（基于位次：位次下降=数字变大=变容易=📉）
        sorted_years = sorted(item['years'].keys())
        trend = '➡️'
        if len(sorted_years) >= 2:
            first_r = item['years'][sorted_years[0]]['rank']
            last_r = item['years'][sorted_years[-1]]['rank']
            if last_r < first_r - 500: trend = '📈'
            elif last_r > first_r + 500: trend = '📉'
        
        # 判断2025年数据缺失原因
        missing_2025_reason = ''
        if '2025' not in item['years'] and len(item['years']) > 0:
            norm = normalize_major(item['major'])
            school_majors = school_2025_norms.get(item['school'], set())
            if school_majors:
                # 找到最接近的2025年专业
                similar = [m for m in school_majors if norm[:4] in m or m[:4] in norm]
                if similar:
                    missing_2025_reason = '2025年该专业名称或培养方向可能已调整'
                else:
                    missing_2025_reason = '2025年该专业可能已停止招生'
            else:
                missing_2025_reason = '2025年该专业可能已停止招生'
        
        # ── 三因子修正 ──
        ranks_list = sorted([item['years'][y]['rank'] for y in sorted_years])
        avg_r = sum(ranks_list) / len(ranks_list)
        std_r = (sum((r - avg_r)**2 for r in ranks_list) / len(ranks_list)) ** 0.5
        volatility = std_r / avg_r if avg_r > 0 else 0  # 变异系数
        
        # 1) 趋势偏移：连续方向×修正系数
        trend_factor = 1.0
        if len(ranks_list) >= 3:
            r0, r1, r2 = ranks_list[0], ranks_list[1], ranks_list[2]
            if r0 < r1 < r2: trend_factor = 0.85    # 连续2年下降(更容易)→调低avg_rank
            elif r0 > r1 > r2: trend_factor = 1.15  # 连续2年上升(更难)→调高avg_rank
        
        # 2) 缩招偏移
        plan_factor = 1.0
        valid_plans_list = [int(item['years'][y]['plan']) for y in sorted_years if item['years'][y].get('plan') and str(item['years'][y]['plan']).strip() and int(item['years'][y]['plan']) > 0]
        if len(valid_plans_list) >= 2:
            p_first, p_last = valid_plans_list[0], valid_plans_list[-1]
            p_change = (p_last - p_first) / p_first
            if p_change <= -0.3: plan_factor = 0.9    # 缩招30%+
            elif p_change >= 0.3: plan_factor = 1.1   # 扩招30%+
        
        # 综合调整位次
        adjusted_rank = item['avg_rank'] * trend_factor * plan_factor
        rank_diff_adj = adjusted_rank - rank
        
        # 3) 波动修正阈值
        adj_threshold = threshold * (1 + volatility * 2)  # 波动大→阈值放宽
        
        entry = {
            'school': item['school'],
            'major': item['major'],
            'school_code': item['school_code'],
            'major_code': item['major_code'],
            'years': item['years'],
            'avg_score': item['avg_score'],
            'avg_rank': item['avg_rank'],
            'adjusted_rank': round(adjusted_rank),
            'diff': score_diff,
            'rank_diff': rank_diff_adj,
            'trend': trend,
            'volatility': round(volatility * 100),
            'major_variants': item.get('major_variants', []),
            'missing_2025_reason': missing_2025_reason,
            'school_info': school_ids.get(item['school'], {})
        }
        
        # ── 三因子分档 ──
        if rank_diff_adj < -adj_threshold:
            cat = '冲'
        elif rank_diff_adj > adj_threshold:
            cat = '保'
        else:
            cat = '稳'
        
        # 分数辅助修正  # 位次在阈值内→稳妥
        
        # 分数辅助修正：位次说稳但分数差大→调整
        if cat == '稳':
            if score_diff < -15: cat = '冲'     # 分数低15+，实际是冲
            elif score_diff > 15: cat = '保'     # 分数高15+，实际是保
        # 分数辅助修正：位次说冲/保但分数与位次矛盾→保持在原档但标记边界
        if cat == '冲' and score_diff > 10:
            entry['borderline'] = '分数有优势，冲上概率较大'
        elif cat == '保' and score_diff < -10:
            entry['borderline'] = '分数不占优，保底不够稳'
        
        results[cat].append(entry)
    
    results['冲'] = results['冲'][:top_chong]
    results['稳'] = results['稳'][:top_wen]
    results['保'] = results['保'][:top_bao]
    
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    pwd = data.get('password', '') if data else ''
    if pwd == ACCESS_PASSWORD:
        session['auth'] = True
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': '密码错误'})

@app.route('/api/logout')
def api_logout():
    session.pop('auth', None)
    return jsonify({'ok': True})

@app.route('/api/check')
def api_check():
    return jsonify({'auth': session.get('auth', False)})

@app.route('/api/recommend')
def api_recommend():
    score = request.args.get('score', type=int)
    rank = request.args.get('rank', type=int)
    top_chong = request.args.get('top_chong', 15, type=int)
    top_wen = request.args.get('top_wen', 15, type=int)
    top_bao = request.args.get('top_bao', 15, type=int)
    
    filters = {}
    for key in ['level_c9','level_985','level_211','level_shuangyiliu','level_province_key','nature','type_name','trade_group','province','region']:
        val = request.args.get(key)
        if val: filters[key] = val
    
    if not score or not rank:
        return jsonify({'error': '请填写分数和位次'})
    
    results = recommend(score, rank, filters, top_chong, top_wen, top_bao)
    return jsonify(results)

@app.route('/api/filters')
def api_filters():
    """返回可用的筛选选项"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT province_name FROM schools WHERE province_name!='' ORDER BY province_name")
    provinces = [r[0] for r in c.fetchall()]
    conn.close()
    return jsonify({
        'provinces': provinces
    })

if __name__ == '__main__':
    conn = get_db()
    c = conn.cursor()
    for y in YEARS:
        if y == 2025:
            c.execute('SELECT COUNT(*) FROM zj_scores')
        else:
            c.execute('SELECT COUNT(*) FROM zj_pdf_scores WHERE year=?', (y,))
        print('  %d年: %d条' % (y, c.fetchone()[0]))
    conn.close()
    print()
    print('访问地址: http://localhost:5001')
    print('='*50)
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
