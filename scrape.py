import json, re, urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', errors='ignore')

def get_monday():
    now = datetime.now(JST)
    wd = now.weekday()
    delta = 1 if wd == 6 else -wd
    return (now + timedelta(days=delta)).strftime('%Y-%m-%d')

WDAY = ['月','火','水','木','金','土','日']

FLAG_MAP = {
    'usa':'🇺🇸','england':'🇬🇧','uk':'🇬🇧','china':'🇨🇳','japan':'🇯🇵',
    'euro':'🇪🇺','australia':'🇦🇺','canada':'🇨🇦',
    'newzy':'🇳🇿','newzealand':'🇳🇿','germany':'🇩🇪','france':'🇫🇷',
    'switzerland':'🇨🇭','sweden':'🇸🇪','norway':'🇳🇴',
}
COUNTRY_MAP = {
    'usa':'米','england':'英','uk':'英','china':'中','japan':'日',
    'euro':'欧','australia':'豪','canada':'加',
    'newzy':'NZ','newzealand':'NZ','germany':'独','france':'仏',
}

# ── みんかぶFX ──────────────────────────────────────────
def parse_minkabu_html(html):
    """みんかぶFXのMarkdown変換済みHTMLから指標データを抽出"""
    days = {}
    current_date = None

    # 日付ヘッダー: *2026年05月18日(月)*
    date_pat = re.compile(r'\*(\d{4}年\d{2}月\d{2}日\([月火水木金土日]\))\*')

    for line in html.split('\n'):
        dm = date_pat.search(line)
        if dm:
            current_date = dm.group(1)
            if current_date not in days:
                days[current_date] = []
            continue

        if not current_date or '|' not in line:
            continue

        # テーブル行をパイプで分割
        parts = [p.strip() for p in line.split('|')]
        # 空要素を除去
        parts = [p for p in parts if p]

        if len(parts) < 6:
            continue

        # parts[0]=時間, parts[1]=空(国旗列), parts[2]=[名前](URL), parts[3]=空(重要度), parts[4]=pips, parts[5]=前回, parts[6]=予想, parts[7]=結果
        # 時間チェック
        if not re.match(r'^\d{1,2}:\d{2}$|^未定$', parts[0]):
            continue

        time_val = parts[0]

        # 指標名: [名前](URL) 形式
        name_m = re.search(r'\[([^\]]+)\]', parts[2])
        if not name_m:
            continue
        name = name_m.group(1).strip()

        # pips: parts[4]
        pips = ''
        if len(parts) > 4:
            pm = re.search(r'([+-]?\d+\.?\d*)pips', parts[4])
            pips = pm.group(1) if pm else ''

        def cv(v):
            return '---' if v.strip() in ('---', '', '-') else v.strip()

        prev_val = cv(parts[5]) if len(parts) > 5 else '---'
        fc_val   = cv(parts[6]) if len(parts) > 6 else '---'
        res_val  = cv(parts[7]) if len(parts) > 7 else '---'

        days[current_date].append({
            'time':       time_val,
            'name':       name,
            'importance': 2,
            'rank':       '',
            'pips':       pips,
            'prev':       prev_val,
            'forecast':   fc_val,
            'result':     res_val,
        })

    return days

def scrape_minkabu(monday_str):
    # date と country を別々に送らず、正しいURL形式で送る
    # みんかぶはdate+countryの組み合わせが正しく動作しないため
    # dateのみ指定して全国データを取得し、後で主要国フィルタを適用する
    url = f'https://fx.minkabu.jp/indicators?date={monday_str}'
    try:
        html = fetch(url)
        print(f'  みんかぶURL: {url}')
    except Exception as e:
        print(f'  みんかぶ取得失敗: {e}')
        return {}

    days = parse_minkabu_html(html)
    total = sum(len(v) for v in days.values())
    print(f'  みんかぶ取得: {len(days)}日 / {total}件')
    return days

# ── 羊飼いFXブログ ──────────────────────────────────────
def flag_from_img(src):
    s = src.lower()
    for k, v in FLAG_MAP.items():
        if k in s:
            return COUNTRY_MAP.get(k, ''), v
    return '', '🌐'

def clean(text):
    t = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', t).strip()

RANK_TO_IMP = {
    'SS':5,'S':4,'A':3,'◎':3,'B':2,'○':2,'C':2,'△':1,'✕':1,'D':1
}

