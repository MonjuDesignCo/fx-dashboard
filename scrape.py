import json, re, urllib.request
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; FX-Dashboard-Bot/1.0)'
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='ignore')

def get_monday():
    now = datetime.now(JST)
    wd = now.weekday()  # 0=月 6=日
    if wd == 6: delta = 1
    else: delta = -wd
    return (now + timedelta(days=delta)).strftime('%Y-%m-%d')

# 国フラグ画像→国名・絵文字マッピング
FLAG_MAP = {
    'usa': ('米', '🇺🇸'), 'england': ('英', '🇬🇧'), 'uk': ('英', '🇬🇧'),
    'china': ('中', '🇨🇳'), 'japan': ('日', '🇯🇵'), 'euro': ('欧', '🇪🇺'),
    'australia': ('豪', '🇦🇺'), 'canada': ('加', '🇨🇦'),
    'newzy': ('NZ', '🇳🇿'), 'newzealand': ('NZ', '🇳🇿'),
    'germany': ('独', '🇩🇪'), 'france': ('仏', '🇫🇷'),
    'switzerland': ('スイス', '🇨🇭'), 'sweden': ('スウェーデン', '🇸🇪'),
}

def flag_from_img(src):
    src = src.lower()
    for key, val in FLAG_MAP.items():
        if key in src:
            return val
    return ('', '🌐')

# ランク画像→ランク文字マッピング（ファイル名ベース）
RANK_IMG_MAP = {
    'rank_s': 'S', 'rank_a': 'A', 'rank_b': 'B', 'rank_c': 'C',
    'rank_d': 'D', 'rank_e': 'E', 'rank_f': 'F',
    'maru': '○', 'sankaku': '△', 'batsu': '✕',
    'rank1': 'S', 'rank2': 'A', 'rank3': 'B', 'rank4': 'C',
}

def rank_from_img(src):
    src = src.lower()
    for key, val in RANK_IMG_MAP.items():
        if key in src:
            return val
    return ''

def scrape_kissfx_day(date_str):
    """
    date_str: '2026-05-18' 形式
    kissfx の日付別記事URLを生成してスクレイピング
    URL例: https://kissfx.com/article/fxdays20260518.html
    """
    d = datetime.strptime(date_str, '%Y-%m-%d')
    url = f"https://kissfx.com/article/fxdays{d.strftime('%Y%m%d')}.html"
    try:
        html = fetch(url)
    except Exception as e:
        print(f"  kissfx {date_str} 取得失敗: {e}")
        return []

    rows = []

    # テーブルの行を抽出（| で区切られたMarkdown表形式）
    # 実際はHTMLなので<tr>タグで抽出
    # まずHTMLから<tr>ブロックを取る
    tr_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    current_time = ''
    for tr in tr_blocks:
        # <td>を取り出す
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(tds) < 4:
            continue

        # 1列目: 時間
        time_raw = re.sub(r'<[^>]+>', '', tds[0]).strip()
        time_raw = re.sub(r'\s+', ' ', time_raw).strip()
        if re.match(r'\d{1,2}:\d{2}', time_raw):
            current_time = time_raw.split()[0]
        elif time_raw in ('-', ''):
            pass  # current_timeを引き継ぐ
        elif '翌' in time_raw:
            m = re.search(r'(\d{1,2}:\d{2})', time_raw)
            current_time = '翌' + (m.group(1) if m else '')

        # 2列目: 国フラグ画像
        img_src = ''
        img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', tds[1])
        if img_m:
            img_src = img_m.group(1)
        country_name, country_flag = flag_from_img(img_src)

        # 3列目: タイトル（HTMLタグ除去）
        title_html = tds[2]
        # 重要度判定（赤太字=最重要、太字=重要、通常=普通）
        is_red_bold = bool(re.search(r'<(b|strong)[^>]*>.*?<span[^>]*color.*?red|color.*?red.*?<(b|strong)', title_html, re.IGNORECASE)) or \
                      bool(re.search(r'style=["\'][^"\']*color\s*:\s*(red|#[Ee][Ee]0000|rgb\(2[0-9]{2},\s*0,\s*0)', title_html, re.IGNORECASE))
        is_bold = bool(re.search(r'<(b|strong)[^>]*>', title_html, re.IGNORECASE))
        title = re.sub(r'<[^>]+>', '', title_html).strip()
        title = re.sub(r'\s+', ' ', title).strip()
        if not title or title in ('-', '↑・'):
            continue

        # 重要度スコア
        if is_red_bold:
            importance = 3
        elif is_bold:
            importance = 2
        else:
            importance = 1

        # 4列目: 指標ランク（画像）
        rank_html = tds[3]
        rank_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', rank_html)
        rank = ''
        if rank_img:
            rank = rank_from_img(rank_img.group(1))
        # テキストでも判定
        rank_text = re.sub(r'<[^>]+>', '', rank_html).strip()
        if not rank and rank_text:
            rank = rank_text[:3]

        # 5列目: 市場予想値
        forecast = re.sub(r'<[^>]+>', '', tds[4]).strip() if len(tds) > 4 else '-'
        forecast = re.sub(r'\s+', '', forecast)

        # 6列目: 前回発表値
        prev = re.sub(r'<[^>]+>', '', tds[5]).strip() if len(tds) > 5 else '-'
        prev = re.sub(r'\s+', '', prev)

        if not title:
            continue

        rows.append({
            'time': current_time,
            'country': country_name,
            'flag': country_flag,
            'name': title,
            'importance': importance,
            'rank': rank,
            'forecast': forecast if forecast else '-',
            'prev': prev if prev else '-',
            '_source': 'kissfx'
        })

    return rows

