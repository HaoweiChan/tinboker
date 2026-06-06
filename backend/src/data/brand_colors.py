# Official brand hex colors sourced from brand guidelines / corporate identity.
# Applied at startup to fill any NULL brand_color rows in stock_translations.

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
    # --- Extended US stocks ---
    # Semiconductors / Hardware
    "MU": "#003087",
    "ARM": "#0091BD",
    "LRCX": "#003C87",
    "AMAT": "#003B5C",
    "TXN": "#C8102E",
    "KLAC": "#0072BC",
    "ADI": "#007BBD",
    "ANET": "#0060A9",
    "MRVL": "#003DA5",
    "NXPI": "#FF6900",
    "CDNS": "#002060",
    "SNPS": "#5B2D8E",
    "APH": "#003DA5",
    "GLW": "#003087",
    # AI / Cloud / Software
    "PLTR": "#101113",
    "CRWD": "#F04E23",
    "NOW": "#81B5A1",
    "PANW": "#FA582D",
    "SNOW": "#29B5E8",
    "DDOG": "#632CA6",
    "NET": "#F38020",
    "INTU": "#365EBF",
    "FTNT": "#EE3124",
    "ACN": "#A100FF",
    "ADP": "#CC2529",
    "WDAY": "#005CB9",
    "ZS": "#0079B8",
    "SHOP": "#96BF48",
    "APP": "#000000",
    "OKTA": "#007DC1",
    "TTD": "#005CA2",
    # Communication / Media
    "ZM": "#2D8CFF",
    "SPOT": "#1DB954",
    "TMUS": "#E20074",
    # Finance / Banking
    "AXP": "#007CC3",
    "BLK": "#000000",
    "BX": "#1C1C1C",
    "SCHW": "#0074AF",
    "SPGI": "#C8102E",
    "CME": "#0047BB",
    "ICE": "#003087",
    "COF": "#D22128",
    "PNC": "#F26522",
    "USB": "#006DB6",
    "BNY": "#5A0F7E",
    "PGR": "#0063A5",
    "CB": "#00538B",
    "KKR": "#1C1C1C",
    # Fintech / Crypto
    "PYPL": "#003087",
    "SQ": "#3D3D3D",
    "COIN": "#0052FF",
    "HOOD": "#00C805",
    "AFRM": "#4A4AF4",
    "SOFI": "#9ABEAA",
    # Healthcare / Biotech / Pharma
    "UNH": "#005EB8",
    "ISRG": "#005EA2",
    "DHR": "#003DA5",
    "SYK": "#003087",
    "AMGN": "#003DA5",
    "GILD": "#C8102E",
    "VRTX": "#F15A22",
    "REGN": "#003DA5",
    "MRNA": "#0E5A7E",
    "BSX": "#007FC5",
    "MDT": "#00A3E0",
    "ELV": "#003DA5",
    "CVS": "#CC0000",
    "HCA": "#003DA5",
    "BMY": "#003087",
    "ZTS": "#007DC3",
    # Energy
    "CVX": "#007AC1",
    "COP": "#C8102E",
    "NEE": "#003DA5",
    "CEG": "#0032A0",
    "FCX": "#003DA5",
    # Industrials / Aerospace / Defense
    "GE": "#003DA5",
    "CAT": "#FFCD11",
    "RTX": "#003DA5",
    "HON": "#003DA5",
    "BA": "#003087",
    "LMT": "#003087",
    "GD": "#003DA5",
    "NOC": "#003DA5",
    "DE": "#367C2B",
    "ETN": "#FABB05",
    "UNP": "#FFCD00",
    "UPS": "#351C15",
    "FDX": "#FF6200",
    "VRT": "#003DA5",
    # Consumer Discretionary / Retail / Travel
    "TJX": "#CC0000",
    "LOW": "#003DA5",
    "TGT": "#CC0000",
    "CMG": "#441500",
    "LULU": "#000000",
    "MNST": "#000000",
    "MO": "#003DA5",
    "PM": "#003DA5",
    "BKNG": "#003580",
    "MAR": "#A8292C",
    "UBER": "#000000",
    "ABNB": "#FF5A5F",
    "DASH": "#FF3008",
    "LYFT": "#FF00BF",
    "MELI": "#FFE600",
    "ROKU": "#6C1AF0",
    # EV / Auto
    "GM": "#0009AA",
    "F": "#003499",
    "RIVN": "#00A0DC",
    "LCID": "#B5B5B5",
    # Social Media / Gaming
    "PINS": "#E60023",
    "SNAP": "#FFFC00",
    "RBLX": "#E2231A",
    "AI": "#FF0000",
    # Real Estate / Data Infrastructure
    "EQIX": "#003DA5",
    "AMT": "#003DA5",
    "PLD": "#003DA5",
    # Other
    "DELL": "#007DB8",
    "IBKR": "#C8102E",
    "RKLB": "#1B75BC",
    "PWR": "#003DA5",
    # --- TW stocks (extended) ---
    # IC Design
    "2344": "#0070C0",  # Winbond Electronics
    "2337": "#003087",  # Macronix International
    "2379": "#0056A2",  # Realtek Semiconductor
    "3034": "#003087",  # Novatek Microelectronics
    "2327": "#E2231A",  # Yageo Corporation
    "3443": "#003F87",  # Global Unichip
    "3661": "#1B3F8B",  # Alchip Technologies
    "5274": "#005BAC",  # ASPEED Technology
    "8299": "#E2231A",  # Phison Electronics
    "3529": "#003DA5",  # eMemory Technology
    "6415": "#006DB6",  # Silergy Corp
    "5269": "#0071C5",  # ASMedia Technology
    "6526": "#003087",  # Airoha Technology
    "3227": "#003F8F",  # PixArt Imaging
    "4966": "#005BAC",  # Parade Technologies
    "6643": "#003DA5",  # M31 Technology
    "4919": "#003DA5",  # Nuvoton Technology
    "3035": "#004B87",  # Faraday Technology
    "6223": "#004B8D",  # MPI Corporation
    # Foundry / Wafer
    "5347": "#004B87",  # Vanguard International Semiconductor
    "6488": "#003DA5",  # GlobalWafers
    "6770": "#0055A5",  # Powerchip Semiconductor
    "5483": "#003087",  # Sino-American Silicon Products
    "3105": "#0071C5",  # WIN Semiconductors
    "3532": "#003087",  # Formosa Sumco Technology
    # Packaging / Test
    "6239": "#003F87",  # Powertech Technology
    "2449": "#003DA5",  # King Yuan Electronics
    "8150": "#003087",  # ChipMOS Technologies
    "6147": "#004B87",  # Chipbond Technology
    "6510": "#003DA5",  # Chunghwa Precision Test Tech
    "2441": "#0055A5",  # Greatek Electronics
    "6257": "#0056A2",  # Sigurd Microelectronics
    "6789": "#0071C5",  # VisEra Technologies
    # PCB / Substrate / Passive
    "3037": "#005BAC",  # Unimicron Technology
    "3189": "#003087",  # Kinsus Interconnect Technology
    "3044": "#0055A5",  # Tripod Technology
    "2313": "#004B87",  # Compeq Manufacturing
    "8046": "#005BAC",  # Nan Ya Printed Circuit Board
    "4958": "#005BAC",  # Zhen Ding Technology
    "2368": "#E2231A",  # Gold Circuit Electronics
    "2383": "#003DA5",  # Elite Material
    "6213": "#003DA5",  # ITEQ Corporation
    "2492": "#C8102E",  # Walsin Technology
    "3026": "#0055A5",  # Holy Stone Enterprise
    # Equipment / Test / Materials
    "2360": "#E2231A",  # Chroma ATE
    "3030": "#003087",  # Test Research
    "3680": "#003DA5",  # Gudeng Precision Industrial
    "5434": "#005BAC",  # Topco Scientific
    "6139": "#004B87",  # L&K Engineering
    "6196": "#003087",  # Marketech International
    # Thermal / Power / Connectors / Cable
    "3017": "#E2231A",  # Asia Vital Components
    "3653": "#003DA5",  # Jentech Precision Industrial
    "3533": "#004B87",  # Lotes
    "3324": "#E2231A",  # Auras Technology
    "3665": "#003DA5",  # BizLink Holding
    "2421": "#003DA5",  # Sunonwealth Electric Machine Industry
    "2059": "#003087",  # King Slide Works
    # EMS / ODM / Notebook / Server
    "2324": "#003087",  # Compal Electronics
    "2356": "#003F87",  # Inventec Corporation
    "4938": "#C8102E",  # Pegatron Corporation
    "3231": "#005BAC",  # Wistron Corporation
    "2354": "#003DA5",  # Foxconn Technology
    "6669": "#003F87",  # Wiwynn Corporation
    "3706": "#003087",  # MiTAC Holdings
    "3702": "#E2231A",  # WPG Holdings
    "2347": "#003087",  # Synnex Technology International
    "3036": "#005BAC",  # WT Microelectronics
    # Consumer Electronics / IT
    "2376": "#E2231A",  # Giga-Byte Technology
    "2377": "#C8102E",  # Micro-Star International
    "2353": "#83B81A",  # Acer Incorporated
    "2301": "#E2231A",  # Lite-On Technology
    "2385": "#003DA5",  # Chicony Electronics
    "2352": "#0055A5",  # Qisda Corporation
    "3260": "#E2231A",  # ADATA Technology
    "6121": "#003DA5",  # Simplo Technology
    "5289": "#003087",  # Innodisk Corporation
    "7805": "#003DA5",  # QNAP Systems
    # Memory
    "2408": "#003087",  # Nanya Technology
    # Display
    "3481": "#006DB6",  # Innolux Corporation
    "2409": "#005BAC",  # AUO Corporation
    "8069": "#000000",  # E Ink Holdings
    "6116": "#005BAC",  # Hannstar Display
    # Financials
    "2885": "#E8A000",  # Yuanta Financial Holding
    "2887": "#C8102E",  # Taishin Financial Holding
    "2884": "#007B5E",  # E.SUN Financial Holding
    "2890": "#003DA5",  # SinoPac Financial Holdings
    "2880": "#003087",  # Hua Nan Financial Holdings
    "2892": "#005BAC",  # First Financial Holding
    "2883": "#003DA5",  # KGI Financial Holding
    "5880": "#005BAC",  # Taiwan Cooperative Financial Holding
    "2801": "#004B87",  # Chang Hwa Commercial Bank
    "2888": "#E2231A",  # Shin Kong Financial Holding
    "5876": "#C8102E",  # Shanghai Commercial & Savings Bank
    "5871": "#E2231A",  # Chailease Holding
    "2855": "#E2231A",  # President Securities
    "2834": "#003087",  # Taiwan Business Bank
    # Telecom
    "4904": "#E2231A",  # Far EasTone Telecommunications
    "3045": "#005BAC",  # Taiwan Mobile
    # Retail / Consumer
    "5903": "#00A650",  # Taiwan FamilyMart
    "8454": "#E2231A",  # momo.com
    "5904": "#E2231A",  # POYA International
    "1216": "#E2231A",  # Uni-President Enterprises
    "9940": "#C8102E",  # Sinyi Realty
    "9904": "#003DA5",  # Pou Chen Corporation
    "8464": "#C8102E",  # Nien Made Enterprise
    # Steel / Chemicals / Materials
    "2002": "#003087",  # China Steel Corporation
    "1101": "#003087",  # Taiwan Cement Corporation
    "1102": "#004B87",  # Asia Cement Corporation
    "1326": "#003087",  # Formosa Chemicals & Fibre
    "6505": "#E2231A",  # Formosa Petrochemical
    "2027": "#003087",  # Ta Chen Stainless Pipe
    "1717": "#003DA5",  # Eternal Materials
    "1605": "#E2231A",  # Walsin Lihwa Corporation
    "1802": "#003087",  # Taiwan Glass
    # Transportation / Auto
    "2603": "#007B5E",  # Evergreen Marine
    "2609": "#003DA5",  # Yang Ming Marine Transport
    "2615": "#E2231A",  # Wan Hai Lines
    "2618": "#007B5E",  # EVA Airways
    "2610": "#C8102E",  # China Airlines
    "2633": "#E2231A",  # Taiwan High Speed Rail
    "2207": "#003DA5",  # Hotai Motor
    "2201": "#003087",  # Yulon Motor
    # Industrial / Machinery / Others
    "2049": "#003DA5",  # Hiwin Technologies
    "1590": "#E2231A",  # Airtac International Group
    "1504": "#003087",  # TECO Electric & Machinery
    "1503": "#003087",  # Shihlin Electric & Engineering
    "1519": "#003087",  # Fortune Electric
    "2105": "#E2231A",  # Cheng Shin Rubber
    "1476": "#003DA5",  # Eclat Textile
    "1402": "#003087",  # Far Eastern New Century
    "9921": "#005BAC",  # Giant Manufacturing
    "3042": "#003DA5",  # TXC Corporation
    "5388": "#003DA5",  # Sercomm Corporation
    "6446": "#C8102E",  # PharmaEssentia Corporation
    "8996": "#003087",  # Kaori Heat Treatment
    "6285": "#003087",  # WNC Corporation
    "3023": "#003DA5",  # SINBON Electronics
    "1560": "#003087",  # Kinik Company
    "2838": "#003DA5",  # Union Bank of Taiwan
    "2812": "#003087",  # Taichung Commercial Bank
}
