"""Reference seed data: real NSE/BSE instrument metadata (public facts only).

No prices, no signals — symbols/names/sectors are static reference rows so
the scanner and instrument pages work before any market-data provider runs.
"""

SECTORS = [
    "Information Technology",
    "Banking & Financial Services",
    "Energy & Power",
    "Oil & Gas",
    "FMCG",
    "Automobile",
    "Pharmaceuticals",
    "Metals & Mining",
    "Telecommunications",
    "Infrastructure & Cement",
    "Consumer Durables",
    "Chemicals & Fertilizers",
    "Healthcare Services",
]

# (symbol, exchange, name, type, sector or None)
INSTRUMENTS: list[tuple[str, str, str, str, str | None]] = [
    # --- Indices ---
    ("NIFTY 50", "NSE", "Nifty 50", "INDEX", None),
    ("BANKNIFTY", "NSE", "Nifty Bank", "INDEX", None),
    ("SENSEX", "BSE", "S&P BSE Sensex", "INDEX", None),
    ("FINNIFTY", "NSE", "Nifty Financial Services", "INDEX", None),
    ("MIDCPNIFTY", "NSE", "Nifty Midcap Select", "INDEX", None),
    ("NIFTY NEXT 50", "NSE", "Nifty Next 50", "INDEX", None),

    # --- Banking & Financial Services ---
    ("HDFCBANK", "NSE", "HDFC Bank Limited", "STOCK", "Banking & Financial Services"),
    ("ICICIBANK", "NSE", "ICICI Bank Limited", "STOCK", "Banking & Financial Services"),
    ("SBIN", "NSE", "State Bank of India", "STOCK", "Banking & Financial Services"),
    ("KOTAKBANK", "NSE", "Kotak Mahindra Bank Limited", "STOCK", "Banking & Financial Services"),
    ("AXISBANK", "NSE", "Axis Bank Limited", "STOCK", "Banking & Financial Services"),
    ("BAJFINANCE", "NSE", "Bajaj Finance Limited", "STOCK", "Banking & Financial Services"),
    ("JIOFIN", "NSE", "Jio Financial Services Limited", "STOCK", "Banking & Financial Services"),

    # --- Information Technology ---
    ("TCS", "NSE", "Tata Consultancy Services Limited", "STOCK", "Information Technology"),
    ("INFY", "NSE", "Infosys Limited", "STOCK", "Information Technology"),
    ("HCLTECH", "NSE", "HCL Technologies Limited", "STOCK", "Information Technology"),
    ("WIPRO", "NSE", "Wipro Limited", "STOCK", "Information Technology"),
    ("TECHM", "NSE", "Tech Mahindra Limited", "STOCK", "Information Technology"),
    ("LTIM", "NSE", "LTIMindtree Limited", "STOCK", "Information Technology"),

    # --- Energy & Power / Oil & Gas ---
    ("RELIANCE", "NSE", "Reliance Industries Limited", "STOCK", "Oil & Gas"),
    ("ONGC", "NSE", "Oil & Natural Gas Corporation Limited", "STOCK", "Oil & Gas"),
    ("NTPC", "NSE", "NTPC Limited", "STOCK", "Energy & Power"),
    ("POWERGRID", "NSE", "Power Grid Corporation of India Limited", "STOCK", "Energy & Power"),
    ("COALINDIA", "NSE", "Coal India Limited", "STOCK", "Energy & Power"),
    ("ADANIGREEN", "NSE", "Adani Green Energy Limited", "STOCK", "Energy & Power"),

    # --- FMCG ---
    ("HINDUNILVR", "NSE", "Hindustan Unilever Limited", "STOCK", "FMCG"),
    ("ITC", "NSE", "ITC Limited", "STOCK", "FMCG"),
    ("NESTLEIND", "NSE", "Nestle India Limited", "STOCK", "FMCG"),
    ("BRITANNIA", "NSE", "Britannia Industries Limited", "STOCK", "FMCG"),

    # --- Automobile ---
    ("MARUTI", "NSE", "Maruti Suzuki India Limited", "STOCK", "Automobile"),
    ("TATAMOTORS", "NSE", "Tata Motors Limited", "STOCK", "Automobile"),
    ("M&M", "NSE", "Mahindra & Mahindra Limited", "STOCK", "Automobile"),
    ("BAJAJ-AUTO", "NSE", "Bajaj Auto Limited", "STOCK", "Automobile"),
    ("EICHERMOT", "NSE", "Eicher Motors Limited", "STOCK", "Automobile"),

    # --- Pharmaceuticals / Healthcare ---
    ("SUNPHARMA", "NSE", "Sun Pharmaceutical Industries Limited", "STOCK", "Pharmaceuticals"),
    ("CIPLA", "NSE", "Cipla Limited", "STOCK", "Pharmaceuticals"),
    ("DRREDDY", "NSE", "Dr. Reddys Laboratories Limited", "STOCK", "Pharmaceuticals"),
    ("DIVISLAB", "NSE", "Divis Laboratories Limited", "STOCK", "Pharmaceuticals"),
    ("APOLLOHOSP", "NSE", "Apollo Hospitals Enterprise Limited", "STOCK", "Healthcare Services"),

    # --- Metals & Mining ---
    ("TATASTEEL", "NSE", "Tata Steel Limited", "STOCK", "Metals & Mining"),
    ("JSWSTEEL", "NSE", "JSW Steel Limited", "STOCK", "Metals & Mining"),
    ("HINDALCO", "NSE", "Hindalco Industries Limited", "STOCK", "Metals & Mining"),

    # --- Telecommunications ---
    ("BHARTIARTL", "NSE", "Bharti Airtel Limited", "STOCK", "Telecommunications"),
    ("IDEA", "NSE", "Vodafone Idea Limited", "STOCK", "Telecommunications"),

    # --- Infrastructure & Cement ---
    ("LT", "NSE", "Larsen & Toubro Limited", "STOCK", "Infrastructure & Cement"),
    ("ULTRACEMCO", "NSE", "UltraTech Cement Limited", "STOCK", "Infrastructure & Cement"),
    ("GRASIM", "NSE", "Grasim Industries Limited", "STOCK", "Infrastructure & Cement"),
    ("ADANIENT", "NSE", "Adani Enterprises Limited", "STOCK", "Infrastructure & Cement"),

    # --- Consumer Durables / Chemicals ---
    ("ASIANPAINT", "NSE", "Asian Paints Limited", "STOCK", "Consumer Durables"),
    ("TITAN", "NSE", "Titan Company Limited", "STOCK", "Consumer Durables"),
]
