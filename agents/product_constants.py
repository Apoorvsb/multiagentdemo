_CATEGORY_NORM = {
    "electronics": "Electronics",
    "computers&accessories": "Computers&Accessories",
    "computers & accessories": "Computers&Accessories",
    "computers and accessories": "Computers&Accessories",
    "computers": "Computers&Accessories",
    "home&kitchen": "Home&Kitchen",
    "home & kitchen": "Home&Kitchen",
    "home and kitchen": "Home&Kitchen",
    "kitchen": "Home&Kitchen",
    "home": "Home&Kitchen",
}

BRAND_MAP = {
    "hp": "HP",
    "dell": "Dell",
    "apple": "Apple",
    "samsung": "Samsung",
    "sony": "Sony",
    "lenovo": "Lenovo",
    "oneplus": "OnePlus",
    "boat": "boAt",
    "asus": "ASUS",
    "acer": "Acer",
    "mi": "Mi",
    "realme": "Realme",
    "redmi": "Redmi",
    "motorola": "Motorola",
    "nokia": "Nokia",
    "oppo": "OPPO",
    "vivo": "Vivo",
    "google": "Google",
    "lg": "LG",
    "panasonic": "Panasonic",
    "philips": "Philips",
    "bajaj": "Bajaj",
    "prestige": "Prestige",
    "daikin": "Daikin",
    "voltas": "Voltas",
    "whirlpool": "Whirlpool",
    "bosch": "Bosch",
    "kent": "Kent",
    "aquaguard": "Aquaguard",
    "havells": "Havells",
    "instant": "Instant",
    "tefal": "Tefal",
    "milton": "Milton",
    "pigeon": "Pigeon",
    "hawkins": "Hawkins",
    "cello": "Cello",
    "borosil": "Borosil",
    "butterfly": "Butterfly",
    "vinod": "Vinod",
    "ifb": "IFB",
    "tcl": "TCL",
    "hisense": "Hisense",
}

_GENERIC_WORDS = {
    "product", "products", "item", "items", "thing", "things",
    "anything", "something", "goods", "appliance", "appliances",
}

_CARRY_PRODUCT_TYPES = [
    "laptop", "phone", "smartphone", "tablet", "tv", "television",
    "camera", "watch", "smartwatch", "desktop", "computer",
    "earphone", "headphone", "earbuds", "earbud", "speaker",
    "neckband", "headset", "keyboard", "mouse", "monitor", "charger",
    "mixer grinder", "air conditioner", "washing machine", "water purifier",
    "microwave", "air fryer", "electric kettle", "rice cooker",
    "refrigerator", "pressure cooker", "water bottle",
]

# ── SQL ILIKE pattern expansions per product type ─────────────────────────────

_PHONE_SQL_PATTERNS = [
    "%galaxy%", "%iphone%", "%5g%", "%pixel%", "%nord%",
    "%redmi%", "%realme%", "%narzo%", "%moto%", "%oneplus%",
    "%xperia%", "%nothing phone%",
]

_KITCHEN_SQL_PATTERNS = [
    "%mixer grinder%", "%electric kettle%", "%air fryer%",
    "%pressure cooker%", "%microwave%", "%induction cooktop%",
    "%induction stove%", "%rice cooker%", "%blender%", "%juicer%",
    "%toaster%", "%coffee maker%", "%coffee machine%",
    "%sandwich maker%", "%water bottle%", "%flask%",
]

_HOME_APPLIANCE_SQL_PATTERNS = [
    "%refrigerator%", "%fridge%", "%washing machine%",
    "%air conditioner%", "%water purifier%", "%microwave%",
    "%geyser%", "%water heater%", "%television%", "%smart tv%",
]

_ENERGY_SQL_PATTERNS = [
    "%inverter%", "%5 star%", "%5-star%",
    "%energy efficient%", "%energy saver%", "%energy saving%",
]

_SMARTWATCH_SQL_PATTERNS = ["%watch%", "%smartwatch%"]
_TABLET_SQL_PATTERNS    = ["%ipad%", "%galaxy tab%"]
_EARBUDS_SQL_PATTERNS   = ["%earbuds%", "%airpods%", "%airdopes%"]
_TV_SQL_PATTERNS        = ["%smart tv%", "%television%", "% tv %", "% tv"]

# ── Keyword sets that map to the SQL patterns above ───────────────────────────

