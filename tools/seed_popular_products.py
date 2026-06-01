"""
Seed script — adds the most-searched products for Electronics, Computers &
Accessories, and Home & Kitchen categories directly into the products and
reviews tables.

Run: python tools/seed_popular_products.py
"""

import sys
import os
import uuid
import psycopg2
import psycopg2.extras

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


# ─────────────────────────────────────────────────────────────
# PRODUCT CATALOGUE
# Each entry: (product_id, name, category, brand, price,
#              original_price, discount_pct, rating, rating_count,
#              description)
# ─────────────────────────────────────────────────────────────

PRODUCTS = [

    # ── LAPTOPS ────────────────────────────────────────────────
    ("lap-001", "Dell Inspiron 15 Intel Core i5 12th Gen 8GB RAM 512GB SSD Laptop",
     "Computers&Accessories", "Dell", 52990, 59990, "12%", 4.4, "3,241",
     "15.6-inch FHD display, Windows 11 Home, backlit keyboard, 1-year warranty. Ideal for students and professionals."),

    ("lap-002", "Lenovo IdeaPad Slim 3 AMD Ryzen 5 7520U 8GB RAM 512GB SSD Laptop",
     "Computers&Accessories", "Lenovo", 45990, 52990, "13%", 4.5, "5,128",
     "15.6-inch FHD IPS display, Windows 11, fast-charge, slim 19.9 mm chassis. Best-seller in budget segment."),

    ("lap-003", "ASUS VivoBook 15 Intel Core i3 12th Gen 8GB RAM 256GB SSD Laptop",
     "Computers&Accessories", "ASUS", 34990, 39990, "13%", 4.3, "2,874",
     "15.6-inch FHD display, finger-print sensor, Wi-Fi 6, 1-year warranty. Perfect entry-level laptop."),

    ("lap-004", "HP Pavilion 14 Intel Core i5 13th Gen 16GB RAM 512GB SSD Laptop",
     "Computers&Accessories", "HP", 63490, 72990, "13%", 4.5, "1,987",
     "14-inch IPS FHD, backlit keyboard, B&O audio, fast-charge. Great productivity laptop."),

    ("lap-005", "Apple MacBook Air M2 Chip 8GB RAM 256GB SSD 13-inch Laptop",
     "Computers&Accessories", "Apple", 99900, 114900, "13%", 4.8, "8,432",
     "18-hour battery life, Liquid Retina display, fanless silent design, MagSafe charging. Premium ultrabook."),

    ("lap-006", "Acer Nitro 5 AMD Ryzen 5 7535HS RTX 2050 8GB RAM 512GB SSD Gaming Laptop",
     "Computers&Accessories", "Acer", 62990, 74990, "16%", 4.4, "3,567",
     "15.6-inch FHD 144Hz display, dual-fan cooling, HDMI 2.1, Wi-Fi 6. Excellent budget gaming laptop."),

    ("lap-007", "ASUS ROG Strix G15 AMD Ryzen 9 16GB RAM 1TB SSD RTX 4060 Gaming Laptop",
     "Computers&Accessories", "ASUS", 119990, 139990, "14%", 4.7, "2,109",
     "15.6-inch QHD 165Hz display, RGB keyboard, MUX Switch, advanced cooling. Top-tier gaming performance."),

    ("lap-008", "Lenovo ThinkPad E14 Intel Core i5 13th Gen 16GB RAM 512GB SSD Business Laptop",
     "Computers&Accessories", "Lenovo", 68990, 79990, "14%", 4.6, "1,543",
     "14-inch IPS FHD, spill-resistant keyboard, Rapid Charge, military-grade durability. Business powerhouse."),

    ("lap-009", "Mi Notebook 14 Intel Core i5 10th Gen 8GB RAM 256GB SSD Thin & Light Laptop",
     "Computers&Accessories", "Mi", 41990, 49990, "16%", 4.2, "4,201",
     "14-inch FHD IPS anti-glare display, fingerprint sensor, backlit keyboard. Great value for money."),

    ("lap-010", "HP Victus 15 AMD Ryzen 5 7535HS RTX 3050 8GB RAM 512GB SSD Gaming Laptop",
     "Computers&Accessories", "HP", 67990, 79990, "15%", 4.4, "2,876",
     "15.6-inch FHD 144Hz IPS, micro-edge display, OMEN Gaming Hub. Best mid-range gaming laptop."),

    # ── AIR CONDITIONERS ──────────────────────────────────────
    ("ac-001", "Daikin 1.5 Ton 5 Star Wi-Fi Inverter Split AC with PM 0.1 Filter",
     "Electronics", "Daikin", 46490, 52990, "12%", 4.6, "4,320",
     "Auto-cleanser, Coanda airflow, Powerful mode, R-32 refrigerant. Energy-efficient with 5-star rating."),

    ("ac-002", "LG 1.5 Ton 5 Star DUAL Inverter Split AC with 4 in 1 Convertible Cooling",
     "Electronics", "LG", 43990, 51990, "15%", 4.5, "6,102",
     "HD Filter, Ocean Black Protection, Anti Virus Protection. Auto-restart and 10-year compressor warranty."),

    ("ac-003", "Voltas 1.5 Ton 3 Star Inverter Split AC",
     "Electronics", "Voltas", 33990, 39990, "15%", 4.3, "8,754",
     "Tropical Inverter compressor, auto restart, sleep mode, LED display. Most popular budget AC in India."),

    ("ac-004", "Samsung 1.5 Ton 5 Star Wi-Fi Inverter Split AC with Wind-Free Cooling",
     "Electronics", "Samsung", 47990, 55990, "14%", 4.5, "3,218",
     "WindFree Cooling, AI Auto mode, easy filter plus, Tri-Care filter. Smart home compatible."),

    ("ac-005", "Blue Star 1 Ton 5 Star Inverter Split AC",
     "Electronics", "Blue Star", 38490, 44990, "14%", 4.4, "2,987",
     "Self-cleaning coil, anti-bacterial filter, auto restart, turbo cool. Efficient 1-ton AC for small rooms."),

    ("ac-006", "Voltas 1.5 Ton 5 Star Inverter Split AC with Adjustable Inverter",
     "Electronics", "Voltas", 41990, 48990, "14%", 4.5, "5,431",
     "Adjustable inverter 5-in-1 convertible, active dehumidifier, multi-stage filtration. Best-value 5-star AC."),

    ("ac-007", "LG 2 Ton 5 Star Wi-Fi Inverter Split AC with Convertible 6-in-1 Cooling",
     "Electronics", "LG", 56990, 64990, "12%", 4.6, "1,876",
     "LG ThinQ app control, 6-in-1 convertible, Ocean Black Fin. Powerful AC for large rooms."),

    ("ac-008", "Carrier 1.5 Ton 3 Star Split AC with PM 2.5 Filter",
     "Electronics", "Carrier", 31990, 37990, "16%", 4.2, "3,109",
     "Auto clean, turbo cool, energy saver mode. Good entry-level AC from a trusted brand."),

    ("ac-009", "Panasonic 1.5 Ton 5 Star Wi-Fi Inverter Split AC with 7-in-1 Convertible",
     "Electronics", "Panasonic", 44990, 52990, "15%", 4.5, "2,654",
     "7-in-1 convertible, nanoe-X air purifying technology, Miraie remote app, Econavi. Premium features."),

    ("ac-010", "Hitachi 1.5 Ton 3 Star Inverter Split AC with Auto Changeable Filter",
     "Electronics", "Hitachi", 35490, 41990, "15%", 4.3, "1,987",
     "Self-cleaning filter, frost wash technology, sleep mode, 24-hour timer. Reliable mid-range AC."),

    # ── SMART TVs ──────────────────────────────────────────────
    ("tv-001", "Samsung 43-inch Crystal 4K UHD Smart TV with AirSlim Design",
     "Electronics", "Samsung", 32990, 42900, "23%", 4.5, "12,432",
     "Crystal Processor 4K, Motion Xcelerator, PurColor, Smart Hub, Alexa Built-in. India's No.1 TV brand."),

    ("tv-002", "LG 43-inch 4K UHD Smart LED TV with WebOS 23",
     "Electronics", "LG", 34990, 44990, "22%", 4.5, "9,876",
     "4K Active HDR, α5 AI Processor 4K, ThinQ AI, Filmmaker Mode, HDMI 2.1. Premium LG experience."),

    ("tv-003", "Sony Bravia 43-inch 4K UHD Google TV with Triluminos Pro",
     "Electronics", "Sony", 44990, 59990, "25%", 4.7, "7,321",
     "Bravia Core, Google TV, Motionflow XR, X-Reality Pro, Acoustic Multi-Audio. Best picture quality TV."),

    ("tv-004", "MI 55-inch 4K Ultra HD Smart Android TV with Vivid Picture Engine",
     "Electronics", "MI", 31999, 45999, "30%", 4.3, "21,543",
     "A+Grade Panel, Dolby Vision, Dolby Audio, Android TV, Chromecast. Best budget 55-inch TV."),

    ("tv-005", "TCL 55-inch QLED 4K Google TV with Hands-Free Voice Control",
     "Electronics", "TCL", 39990, 54990, "27%", 4.4, "8,765",
     "QLED display, Onkyo Audio, 60W output, Game Master Pro, AiPQ processor. Feature-rich at great price."),

    ("tv-006", "Hisense 50-inch 4K ULED QLED Smart Google TV",
     "Electronics", "Hisense", 35990, 48990, "27%", 4.3, "5,432",
     "QLED, Quantum Dot Color, 60Hz, Dolby Vision IQ, Filmmaker Mode. Premium picture tech at budget price."),

    # ── SMARTPHONES ───────────────────────────────────────────
    ("ph-001", "Samsung Galaxy S23 FE 5G 8GB RAM 256GB Storage Dual SIM",
     "Electronics", "Samsung", 39999, 49999, "20%", 4.4, "9,876",
     "6.4-inch Dynamic AMOLED 2X, 50MP camera, 4500mAh, IP68, Snapdragon 8 Gen 1. Flagship features, fan price."),

    ("ph-002", "OnePlus 12R 5G 8GB RAM 128GB Storage",
     "Electronics", "OnePlus", 39999, 44999, "11%", 4.5, "7,654",
     "6.78-inch 120Hz AMOLED, Snapdragon 8 Gen 2, 50MP triple camera, 100W SUPERVOOC, 5500mAh."),

    ("ph-003", "Redmi Note 13 5G 8GB RAM 256GB Storage",
     "Electronics", "Redmi", 19999, 24999, "20%", 4.4, "18,543",
     "6.67-inch FHD+ AMOLED 120Hz, 108MP main camera, Snapdragon 685, 5000mAh, IP54. Best mid-range phone."),

    ("ph-004", "Realme Narzo 60 Pro 5G 8GB RAM 128GB Storage",
     "Electronics", "Realme", 17999, 22999, "22%", 4.3, "11,234",
     "6.7-inch AMOLED curved display, 100MP OIS camera, Dimensity 7050, 67W fast charge."),

    ("ph-005", "Apple iPhone 15 128GB",
     "Electronics", "Apple", 79900, 89900, "11%", 4.8, "15,432",
     "6.1-inch Super Retina XDR, Dynamic Island, A16 Bionic, 48MP main camera, USB-C, crash detection."),

    ("ph-006", "Motorola Edge 40 Neo 5G 8GB RAM 256GB Storage",
     "Electronics", "Motorola", 19999, 25999, "23%", 4.3, "6,432",
     "6.55-inch pOLED 144Hz, IP68, 50MP camera, 5000mAh, Moto Secure. Clean Android experience."),

    # ── REFRIGERATORS ─────────────────────────────────────────
    ("rf-001", "LG 242L 3 Star Smart Inverter Double Door Refrigerator",
     "Electronics", "LG", 26990, 32990, "18%", 4.5, "8,765",
     "Smart Diagnosis, Moist Balance Crisper, DoorCooling+, 10-year compressor warranty. Energy-efficient."),

    ("rf-002", "Samsung 253L 3 Star Digital Inverter Double Door Refrigerator",
     "Electronics", "Samsung", 27490, 33990, "19%", 4.4, "7,654",
     "All-Around Cooling, Power Freeze, SpaceMax Technology, Stabilizer Free Operation. Smart inverter compressor."),

    ("rf-003", "Whirlpool 265L 3 Star Frost-Free Double Door Refrigerator",
     "Electronics", "Whirlpool", 26490, 31990, "17%", 4.3, "6,543",
     "6th Sense technology, IntelliFresh, Microblock, ZeroStat anti-bacterial gasket. Trusted brand."),

    # ── WASHING MACHINES ──────────────────────────────────────
    ("wm-001", "LG 7kg 5 Star Inverter Fully Automatic Front Load Washing Machine",
     "Electronics", "LG", 34990, 42990, "19%", 4.6, "9,876",
     "AI Direct Drive, TurboWash, Steam+, SmartDiagnosis, 6 Motion DD. Best front-load washing machine."),

    ("wm-002", "Samsung 7kg 5 Star Inverter Fully Automatic Top Load Washing Machine",
     "Electronics", "Samsung", 19990, 25990, "23%", 4.4, "11,234",
     "Digital Inverter Motor, Active Wash+, Child Lock, Magic Filter. Energy-efficient top loader."),

    ("wm-003", "Bosch 7kg 5 Star Fully Automatic Front Load Washing Machine",
     "Electronics", "Bosch", 38490, 46990, "18%", 4.7, "5,432",
     "EcoSilence Motor, Anti-Vibration, ActiveWater Plus, AllergyPlus. German engineering, whisper-quiet."),

    # ── KITCHEN APPLIANCES ────────────────────────────────────
    ("kit-001", "Philips HL7756/00 750W Mixer Grinder with 4 Jars",
     "Home&Kitchen", "Philips", 3295, 4495, "27%", 4.4, "14,321",
     "750W motor, 4 stainless steel jars, turbo boost, overload protection, 2-year warranty. Best mixer grinder."),

    ("kit-002", "Prestige Iris 550W Mixer Grinder with 3 Stainless Steel Jars",
     "Home&Kitchen", "Prestige", 1799, 2499, "28%", 4.3, "22,543",
     "550W motor, 3 stainless steel jars, anti-rust blades, 1-year warranty. Best budget mixer grinder."),

    ("kit-003", "Bajaj Rex 500W Mixer Grinder with 3 Jars",
     "Home&Kitchen", "Bajaj", 1449, 1999, "28%", 4.2, "18,765",
     "500W motor, stainless steel jar and blades, overload protection, 2-year warranty. Trusted value brand."),

    ("kit-004", "LG 28L NeoChef Convection Microwave Oven",
     "Home&Kitchen", "LG", 17490, 21990, "20%", 4.5, "7,654",
     "Convection + Grill + Microwave, Smart Inverter, Even Heating, Indian Menu Option, EasyClean. Best microwave."),

    ("kit-005", "Samsung 28L Convection Microwave Oven with SlimFry",
     "Home&Kitchen", "Samsung", 16490, 20990, "21%", 4.4, "6,543",
     "Triple Distribution System, SlimFry, Slim Fry, 15 Auto Cook menus. Feature-packed convection microwave."),

    ("kit-006", "IFB 25L Convection Microwave Oven with Multi-Stage Cooking",
     "Home&Kitchen", "IFB", 11490, 14990, "23%", 4.3, "9,876",
     "Multi-stage cooking, Deodorizer, Steam Clean, 101 Autocook menus. Best mid-range microwave."),

    ("kit-007", "Philips HD9252/90 Air Fryer with Rapid Air Technology",
     "Home&Kitchen", "Philips", 7995, 11995, "33%", 4.5, "18,432",
     "1400W, 4.1L capacity, Rapid Air technology, touch panel, 7 preset programs. No.1 air fryer brand."),

    ("kit-008", "Instant Vortex 4-in-1 Air Fryer 5.7L with EvenCrisp Technology",
     "Home&Kitchen", "Instant", 8495, 10995, "23%", 4.6, "11,234",
     "Air Fry, Roast, Bake, Reheat, 5.7L large capacity, app connectivity, 100+ recipes. Premium air fryer."),

    ("kit-009", "Tefal Easy Fry Classic+ 4.2L Air Fryer with XL Pan",
     "Home&Kitchen", "Tefal", 6995, 9495, "26%", 4.4, "8,765",
     "4.2L capacity, 8 preset programs, 80% less oil, dishwasher-safe pan. Healthy frying made easy."),

    ("kit-010", "Prestige PKOSS 1.8L Electric Kettle 1500W",
     "Home&Kitchen", "Prestige", 999, 1499, "33%", 4.3, "31,234",
     "1500W, 1.8L stainless steel, auto shut-off, dry boil protection, 360° swivel base. Best budget kettle."),

    ("kit-011", "Philips HD9306/06 Electric Kettle 1.7L 2400W",
     "Home&Kitchen", "Philips", 1495, 2195, "32%", 4.5, "15,432",
     "2400W rapid boil, 1.7L, anti-scale filter, concealed heating element, auto shut-off. Fast and safe."),

    ("kit-012", "Bajaj Majesty ICX 3 1900W Induction Cooktop",
     "Home&Kitchen", "Bajaj", 1699, 2499, "32%", 4.3, "27,654",
     "1900W, 7 preset menus, feather touch, auto-off, Indian menu options. Best-selling induction cooktop."),

    ("kit-013", "Philips Viva Collection HD4928/01 2100W Induction Cooktop",
     "Home&Kitchen", "Philips", 2495, 3495, "29%", 4.4, "14,321",
     "2100W, 5 preset cooking functions, touch control, child lock, keep warm. Premium induction cooktop."),

    ("kit-014", "Kent Grand Plus 9L RO+UV+UF+TDS Water Purifier",
     "Home&Kitchen", "Kent", 14999, 19999, "25%", 4.4, "13,432",
     "Multiple purification stages, saves 50% water, digital purity display, mineral RO. #1 water purifier brand."),

    ("kit-015", "Aquaguard Aura NXT 7L RO+UV+SS+MTDS Water Purifier",
     "Home&Kitchen", "Aquaguard", 13999, 18499, "24%", 4.4, "9,876",
     "IntelliSense Technology, Active Copper Zinc, Mineral Guard, tank full indicator. Smart water purifier."),

    ("kit-016", "Havells Diamo 7L RO+UV Water Purifier with Alkaline Water",
     "Home&Kitchen", "Havells", 11999, 15999, "25%", 4.3, "5,432",
     "7-stage purification, in-tank UV sterilization, iProtect Purification Monitoring. Budget RO purifier."),

    ("kit-017", "Prestige PRCK 6.0 L Electric Rice Cooker",
     "Home&Kitchen", "Prestige", 1299, 1999, "35%", 4.3, "20,543",
     "6L capacity, 500W, non-stick bowl, auto cooking & warm. Perfect for large families."),

    ("kit-018", "Panasonic SR-WA18H 4.4L Automatic Rice Cooker",
     "Home&Kitchen", "Panasonic", 1995, 2795, "29%", 4.5, "12,321",
     "4.4L, 660W, non-stick inner pan, automatic keep warm, cool-touch handles. Trusted rice cooker."),

    # ── MONITORS ──────────────────────────────────────────────
    ("mon-001", "LG 24MP400-B 24-inch Full HD IPS Monitor with AMD FreeSync",
     "Computers&Accessories", "LG", 8999, 11999, "25%", 4.5, "11,234",
     "24-inch FHD IPS, 75Hz, 3-side borderless, Anti-Glare, HDMI+VGA. Best budget IPS monitor."),

    ("mon-002", "Samsung 24-inch FHD IPS Ultra Slim Monitor with Eye Saver Mode",
     "Computers&Accessories", "Samsung", 9999, 13499, "26%", 4.4, "8,765",
     "IPS panel, 75Hz, Game Mode, Eye Saver Mode, Flicker Free, thin bezel. Great office monitor."),

    ("mon-003", "Dell 27-inch QHD IPS Monitor with USB-C and 165Hz",
     "Computers&Accessories", "Dell", 26990, 35990, "25%", 4.7, "4,321",
     "QHD 2560x1440, 165Hz, IPS, 1ms, USB-C 65W, Height Adjust Stand. Best QHD gaming and work monitor."),

    # ── PRINTERS ──────────────────────────────────────────────
    ("prt-001", "HP Ink Tank 315 Multi-Function Colour Printer",
     "Computers&Accessories", "HP", 9499, 12999, "27%", 4.4, "18,765",
     "Print, Scan, Copy, 1200x1200 dpi, 1000-page yield per bottle, USB. Best ink tank printer under ₹10k."),

    ("prt-002", "Epson EcoTank L3252 Wi-Fi All-in-One Ink Tank Printer",
     "Computers&Accessories", "Epson", 11999, 15999, "25%", 4.5, "13,432",
     "Wi-Fi Direct, Print/Scan/Copy, 7500-page colour yield, borderless printing. Best Wi-Fi ink tank printer."),

    ("prt-003", "Canon PIXMA G3020 NX All-in-One Wi-Fi Ink Tank Printer",
     "Computers&Accessories", "Canon", 10499, 13999, "25%", 4.4, "9,876",
     "Wi-Fi, 1200x4800 dpi, 7700-page black yield, Auto Duplex, Cloud Print. Trusted Canon quality."),

]


