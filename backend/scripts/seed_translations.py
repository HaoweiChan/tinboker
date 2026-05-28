#!/usr/bin/env python3
"""
One-shot bootstrap: seed stock_translations into the configured database.

These rows are the snapshot of the prior local SQLite DB at the time of the
Postgres restoration. Run once after the new Postgres comes up; the file is
intended to be deleted in a follow-up PR.

Usage:
    docker exec tinboker-backend-dev python -m scripts.seed_translations
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.postgres import get_session, init_engine, create_all_tables
from src.services.translation_service import TranslationService
from src.database import models  # noqa: F401 - register models with Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Official brand hex colors sourced from brand guidelines / corporate identity
BRAND_COLORS: dict[str, str] = {
    "1301": "#003087",
    "1303": "#00703C",
    "2303": "#0055A5",
    "2308": "#E2231A",
    "2317": "#003DA5",
    "2330": "#003F87",
    "2345": "#004B87",
    "2357": "#00539B",
    "2382": "#005BAC",
    "2395": "#E30613",
    "2412": "#E2231A",
    "2454": "#E2001A",
    "2474": "#0072BC",
    "2881": "#E86800",
    "2882": "#00703C",
    "2886": "#C8102E",
    "2891": "#D31920",
    "2912": "#F37021",
    "3008": "#005BAC",
    "3711": "#0055A5",
    "AAPL": "#000000",
    "ABBV": "#071D49",
    "ABT": "#C8102E",
    "ADBE": "#FF0000",
    "AMD": "#ED1C24",
    "AMZN": "#FF9900",
    "ASML": "#007BC7",
    "AVGO": "#CC0000",
    "BABA": "#FF6A00",
    "BAC": "#E31837",
    "BIDU": "#2932E1",
    "BRK-B": "#003087",
    "BYD": "#1B5FAD",
    "C": "#003B70",
    "CMCSA": "#6F3FA3",
    "COST": "#E31837",
    "CRM": "#00A1E0",
    "CSCO": "#049FD9",
    "DIS": "#006E99",
    "GOOGL": "#4285F4",
    "GS": "#7399C6",
    "HD": "#F96302",
    "IBM": "#0F62FE",
    "INTC": "#0071C5",
    "JD": "#E1251B",
    "JNJ": "#CA0A0F",
    "JPM": "#003087",
    "KO": "#F40009",
    "LI": "#003DA5",
    "LLY": "#C8102E",
    "MA": "#EB001B",
    "MCD": "#FFC72C",
    "META": "#0082FB",
    "MRK": "#009999",
    "MS": "#003087",
    "MSFT": "#00A4EF",
    "NFLX": "#E50914",
    "NIO": "#00AEEF",
    "NKE": "#000000",
    "NVDA": "#76B900",
    "ORCL": "#F80000",
    "PDD": "#E2231A",
    "PEP": "#004B93",
    "PFE": "#0093D0",
    "PG": "#003DA5",
    "QCOM": "#3253DC",
    "SAP": "#0070F2",
    "SBUX": "#00704A",
    "SONY": "#000000",
    "T": "#00A8E0",
    "TM": "#EB0A1E",
    "TMO": "#002060",
    "TSLA": "#CC0000",
    "TSM": "#003F87",
    "V": "#1A1F71",
    "VZ": "#CD040B",
    "WFC": "#D71E28",
    "WMT": "#0071CE",
    "XOM": "#E0002B",
    "XPEV": "#0064D2",
}

# (ticker, market, name_en, name_zh_tw, status)
TRANSLATIONS: list[tuple[str, str, str | None, str | None, str]] = [
    ("1301", "TW", "Formosa Plastics", "台塑", "approved"),
    ("1303", "TW", "Nan Ya Plastics", "南亞", "approved"),
    ("2303", "TW", "United Microelectronics", "聯電", "approved"),
    ("2308", "TW", "Delta Electronics", "台達電", "approved"),
    ("2317", "TW", "Hon Hai Precision Industry", "鴻海", "approved"),
    ("2330", "TW", "Taiwan Semiconductor Manufacturing", "台積電", "approved"),
    ("2345", "TW", "Accton Technology", "智邦", "approved"),
    ("2357", "TW", "Asustek Computer", "華碩", "approved"),
    ("2382", "TW", "Quanta Computer", "廣達", "approved"),
    ("2395", "TW", "Advantech", "研華", "approved"),
    ("2412", "TW", "Chunghwa Telecom", "中華電信", "approved"),
    ("2454", "TW", "Mediatek", "聯發科", "approved"),
    ("2474", "TW", "Catcher Technology", "可成", "approved"),
    ("2881", "TW", "Fubon Financial", "富邦金", "approved"),
    ("2882", "TW", "Cathay Financial", "國泰金", "approved"),
    ("2886", "TW", "Mega Financial", "兆豐金", "approved"),
    ("2891", "TW", "Ctbc Financial", "中信金", "approved"),
    ("2912", "TW", "President Chain Store", "統一超", "approved"),
    ("3008", "TW", "Largan Precision", "大立光", "approved"),
    ("3711", "TW", "Ase Technology", "日月光投控", "approved"),
    ("AAPL", "US", "Apple", "蘋果", "approved"),
    ("ABBV", "US", "Abbvie", "艾伯維", "approved"),
    ("ABT", "US", "Abbott Laboratories", "亞培", "approved"),
    ("ADBE", "US", "Adobe", "奧多比", "approved"),
    ("AMD", "US", "Advanced Micro Devices", "超微", "approved"),
    ("AMZN", "US", "Amazon Com", "亞馬遜", "approved"),
    ("ASML", "US", "Asml", "艾司摩爾", "approved"),
    ("AVGO", "US", "Broadcom", "博通", "approved"),
    ("BABA", "US", "Alibaba", "阿里巴巴", "approved"),
    ("BAC", "US", "Bank of America", "美國銀行", "approved"),
    ("BIDU", "US", "Baidu", "百度", "approved"),
    ("BRK-B", "US", "Berkshire Hathaway", "波克夏", "approved"),
    ("BYD", "US", "Byd", "比亞迪", "approved"),
    ("C", "US", "Citigroup", "花旗", "approved"),
    ("CMCSA", "US", "Comcast Corp New", "康卡斯特", "approved"),
    ("COST", "US", "Costco Wholesale", "好市多", "approved"),
    ("CRM", "US", "Salesforce", "賽富時", "approved"),
    ("CSCO", "US", "Cisco Systems", "思科", "approved"),
    ("DIS", "US", "Walt Disney", "迪士尼", "approved"),
    ("GOOGL", "US", "Alphabet", "谷歌", "approved"),
    ("GS", "US", "Goldman Sachs", "高盛", "approved"),
    ("HD", "US", "Home Depot", "家得寶", "approved"),
    ("IBM", "US", "IBM", "IBM", "approved"),
    ("INTC", "US", "Intel", "英特爾", "approved"),
    ("JD", "US", "Jd.com", "京東", "approved"),
    ("JNJ", "US", "Johnson & Johnson", "嬌生", "approved"),
    ("JPM", "US", "Jpmorgan Chase &", "摩根大通", "approved"),
    ("KO", "US", "Coca-cola", "可口可樂", "approved"),
    ("LI", "US", "Li Auto", "理想汽車", "approved"),
    ("LLY", "US", "Eli Lilly &", "禮來", "approved"),
    ("MA", "US", "Mastercard", "萬事達", "approved"),
    ("MCD", "US", "Mcdonald's", "麥當勞", "approved"),
    ("META", "US", "Meta Platforms", "Meta", "approved"),
    ("MRK", "US", "Merck &", "默克", "approved"),
    ("MS", "US", "Morgan Stanley", "摩根士丹利", "approved"),
    ("MSFT", "US", "Microsoft", "微軟", "approved"),
    ("NFLX", "US", "Netflix", "網飛", "approved"),
    ("NIO", "US", "Nio", "蔚來", "approved"),
    ("NKE", "US", "Nike", "耐吉", "approved"),
    ("NVDA", "US", "Nvidia", "輝達", "approved"),
    ("ORCL", "US", "Oracle", "甲骨文", "approved"),
    ("PDD", "US", "Pdd", "拼多多", "approved"),
    ("PEP", "US", "Pepsico", "百事", "approved"),
    ("PFE", "US", "Pfizer", "輝瑞", "approved"),
    ("PG", "US", "Procter & Gamble", "寶僑", "approved"),
    ("QCOM", "US", "Qualcomm", "高通", "approved"),
    ("SAP", "US", "Sap Se", "SAP", "approved"),
    ("SBUX", "US", "Starbucks", "星巴克", "approved"),
    ("SONY", "US", "Sony", "索尼", "approved"),
    ("T", "US", "AT&T", "AT&T", "approved"),
    ("TM", "US", "Toyota Motor", "豐田", "approved"),
    ("TMO", "US", "Thermo Fisher Scientific", "賽默飛世爾", "approved"),
    ("TSLA", "US", "Tesla", "特斯拉", "approved"),
    ("TSM", "US", "Taiwan Semiconductor Manufacturing", "台積電", "approved"),
    ("V", "US", "Visa", "威士", "approved"),
    ("VZ", "US", "Verizon Communications", "威訊", "approved"),
    ("WFC", "US", "Wells Fargo &", "富國銀行", "approved"),
    ("WMT", "US", "Walmart", "沃爾瑪", "approved"),
    ("XOM", "US", "Exxon Mobil", "艾克森美孚", "approved"),
    ("XPEV", "US", "Xpeng", "小鵬", "approved"),
    ("XYZZZ", "US", None, None, "pending"),
]


def seed_translations() -> None:
    init_engine()
    create_all_tables()
    imported = 0
    updated = 0
    for session in get_session():
        service = TranslationService(session)
        for ticker, market, name_en, name_zh_tw, status in TRANSLATIONS:
            try:
                _, is_new = service.create_or_update(
                    ticker=ticker,
                    market=market,
                    name_en=name_en,
                    name_zh_tw=name_zh_tw,
                    status=status,
                    updated_by="seed_script",
                    brand_color=BRAND_COLORS.get(ticker),
                )
                if is_new:
                    imported += 1
                else:
                    updated += 1
            except Exception as e:
                logger.error(f"Error seeding {market}:{ticker}: {e}")
        break
    logger.info(f"Seeding complete: {imported} imported, {updated} updated")


if __name__ == "__main__":
    seed_translations()
