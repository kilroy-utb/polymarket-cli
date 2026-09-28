#!/usr/bin/env python3
"""Generate a Polymarket snapshot digest HTML (v2 — grouped + categorized + i18n).

For full documentation, see the polymarket-digest skill:
  news-digest/polymarket-digest/SKILL.md
"""
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone

CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"FAIL {url}: {e}", file=sys.stderr)
        return None


# ---------- Filter: drop test / archival data ----------

_JUNK_PREFIXES = ("arch", "exciting", "test", "spam")


def is_junk(question: str) -> bool:
    q = question.lower().strip()
    for p in _JUNK_PREFIXES:
        if q.startswith(p):
            return True
    # Truly empty / placeholder questions
    if len(q) < 10:
        return True
    if q.endswith("?") and len(q.split()) <= 2:
        return True
    # Test / placeholder patterns
    for pat in (r"^test\b", r"\bexciting\b", r"^arch", r"placeholder", r"sample market",
                r"this is my market", r"\[new market\]", r"awefawef", r"^\[new",
                r"clob strapi", r"strapi integration", r"awdoiajwfiojawf",
                r"^[a-z]{10,}$"):
        if re.search(pat, q):
            return True
    return False


# ---------- Categorize by keyword ----------

CATEGORY_RULES = [
    ("crypto",   [r"\$btc", r"\$eth", r"\$sol", r"\$doge", r"\$matic", r"bitcoin", r"ethereum",
                  r"solana", r" fdv ", r"token launch", r"crypto", r"stablecoin",
                  r"defi", r"opensea", r"binance", r"coinbase", r"nft", r"luna", r"do kwon",
                  r"uniswap", r"blur", r"arbitrum", r"avax", r"staking"]),
    ("politics", [r"president", r"presidential", r"nominee", r"election", r"caucus",
                  r"primary ", r"poll", r"biden", r"trump", r"desantis", r"newsom",
                  r"republican", r"democrat", r"senator", r"congress", r"secretary of",
                  r"governor", r"speaker ", r"vote", r"party", r"resign", r"rnc",
                  r"attorney general", r"indict", r"indicted", r"extradited", r"charged",
                  r"federally", r"white house", r"impeach", r"cabinet"]),
    ("movies",   [r"golden globes", r" oscar", r"\boscars\b", r"best picture", r"best actor",
                  r"best actress", r"avatar", r"top gun", r"fabelmans", r"everything everywhere",
                  r"shazam", r"box office", r"movie", r"film ", r"ant-man", r"cocaine bear",
                  r"gross more than", r"domestically", r"opening weekend"]),
    ("sports",   [r"finals", r"championship", r"premier league", r"la liga", r"bundesliga",
                  r" serie a", r"nba", r"nfl", r"mlb", r"ufc", r" boxing", r" grand slam",
                  r" wimbledon", r" us open", r" australian open", r"f1 ", r"formula 1",
                  r" beat ", r" win .*final", r"super bowl", r"world cup", r" chess",
                  r"magnus", r"soccer", r"tennis", r"masters ", r"pga", r" qb ", r"scramble",
                  r"parlay", r" red zone", r"daytona", r"jake paul", r"tommy fury",
                  r"swiatek", r"pegula", r"lebron", r"red parlay", r"tails never fails",
                  r"manchester united", r"newcastle", r" ef ", r"field goal"]),
    ("economics",[r"\bfed\b", r"federal reserve", r"inflation", r"cpi", r"interest rate",
                  r" rate cut", r" rate hike", r"gdp", r"recession", r"unemployment",
                  r"treasury", r"bond yield", r"jobless", r"balance sheet", r"market cap",
                  r"price of .*oil", r"crude oil", r"barrel"]),
    ("tech",     [r"openai", r"gpt-", r"anthropic", r"gemini", r"llama", r"chatgpt",
                  r"deepmind", r"claude", r"nvidia", r" apple ", r"tesla", r"microsoft",
                  r" google ", r"amazon", r"meta ", r"spacex", r"ai model",
                  r"silicon valley", r"startup", r"ipo ", r"parameters", r"chatgpt competitor",
                  r" bing ", r"ai chatbot"]),
    ("crypto",   [r"\$btc", r"\$eth", r"\$sol", r"\$doge", r"\$matic", r"\$usdc",
                  r"\$busd", r"\$safe", r"\$matic", r"bitcoin", r"ethereum",
                  r"solana", r" fdv ", r"token launch", r"crypto", r"stablecoin",
                  r"defi", r"opensea", r"binance", r"coinbase", r"nft", r"luna", r"do kwon",
                  r"uniswap", r"blur", r"arbitrum", r"avax", r"staking",
                  r"usdc redemption", r"minting be halted",
                  r"safe token", r"silvergate", r"\bbase\b mainnet", r"usdc .*circulation",
                  r"metamask", r"airdrop"]),
    ("economics",[r"\bfed\b", r"federal reserve", r"inflation", r"cpi", r"interest rate",
                  r" rate cut", r" rate hike", r"gdp", r"recession", r"unemployment",
                  r"treasury", r"bond yield", r"jobless", r"balance sheet", r"market cap",
                  r"price of .*oil", r"crude oil", r"barrel", r"us bank fail",
                  r"svb", r"silicon valley bank", r"signature bank"]),
    ("world",    [r"israel", r"hamas", r"gaza", r"russia", r"ukraine", r"putin", r"zelensky",
                  r"taiwan", r"china", r"xi jinping", r"north korea", r"iran", r"saudi",
                  r"ceasefire", r"suez", r"un security", r"nato", r"nuclear weapon",
                  r"spy balloon", r"flying object"]),
    ("politics", [r"president", r"presidential", r"nominee", r"election", r"caucus",
                  r"primary ", r"poll", r"biden", r"trump", r"desantis", r"newsom",
                  r"republican", r"democrat", r"senator", r"congress", r"secretary of",
                  r"governor", r"speaker ", r"vote", r"party", r"resign", r"rnc",
                  r"attorney general", r"indict", r"indicted", r"extradited", r"charged",
                  r"federally", r"white house", r"impeach", r"cabinet",
                  r"supreme court", r"wisconsin"]),
    ("weather",  [r" snow ", r"snowfall", r"temperature", r"°c", r"°f", r" degrees ",
                  r"hurricane", r"tornado", r"flood"]),
    ("movies",   [r"golden globes", r" oscar", r"\boscars\b", r"best picture", r"best actor",
                  r"best actress", r"avatar", r"top gun", r"fabelmans", r"everything everywhere",
                  r"shazam", r"box office", r"movie", r"film ", r"ant-man", r"cocaine bear",
                  r"gross more than", r"domestically", r"opening weekend"]),
    ("music",    [r"spotify", r"billboard", r"#1 .*globally", r"album", r" grammy",
                  r"flowers"]),
    ("platform", [r"predictit", r"twitter outage", r" kalshi", r"ftx", r" dcg ",
                  r"genesis ", r"blockfi", r" voyager", r"three arrows"]),
    ("energy",   [r"crude oil", r"barrel of", r"natural gas", r"opec"]),
]