def scrape_kissfx_day(date_str):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    url = f'https://kissfx.com/article/fxdays{d.strftime("%Y%m%d")}.html'
    try:
        html = fetch(url)
    except Exception as e:
        print(f'  kissfx {date_str} 取得失敗: {e}')
        return []

    rows = []
    tr_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    current_time = ''

    for tr in tr_blocks:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(tds) < 4:
            continue

        time_raw = clean(tds[0])
        if re.match(r'\d{1,2}:\d{2}', time_raw):
            current_time = time_raw.split()[0]
        elif '翌' in time_raw:
            m2 = re.search(r'(\d{1,2}:\d{2})', time_raw)
            current_time = '翌' + (m2.group(1) if m2 else '')

        img_src = ''
        img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', tds[1])
        if img_m:
            img_src = img_m.group(1)
        country, flag = flag_from_img(img_src)

        title_html = tds[2]
        if re.search(r'color\s*:\s*(red|#[Ee][Ee]0{4})|<font[^>]+color=["\']?red', title_html, re.I):
            text_imp = 3
        elif re.search(r'<(b|strong)[^>]*>', title_html, re.I):
            text_imp = 2
        else:
            text_imp = 1
        title = clean(title_html)
        if not title or title in ('-', '↑・', '↑'):
            continue

        rank = ''
        rank_text = clean(tds[3])
        for candidate in ['SS','S','A','B','C','D','◎','○','△','✕']:
            if candidate in rank_text:
                rank = candidate
                break

        importance = max(text_imp, RANK_TO_IMP.get(rank, 1))
        forecast = clean(tds[4]) if len(tds) > 4 else '-'
        prev     = clean(tds[5]) if len(tds) > 5 else '-'

        rows.append({
            'time':       current_time,
            'country':    country,
            'flag':       flag,
            'name':       title,
            'importance': importance,
            'rank':       rank,
            'forecast':   forecast or '-',
            'prev':       prev or '-',
        })

    print(f'  kissfx {date_str}: {len(rows)}件')
    return rows

# ── メイン ────────────────────────────────────────────
def build_data():
    now        = datetime.now(JST)
    monday_str = get_monday()
    monday_dt  = datetime.strptime(monday_str, '%Y-%m-%d')
    weekdays   = [monday_dt + timedelta(days=i) for i in range(5)]

    print(f'今週月曜: {monday_str}')

    print('Fetching みんかぶFX...')
    minkabu_data = scrape_minkabu(monday_str)

    # デバッグ: 取得できた日付キーを確認
    print(f'  取得日付キー: {list(minkabu_data.keys())}')

    print('Fetching 羊飼いFXブログ...')
    kissfx_by_date = {}
    for dt in weekdays:
        date_str = dt.strftime('%Y-%m-%d')
        ja_key   = f"{dt.month}月{dt.day:02d}日"
        kissfx_by_date[ja_key] = scrape_kissfx_day(date_str)

    days_out = []
    for dt in weekdays:
        ja_key      = f"{dt.month}月{dt.day:02d}日"
        ja_date     = f"{dt.month}月{dt.day}日({WDAY[dt.weekday()]})"
        minkabu_key = dt.strftime('%Y年%m月%d日(') + WDAY[dt.weekday()] + ')'

        mb = minkabu_data.get(minkabu_key, [])
        print(f'  {ja_date}: みんかぶ{len(mb)}件 / kissfx{len(kissfx_by_date.get(ja_key,[]))}件')

        days_out.append({
            'date':    ja_date,
            'minkabu': mb,
            'kissfx':  kissfx_by_date.get(ja_key, []),
        })

    sat        = monday_dt + timedelta(days=5)
    week_range = (
        f"{monday_dt.month}/{monday_dt.day}({WDAY[monday_dt.weekday()]})"
        f" — {sat.month}/{sat.day}({WDAY[sat.weekday()]})"
    )
    this_week = {'week_range': week_range, 'days': days_out}

    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
        weeks = existing.get('weeks', [])
        found = False
        for i, w in enumerate(weeks):
            if w.get('week_range') == week_range:
                weeks[i] = this_week
                found = True
                break
        if not found:
            weeks.append(this_week)
    except Exception:
        weeks = [this_week]

    data = {'updated_at': now.isoformat(), 'weeks': weeks}
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 完了: {len(weeks)}週分 / {now.strftime("%Y-%m-%d %H:%M JST")}')

if __name__ == '__main__':
    build_data()
