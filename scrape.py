import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; FX-Dashboard-Bot/1.0)'
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8', errors='ignore')

def get_week_monday():
    now = datetime.now(JST)
    days_ahead = (0 - now.weekday()) % 7
    if now.weekday() == 6:  # Sunday
        days_ahead = 1
    elif now.weekday() == 0:
        days_ahead = 0
    else:
        days_ahead = (0 - now.weekday()) % 7
    monday = now + timedelta(days=days_ahead)
    return monday.strftime('%Y-%m-%d')

def scrape_minkabu():
    monday = get_week_monday()
    url = f'https://fx.minkabu.jp/indicators?date={monday}'
    html = fetch(url)

    days = {}
    current_date = None

    date_pattern = re.compile(r'(\d{4}年\d{2}月\d{2}日\([月火水木金土日]\))')
    row_pattern = re.compile(
        r'(\d{2}:\d{2})\s*\|[^|]*\|\s*\[([^\]]+)\]\([^)]+\)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)',
        re.DOTALL
    )

    lines = html.split('\n')
    for line in lines:
        dm = date_pattern.search(line)
        if dm:
            current_date = dm.group(1)
            if current_date not in days:
                days[current_date] = []

        if current_date and '|' in line:
            rm = row_pattern.search(line)
            if rm:
                time_val = rm.group(1).strip()
                name = rm.group(2).strip()
                stars_raw = rm.group(3).strip()
                pips_raw = rm.group(4).strip()
                prev_raw = rm.group(5).strip()
                fc_raw = rm.group(6).strip()
                res_raw = rm.group(7).strip()

                imp = len(re.findall(r'★', stars_raw)) or 1

                pips_clean = re.search(r'[+-]?\d+\.?\d*pips', pips_raw)
                pips_val = pips_clean.group(0).replace('pips','').strip() if pips_clean else '---'

                days[current_date].append({
                    'time': time_val,
                    'name': name,
                    'importance': imp,
                    'rank': '',
                    'pips': pips_val,
                    'prev': prev_raw if prev_raw != '---' else '---',
                    'forecast': fc_raw if fc_raw != '---' else '---',
                    'result': res_raw if res_raw != '---' else '---'
                })

    # Fallback: simpler table extraction
    if not any(days.values()):
        table_rows = re.findall(
            r'\|\s*(\d{2}:\d{2})\s*\|[^|]+\|\s*\[([^\]]+)\]',
            html
        )
        for time_val, name in table_rows:
            if current_date:
                days.setdefault(current_date, []).append({
                    'time': time_val, 'name': name,
                    'importance': 2, 'rank': '',
                    'pips': '---', 'prev': '---',
                    'forecast': '---', 'result': '---'
                })

    return days

def scrape_kissfx():
    html = fetch('https://kissfx.com/article/20260518weekfx.html')

    # Try to find this week's article link
    week_link = re.search(r'href="(https://kissfx\.com/article/\d{8}weekfx\.html)"', html)
    if not week_link:
        # Try top page
        top = fetch('https://kissfx.com/')
        week_link = re.search(r'href="(https://kissfx\.com/article/\d{8}weekfx\.html)"', top)

    focus_by_day = {}
    week_theme = ''

    if week_link:
        html = fetch(week_link.group(1))

    # Extract week theme
    theme_m = re.search(r'今週の.*?焦点.*?\n(.+?)(?:\n|$)', html)
    if theme_m:
        week_theme = theme_m.group(1)[:60].strip()

    # Extract daily focus items
    day_sections = re.findall(
        r'▼\[?(5月\d+日\([月火水木金土日]\))\]?.*?\n((?:(?!▼\[?5月).)*)',
        html, re.DOTALL
    )
    for day_label, content in day_sections:
        items = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('・') or line.startswith('日)') or line.startswith('英)') or \
               line.startswith('米)') or line.startswith('豪)') or line.startswith('加)') or \
               line.startswith('欧)') or line.startswith('NZ)') or line.startswith('独)'):
                clean = re.sub(r'\*\*|\[|\]|\(https?://[^)]+\)', '', line).strip()
                if clean and len(clean) > 2:
                    items.append(clean[:80])
        if items:
            focus_by_day[day_label] = items[:6]

    return focus_by_day, week_theme

def build_data():
    now = datetime.now(JST)

    print("Fetching みんかぶFX...")
    try:
        minkabu_days = scrape_minkabu()
    except Exception as e:
        print(f"みんかぶ取得エラー: {e}")
        minkabu_days = {}

    print("Fetching 羊飼いFXブログ...")
    try:
        kissfx_focus, week_theme = scrape_kissfx()
    except Exception as e:
        print(f"羊飼い取得エラー: {e}")
        kissfx_focus, week_theme = {}, ''

    # Merge
    all_dates = sorted(set(list(minkabu_days.keys()) + list(kissfx_focus.keys())))

    days = []
    for date in all_dates:
        indicators = minkabu_days.get(date, [])
        focus = kissfx_focus.get(date, [])

        # Assign ranks from kissfx if available (simplified heuristic)
        rank_map = {
            'GDP': 'S', 'FOMC': 'S', 'PMI': 'A', 'CPI': 'A', '消費者物価': 'A',
            '雇用統計': 'A', '失業率': 'A', 'NVIDIA': 'S', 'RBA': 'B',
            '住宅': 'B', '生産': 'B', '小売': 'B', '鉱工業': 'B'
        }
        for ind in indicators:
            for keyword, rank in rank_map.items():
                if keyword in ind['name']:
                    if not ind['rank']:
                        ind['rank'] = rank
                    break

        days.append({
            'date': date,
            'focus': focus,
            'indicators': indicators
        })

    # Week range
    monday = get_week_monday()
    monday_dt = datetime.strptime(monday, '%Y-%m-%d')
    saturday_dt = monday_dt + timedelta(days=5)
    week_range = f"{monday_dt.month}/{monday_dt.day}({['月','火','水','木','金','土','日'][monday_dt.weekday()]}) — {saturday_dt.month}/{saturday_dt.day}({['月','火','水','木','金','土','日'][saturday_dt.weekday()]})"

    data = {
        'updated_at': now.isoformat(),
        'week_range': week_range,
        'week_theme': week_theme or '今週の相場注目材料',
        'days': days
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ data.json 生成完了: {len(days)}日分, 更新時刻: {now.strftime('%Y-%m-%d %H:%M JST')}")

if __name__ == '__main__':
    build_data()