def categorize(question: str) -> str:
    q = question.lower()
    scores = Counter()
    for cat, patterns in CATEGORY_RULES:
        for p in patterns:
            if re.search(p, q):
                scores[cat] += 1
    if not scores:
        return "other"
    return scores.most_common(1)[0][0]


CATEGORY_ZH = {
    "crypto":    "加密貨幣",
    "politics":  "政治",
    "sports":    "體育",
    "economics": "經濟",
    "tech":      "科技",
    "celebrity": "名人",
    "world":     "國際",
    "weather":   "天氣",
    "movies":    "電影",
    "music":     "音樂",
    "platform":  "平台 / 業界",
    "energy":    "能源",
    "other":     "其他",
}


# ---------- Group similar markets ----------

def normalize_for_grouping(q: str) -> str:
    """Strip entities so 'Will X win?' and 'Will Y win?' group together."""
    base = q
    base = re.sub(r"^archWill\s+", "", base)
    base = re.sub(r"^Will\s+", "", base, flags=re.I)
    # Specific entities → generic placeholders
    base = re.sub(r"\b(Donald\s+)?Trump\b", "X-PERSON", base, flags=re.I)
    base = re.sub(r"\bJoe\s+Biden\b", "X-PERSON", base, flags=re.I)
    base = re.sub(r"\bRon\s+DeSantis\b", "X-PERSON", base, flags=re.I)
    base = re.sub(r"\bGavin\s+Newsom\b", "X-PERSON", base, flags=re.I)
    base = re.sub(r"\bKamala\s+Harris\b", "X-PERSON", base, flags=re.I)
    base = re.sub(r"\bNikki\s+Haley\b", "X-PERSON", base, flags=re.I)
    base = re.sub(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", "X-PERSON", base)  # FirstName LastName
    base = re.sub(r"Liverpool|Chelsea|Arsenal|Manchester City|Tottenham|Brentford|Brighton|Everton|Newcastle|Leicester|West Ham|Aston Villa|Crystal Palace|Fulham|Wolves|Nottingham|Sheffield|Burnley|Luton|Sunderland|Bournemouth|Ipswich", "X-TEAM", base)
    base = re.sub(r"\$\d+[kbm]?", "X-PRICE", base, flags=re.I)
    base = re.sub(r"\d{4}", "X-YEAR", base)
    return base.lower().strip().rstrip("?!.,")


def group_key(question: str) -> str:
    n = normalize_for_grouping(question)
    # Use first ~50 chars as group signature
    return n[:50]


# ---------- Translate: structured question parser ----------

# People / entities / companies / places — solid dictionary.
ENTITY_ZH = {
    # People
    "Donald Trump": "川普", "Donald J. Trump": "川普", "Trump": "川普",
    "Joe Biden": "拜登", "Biden": "拜登",
    "Ron DeSantis": "迪桑蒂斯", "DeSantis": "迪桑蒂斯",
    "Gavin Newsom": "紐森", "Newsom": "紐森",
    "Nikki Haley": "海利", "Haley": "海利",
    "Kamala Harris": "賀錦麗", "Harris": "賀錦麗",
    "Mike Pence": "彭斯", "Pence": "彭斯",
    "Vivek Ramaswamy": "拉馬斯瓦米", "Ramaswamy": "拉馬斯瓦米",
    "Tim Ryan": "提姆·萊恩",
    "Andy Levin": "安迪·李文",
    "Sean Patrick Maloney": "馬洛尼",
    "Julie Su": "朱莉·蘇",
    "George Santos": "喬治·桑托斯",
    "Ronna McDaniel": "羅娜·麥克丹尼爾",
    "Benjamin Netanyahu": "納坦雅胡", "Netanyahu": "納坦雅胡",
    "Volodymyr Zelensky": "澤倫斯基", "Zelensky": "澤倫斯基", "Zelenskyy": "澤倫斯基",
    "Vladimir Putin": "普丁", "Putin": "普丁",
    "Xi Jinping": "習近平",
    "Elon Musk": "馬斯克",
    "Sam Bankman-Fried": "SBF", "SBF": "SBF",
    "Sam Trabucco": "山姆·特拉布科", "Sam Tabucco": "山姆·特拉布科",
    "Caroline Ellison": "卡羅琳·艾莉森",
    "Andrew Tate": "安德魯·泰特",
    "Do Kwon": "權道亨",
    "Brendan Fraser": "布蘭登·費雪",
    "Cate Blanchett": "凱特·布蘭琪",
    "Jake Paul": "傑克·保羅",
    "Tommy Fury": "湯米·富里",
    "Magnus Carlsen": "卡爾森",
    "LeBron": "詹姆斯", "LeBron James": "詹姆斯",
    "Iga Swiatek": "斯威雅蒂", "Swiatek": "斯威雅蒂",
    "Jessica Pegula": "佩古拉", "Pegula": "佩古拉",
    # Companies / orgs
    "Polymarket": "Polymarket",
    "OpenAI": "OpenAI", "ChatGPT": "ChatGPT", "GPT-4": "GPT-4",
    "Google": "Google", "Bing": "Bing",
    "Apple": "Apple", "Microsoft": "微軟",
    "Amazon": "Amazon", "Meta": "Meta",
    "Tesla": "Tesla", "Nvidia": "Nvidia",
    "Coinbase": "Coinbase", "Binance": "幣安", "OpenSea": "OpenSea",
    "Uniswap": "Uniswap", "Arbitrum": "Arbitrum", "Blur": "Blur",
    "Optimism": "Optimism", "Base": "Base",
    "Anthropic": "Anthropic", "Claude": "Claude",
    "DeepMind": "DeepMind", "Gemini": "Gemini",
    "LLaMA": "LLaMA", "Llama": "LLaMA",
    "Twitter": "Twitter",
    "Spotify": "Spotify",
    "BlockFi": "BlockFi", "Voyager": "Voyager", "Three Arrows Capital": "三箭資本",
    "Genesis": "Genesis", "DCG": "DCG",
    "FTX": "FTX", "Silvergate": "Silvergate",
    "Metamask": "MetaMask",
    "SpaceX": "SpaceX",
    # Tokens / cryptos
    "Bitcoin": "比特幣", "BTC": "比特幣",
    "Ethereum": "以太幣", "ETH": "以太幣",
    "Solana": "Solana", "SOL": "Solana",
    "Dogecoin": "狗狗幣", "DOGE": "狗狗幣",
    "Polygon": "Polygon", "MATIC": "MATIC",
    "USDC": "USDC", "BUSD": "BUSD", "SAFE": "SAFE",
    "Luna": "Luna", "LUNA": "Luna",
    "Arbitrum's token": "Arbitrum 代幣", "OpenSea's token": "OpenSea 代幣",
    # Sports teams
    "Liverpool": "利物浦", "Manchester City": "曼城", "Chelsea": "切爾西",
    "Arsenal": "阿森納", "Manchester United": "曼聯", "Newcastle": "紐卡斯爾",
    "Tottenham": "熱刺", "Spurs": "熱刺", "Brentford": "布倫特福德",
    "Brighton": "布萊頓", "Everton": "埃弗頓", "West Ham": "西漢姆",
    "Aston Villa": "阿斯頓維拉", "Crystal Palace": "水晶宮", "Fulham": "富勒姆",
    "Wolves": "狼隊", "Wolverhampton": "狼隊",
    "Nottingham Forest": "諾丁漢森林", "Bournemouth": "伯恩茅斯",
    "Luton": "盧頓", "Burnley": "伯恩利", "Sheffield": "謝菲爾德",
    "Ipswich": "伊普斯維奇", "Sunderland": "桑德蘭",
    "Celtics": "塞爾蒂克", "Dodgers": "道奇",
    "Southampton": "南安普敦", "Leicester": "萊斯特城", "Liecester": "萊斯特城",
    "Leeds": "利茲", "OKC": "雷霆",
    # Places / countries
    "U.S.": "美國", "US": "美國", "United States": "美國", "USA": "美國",
    "New York": "紐約", "Central Park": "中央公園",
    "Pennsylvania": "賓州", "Wisconsin": "威斯康辛",
    "U.K.": "英國", "UK": "英國",
    "Israel": "以色列", "Russia": "俄羅斯", "Ukraine": "烏克蘭",
    "China": "中國", "Taiwan": "台灣", "Iran": "伊朗",
    "North Korea": "北韓", "Saudi": "沙烏地",
    "Qatar": "卡達",
    # Movies / pop culture
    "Avatar: The Way of Water": "《阿凡達：水之道》", "Avatar": "《阿凡達》",
    "Top Gun: Maverick": "《捍衛戰士：獨行俠》", "Top Gun": "《捍衛戰士》",
    "The Fabelmans": "《法貝爾曼》",
    "Everything Everywhere All At Once": "《媽的多重宇宙》",
    "Shazam! Fury of the Gods": "《沙贊！眾神之怒》",
    "Ant-Man and the Wasp: Quantumania": "《蟻人與黃蜂女：量子狂熱》",
    "Cocaine Bear": "《古柯鹼熊》",
    "Flowers": "《Flowers》",
}

# Common verbs / patterns
VERB_ZH = {
    "win the": "贏得", "beat": "擊敗", "remain": "繼續擔任",
    "be the next": "成為下一任", "file to run": "宣布參選",
    "reach": "達到", "gross more than": "票房超過",
    "be above": "超過", "be below": "低於",
    "launch": "發行", "have": "擁有", "release": "釋出",
    "be available in the US": "在美國開放",
    "cut rates": "降息", "hike rates": "升息",
    "go insolvent": "倒閉", "depeg": "脫鉤",
    "file for bankruptcy": "聲請破產",
    "extradite": "引渡", "indict": "起訴",
    "report": "回報", "outage": "中斷",
    "snow": "下雪",
}

# Locations / events
EVENT_ZH = {
    "2024 Iowa Caucus": "2024 年愛荷華州黨團會議",
    "2024 Presidential Election": "2024 總統大選",
    "U.S. 2024 Republican presidential nomination": "美國 2024 共和黨總統提名",
    "U.S. 2024 Presidential Election": "2024 美國總統大選",
    "2024 US Presidential Election": "2024 美國總統大選",
    "U.S. Secretary of Labor": "美國勞工部長",
    "Secretary of Labor": "勞工部長",
    "U.S. Senate": "美國參議院",
    "2024 election": "2024 選舉",
    "the 2024 election": "2024 選舉",
    "World Cup": "世界盃", "Super Bowl": "超級盃",
    "Super Bowl LVII": "超級盃 LVII", "Super Bowl LVIII": "超級盃 LVIII",
    "NBA Finals": "NBA 總冠軍賽",
    "Wimbledon Championships": "溫布頓網球錦標賽",
    "Australian Open": "澳洲網球公開賽",
    "U.S. Open": "美國公開賽",
    "Premier League championship": "英超冠軍",
    "English Premier League": "英格蘭超級聯賽",
    "Tata Steel Masters 2023": "2023 Tata Steel 大師賽",
    "Golden Globes": "金球獎", "Oscar": "奧斯卡",
    "Best Picture - Drama": "最佳劇情片",
    "Best Picture - Musical or Comedy": "最佳音樂或喜劇片",
    "Best Actor - Drama": "最佳劇情片男主角",
    "Best Actress - Drama": "最佳劇情片女主角",
    "Best Picture": "最佳影片",
    "Best Actor": "最佳男主角",
    "Best Actress": "最佳女主角",
    "central bank digital currency": "央行數位貨幣",
    "FDV": "完全稀釋估值",
    "ChatGPT competitor": "ChatGPT 競爭對手",
    "2028 Republican presidential nomination": "2028 共和黨總統提名",
    "2028 Democratic presidential nomination": "2028 民主黨總統提名",
    "2028 US Presidential Election": "2028 美國總統大選",
    "Iowa Caucus": "愛荷華州黨團會議",
    "New Hampshire primary": "新罕布什爾州初選",
    "presidential primary": "總統初選",
    "Speaker of the House": "聯邦眾議院議長",
    "Speaker of the United States House of Representatives": "聯邦眾議院議長",
    "Tata Steel Masters": "Tata Steel 大師賽",
    "Republican presidential nomination": "共和黨總統提名",
    "Democratic presidential nomination": "民主黨總統提名",
    "Republican Party": "共和黨", "Democratic Party": "民主黨",
    "Republican House": "共和黨眾議院",
    "Democratic House": "民主黨眾議院",
    "Senate": "參議院", "House": "眾議院",
    "White House": "白宮",
    "Federal Reserve": "聯準會", "the Fed": "聯準會",
    "Bond yield": "債券殖利率", "treasury": "財政部",
    "interest rate": "利率", "rate cut": "降息", "rate hike": "升息",
    "inflation rate": "通膨率", "balance sheet": "資產負債表",
    "rate": "利率",
}

# Months / dates
MONTH_ZH = {
    "January": "一月", "February": "二月", "March": "三月", "April": "四月",
    "May": "五月", "June": "六月", "July": "七月", "August": "八月",
    "September": "九月", "October": "十月", "November": "十一月", "December": "十二月",
    "Jan": "一月", "Feb": "二月", "Mar": "三月", "Apr": "四月",
    "Jun": "六月", "Jul": "七月", "Aug": "八月", "Sep": "九月", "Oct": "十月", "Nov": "十一月", "Dec": "十二月",
}

# Other phrases
PHRASE_ZH = {
    "year end": "年底", "EOY": "年底", "by year end": "年底前",
    "next ": "下一任 ", "next year": "明年", "this year": "今年",
    "publicly": "公開", "officially": "正式",
    "President of the USA": "美國總統",
    "be President of the USA": "成為美國總統",
    "be the next president": "成為下一任總統",
    "be the next Secretary of Labor": "成為下一任勞工部長",
    "win the White House": "入主白宮",
}


def _translate_dict(s: str, table: dict) -> str:
    """Apply dictionary, longest-key-first to avoid prefix collisions.

    Uses word boundaries so 'US' inside 'USDC' isn't matched separately.
    """
    for k in sorted(table.keys(), key=len, reverse=True):
        # Use word boundaries; fall back to plain replace for keys that
        # already contain non-word chars.
        if re.search(r"\w", k):
            pattern = r"\b" + re.escape(k) + r"\b"
            s = re.sub(pattern, table[k], s)
        else:
            s = s.replace(k, table[k])
    return s


def summarize(question: str) -> str:
    """Render a 5-15 character Chinese summary of what the market asks.

    Strategy: extract named entities (already in ENTITY_ZH / EVENT_ZH),
    keep critical numbers/dates in original form. Skip articles and verbs.
    Never produce broken mixed English — this is NOT a full translation.
    """
    # First apply entity/event translation (these are unambiguous)
    s = _translate_dict(question, EVENT_ZH)
    s = _translate_dict(s, ENTITY_ZH)
    s = _translate_dict(s, MONTH_ZH)
    s = _translate_dict(s, PHRASE_ZH)

    # Strip leading question words
    s = re.sub(r"^(Who will|Which party will|Will|Would)\s+", "", s, flags=re.I)

    # Drop common verbs / connectors — leave entities and the thing being asked about
    # We strip the verb but keep "Yes/No" relationship implicit
    drop_words = [
        r"\bbe the next\b", r"\bbe available\b", r"\bbe above\b", r"\bbe below\b",
        r"\bwin the\b", r"\bbeat\b", r"\breach\b", r"\bhave\b",
        r"\bgross more than\b", r"\bfile to run\b", r"\bfile for\b",
        r"\bremain\b", r"\bcut rates?\b", r"\bhike rates?\b",
        r"\blaunch their token\b", r"\blaunch\b", r"\btransferable\b",
        r"\bextradited\b", r"\bindicted\b", r"\bcharged\b",
        r"\bsuspend\b", r"\bgo insolvent\b", r"\bdepeg\b",
        r"\benter\b", r"\bpublicly\b", r"\bfile\b",
        r"\bwill\b", r"\bwould\b", r"\bcan\b",
        r"\bfor president\b", r"\bsnow\b", r"\bany field goal\b",
        r"\bany\s+\w+\s+be\b",
    ]
    for w in drop_words:
        s = re.sub(w, "", s, flags=re.I)

    # Strip "by <date>" / "in <year>" / "on <date>" — keep date but drop the prep
    s = re.sub(r"\s+by\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+in\s+(\d{4})\b", r" \1", s)
    s = re.sub(r"\s+on\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+through\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+after\s+launch\b", " 發行後", s, flags=re.I)
    s = re.sub(r"\s+after\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+before\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+from\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+the\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+of the\s+", " ", s, flags=re.I)
    s = re.sub(r"\s+to\s+", " ", s, flags=re.I)

    # Apostrophe-s → 的
    s = re.sub(r"(\w)'s\b", r"\1的", s)

    # Drop article / connector words that survived
    s = re.sub(r"\bthere\s+be\s+a\b", "", s, flags=re.I)
    s = re.sub(r"\bthere\s+be\b", "", s, flags=re.I)
    s = re.sub(r"\bany\s+", "", s, flags=re.I)

    # Drop filler English verbs / preps
    for w in ["be", "a", "an", "or", "and", "the", "for", "in", "of", "on", "at", "to"]:
        s = re.sub(r"\b" + w + r"\b\s*", "", s, flags=re.I)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    # Drop leading question words that may have escaped
    s = re.sub(r"^(Who|Which|What|When|Where)\s+", "", s, flags=re.I)

    # Cap at reasonable length
    if len(s) > 60:
        # Try to find a natural break
        for sep in [" vs ", " 達 ", " 贏 ", " 擊敗 ", " 降 ", " 升 "]:
            if sep in s:
                s = s.split(sep)[0] + sep.rstrip() + " ..."
                break

    # Trim trailing punctuation
    s = s.rstrip(" ?.,")
    return s


# Keep the original translate() as a fallback (returns best-effort full sentence).
# The HTML now uses summarize() instead, which produces cleaner zh text.


# ---------- Pull data ----------

markets = _get(f"{CLOB}/markets?limit=500")
if not markets or "data" not in markets:
    print("Could not fetch CLOB markets", file=sys.stderr)
    sys.exit(1)

data = markets["data"]


def is_active(m):
    """Show the market if it has prices AND (is still active OR has a resolved outcome)."""
    q = m.get("question", "")
    if is_junk(q):
        return False
    if not m.get("tokens"):
        return False
    # Active (open) — always show
    if not m.get("closed"):
        return True
    # Closed — only show if it was actually resolved (some winner token)
    for t in m["tokens"]:
        if t.get("winner") is True:
            return True
    return False


active = [m for m in data if is_active(m)]

# Sort: trading first, then by resolved (resolved first), then by |spread| desc
def sort_key(m):
    return (
        not bool(m.get("accepting_orders")),
        not any(t.get("winner") is True for t in m.get("tokens", [])),
        -abs((next((t for t in m["tokens"] if t.get("outcome") == "No"), {}).get("price") or 0)
            - (next((t for t in m["tokens"] if t.get("outcome") == "Yes"), {}).get("price") or 0)),
    )
active.sort(key=sort_key)
# Cap to keep page load reasonable
MAX_MARKETS = 200
active = active[:MAX_MARKETS]

# Build per-market rows
rows = []
for m in active:
    yes_t = next((t for t in m["tokens"] if t.get("outcome") == "Yes"), m["tokens"][0])
    no_t = next((t for t in m["tokens"] if t.get("outcome") == "No"), m["tokens"][1])
    yp, np = yes_t.get("price"), no_t.get("price")
    spread = (np - yp) if (yp is not None and np is not None) else None
    # Determine resolved outcome (winner flag)
    yes_won = yes_t.get("winner") is True
    no_won = no_t.get("winner") is True
    if yes_won:
        result = "yes"
    elif no_won:
        result = "no"
    else:
        result = None  # unresolved / open
    q = m.get("question", "?")
    rows.append({
        "question": q,
        "question_zh": summarize(q),
        "category": categorize(q),
        "yes_price": yp, "no_price": np, "spread": spread,
        "trading": bool(m.get("accepting_orders")),
        "closed": bool(m.get("closed")),
        "result": result,
        "group": group_key(q),
    })

# Group by (category, group_key)
groups: dict = {}
for r in rows:
    key = (r["category"], r["group"])
    groups.setdefault(key, []).append(r)

# Each group: take the one with highest trading status / most activity
def group_summary(items):
    # Pick "primary" market: trading first, then by |spread| desc
    items_sorted = sorted(items, key=lambda r: (not r["trading"], -abs(r["spread"]) if r["spread"] is not None else 0))
    primary = items_sorted[0]
    # Collect all distinct questions for the expanded view
    return {
        "category": primary["category"],
        "primary": primary,
        "all": items_sorted,
        "count": len(items_sorted),
    }


group_list = [group_summary(items) for items in groups.values()]
# Sort groups: trading first, then by category, then by |spread| of primary
group_list.sort(key=lambda g: (
    not g["primary"]["trading"],
    g["category"],
    -abs(g["primary"]["spread"]) if g["primary"]["spread"] is not None else 0,
))

trades = _get(f"{DATA}/trades?limit=30") or []

now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ---------- Render HTML ----------

def fmt_pct(p):
    if p is None:
        return "?"
    return f"{float(p) * 100:.1f}%"


def fmt_spread(s):
    if s is None:
        return "—"
    return f"{float(s) * 100:.1f}pp"


# Render one group as a card / table
def render_group(g):
    primary = g["primary"]
    badge = "\U0001F7E2" if primary["trading"] else ("\u26AA" if primary["closed"] else "\U0001F7E1")
    cls = "trading" if primary["trading"] else ""
    spread_class = ""
    if primary["spread"] is not None:
        if abs(primary["spread"]) > 0.1:
            spread_class = "spread-huge"
        elif abs(primary["spread"]) > 0.02:
            spread_class = "spread-wide"
        elif abs(primary["spread"]) < 0.001:
            spread_class = "spread-locked"

    # Result badge: "✓ Yes" / "✓ No" / "—" (open) with color
    result_cell = '<td class="num result">—</td>'
    if primary.get("result") == "yes":
        result_cell = '<td class="num result yes-win">✓ 是</td>'
    elif primary.get("result") == "no":
        result_cell = '<td class="num result no-win">✓ 否</td>'

    extra_rows = ""
    if g["count"] > 1:
        extra_rows = "<tr class=\"group-detail\"><td colspan=\"5\"><details><summary>展開看其他 "
        extra_rows += str(g["count"]) + " 個相關市場</summary><ul>"
        for r in g["all"][:8]:  # cap at 8 to keep page light
            extra_rows += "<li>" + r["question"] + " — <b>Yes " + fmt_pct(r["yes_price"]) + "</b></li>"
        extra_rows += "</ul></details></td></tr>"

    return (
        "\n    <tr class=\"" + spread_class + " " + cls + "\">"
        "<td class=\"q\">" + badge + " " + primary["question"]
        + "<div class=\"q-zh\">" + primary["question_zh"] + "</div>"
        + (f"<span class=\"group-count\">+{g['count']-1} 相關</span>" if g["count"] > 1 else "")
        + "</td>"
        "<td class=\"num yes\">" + fmt_pct(primary["yes_price"]) + "</td>"
        "<td class=\"num no\">" + fmt_pct(primary["no_price"]) + "</td>"
        "<td class=\"num spread\">" + fmt_spread(primary["spread"]) + "</td>"
        + result_cell
        + "</tr>"
        + extra_rows
    )


# Group by category, then render each category as a section
groups_by_cat: dict = {}
for g in group_list:
    groups_by_cat.setdefault(g["category"], []).append(g)


cat_sections_html = ""
for cat_key in ("politics", "economics", "world", "tech", "crypto", "sports",
                "weather", "movies", "music", "platform", "energy", "celebrity", "other"):
    if cat_key not in groups_by_cat:
        continue
    cat_zh = CATEGORY_ZH[cat_key]
    cat_groups = groups_by_cat[cat_key]
    cat_sections_html += (
        "\n<h2>" + cat_zh + " (" + str(len(cat_groups)) + " 主題)</h2>"
        "\n<table>"
        "\n  <thead><tr><th>主題</th><th>是</th><th>否</th><th>差距</th><th>結果</th></tr></thead>"
        "\n  <tbody>"
    )
    for g in cat_groups:
        cat_sections_html += render_group(g)
    cat_sections_html += "\n  </tbody>\n</table>"


# Trades table (translate titles too)
def translate_title(t: str) -> str:
    return summarize(t) if t else "?"


trades_html = ""
for t in trades[:20]:
    side = t.get("side", "?")
    cls = "buy" if side == "BUY" else "sell"
    try:
        ts = datetime.fromtimestamp(int(t.get("timestamp", 0)), tz=timezone.utc).strftime("%H:%M:%S")
    except Exception:
        ts = "?"
    price = fmt_pct(t.get("price"))
    try:
        size_str = f"{float(t.get('size', 0)):>8.2f}"
    except (ValueError, TypeError):
        size_str = "?"
    out = t.get("outcome", "?")
    title_en = (t.get("title", "?") or "?")[:60]
    title_zh = translate_title(title_en)
    trades_html += (
        "\n    <tr class=\"" + cls + "\">"
        "<td class=\"time\">" + ts + "</td>"
        "<td class=\"side\">" + side + "</td>"
        "<td class=\"num\">" + price + "</td>"
        "<td class=\"num\">x" + size_str + "</td>"
        "<td class=\"out\">[" + out + "]</td>"
        "<td class=\"title\">" + title_en + "<div class=\"q-zh\">" + title_zh + "</div></td>"
        "</tr>"
    )


html = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymarket 全球焦點 """ + now_utc + """</title>
<style>
  :root {
    --bg: #0e1117; --panel: #161b22; --panel-alt: #1a1f2b;
    --fg: #c9d1d9; --fg-dim: #8b949e; --border: #30363d;
    --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC",
                 "Microsoft JhengHei", Consolas, monospace;
    margin: 0; padding: 24px; line-height: 1.5;
  }
  h1 { color: var(--accent); margin: 0 0 4px 0; font-size: 22px; }
  .sub { color: var(--fg-dim); margin-bottom: 8px; font-size: 13px; }
  .intro { color: var(--fg-dim); margin: 0 0 24px 0; font-size: 12px; max-width: 800px; }
  h2 {
    color: var(--accent); font-size: 14px; font-weight: 600;
    margin: 32px 0 12px 0; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }
  table { width: 100%; border-collapse: collapse; background: var(--panel); font-size: 13px; }
  th {
    text-align: left; color: var(--fg-dim); font-weight: normal;
    padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--panel-alt);
  }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
  tr:hover td { background: var(--panel-alt); }
  td.q { max-width: 800px; }
  td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  td.yes { color: var(--green); font-weight: 600; }
  td.no  { color: var(--red);   font-weight: 600; }
  td.spread { color: var(--fg-dim); }
  tr.spread-huge td.spread { color: var(--yellow); font-weight: 600; }
  tr.spread-wide td.spread  { color: var(--yellow); }
  tr.spread-locked td.spread { color: var(--green); }
  tr.trading td.q { font-weight: 600; }
  tr.buy td.side  { color: var(--green); font-weight: 600; }
  tr.sell td.side { color: var(--red);   font-weight: 600; }
  td.time { color: var(--fg-dim); font-variant-numeric: tabular-nums; }
  td.out  { color: var(--accent); }
  td.title { color: var(--fg-dim); }
  td.title .q-zh { color: var(--fg); margin-top: 2px; font-size: 12px; }
  td.result { font-weight: 600; }
  td.yes-win { color: var(--green); }
  td.no-win  { color: var(--red); }
  .q-zh {
    color: var(--fg); margin-top: 2px; font-size: 12px; opacity: 0.85;
  }
  .group-count {
    display: inline-block; margin-left: 8px;
    padding: 1px 6px; border-radius: 3px;
    background: var(--panel-alt); color: var(--fg-dim); font-size: 11px;
  }
  tr.group-detail td { padding: 0 12px 8px 36px; background: var(--bg); border-bottom: 1px solid var(--border); }
  tr.group-detail details { color: var(--fg-dim); font-size: 12px; }
  tr.group-detail summary { cursor: pointer; padding: 4px 0; }
  tr.group-detail ul { margin: 4px 0; padding-left: 20px; }
  tr.group-detail li { margin: 2px 0; }
  .meta {
    display: flex; gap: 24px; margin: 16px 0 32px 0; padding: 12px 16px;
    background: var(--panel); border-left: 3px solid var(--accent); font-size: 13px;
    flex-wrap: wrap;
  }
  .meta b { color: var(--fg-dim); font-weight: normal; margin-right: 6px; }
  .legend { color: var(--fg-dim); font-size: 12px; margin-top: 8px; }
