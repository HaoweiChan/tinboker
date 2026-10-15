"""Curated US-listed theme baskets for the market-move theme lane.

Source holdings: issuer snapshots dated 2026-10-14, retrieved 2026-10-15.
Only NYSE/Nasdaq common equities/ADRs in Nasdaq Trader's symbol directories
are retained; cash, funds, OTC and foreign-exchange listings are excluded.
Broad sector baskets retain the first 80 eligible issuer holdings. Narrower
baskets select directly exposed companies from the cited issuer holdings.
Membership is equally weighted by the detector, not by ETF portfolio weights.

Validation on 2026-10-15 (completed before 15:52 UTC): all 1,567 final symbols
returned usable Yahoo spark quotes. The pre-pruning universe of 1,578 symbols
completed 79 uncached batches at concurrency 2 in 4.054s, with no failed batches.
NYSE/Nasdaq directory source: https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
Additional SPDR source files referenced by the narrow baskets:
https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xtl.xlsx
https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xar.xlsx
https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xbi.xlsx

To refresh: retrieve the cited issuer holdings, recheck US exchange listings,
prune thematic mismatches, and validate every symbol with Yahoo spark using
range=1d, interval=5m and batches of 20 (the yahoo_chart.quotes parameters).
Keep exposure IDs stable; run tests/unit/test_us_themes.py after any update.
"""