# ─────────────────────────────────────────────────────────────
# REVIEWS  (product_id → list of (title, text, rating))
# ─────────────────────────────────────────────────────────────

REVIEWS = {
    "lap-001": [
        ("Excellent value laptop", "Fast boot, smooth multitasking. Battery lasts 7+ hours. Great buy for the price.", 4.5),
        ("Good for work and studies", "Solid build, good display. Heats slightly under load but manageable.", 4.0),
        ("Best Dell budget laptop", "Keyboard feel is great, trackpad is responsive. Highly recommend.", 4.5),
    ],
    "lap-002": [
        ("Amazing battery life", "Ryzen 5 handles everything smoothly. Battery easily lasts 8 hours.", 4.5),
        ("Great slim laptop", "Very light and portable. Display is bright and accurate. Good value.", 4.5),
        ("Best budget laptop 2024", "Fast SSD, decent RAM, handles coding and light gaming well.", 5.0),
    ],
    "lap-003": [
        ("Good entry-level laptop", "For the price this is excellent. Smooth for browsing and office work.", 4.0),
        ("Decent starter laptop", "Light and portable. Wi-Fi 6 is a great touch. Display is good.", 4.5),
    ],
    "lap-004": [
        ("Premium feel at mid-range price", "Build quality is excellent. B&O speakers are surprisingly good.", 4.5),
        ("Fast and efficient", "i5 13th gen handles multitasking easily. Fast charge is super useful.", 5.0),
    ],
    "lap-005": [
        ("Simply the best laptop", "MacBook Air M2 is a beast. Incredibly fast, silent, stunning display.", 5.0),
        ("Worth every rupee", "Battery life is unmatched. 18 hours is real-world achievable. Love it.", 5.0),
        ("Best in class", "Feather light, blazing fast, gorgeous display. Perfect laptop for 2024.", 5.0),
    ],
    "lap-006": [
        ("Best budget gaming laptop", "RTX 2050 handles 1080p gaming very well. 144Hz display is smooth.", 4.5),
        ("Great for gaming and college", "Runs PUBG and Valorant smoothly. Good thermal performance.", 4.0),
    ],
    "lap-007": [
        ("Beast gaming laptop", "ROG Strix is phenomenal. QHD 165Hz looks incredible. Runs anything.", 5.0),
        ("Worth the premium", "RTX 4060 paired with Ryzen 9 is a killer combo. No thermal throttling.", 4.5),
    ],
    "lap-008": [
        ("Reliable business workhorse", "ThinkPad build quality is legendary. Spill-resistant keyboard is great.", 4.5),
        ("Perfect for professionals", "Fast charge is handy. MIL-STD durability gives confidence.", 5.0),
    ],
    "lap-009": [
        ("Great value Mi laptop", "Clean MIUI software experience. Fast SSD. Fingerprint sensor works perfectly.", 4.0),
        ("Good for basic use", "Handles office work and streaming without issues. Good battery.", 4.0),
    ],
    "lap-010": [
        ("Best HP gaming laptop", "144Hz panel makes a huge difference. Runs all popular games at high settings.", 4.5),
        ("Excellent mid-range gaming", "Great cooling, good keyboard, bright display. Highly recommended.", 4.0),
    ],
    "ac-001": [
        ("Best AC in India", "Daikin quality is unmatched. Cools 200 sq ft room in 10 mins. Very quiet.", 5.0),
        ("Superb inverter AC", "Electricity bill dropped significantly. PM 0.1 filter is a great feature.", 4.5),
        ("Excellent cooling", "Auto-clean feature keeps the unit fresh. Wifi control is very convenient.", 4.5),
    ],
    "ac-002": [
        ("LG never disappoints", "4-in-1 convertible is genius. Use 60% capacity in winter — saves energy.", 4.5),
        ("Quiet and powerful", "Dual inverter is whisper quiet. Ocean Black Protection means no rust. Love it.", 5.0),
        ("Great features", "10-year compressor warranty shows confidence. HD filter really works.", 4.5),
    ],
    "ac-003": [
        ("Best budget AC", "Cools well, affordable price, easy installation. Voltas is reliable.", 4.0),
        ("Value for money", "Does its job effectively. Sleep mode helps save power at night.", 4.5),
    ],
    "ac-004": [
        ("Smart AC done right", "WindFree cooling is a revelation — no direct cold air blast. AI mode works well.", 4.5),
        ("Samsung quality", "Tri-Care filter removes allergens. Works great with SmartThings app.", 5.0),
    ],
    "ac-005": [
        ("Efficient 1-ton AC", "Ideal for 10x12 room. Cools quickly. Self-cleaning is very convenient.", 4.5),
        ("Blue Star is underrated", "Very quiet, efficient, and cools fast. Great brand backed by good service.", 4.0),
    ],
    "ac-006": [
        ("Best 5-star AC for the price", "5-in-1 convertible works brilliantly. Use 40% in mild weather.", 4.5),
        ("Excellent value", "Active dehumidifier keeps room comfortable even in monsoon. Great buy.", 5.0),
    ],
    "ac-007": [
        ("Powerful 2-ton cooling", "Cools large hall in 15 minutes. 6-in-1 convertible is very useful.", 4.5),
        ("Premium LG experience", "ThinQ app is seamless. Weekly scheduling saves electricity bills.", 5.0),
    ],
    "ac-008": [
        ("Good entry AC", "Cools effectively for the price. PM 2.5 filter is good for air quality.", 4.0),
        ("Decent cooling", "Good brand, does the job. After-sales service was prompt.", 4.0),
    ],
    "ac-009": [
        ("Best premium AC", "nanoe-X purification is remarkable — air quality improved noticeably.", 5.0),
        ("Smart and efficient", "Miraie app works flawlessly. 7-in-1 modes cover all weather scenarios.", 4.5),
    ],
    "ac-010": [
        ("Reliable Hitachi quality", "Frost wash cleans coils automatically — very innovative feature.", 4.5),
        ("Solid mid-range AC", "Good cooling capacity. 24-hour timer is convenient.", 4.0),
    ],
    "tv-001": [
        ("Best 4K TV value", "Crystal 4K picture is stunning. Alexa voice control works seamlessly.", 4.5),
        ("Amazing Samsung TV", "Colors are vivid, blacks are deep. Smart Hub has all OTT apps.", 5.0),
        ("Great purchase", "Motion Xcelerator reduces blur in sports content. Very happy.", 4.5),
    ],
    "tv-002": [
        ("WebOS is the best TV OS", "LG's WebOS is intuitive. Picture quality is excellent.", 4.5),
        ("Filmmaker Mode is amazing", "Colors are accurate in Filmmaker Mode. Great for movie lovers.", 5.0),
    ],
    "tv-003": [
        ("Sony picture quality is unmatchable", "Triluminos Pro makes every frame look cinematic. Worth the premium.", 5.0),
        ("Best TV I've owned", "Bravia Core streams in highest bitrate. Acoustic Multi-Audio fills the room.", 5.0),
    ],
    "tv-004": [
        ("Best budget 55-inch TV", "A+ Grade panel is surprisingly good for the price. Dolby Vision works.", 4.0),
        ("Great value 55-inch", "Chromecast built-in is very useful. Smooth Android TV experience.", 4.5),
    ],
    "tv-005": [
        ("QLED at this price is insane", "QLED makes colors pop beautifully. Game Master Pro reduces lag.", 4.5),
        ("Excellent TCL TV", "60W Onkyo audio doesn't need a soundbar. Hands-free voice control works.", 4.0),
    ],
    "tv-006": [
        ("Hisense punches above its weight", "ULED picture quality rivals much pricier TVs. Dolby Vision IQ.", 4.5),
        ("Great value QLED TV", "Bright panel, accurate colors, smooth motion. Very happy with purchase.", 4.0),
    ],
    "ph-001": [
        ("Best Samsung flagship experience", "Dynamic AMOLED display is gorgeous. IP68 is reassuring.", 4.5),
        ("Great camera phone", "50MP camera delivers stunning shots. Smooth performance.", 4.0),
    ],
    "ph-002": [
        ("Fastest mid-range phone", "Snapdragon 8 Gen 2 is blazing fast. 100W charging in 25 mins!", 5.0),
        ("OnePlus quality", "120Hz AMOLED looks amazing. OxygenOS is smooth and clean.", 4.5),
    ],
    "ph-003": [
        ("Best phone under 20k", "108MP camera is exceptional. AMOLED 120Hz is smooth. Long battery.", 4.5),
        ("Redmi reliability", "Great build quality, good cameras, fast charging. Perfect mid-ranger.", 4.0),
    ],
    "ph-004": [
        ("Great Realme phone", "100MP OIS camera is impressive. 67W charges in under 45 mins.", 4.5),
        ("Smooth performer", "Dimensity 7050 handles gaming well. Curved display looks premium.", 4.0),
    ],
    "ph-005": [
        ("iPhone 15 is perfect", "Dynamic Island is brilliant. USB-C is finally here. Camera is best-in-class.", 5.0),
        ("Worth every rupee", "A16 Bionic makes everything buttery smooth. Build quality is exceptional.", 5.0),
        ("Simply the best phone", "Best camera I've used. Portrait mode is stunning. Battery improved a lot.", 5.0),
    ],
    "ph-006": [
        ("Clean Android experience", "Near-stock Android is refreshing. IP68 at this price is incredible.", 4.5),
        ("Great Moto phone", "144Hz pOLED is very smooth. Good cameras and battery life.", 4.0),
    ],
    "rf-001": [
        ("Best refrigerator under 30k", "DoorCooling+ keeps everything fresh. Smart Diagnosis app is handy.", 4.5),
        ("Great LG fridge", "Very quiet compressor. 10-year warranty gives peace of mind.", 5.0),
    ],
    "rf-002": [
        ("Samsung always delivers", "SpaceMax technology means more storage in same footprint. Great.", 4.5),
        ("Excellent refrigerator", "Power Freeze mode is very useful. Digital inverter is whisper quiet.", 4.0),
    ],
    "rf-003": [
        ("Reliable Whirlpool", "6th Sense technology prevents overcooling. Fresh food stays fresh longer.", 4.0),
        ("Good family fridge", "265L is perfect for family of 4. Frost-free means no maintenance.", 4.5),
    ],
    "wm-001": [
        ("Best washing machine ever", "AI Direct Drive adapts wash motion. Clothes come out perfectly clean.", 5.0),
        ("TurboWash saves time", "Full wash in 39 minutes with TurboWash. Steam removes allergens.", 4.5),
    ],
    "wm-002": [
        ("Great top loader", "Digital inverter is very quiet. Magic Filter catches all lint and debris.", 4.5),
        ("Good Samsung washer", "Simple controls, effective cleaning, energy efficient. Happy customer.", 4.0),
    ],
    "wm-003": [
        ("German engineering shows", "Absolutely silent — can't hear it running. AllergyPlus cycle is great.", 5.0),
        ("Best front loader quality", "EcoSilence motor is exceptional. Anti-vibration design is solid.", 4.5),
    ],
    "kit-001": [
        ("Best mixer grinder", "750W motor crushes everything effortlessly. 4 jars cover all needs.", 4.5),
        ("Philips never disappoints", "Very durable, blades stay sharp. Turbo boost for tough ingredients.", 5.0),
        ("Excellent kitchen companion", "Smooth grinding, easy to clean. Motor stays cool even after long use.", 4.5),
    ],
    "kit-002": [
        ("Best budget mixer", "550W is more than enough for daily use. Good value for money.", 4.0),
        ("Prestige quality", "Sturdy build, sharp blades, works great. Very popular brand.", 4.5),
    ],
    "kit-003": [
        ("Bajaj is trusted", "Basic but reliable. Good for everyday grinding and mixing needs.", 4.0),
        ("Good value", "Does what it promises. Overload protection is a useful safety feature.", 4.0),
    ],
    "kit-004": [
        ("Best microwave oven", "SmartInverter heats evenly — no cold spots! Indian menu options are spot-on.", 5.0),
        ("LG quality is excellent", "EasyClean coating is fantastic. 28L is perfect for family of 4.", 4.5),
    ],
    "kit-005": [
        ("Feature-packed Samsung microwave", "SlimFry is a great feature for low-oil cooking. 15 auto cook menus cover all.", 4.5),
        ("Great convection oven", "Triple Distribution heats perfectly. Build quality is solid.", 4.0),
    ],
    "kit-006": [
        ("Good IFB microwave", "101 autocook menus are helpful for Indian cooking. Deodorizer works well.", 4.0),
        ("Decent microwave", "Good value for price. Steam clean feature makes maintenance easy.", 4.5),
    ],
    "kit-007": [
        ("Philips air fryer is the best", "Rapid Air technology cooks evenly without any oil. Fries are crispy!", 5.0),
        ("Game changer in kitchen", "Used it daily for 6 months — still works like new. Easy to clean.", 4.5),
        ("Healthy cooking made easy", "7 preset programs cover all my needs. Much healthier than deep frying.", 4.5),
    ],
    "kit-008": [
        ("Instant Vortex is amazing", "EvenCrisp technology delivers perfectly crispy results every time.", 5.0),
        ("Large capacity air fryer", "5.7L is great for family cooking. App with 100+ recipes is excellent.", 4.5),
    ],
    "kit-009": [
        ("Great Tefal air fryer", "8 presets are very useful. XL pan holds enough for 3-4 people.", 4.5),
        ("Healthy and easy cooking", "Non-stick pan is easy to clean. Results are consistently good.", 4.0),
    ],
    "kit-010": [
        ("Best budget kettle", "Boils faster than gas. Auto shut-off and dry boil protection is reassuring.", 4.5),
        ("Excellent value", "Very durable stainless steel build. 360° swivel base is convenient.", 4.0),
    ],
    "kit-011": [
        ("Fast Philips kettle", "2400W boils 1.7L in under 4 minutes. Anti-scale filter keeps water clean.", 4.5),
        ("Premium kettle", "Concealed element makes cleaning easy. Auto shut-off works flawlessly.", 5.0),
    ],
    "kit-012": [
        ("Best induction cooktop value", "7 preset menus make cooking easy. Very fast heating. Good brand.", 4.0),
        ("Bajaj quality", "Feather touch controls are responsive. Auto-off for safety. Reliable.", 4.5),
    ],
    "kit-013": [
        ("Excellent Philips induction", "2100W heats instantly. Child lock gives peace of mind. Keep warm is useful.", 4.5),
        ("Best induction under 3k", "5 cooking functions cover all daily needs. Touch controls are precise.", 4.0),
    ],
    "kit-014": [
        ("Kent is the best RO", "Multiple purification stages give confidence. Digital display is helpful.", 4.5),
        ("Saves 50% water — brilliant", "Most ROs waste water but Kent's zero-water-wastage tech is amazing.", 5.0),
    ],
    "kit-015": [
        ("Aquaguard is trusted", "IntelliSense tells you when service is due. Active Copper health benefit.", 4.5),
        ("Great water purifier", "Easy installation, good customer support. Purified water tastes great.", 4.0),
    ],
    "kit-016": [
        ("Good budget RO", "7-stage purification at this price is great value. iProtect monitor is useful.", 4.0),
        ("Havells quality", "Alkaline water feature is a nice premium touch. Good after-sales support.", 4.5),
    ],
    "kit-017": [
        ("Best rice cooker for family", "6L cooks for 8 people at once. Non-stick bowl makes cleaning easy.", 4.0),
        ("Prestige is reliable", "Simple and effective. Auto-warm keeps rice fresh for hours.", 4.5),
    ],
    "kit-018": [
        ("Best rice cooker brand", "Panasonic quality is excellent. Non-stick pan and auto keep-warm is perfect.", 5.0),
        ("Cooks perfect rice every time", "Just add rice and water — perfect fluffy rice every time. Love it.", 4.5),
    ],
    "mon-001": [
        ("Best budget IPS monitor", "Colors are accurate and bright. 75Hz with FreeSync eliminates tearing.", 4.5),
        ("Great LG monitor", "3-side borderless design looks great on desk. Anti-glare reduces fatigue.", 4.5),
    ],
    "mon-002": [
        ("Excellent Samsung monitor", "Eye Saver Mode reduces eye strain during long work sessions.", 4.5),
        ("Good office monitor", "Ultra slim design looks premium. Flicker Free display is easy on eyes.", 4.0),
    ],
    "mon-003": [
        ("Best QHD monitor", "QHD 165Hz is a huge upgrade for gaming and design work. USB-C 65W charges laptop.", 5.0),
        ("Dell quality is premium", "Height-adjustable stand is very ergonomic. Picture quality is stunning.", 4.5),
    ],
    "prt-001": [
        ("Best ink tank printer", "Ink bottles last incredibly long. Print quality is sharp. Easy setup.", 4.5),
        ("Great HP printer", "Scan and copy work well too. Much cheaper than cartridge printers long-term.", 4.5),
    ],
    "prt-002": [
        ("Best Wi-Fi ink tank printer", "Wi-Fi Direct is very convenient. 7500-page yield per colour bottle.", 5.0),
        ("Epson EcoTank saves money", "Initial cost is high but running cost is minimal. Excellent printer.", 4.5),
    ],
    "prt-003": [
        ("Canon PIXMA is reliable", "7700-page black yield is exceptional. Cloud Print works perfectly.", 4.5),
        ("Great all-in-one printer", "Wi-Fi setup was easy. Print quality is crisp and accurate.", 4.0),
    ],
}