</style>
</head>
<body>
<h1>Polymarket 全球焦點</h1>
<div class="sub">Generated """ + now_utc + """</div>
<p class="intro">
  Polymarket 是全球關注的時事與趨勢的「市場機率」訊號源 — 這份報告把今天 30+ 個主題的市場共識整理出來，
  按分類（政治 / 加密 / 經濟 / 科技 / 國際 / 體育 / 名人）排序，並附中文摘要。
  「差距」欄位（Yes 機率 - No 機率）表示全球共識強度：綠色 ≈ 0 為強烈共識，黃色差距大為有爭議或流動性差。
</p>

<div class="meta">
  <div><b>主題數:</b>""" + str(len(group_list)) + """</div>
  <div><b>市場總數:</b>""" + str(len(rows)) + """</div>
  <div><b>現正交易中:</b>""" + str(sum(1 for r in rows if r["trading"])) + """</div>
  <div><b>分類:</b>""" + str(len(groups_by_cat)) + """</div>
  <div><b>資料來源:</b>CLOB API, Data API</div>
</div>
""" + cat_sections_html + """

<h2>最近交易 (最新在上)</h2>
<table>
  <thead>
    <tr><th>時間</th><th>方向</th><th>價格</th><th>數量</th><th>結果</th><th>市場</th></tr>
  </thead>
  <tbody>""" + trades_html + """
  </tbody>
</table>
<div class="legend">
  &#x1F7E2; 現正接受下單 · &#x1F7E1; 活躍但暫停接受下單 · 綠色差距 ≈ 0 為強烈共識 · 黃色差距大為有爭議
</div>
</body>
</html>
"""

with open("report.html", "w") as f:
    f.write(html)

n_trading = sum(1 for r in rows if r["trading"])
print(f"Report: report.html ({len(html)} bytes, {len(group_list)} topics, {len(rows)} markets, {n_trading} trading, {len(groups_by_cat)} categories)")