US_THEMES: list[dict] = [
    # IYT — https://www.ishares.com/us/products/239501/ishares-u-s-transportation-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_transportation",
        "name": "交通運輸",
        "members": [
            "UNP", "UBER", "CSX", "ODFL", "NSC", "DAL", "UPS", "FDX", "UAL",
            "EXPD", "XPO", "LUV", "JBHT", "CHRW", "FDXF", "KNX", "R", "SAIA",
            "AAL", "KEX", "MATX", "LYFT", "LSTR", "GXO", "RXO", "ALK", "SKYW",
            "ARCB", "JOBY", "WERN", "CAR", "ALGT", "HUBG", "SNDR", "JBLU", "GNK",
            "MRTN", "HTLD", "CVLG", "FWRD", "ULCC", "HTZ", "FIP",
        ],
    },
    # ITA — https://www.ishares.com/us/products/239502/ishares-u-s-aerospace-defense-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_aerospace_defense",
        "name": "航太軍工",
        "members": [
            "GE", "RTX", "BA", "LMT", "TDG", "NOC", "GD", "HWM", "HONA",
            "LHX", "AXON", "RKLB", "ATI", "WWD", "CRS", "CW", "FTAI", "TXT",
            "BWXT", "HEI", "HII", "KTOS", "HXL", "AVAV", "VSEC", "SARO", "MRCY",
            "AIR", "KRMN", "DRS", "ACHR", "ARXS", "DCO", "ATRO", "LOAR", "RDW",
            "VVX", "BETA", "LUNR", "FLY", "VOYG", "CDRE", "NPK", "RCAT", "SWBI",
            "RGR", "YSS", "SPCE",
        ],
    },
    # IYM — https://www.ishares.com/us/products/239503/ishares-u-s-basic-materials-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_basic_materials",
        "name": "基礎原物料",
        "members": [
            "LIN", "NEM", "FCX", "ECL", "APD", "NUE", "AU", "STLD", "IFF",
            "RS", "RGLD", "SCCO", "CRS", "CF", "IP", "LYB", "CDE", "MLI",
            "AVY", "ALB", "AA", "SOLS", "HL", "CTVA", "ESI", "EMN", "CLF",
            "MOS", "MP", "NEU", "CE", "AUGO", "ALM", "SMG", "WLK", "OLN",
        ],
    },
    # IAI — https://www.ishares.com/us/products/239504/ishares-u-s-broker-dealers-securities-exchanges-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_brokers_exchanges",
        "name": "券商與交易所",
        "members": [
            "GS", "MS", "SCHW", "CME", "ICE", "SPGI", "MCO", "HOOD", "NDAQ",
            "MSCI", "COIN", "IBKR", "RJF", "LPLA", "TW", "SF", "FDS", "EVR",
            "HLI", "JEF", "SNEX", "MKTX", "VIRT", "PIPR", "BGC", "MC", "MORN",
            "LAZ", "PJT", "MIAX", "DFIN", "PWP", "OPY", "BTGO",
        ],
    },
    # IYK — https://www.ishares.com/us/products/239505/ishares-u-s-consumer-staples-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_consumer_staples",
        "name": "民生消費",
        "members": [
            "PG", "KO", "PM", "PEP", "MO", "MCK", "CVS", "MDLZ", "CL",
            "COR", "MNST", "CAH", "VYLR", "KDP", "ADM", "SYY", "KR", "KVUE",
            "KMB", "CHD", "CASY", "HSY", "USFD", "KHC", "STZ", "GIS", "TSN",
            "BG", "PFGC", "SJM", "MKC", "COKE", "CLX", "DAR", "LW", "CAG",
            "INGR", "SFM", "TAP", "HRL", "PRMB", "CELH", "JBS", "ACI", "CPB",
            "FRPT", "POST", "PPC", "REYN", "SFD",
        ],
    },
    # IYC — https://www.ishares.com/us/products/239506/ishares-u-s-consumer-discretionary-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_consumer_discretionary",
        "name": "非必需消費",
        "members": [
            "AMZN", "TSLA", "WMT", "COST", "HD", "NFLX", "DIS", "MCD", "TJX",
            "UBER", "BKNG", "LOW", "SBUX", "SPOT", "MAR", "GM", "HLT", "ROST",
            "RCL", "ORLY", "TGT", "ABNB", "DAL", "AZO", "F", "EBAY", "GRMN",
            "CVNA", "NKE", "YUM", "CMG", "TTWO", "CCL", "DHI", "UAL", "RBLX",
            "EXPE", "WSM", "DG", "LYV", "ULTA", "EL", "QSR", "DRI", "TPR",
            "CPRT", "DLTR", "OMC", "PHM", "FWONK", "CPNG", "LUV", "GPC", "TSCO",
            "BBY", "BURL", "RBA", "SN", "LEN", "NVR", "VIK", "ARMK", "SGI",
            "RL", "HAS", "RIVN", "BJ", "FOXA", "BWA", "TOL", "FIVE", "DECK",
            "W", "GME", "FLUT", "NWSA", "TKO", "TXRH", "SCI", "LVS",
        ],
    },
    # IYE — https://www.ishares.com/us/products/239507/ishares-u-s-energy-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_energy",
        "name": "能源",
        "members": [
            "XOM", "CVX", "COP", "MPC", "VLO", "PSX", "WMB", "EOG", "SLB",
            "KMI", "TRGP", "LNG", "OKE", "DVN", "BKR", "OXY", "FANG", "EQT",
            "HAL", "FTI", "TPL", "EXE", "DINO", "PR", "OVV", "FSLR", "APA",
            "DTM", "NXT", "AR", "RRC", "VNOM", "CHRD", "AM", "NOV", "MTDR",
            "WFRD", "ENPH", "MWH", "XE",
        ],
    },
    # IYG — https://www.ishares.com/us/products/239509/ishares-u-s-financial-services-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_financial_services",
        "name": "金融服務",
        "members": [
            "JPM", "V", "MA", "BAC", "GS", "WFC", "MS", "C", "AXP",
            "SCHW", "BLK", "SPGI", "COF", "CME", "BNY", "USB", "ICE", "PNC",
            "HOOD", "BX", "MCO", "KKR", "TFC", "APO", "STT", "FITB", "AMP",
            "NDAQ", "MSCI", "COIN", "IBKR", "MTB", "HBAN", "NTRS", "RJF", "CFG",
            "ARES", "LPLA", "SYF", "RF", "TROW", "SOFI", "FCNCA", "KEY", "EWBC",
            "PNFP", "EQH", "IVZ", "TW", "SEIC", "FHN", "RKT", "SF", "FDS",
            "ALLY", "BPOP", "CG", "AMG", "SSB", "EVR", "WTFC", "CFR", "UMBF",
            "BEN", "CRBG", "FCFS", "VOYA", "ZION", "PB", "WAL", "CBSH", "HLI",
            "JEF", "OMF", "FNB", "OWL", "TPG", "VLY", "UBSI", "GBCI",
        ],
    },
    # IHF — https://www.ishares.com/us/products/239510/ishares-u-s-healthcare-providers-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_healthcare_providers",
        "name": "醫療服務",
        "members": [
            "UNH", "CVS", "ELV", "VEEV", "HCA", "HUM", "CI", "CNC", "DGX",
            "LH", "GH", "THC", "EHC", "MOH", "BTSG", "ENSG", "UHS", "HQY",
            "CHE", "HNGE", "DVA", "HIMS", "RDNT", "OPCH", "CON", "DOCS", "LFST",
            "HTFL", "WAY", "ACHC", "PRVA", "CRVL", "BKD", "BLLN", "NEO", "MD",
            "PACS", "PGNY", "ADUS", "CLOV", "ASTH", "WGS", "ALHC", "AVAH", "AMN",
            "SDGR", "PNTG", "USPH", "SGRY", "AGL", "CERT", "TDOC", "CSTL", "OMDA",
            "HSTM", "OPK", "PHR", "EVH", "FLGT", "CYH",
        ],
    },
    # ITB — https://www.ishares.com/us/products/239512/ishares-u-s-home-construction-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_homebuilders",
        "name": "住宅營建供應鏈",
        "members": [
            "DHI", "PHM", "NVR", "LEN", "SHW", "TOL", "LOW", "HD", "MAS",
            "LII", "IBP", "SKY", "CVCO", "MTH", "OC", "MHO", "SSD", "KBH",
            "MHK", "BLDR", "EXP", "FND", "FBIN", "TREX", "GRBK", "LPX", "UFPI",
            "GFF", "CCS", "HAYW", "LGIH", "BZH", "MBC", "LZB", "ROCK", "HOV",
            "NX", "DFH", "ARHS", "ETD", "BOBS", "JELD",
        ],
    },
    # IYJ — https://www.ishares.com/us/products/239514/ishares-u-s-industrials-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_industrials",
        "name": "工業",
        "members": [
            "CAT", "GE", "GEV", "RTX", "UNP", "ETN", "DE", "BA", "PH",
            "TT", "PWR", "LMT", "JCI", "EMR", "VRT", "CSX", "HWM", "GD",
            "MMM", "ITW", "SHW", "BE", "CMI", "NSC", "UPS", "CTAS", "URI",
            "HON", "NOC", "FDX", "KEYS", "TDG", "GWW", "AME", "FIX", "PCAR",
            "CRH", "HONA", "ROK", "WAB", "LHX", "CARR", "FERG", "RKLB", "EME",
            "ODFL", "MTD", "AXON", "SUNB", "VMC", "IR", "MLM", "TDY", "OTIS",
            "NVT", "ATI", "DOV", "EXPD", "HUBB", "VLTO", "XYL", "PPG", "VRSK",
            "SW", "XPO", "DOW", "PKG",
        ],
    },
    # IAK — https://www.ishares.com/us/products/239515/ishares-u-s-insurance-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_insurance",
        "name": "保險",
        "members": [
            "PGR", "CB", "TRV", "ALL", "MET", "AFL", "AIG", "PRU", "HIG",
            "ACGL", "CINF", "MKL", "PFG", "L", "WRB", "AIZ", "UNM", "GL",
            "AFG", "OSCR", "PRI", "ORI", "THG", "KNSL", "FNF", "FAF", "AXS",
            "ERIE", "RLI", "SIGI", "CNO", "WTM", "LNC", "PLMR", "LMND", "AGO",
            "BHF", "MCY", "GNW", "SKWD", "HCI", "HMN", "SLDE", "STC", "SAFT",
            "PRCH", "KMPR", "UFCS", "UVE", "CNA", "TRUP", "EIG", "HRTG", "HIPO",
            "ROOT", "FG", "BOW", "AMSF", "TIPT",
        ],
    },
    # IHI — https://www.ishares.com/us/products/239516/ishares-u-s-medical-devices-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_medical_devices",
        "name": "醫療器材",
        "members": [
            "ABT", "ISRG", "MDT", "RMD", "BDX", "IDXX", "SYK", "EW", "DXCM",
            "GEHC", "BSX", "STE", "ZBH", "BAX", "PEN", "GKOS", "PODD", "GMED",
            "TFX", "ITGR", "LIVN", "NVST", "IRTC", "ATRC", "TMDX", "AXGN", "INSP",
            "LMAT", "BFLY", "OMCL", "NVCR", "CNMD", "ATEC", "TNDM", "ENOV", "AORT",
            "PRCT", "QDEL", "PLSE", "SIBN", "IART", "KMTS", "VREX", "BBNX", "IRMD",
            "CBLL", "ANGO", "OFIX",
        ],
    },
    # IEO — https://www.ishares.com/us/products/239517/ishares-u-s-oil-gas-exploration-production-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_oil_gas_production",
        "name": "油氣開採與煉製",
        "members": [
            "COP", "MPC", "VLO", "PSX", "EOG", "DVN", "FANG", "EQT", "EXE",
            "TPL", "PR", "DINO", "OVV", "APA", "AR", "RRC", "SM", "PBF",
            "VNOM", "CHRD", "VG", "MTDR", "MGY", "MUR", "CNX", "DK", "PARR",
            "CRC", "CRGY", "CLMT", "NOG", "GPOR", "TALO", "WKC", "CVI", "KOS",
            "REX", "CRK", "GPRE", "DEC", "BKV", "EGY", "VTS", "SOC", "SD",
            "CLNE",
        ],
    },
    # IEZ — https://www.ishares.com/us/products/239518/ishares-u-s-oil-equipment-services-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_oil_services",
        "name": "油田服務",
        "members": [
            "BKR", "SLB", "FTI", "HAL", "NOV", "RIG", "VAL", "NE", "WFRD",
            "AROC", "KGS", "SEI", "PTEN", "WHD", "OII", "HP", "TDW", "LBRT",
            "SDRL", "WTTR", "XPRO", "INVX", "NESR", "NBR", "VTOL", "PUMP", "HOS",
            "AESI", "TTI", "FLOC", "RES", "CLB",
        ],
    },
    # IHE — https://www.ishares.com/us/products/239519/ishares-u-s-pharmaceuticals-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_pharmaceuticals",
        "name": "製藥",
        "members": [
            "LLY", "JNJ", "PFE", "ZTS", "VTRS", "MRK", "RPRX", "BMY", "JAZZ",
            "CORT", "ELAN", "AXSM", "LGND", "DFTX", "INDV", "MANE", "OGN", "AMRX",
            "EWTX", "AMLX", "TARS", "ELVN", "SUPN", "PBH", "PRGO", "LQDA", "XERS",
            "HRMY", "INVA", "TRVI", "MBX", "PCRX", "ANIP", "OMER", "OCUL", "NUVB",
            "RAPP", "MAZE", "HROW", "LBRX", "SEPN", "AMPH", "PAHC", "COLL", "ALMS",
            "CRMD", "WVE", "EOLS", "AVLN", "ARVN", "PHAT", "EYPT", "BIOA",
        ],
    },
    # IYR — https://www.ishares.com/us/products/239520/ishares-u-s-real-estate-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_real_estate",
        "name": "不動產",
        "members": [
            "WELL", "PLD", "AMT", "EQIX", "SPG", "DLR", "O", "PSA", "VMRK",
            "VTR", "CBRE", "CCI", "IRM", "EXR", "VICI", "SBAC", "ESS", "HST",
            "KIM", "WPC", "INVH", "SUI", "NLY", "OHI", "WY", "JLL", "MAA",
            "DOC", "LAMR", "CSGP", "REG", "ELS", "AHR", "GLPI", "EGP", "AGNC",
            "UDR", "CPT", "AMH", "BXP", "FRT", "REXR", "BRX", "ADC", "CUBE",
            "NNN", "FR", "STAG", "ARE", "HR", "VNO", "SBRA", "RITM", "Z",
            "CUZ", "STWD", "LINE", "ZG",
        ],
    },
    # IAT — https://www.ishares.com/us/products/239521/ishares-u-s-regional-banks-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_regional_banks",
        "name": "區域銀行",
        "members": [
            "USB", "PNC", "TFC", "FITB", "HBAN", "MTB", "CFG", "RF", "FCNCA",
            "KEY", "EWBC", "PNFP", "FHN", "BPOP", "SSB", "WTFC", "CFR", "UMBF",
            "ZION", "PB", "WAL", "CBSH", "FNB", "VLY", "UBSI", "GBCI", "HOMB",
            "OZK", "FFIN", "BOKF",
        ],
    },
    # IYW — https://www.ishares.com/us/products/239522/ishares-u-s-technology-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_technology",
        "name": "科技",
        "members": [
            "NVDA", "AAPL", "MSFT", "META", "AMD", "AVGO", "MU", "GOOGL", "INTC",
            "PLTR", "GOOG", "LRCX", "AMAT", "PANW", "CRWD", "TXN", "ORCL", "KLAC",
            "MRVL", "IBM", "SNDK", "APH", "ADI", "CRM", "QCOM", "DELL", "NOW",
            "WDC", "SNOW", "GLW", "FTNT", "NET", "ADBE", "DDOG", "CDNS", "SNPS",
            "HPE", "INTU", "DASH", "APP", "MPWR", "TER", "COHR", "MSTR", "ALAB",
            "P", "ADSK", "NTAP", "TWLO", "FLEX", "MCHP", "OKTA", "WDAY", "ROP",
            "JBL", "TEAM", "CRDO", "ON", "MDB", "HPQ", "CTSH", "FFIV", "ZM",
            "Q", "VRSN", "ENTG", "CRWV", "ZS", "SMCI", "RDDT", "SNX", "PTC",
            "MTSI", "CDW", "NTNX", "DT", "RBRK", "SWKS", "LSCC", "U",
        ],
    },
    # IYZ — https://www.ishares.com/us/products/239523/ishares-u-s-telecommunications-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_telecommunications",
        "name": "電信通訊",
        "members": [
            "CSCO", "ANET", "VZ", "T", "SPCX", "MSI", "CIEN", "TMUS", "LITE",
            "CMCSA", "UI", "ROKU", "GSAT", "VIAV", "ECHO", "IRDM", "TIGO", "CHTR",
            "AAOI", "ASTS", "LBTYA", "LBTYK",
        ],
    },
    # IDU — https://www.ishares.com/us/products/239524/ishares-u-s-utilities-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_utilities",
        "name": "公用事業",
        "members": [
            "NEE", "SO", "DUK", "CEG", "WM", "AEP", "D", "SRE", "VST",
            "ETR", "XEL", "RSG", "EXC", "ED", "PEG", "WEC", "AEE", "PCG",
            "ATO", "DTE", "PPL", "AWK", "CNP", "ES", "FE", "EIX", "CMS",
            "NRG", "NI", "EVRG", "LNT", "CLH", "TLN", "GFL", "PNW", "WTRG",
            "AES", "OGE", "UGI", "IDA", "NFG", "OKLO", "BEPC", "MDU", "CWEN",
            "FRVO",
        ],
    },
    # REM — https://www.ishares.com/us/products/239543/ishares-mortgage-real-estate-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_mortgage_reits",
        "name": "房貸 REITs",
        "members": [
            "NLY", "AGNC", "STWD", "EFC", "DX", "RITM", "ARR", "BXMT", "ORC",
            "LADR", "CIM", "MFA", "ADAM", "PMT", "IVR", "FBRT", "BRSP", "TRTX",
            "RWT", "ABR", "KREF", "REFI", "ACRE", "MITT", "RC", "SEVN", "AOMR",
            "NREF", "CMTG",
        ],
    },
    # REZ — https://www.ishares.com/us/products/239545/ishares-residential-and-multisector-real-estate-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_residential_reits",
        "name": "住宅與照護 REITs",
        "members": [
            "WELL", "PSA", "VMRK", "VTR", "EXR", "ESS", "INVH", "SUI", "OHI",
            "MAA", "DOC", "ELS", "UDR", "AMH", "AHR", "CPT", "CUBE", "CTRE",
            "ARE", "HR", "SBRA", "IRT", "NHI", "LTC", "JAN", "SMA", "DHC",
            "MPT", "UMH", "CSR", "UHT", "NXRT", "NHP", "XRN", "CHCT", "BRT",
        ],
    },
    # POWR — https://www.ishares.com/us/products/239653/ishares-u-s-power-infrastructure-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_power_infrastructure",
        "name": "電力基礎建設",
        "members": [
            "PWR", "GEV", "ETN", "NEE", "EQT", "SO", "CEG", "DUK", "NVT",
            "HUBB", "EXE", "FSLR", "AEP", "D", "VST", "ETR", "NXT", "XEL",
            "GNRC", "EXC", "AR", "ED", "PEG", "RRC", "WEC", "VMI", "PCG",
            "AEE", "DTE", "PPL", "CNP", "ES", "FE", "NRG", "ENS", "EIX",
            "CMS", "EVRG", "POWL", "CNX", "LNT", "HCC", "TLN", "MYRG", "CNR",
            "ENPH", "ITRI", "PNW", "AES", "OGE", "IDA", "SEDG", "AMR", "TXNM",
            "ORA", "POR", "NWE", "CRK", "CWEN", "AVA", "SXC", "MGEE", "IIIN",
            "RUN", "UTL",
        ],
    },
    # IBB — https://www.ishares.com/us/products/239699/ishares-biotechnology-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_biotechnology",
        "name": "生技",
        "members": [
            "GILD", "AMGN", "VRTX", "MRNA", "REGN", "NTRA", "ARGX", "ILMN", "RVMD",
            "BIIB", "ALNY", "ONC", "INCY", "UTHR", "INSM", "GMAB", "ROIV", "EXEL",
            "CRL", "ASND", "MEDP", "NBIX", "HALO", "BBIO", "TECH", "BMRN", "MDGL",
            "PCVX", "RGEN", "TWST", "KRYS", "BNTX", "TXG", "CYTK", "PTGX", "KYMR",
            "ARWR", "TEM", "AXSM", "IONS", "ABVX", "ALKS", "PRAX", "SYRE", "BRKR",
            "GRAL", "RYTM", "IOVA", "TVTX", "PTCT", "KOD", "ORKA", "CRSP", "DFTX",
            "COGT", "MIRM", "ADPT", "SRRK", "IBRX", "CAI", "CGON", "ERAS", "VCYT",
            "ACAD", "LEGN", "XENE", "TNGX", "ABCL", "IDYA", "CDNA", "EWTX", "TARS",
            "RLAY", "ARQT", "AMLX", "DNLI", "ELVN", "IMVT", "NRIX", "DYN",
        ],
    },
    # SOXX — https://www.ishares.com/us/products/239705/ishares-semiconductor-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_semiconductors",
        "name": "半導體",
        "members": [
            "AMD", "INTC", "NVDA", "MU", "AVGO", "MRVL", "ADI", "TXN", "KLAC",
            "QCOM", "AMAT", "LRCX", "MPWR", "TSM", "TER", "NXPI", "SKHY", "ALAB",
            "MCHP", "CRDO", "ON", "ASML", "ENTG", "TSEM", "MTSI", "ASX", "CBRS",
            "UMC", "ARM", "STM",
        ],
    },
    # ICLN — https://www.ishares.com/us/products/239738/ishares-global-clean-energy-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_clean_energy",
        "name": "潔淨能源",
        "members": [
            "BE", "FSLR", "NXT", "ENPH", "PLUG", "SEDG", "CWEN", "SHLS", "GPRE",
            "TE", "ARRY", "CSIQ", "REX", "RNW", "JKS",
        ],
    },
    # IDGT — https://www.ishares.com/us/products/239770/ishares-u-s-digital-infrastructure-and-real-estate-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_digital_infrastructure",
        "name": "數位基礎建設",
        "members": [
            "AMT", "EQIX", "FSLY", "SBAC", "CCI", "NTAP", "CIEN", "EXTR", "ANET",
            "SMCI", "DLR", "CSCO", "UNIT", "NOK", "QCOM", "CRWV", "CALX", "CRDO",
            "VISN", "ATEN", "ERIC", "ADTN", "CLFD", "MSI", "UI",
        ],
    },
    # IGV — https://www.ishares.com/us/products/239771/ishares-expanded-tech-software-sector-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_software",
        "name": "軟體",
        "members": [
            "PLTR", "PANW", "MSFT", "CRWD", "ORCL", "NOW", "CRM", "FTNT", "ADBE",
            "SNPS", "CDNS", "DDOG", "INTU", "APP", "ADSK", "WDAY", "ROP", "TTWO",
            "TEAM", "ZM", "ZS", "PTC", "NTNX", "DT", "RBRK", "FICO", "IOT",
            "U", "DOCU", "TRMB", "GWRE", "TYL", "MANH", "GEN", "HUBS", "ESTC",
            "IDCC", "GTLB", "S", "ZETA", "DSGX", "AUR", "PCOR", "SNAP", "QLYS",
            "CVLT", "OTEX", "BSY", "RNG", "VRNS", "PATH", "BOX", "ACIW", "DBX",
            "APPF", "BB", "QBTS", "TTAN", "YOU", "TENB", "CCC", "QTWO", "WK",
            "BILL", "DLB", "LIF", "SPSC", "FRSH", "PEGA", "ALRM", "TDC",
        ],
    },
    # IFRA — https://www.ishares.com/us/products/294315/ishares-u-s-infrastructure-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_infrastructure",
        "name": "基礎建設",
        "members": [
            "PWR", "UNP", "CAT", "NEE", "CSX", "SO", "CEG", "NSC", "DUK",
            "WMB", "URI", "NUE", "FIX", "CRH", "AEP", "KMI", "TRP", "OKE",
            "D", "VST", "SRE", "ETR", "XEL", "EME", "EXC", "STLD", "VMC",
            "ED", "MLM", "PEG", "ATI", "WEC", "PCG", "AEE", "RS", "FTS",
            "ATO", "DTE", "FE", "PPL", "CNP", "AWK", "CRS", "ES", "AMRZ",
            "J", "NRG", "EIX", "APG", "CMS", "STRL", "NI", "JHX", "EVRG",
            "MLI", "MTZ", "CSL", "LNT", "IESC", "EMA", "SOLS", "DTM", "PNW",
            "VMI", "WMS", "OC", "TTEK", "WTRG", "OSK", "ACM", "STN", "CLF",
            "OGE", "EMN", "CMC", "SSD", "AWI", "FLR", "ECG", "TEX",
        ],
    },
    # IDRV — https://www.ishares.com/us/products/307332/ishares-self-driving-ev-and-tech-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_autonomous_driving",
        "name": "自駕車",
        "members": [
            "TSLA", "RIVN", "ALV", "ALB", "AUR", "LEA", "GNTX", "QS", "BLBD",
            "VC", "OUST", "AMPX", "ADNT", "LCID", "SLDP", "PSNY", "SERV", "CPS",
            "ABAT", "STRT", "EVGO",
        ],
    },
    # IHAK — https://www.ishares.com/us/products/307352/ishares-cybersecurity-and-tech-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_cybersecurity",
        "name": "資安",
        "members": [
            "NTSK", "OKTA", "QLYS", "ZS", "CRWD", "S", "VRNS", "TENB", "PANW",
            "FTNT", "SAIC", "CACI", "ALRM", "CHKP", "BAH", "CALX", "YOU", "ATEN",
            "AKAM", "SAIL", "RDWR", "RPD", "OSPN", "ALLT", "GRRR",
        ],
    },
    # IDNA — https://www.ishares.com/us/products/308878/ishares-genomics-immunology-and-healthcare-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_genomics",
        "name": "基因醫療",
        "members": [
            "MRNA", "TWST", "IOVA", "RVMD", "REGN", "MRK", "IBRX", "CAI", "EXEL",
            "VRTX", "INCY", "BNTX", "ABCL", "IDYA", "NVAX", "RCUS", "CRSP", "VIR",
            "NUVB", "PSNL", "JANX", "RIGL", "KURA", "VSTM", "CRVS", "ALVO", "PACB",
            "DNA", "XNCR", "NTLA", "CTMX", "DSGN", "OCGN", "PRME",
        ],
    },
    # IBLC — https://www.ishares.com/us/products/326614/ishares-blockchain-and-tech-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_blockchain",
        "name": "區塊鏈",
        "members": [
            "COIN", "CRCL", "IREN", "HUT", "APLD", "RIOT", "CORZ", "WULF", "CIFR",
            "GLXY", "MARA", "IOND", "CLSK", "HOOD", "KEEL", "SECZ", "BTDR", "ETOR",
            "PYPL", "BLSH", "HIVE", "BTGO", "DGXX", "ZSQR", "CAN", "ABTC", "BKKT",
            "GEMI", "SLNH", "CNTN",
        ],
    },
    # EFRA — https://www.ishares.com/us/products/330188/ishares-environmental-infrastructure-and-industrials-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_environmental_infrastructure",
        "name": "環保工程",
        "members": [
            "VLTO", "WAB", "SW", "XYL", "AWK", "CLH", "WTRG", "WTS", "WMS",
            "TTEK", "PNR", "CNM", "MSA", "BMI", "FELE", "MWA", "AWR", "CWT",
            "NGVT", "HTO",
        ],
    },
    # ICOP — https://www.ishares.com/us/products/332280/ishares-copper-and-metals-mining-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_copper_mining",
        "name": "銅與多金屬礦業",
        "members": [
            "FCX", "SCCO", "NEM", "RIO", "VALE", "AUGO", "NEXA",
        ],
    },
    # ILIT — https://www.ishares.com/us/products/332281/ishares-lithium-miners-and-producers-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_lithium_mining",
        "name": "鋰礦",
        "members": [
            "SQM", "ALB", "LAC", "LAR", "SGML", "CRML", "ABAT",
        ],
    },
    # IBAT — https://www.ishares.com/us/products/336296/ishares-energy-storage-materials-etf/latest-holdings.csv
    {
        "exposure_id": "us_theme_battery_materials",
        "name": "儲能與電池材料",
        "members": [
            "BE", "APD", "LIN", "ETN", "ENS", "ENPH", "ENTG", "DOW", "QS",
            "SEDG", "PLUG", "FCEL", "AMPX", "EOSE", "FLNC", "BLDP", "ASPN",
        ],
    },
    # XRT — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xrt.xlsx
    {
        "exposure_id": "us_theme_retail",
        "name": "零售",
        "members": [
            "GME", "OLLI", "KSS", "BJ", "VSXY", "ETSY", "TJX", "EBAY", "GO",
            "KR", "RVLV", "ACI", "BURL", "WMT", "ULTA", "URBN", "ASO", "COST",
            "BKE", "WMK", "BBWI", "IMKTA", "GAP", "CART", "M", "SIG", "DG",
            "AEO", "MUSA", "CASY", "DLTR", "DKS", "ROST", "WRBY", "BBY", "AZO",
            "ORLY", "AMZN", "SBH", "CHWY", "HZO", "VVV", "EYE", "PSMT", "TGT",
            "ANF", "CPNG", "TSCO", "AAP", "WINA", "REAL", "PAG", "FIVE", "SFM",
            "PTRN", "SVV", "UPBD", "KMX", "GPI", "CVNA", "BOOT", "SAH", "LAD",
            "ABG", "AN", "CAL", "GRPN", "CTRN", "MNRO", "BBW", "SFIX", "ARKO",
            "CWH",
        ],
    },
    # KBE — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-kbe.xlsx
    {
        "exposure_id": "us_theme_banks",
        "name": "銀行",
        "members": [
            "CBC", "NBTB", "OFG", "UBSI", "TRMK", "SYBT", "EWBC", "TBBK", "CVBF",
            "HWC", "CHCO", "ONB", "FCNCA", "BANF", "CATY", "RNST", "SFNC", "FBP",
            "EBC", "BUSE", "FFBC", "NWBI", "FRME", "HOMB", "NIC", "FHB", "IBOC",
            "WSFS", "PFS", "FCF", "AUB", "LKFN", "UCB", "BPOP", "CBU", "JPM",
            "FFIN", "CLBK", "TOWN", "BANR", "SSB", "COLB", "CUBI", "ASB", "CBSH",
            "WTFC", "PNFP", "CFR", "PB", "SBCF", "FIBK", "GBCI", "FULT", "FNB",
            "ABCB", "AX", "TFIN", "EFSC", "FBNC", "INDB", "BANC", "OZK", "FHN",
            "FBK", "FITB", "BOKF", "UMBF", "HTH", "KEY", "WSBC", "TFC", "HBAN",
            "MTB",
        ],
    },
    # XME — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xme.xlsx
    {
        "exposure_id": "us_theme_metals_mining",
        "name": "金屬礦業",
        "members": [
            "CLF", "RS", "STLD", "NUE", "CMC", "FCX", "MTRN", "NEM", "RGLD",
            "AA", "MP", "HL", "CDE", "HCC", "CNR", "BTU", "USAR", "KALU",
            "LEU", "CENX", "AMR", "RYZ", "HYMC", "SXC", "MUX", "WS", "CMP",
            "MTUS", "ALOY", "METC", "UAMY", "ABAT",
        ],
    },
    # XHB — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xhb.xlsx
    {
        "exposure_id": "us_theme_building_products",
        "name": "建材與居家修繕",
        "members": [
            "SN", "WSM", "TT", "JCI", "W", "ALLE", "MAS", "SSD", "CSL",
            "TOL", "DHI", "HD", "WMS", "LOW", "CVCO", "CARR", "LII", "NVR",
            "PHM", "SKY", "LEN", "SGI", "MTH", "OC", "IBP", "MOD", "MHO",
            "KBH", "BLDR", "CCS", "GRBK", "LGIH", "BZH", "HOV", "DFH",
        ],
    },
    # XHE — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xhe.xlsx
    {
        "exposure_id": "us_theme_healthcare_equipment",
        "name": "醫療設備",
        "members": [
            "ISRG", "HAE", "ATEC", "QDEL", "ATRC", "IRMD", "RMD", "MDLN", "OMCL",
            "BDX", "GEHC", "UFPT", "LMAT", "IDXX", "MDT", "GMED", "INSP", "SYK",
            "BFLY", "NEOG", "BAX", "STE", "ICUI", "ITGR", "EW", "PEN", "MMSI",
            "DXCM", "LNTH", "ENOV", "ABT", "PODD", "ZBH", "SOLV", "BBNX", "LIVN",
            "CNMD", "BSX", "ALGN", "GKOS", "ASST", "TFX", "STAA", "IRTC", "NVCR",
            "TMDX", "COO", "NVST", "AORT", "PRCT", "PLSE", "TNDM", "IART", "XRAY",
            "SIBN", "AXGN", "BVS", "KMTS", "AVR", "CBLL", "MMED", "CERS", "TCMD",
            "DCTH", "CLPT", "VREX", "OFIX", "ANGO", "SENS", "KIDS", "NPCE",
        ],
    },
    # XHS — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xhs.xlsx
    {
        "exposure_id": "us_theme_healthcare_services",
        "name": "醫療照護",
        "members": [
            "OPCH", "HNGE", "CRVL", "ACHC", "HCA", "CLOV", "AMN", "CON", "MCK",
            "CNC", "USPH", "ELV", "MOH", "HUM", "PRVA", "UHS", "SGRY", "COR",
            "EHC", "CI", "CAH", "PGNY", "ENSG", "BTSG", "PACS", "THC", "UNH",
            "GH", "MD", "NUTX", "HIMS", "ASTH", "LFST", "DGX", "CHE", "LH",
            "DVA", "BLLN", "ADUS", "RDNT", "HSIC", "HQY", "NEO", "CVS", "GRDN",
            "AGL", "SNDA", "AVAH", "OMDA", "AHCO", "BKD", "PNTG", "WGS", "CSTL",
            "STLN", "ALHC", "FLGT", "SRTA", "CYH", "OPK",
        ],
    },
    # XSW — https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xsw.xlsx
    {
        "exposure_id": "us_theme_software_services",
        "name": "軟體服務",
        "members": [
            "PTC", "NTSK", "ZS", "RBRK", "TTAN", "EFOR", "DT", "AMPL", "PD",
            "ACN", "SNPS", "VIA", "CRWD", "DDOG", "BRZE", "ASAN", "PLTR", "S",
            "RPD", "CVLT", "FTNT", "DXC", "DOCU", "GWRE", "CDNS", "IT", "TEAM",
            "FRSH", "GTLB", "TENB", "FFIV", "CCC", "AI", "APPN", "PANW", "ADSK",
            "QLYS", "BLKB", "BOX", "SAIL", "BSY", "OSPN", "ATEN", "SPT", "SPSC",
            "FIVN", "YEXT", "MSFT", "AVPT", "RNG", "MSTR", "CTSH", "TDC", "NOW",
            "RBLX", "MANH", "ESTC", "ZETA", "CXM", "IOT", "CRNC", "KVYO", "NTNX",
            "PCOR", "ALRM", "VERX", "DBX", "TRMB", "YOU", "INTA", "TYL", "VRNS",
            "RDVT", "WDAY", "AGYS", "WEAV", "EPAM", "WK", "RAMP", "BL",
        ],
    },
    # URA — https://www.globalxetfs.com/funds/ura/
    {
        "exposure_id": "us_theme_uranium_nuclear",
        "name": "鈾礦與核能",
        "members": [
            "OKLO", "LEU", "XE", "SMR", "NNE", "UROY", "IMSR", "LTBR", "NUCL",
            "NKLR",
        ],
    },
    # LIT — https://www.globalxetfs.com/funds/lit/
    {
        "exposure_id": "us_theme_lithium_batteries",
        "name": "鋰電池",
        "members": [
            "RIO", "TSLA", "ALB", "SQM", "ENS", "LCID", "SGML",
        ],
    },
    # BOTZ — https://www.globalxetfs.com/funds/botz/
    {
        "exposure_id": "us_theme_robotics",
        "name": "機器人",
        "members": [
            "ISRG", "NVDA", "CGNX", "AUR", "GOOGL", "TSLA", "DE", "SYM", "ROK",
            "OUST", "BIDU", "HSAI", "PONY", "ALNT", "OMCL", "WRD", "PRCT", "AVEX",
            "XPEV", "NOVT", "KDK", "SERV", "RR", "EH",
        ],
    },
    # CLOU — https://www.globalxetfs.com/funds/clou/
    {
        "exposure_id": "us_theme_cloud",
        "name": "雲端運算",
        "members": [
            "SNOW", "DDOG", "PAYC", "TWLO", "ZS", "NOW", "NET", "WDAY", "QLYS",
            "SHOP", "CRM", "DBX", "DOCN", "BOX", "HUBS", "PCOR", "ZM", "AKAM",
            "WIX", "DLR", "FSLY", "WK", "FRSH", "SPSC", "MSFT", "FIVN", "AMZN",
            "GOOGL", "AI", "VNET", "YEXT", "PUBM", "ORCL", "BABA", "IBM", "KC",
        ],
    },
    # FINX — https://www.globalxetfs.com/funds/finx/
    {
        "exposure_id": "us_theme_fintech",
        "name": "金融科技",
        "members": [
            "HOOD", "PYPL", "XYZ", "COIN", "FISV", "GPN", "INTU", "AFRM", "SSNC",
            "SOFI", "FIS", "CRCL", "TOST", "GWRE", "JKHY", "PAYP", "HQY", "RIOT",
            "ACIW", "KLAR", "VIRT", "BLSH", "BILL", "CORZ", "SEZL", "CIFR", "GLXY",
            "LMND", "MARA", "FOUR", "STNE", "BULL", "PAYO", "DLO", "NCNO", "UPST",
            "FLYW", "PAY", "PAGS", "PURR", "HAPN", "KEEL", "PGY", "ETOR", "VERX",
            "LU", "MITK", "BTGO", "PRTH", "CSHR", "CD", "TREE", "RPAY", "PSFE",
            "BLND", "BKKT", "GEMI", "ABTC",
        ],
    },
    # SOCL — https://www.globalxetfs.com/funds/socl/
    {
        "exposure_id": "us_theme_social_media",
        "name": "社群媒體",
        "members": [
            "META", "RDDT", "PINS", "NTES", "GOOGL", "SPOT", "MTCH", "BIDU", "SNAP",
            "TME", "BILI", "PPLI", "JOYY", "DJT", "YELP", "CXM", "RUM", "NXDR",
            "SPT", "WB", "GRND", "MOMO", "GRPN", "BMBL", "FVRR", "ANGI", "HUYA",
            "YALA",
        ],
    },
    # HERO — https://www.globalxetfs.com/funds/hero/
    {
        "exposure_id": "us_theme_video_games",
        "name": "遊戲",
        "members": [
            "U", "NTES", "RBLX", "TTWO", "BILI", "CRSR", "GRVY", "TBCH", "IMMR",
            "HUYA", "PLTK",
        ],
    },
    # AIQ — https://www.globalxetfs.com/funds/aiq/
    {
        "exposure_id": "us_theme_artificial_intelligence",
        "name": "人工智慧",
        "members": [
            "PLTR", "MSFT", "SPCX", "META", "TSLA", "GOOGL", "ORCL", "AMZN", "AAPL",
            "NVDA", "AMD", "TSM", "NFLX", "CSCO", "INTC", "MU", "AVGO", "SAP",
            "BABA", "MRVL", "IBM", "SHOP", "CRM", "QCOM", "STX", "NOW", "UBER",
            "ACN", "SNOW", "ADBE", "SNPS", "CDNS", "DDOG", "HPE", "APP", "NXPI",
            "ZS", "NOK", "DT", "OKTA", "WIX", "WDAY", "ZBRA", "TWLO", "AI",
            "SNAP", "DXC", "TRI", "CCC", "PEGA", "PATH", "GLOB", "G", "SMCI",
            "GEHC", "TDC", "CLS", "ERIC", "EFX", "AMBA", "CRWV", "QUBT", "BIDU",
            "SOUN", "PONY", "HUT",
        ],
    },
    # DRIV — https://www.globalxetfs.com/funds/driv/
    {
        "exposure_id": "us_theme_electric_vehicles",
        "name": "電動車",
        "members": [
            "MSFT", "NVDA", "INTC", "GOOGL", "TSLA", "QCOM", "GM", "BE", "WAB",
            "SWKS", "COHR", "NBIS", "NXPI", "F", "ITT", "ATI", "ON", "DCH",
            "SITM", "SQM", "HY", "AMBA", "ENS", "BIDU", "ALB", "CBT", "THRM",
            "VC", "BB", "MBLY", "NIO", "XPEV", "AMPX", "ALGM", "PLUG", "QS",
            "AEVA", "LCID", "INDI",
        ],
    },
    # SIL — https://www.globalxetfs.com/funds/sil/
    {
        "exposure_id": "us_theme_silver_mining",
        "name": "白銀礦業",
        "members": [
            "WPM", "PAAS", "CDE", "HL", "SSRM", "BVN", "EXK", "MUX", "HYMC",
        ],
    },
    # SOXX; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_ai_chips",
        "name": "AI 晶片",
        "members": [
            "NVDA", "AMD", "AVGO", "MRVL", "ARM", "INTC", "QCOM",
        ],
    },
    # SOXX, IYW; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_advanced_packaging",
        "name": "AI 先進封裝",
        "members": [
            "AMKR", "ASX", "TSM", "INTC", "AMAT", "KLAC", "LRCX",
        ],
    },
    # IYW, IYZ, XTL; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_optical",
        "name": "光通訊",
        "members": [
            "COHR", "LITE", "CIEN", "AAOI", "FN", "ADTN", "VIAV",
        ],
    },
    # IYJ; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_cooling",
        "name": "散熱",
        "members": [
            "VRT", "TT", "CARR", "JCI", "MOD", "AAON",
        ],
    },
    # IYW, IYJ, IDGT; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_ai_servers",
        "name": "AI伺服器",
        "members": [
            "DELL", "HPE", "SMCI", "VRT", "ANET", "NTAP",
        ],
    },
    # IYW, IYC; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_magnificent_seven",
        "name": "七巨頭",
        "members": [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
        ],
    },
    # ITA, IYZ, IYJ, XTL, XAR; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_space",
        "name": "太空與低軌衛星",
        "members": [
            "RKLB", "ASTS", "IRDM", "VSAT", "LUNR", "RDW", "PL",
        ],
    },
    # IHE, IBB, 239511, XBI; selected directly exposed holdings (issuer links above).
    {
        "exposure_id": "us_theme_glp1",
        "name": "減肥藥 GLP-1",
        "members": [
            "LLY", "VKTX", "ALT", "GPCR", "AMGN", "PFE",
        ],
    },
    # CLOU, SOCL, HERO; selected China ADR holdings (issuer links above).
    {
        "exposure_id": "us_theme_china_adrs",
        "name": "中概股 ADR",
        "members": [
            "BABA", "BIDU", "NTES", "TME", "BILI", "WB", "JOYY", "HUYA",
        ],
    },
]