# ─────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────

def load():
    with get_conn() as conn:
        with conn.cursor() as cur:
            p_inserted = 0
            p_skipped = 0
            for row in PRODUCTS:
                (pid, name, cat, brand, price, orig, disc,
                 rating, rating_count, desc) = row
                try:
                    cur.execute(
                        """
                        INSERT INTO products
                            (product_id, name, category, brand, price,
                             original_price, discount_pct, rating,
                             rating_count, description, availability)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (product_id) DO NOTHING
                        """,
                        [pid, name, cat, brand, price, orig, disc,
                         rating, rating_count, desc, True],
                    )
                    if cur.rowcount:
                        p_inserted += 1
                    else:
                        p_skipped += 1
                except Exception as e:
                    print(f"  Product error [{pid}]: {e}")

            r_inserted = 0
            r_skipped = 0
            for pid, review_list in REVIEWS.items():
                for title, text, rat in review_list:
                    rid = str(uuid.uuid4())
                    try:
                        cur.execute(
                            """
                            INSERT INTO reviews
                                (review_id, product_id, customer_name,
                                 rating, review_title, review_text)
                            VALUES (%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (review_id) DO NOTHING
                            """,
                            [rid, pid, "Verified Buyer",
                             rat, title, text],
                        )
                        if cur.rowcount:
                            r_inserted += 1
                        else:
                            r_skipped += 1
                    except Exception as e:
                        print(f"  Review error [{pid}]: {e}")

    print(f"Products  — inserted: {p_inserted}, already existed: {p_skipped}")
    print(f"Reviews   — inserted: {r_inserted}, already existed: {r_skipped}")


def verify():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, COUNT(*) FROM products GROUP BY category ORDER BY COUNT(*) DESC"
            )
            print("\nCategory breakdown:")
            for cat, cnt in cur.fetchall():
                print(f"  {cat:<30} {cnt}")

            for label, kw in [("Laptops", "laptop"), ("Air Conditioners", "air conditioner"),
                               ("Smart TVs", "inch"), ("Smartphones", "5g"),
                               ("Kitchen", "mixer grinder")]:
                cur.execute(
                    "SELECT COUNT(*) FROM products WHERE name ILIKE %s",
                    [f"%{kw}%"]
                )
                print(f"  Products matching '{label}': {cur.fetchone()[0]}")


if __name__ == "__main__":
    print("Seeding popular products...")
    load()
    verify()
    print("\nDone.")