_PHONE_KEYWORDS         = {"phone", "smartphone", "mobile"}
_KITCHEN_KEYWORDS       = {
    "kitchen appliance", "kitchen appliances", "cooking appliance",
    "cooking appliances", "kitchen", "cooking", "kitchen items",
    "kitchen products", "kitchen tools", "kitchen gadget",
    "kitchen gadgets", "kitchen gift", "gift for kitchen",
}
_HOME_APPLIANCE_KEYWORDS = {"home appliance", "home appliances", "home essential", "home essentials"}
_ENERGY_KEYWORDS        = {
    "energy saving", "energy efficient", "power saving",
    "energy saving appliance", "energy saving appliances",
    "energy-saving", "eco-friendly", "eco friendly",
}
_SMARTWATCH_KEYWORDS    = {"smartwatch", "smartwatches", "watch", "watches", "smart watch"}
_TABLET_KEYWORDS        = {"tablet", "tablets", "ipad"}
_EARBUDS_KEYWORDS       = {"earbud", "earbuds", "airpods", "air pods"}
_TV_KEYWORDS            = {"tv", "television", "smart tv", "oled tv", "qled tv", "4k tv"}

_KEYWORD_TO_SQL_PATTERNS = [
    (_PHONE_KEYWORDS,          _PHONE_SQL_PATTERNS),
    (_KITCHEN_KEYWORDS,        _KITCHEN_SQL_PATTERNS),
    (_HOME_APPLIANCE_KEYWORDS, _HOME_APPLIANCE_SQL_PATTERNS),
    (_ENERGY_KEYWORDS,         _ENERGY_SQL_PATTERNS),
    (_SMARTWATCH_KEYWORDS,     _SMARTWATCH_SQL_PATTERNS),
    (_TABLET_KEYWORDS,         _TABLET_SQL_PATTERNS),
    (_EARBUDS_KEYWORDS,        _EARBUDS_SQL_PATTERNS),
    (_TV_KEYWORDS,             _TV_SQL_PATTERNS),
]

# ── Product type & accessory filtering ───────────────────────────────────────

_MAIN_PRODUCT_TYPES = [
    "laptop", "phone", "smartphone", "tablet", "tv", "television",
    "camera", "watch", "smartwatch", "desktop", "computer",
    "earphone", "headphone", "earbuds", "earbud", "speaker",
    "neckband", "headset", "mixer grinder", "air conditioner",
    "washing machine", "water purifier", "microwave oven", "air fryer",
    "induction cooktop", "electric kettle", "rice cooker", "refrigerator",
    "pressure cooker", "water bottle", "coffee maker", "blender",
    "juicer", "toaster", "kitchen appliance", "home appliance", "energy saving",
]

_ACCESSORY_KEYWORDS = [
    "mouse", "cable", "adapter", "charger", "stand", "bag", "case",
    "cover", "keyboard", "hub", "dongle", "wire", "cord", "sleeve",
    "memory", "mousepad", "mat", "cooling pad", "protector", "organizer",
    "pouch", "winder", "remote", "wall mount", "bracket", "antenna",
    "cleaning kit", "cleaning cloth", "microfiber", "screen cleaner",
    "cleaning spray", "dust blower", "compressed air", "lens cleaner", "wipe",
]

_PHONE_EXTRA_EXCLUSIONS  = [
    "earphone", "earphones", "headset", "handsfree",
    "neckband", "earbuds", "watch", "smartwatch", "tablet", "tab", "buds",
]

_LAPTOP_EXTRA_EXCLUSIONS = [
    "headphone", "earphone", "speaker", "webcam", "headset", "earbuds", "neckband",
]

_CHARGER_EXCLUSIONS = [
    "watch charger", "smartwatch charger", "smart watch charger",
    "cable protector", "cord protector", "charger protector",
    "charging stand", "charger included", "charger in box", "with charger",
]

_BROAD_INTENTS = {"kitchen appliance", "home appliance", "energy saving"}

_TYPE_SIGNATURES = [
    ("mixer",        "mixer grinder"),
    ("kettle",       "electric kettle"),
    ("fryer",        "air fryer"),
    ("cooker",       "pressure cooker"),
    ("microwave",    "microwave"),
    ("induction",    "induction cooktop"),
    ("rice",         "rice cooker"),
    ("coffee",       "coffee maker"),
    ("blender",      "blender"),
    ("juicer",       "juicer"),
    ("toaster",      "toaster"),
    ("sandwich",     "sandwich maker"),
    ("refrigerator", "refrigerator"),
    ("fridge",       "refrigerator"),
    ("washing",      "washing machine"),
    ("conditioner",  "air conditioner"),
    ("purifier",     "water purifier"),
    ("television",   "television"),
    ("inverter",     "inverter appliance"),
]
