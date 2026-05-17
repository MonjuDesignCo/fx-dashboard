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

# ── みんかぶFX スクレイパー ──────────────────────────────
def scrape_minkabu(monday_str):
    # country=focus_countries で主要国のみ取得（余分な指標を除外）
    url = f'https://fx.minkabu.jp/indicators?date={monday_str}&country=focus_countries'
    try:
        html = fetch(url)
    except Exception as e:
        print(f'  みんかぶ取得失敗: {e}')
        return {}

    days = {}
    current_date = None

    # Markdown変換後の形式でパース
    # 日付行: *2026年05月18日(月)*
    date_pat = re.compile(r'\*(\d{4}年\d{2}月\d{2}日\([月火水木金土日]\))\*')
    # テーブル行: | 08:01 |  | [指標名](URL) |  | +1.6pips | 0.8% | --- | --- |
    row_pat = re.compile(
        r'^\|\s*(\d{1,2}:\d{2}|未定)\s*\|[^|]*\|\s*\[([^\]]+)\]\(([^)]+)\)[^|]*\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|',
        re.MULTILINE
    )

    for line in html.split('\n'):
        # 日付ヘッダー検出
        dm = date_pat.search(line)
        if dm:
            current_date = dm.group(1)
            if current_date not in days:
                days[current_date] = []
            continue

        if not current_date:
            continue

        # テーブル行検出
        m = row_pat.match(line)
        if not m:
            continue

        time_val = m.group(1).strip()
        name     = m.group(2).strip()
        pips_raw = m.group(4).strip()
        prev_raw = m.group(5).strip()
        fc_raw   = m.group(6).strip()
        res_raw  = m.group(7).strip()

        # pips数値を抽出（符号付き）
        pm = re.search(r'([+-]?\d+\.?\d*)pips', pips_raw)
        pips = pm.group(1) if pm else ''

        def clean_val(v):
            v = v.strip()
            return '---' if v in ('---', '', '-') else v

        days[current_date].append({
            'time':       time_val,
            'name':       name,
            'importance': 2,  # みんかぶは星が動的描画のためデフォルト値
            'rank':       '',
            'pips':       pips,
            'prev':       clean_val(prev_raw),
            'forecast':   clean_val(fc_raw),
            'result':     clean_val(res_raw),
        })

    return days

# ── 羊飼いFXブログ 日別スクレイパー ────────────────────────
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

def flag_from_img(src):
    s = src.lower()
    for k, v in FLAG_MAP.items():
        if k in s:
            return COUNTRY_MAP.get(k, ''), v
    return '', '🌐'

def clean(text):
    t = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', t).strip()

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

        # 時間
        time_raw = clean(tds[0])
        if re.match(r'\d{1,2}:\d{2}', time_raw):
            current_time = time_raw.split()[0]
        elif '翌' in time_raw:
            m = re.search(r'(\d{1,2}:\d{2})', time_raw)
            current_time = '翌' + (m.group(1) if m else '')

        # 国旗
        img_src = ''
        img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', tds[1])
        if img_m:
            img_src = img_m.group(1)
        country, flag = flag_from_img(img_src)

        # タイトルと重要度
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

        # ランク
        rank = ''
        rank_td_text = clean(tds[3])
        for candidate in ['SS','S','A','B','C','D','◎','○','△','✕']:
            if candidate in rank_td_text:
                rank = candidate
                break

        RANK_TO_IMP = {
            'SS':5,'S':4,'A':3,'◎':3,'B':2,'○':2,'C':2,'△':1,'✕':1,'D':1
        }
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

    return rows

# ── メイン処理 ───────────────────────────────────────────
def build_data():
    now        = datetime.now(JST)
    monday_str = get_monday()
    monday_dt  = datetime.strptime(monday_str, '%Y-%m-%d')
    weekdays   = [monday_dt + timedelta(days=i) for i in range(5)]

    print(f'今週月曜: {monday_str}')

    # みんかぶFX（主要国フィルター付き）
    print('Fetching みんかぶFX (focus_countries)...')
    minkabu_data = scrape_minkabu(monday_str)
    for k, v in minkabu_data.items():
        print(f'  {k}: {len(v)}件')

    # 羊飼いFXブログ（日別）
    print('Fetching 羊飼いFXブログ...')
    kissfx_by_date = {}
    for dt in weekdays:
        date_str = dt.strftime('%Y-%m-%d')
        ja_key   = f"{dt.month}月{dt.day:02d}日"
        rows = scrape_kissfx_day(date_str)
        kissfx_by_date[ja_key] = rows
        print(f'  {date_str}: {len(rows)}件')

    # 週データ構築
    days_out = []
    for dt in weekdays:
        ja_key      = f"{dt.month}月{dt.day:02d}日"
        ja_date     = f"{dt.month}月{dt.day}日({WDAY[dt.weekday()]})"
        minkabu_key = dt.strftime('%Y年%m月%d日(') + WDAY[dt.weekday()] + ')'

        days_out.append({
            'date':    ja_date,
            'minkabu': minkabu_data.get(minkabu_key, []),
            'kissfx':  kissfx_by_date.get(ja_key, []),
        })

    sat = monday_dt + timedelta(days=5)
    week_range = (
        f"{monday_dt.month}/{monday_dt.day}({WDAY[monday_dt.weekday()]})"
        f" — {sat.month}/{sat.day}({WDAY[sat.weekday()]})"
    )
    this_week = {'week_range': week_range, 'days': days_out}

    # 既存data.jsonから過去週を保持して今週を追加/更新
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