def scrape_minkabu(date_str):
    """みんかぶFXから経済指標を取得"""
    url = f'https://fx.minkabu.jp/indicators?date={date_str}'
    try:
        html = fetch(url)
    except Exception as e:
        print(f"  みんかぶ取得失敗: {e}")
        return {}

    days = {}
    current_date = None

    # 日付ヘッダー
    for line in html.split('\n'):
        dm = re.search(r'(\d{4}年\d{2}月\d{2}日\([月火水木金土日]\))', line)
        if dm:
            current_date = dm.group(1)
            if current_date not in days:
                days[current_date] = []

        if current_date and '|' in line:
            # テーブル行パース
            parts = [p.strip() for p in line.split('|')]
            parts = [p for p in parts if p]
            if len(parts) < 3:
                continue

            time_m = re.match(r'\d{2}:\d{2}', parts[0])
            if not time_m:
                continue

            time_val = parts[0]
            # 指標名はリンク形式 [name](url)
            name_m = re.search(r'\[([^\]]+)\]', parts[2] if len(parts) > 2 else '')
            if not name_m:
                continue
            name = name_m.group(1)

            # 星の数
            stars_part = parts[3] if len(parts) > 3 else ''
            imp = len(re.findall(r'★', stars_part))
            if imp == 0:
                imp = 2  # デフォルト

            # pips
            pips_part = parts[4] if len(parts) > 4 else ''
            pips_m = re.search(r'([+-]?\d+\.?\d*)pips', pips_part)
            pips = pips_m.group(0).replace('pips','') if pips_m else ''

            prev = parts[5].strip() if len(parts) > 5 else '-'
            fc   = parts[6].strip() if len(parts) > 6 else '-'
            res  = parts[7].strip() if len(parts) > 7 else '-'

            days[current_date].append({
                'time': time_val,
                'name': name,
                'importance': imp,
                'rank': '',
                'pips': pips,
                'prev': prev,
                'forecast': fc,
                'result': res,
                '_source': 'minkabu'
            })

    return days

def build_data():
    now = datetime.now(JST)
    monday_str = get_monday()
    monday_dt  = datetime.strptime(monday_str, '%Y-%m-%d')

    print(f"今週月曜日: {monday_str}")

    weekdays = [(monday_dt + timedelta(days=i)) for i in range(5)]
    WDAY = ['月','火','水','木','金','土','日']

    # みんかぶ今週分取得
    print("Fetching みんかぶFX...")
    minkabu_data = scrape_minkabu(monday_str)

    # kissfx 日別取得（月〜金）
    print("Fetching 羊飼いFXブログ（日別）...")
    kissfx_by_date = {}
    for dt in weekdays:
        date_str = dt.strftime('%Y-%m-%d')
        ja_key   = f"{dt.month}月{dt.day:02d}日"
        print(f"  {date_str}...")
        rows = scrape_kissfx_day(date_str)
        kissfx_by_date[ja_key] = rows
        print(f"    → {len(rows)}件取得")

    # 今週のdays構築
    days_out = []
    for dt in weekdays:
        ja_key      = f"{dt.month}月{dt.day:02d}日"
        ja_date     = f"{dt.month}月{dt.day}日({WDAY[dt.weekday()]})"
        minkabu_key = dt.strftime('%Y年%m月%d日(') + WDAY[dt.weekday()] + ')'
        days_out.append({
            'date':    ja_date,
            'minkabu': minkabu_data.get(minkabu_key, []),
            'kissfx':  kissfx_by_date.get(ja_key, [])
        })

    sat = monday_dt + timedelta(days=5)
    week_range = f"{monday_dt.month}/{monday_dt.day}({WDAY[monday_dt.weekday()]}) — {sat.month}/{sat.day}({WDAY[sat.weekday()]})"
    this_week = {'week_range': week_range, 'days': days_out}

    # 既存data.jsonから過去週を読み込んで末尾に今週を追加・更新
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
        weeks = existing.get('weeks', [])
        # 同じweek_rangeがあれば上書き、なければ追加
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

    data = {
        'updated_at': now.isoformat(),
        'weeks': weeks
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ data.json 生成完了 ({len(weeks)}週分) / {now.strftime('%Y-%m-%d %H:%M JST')}")

if __name__ == '__main__':
    build_data()
