"""
Seed script — fills gaps in kitchen appliance categories:
  - Pressure cookers  (0 → 10)
  - Water bottles     (1 → 10)
  - Coffee makers     (6 → 14, adds premium options)
  - Microwaves        (3 → 9, adds solo & grill types)
  - More blenders, juicers, toasters for variety

Run: python tools/seed_kitchen_appliances.py
"""

import sys, os, uuid
import psycopg2, psycopg2.extras

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


PRODUCTS = [
    # ══════════════════════════════════════════════
    # PRESSURE COOKERS
    # ══════════════════════════════════════════════
    (
        "pc-001",
        "Prestige Deluxe Plus Outer Lid Pressure Cooker 5 Litre Aluminium",
        "Home&Kitchen",
        "Prestige",
        1195,
        1695,
        "30%",
        4.4,
        "28,432",
        "Hard anodized aluminium, pressure indicator, safety plug, Teflon coated. Most popular Indian pressure cooker.",
    ),
    (
        "pc-002",
        "Hawkins Stainless Steel Pressure Cooker 5 Litre",
        "Home&Kitchen",
        "Hawkins",
        2499,
        3199,
        "22%",
        4.5,
        "14,321",
        "Food-grade stainless steel, tri-ply base, even heat distribution, 5-year warranty. Premium build quality.",
    ),
    (
        "pc-003",
        "Prestige Popular Aluminium Pressure Cooker 3 Litre",
        "Home&Kitchen",
        "Prestige",
        845,
        1195,
        "29%",
        4.3,
        "32,543",
        "Lightweight aluminium, sturdy lid, pressure indicator, safety valve, 1-year warranty. Best budget cooker.",
    ),
    (
        "pc-004",
        "Butterfly Blue Line Aluminium Pressure Cooker 5 Litre",
        "Home&Kitchen",
        "Butterfly",
        999,
        1399,
        "29%",
        4.3,
        "18,765",
        "Outer lid design, aluminium body, pressure indicator, gasket release system. Trusted South Indian brand.",
    ),
    (
        "pc-005",
        "Vinod Stainless Steel Pressure Cooker 5 Litre Inner Lid",
        "Home&Kitchen",
        "Vinod",
        2195,
        2895,
        "24%",
        4.4,
        "9,876",
        "Triply stainless steel, induction compatible, dishwasher safe, ISI certified. Premium cooking performance.",
    ),
    (
        "pc-006",
        "Instant Pot Duo 5.7L 7-in-1 Multi-Use Electric Pressure Cooker",
        "Home&Kitchen",
        "Instant",
        9995,
        14995,
        "33%",
        4.6,
        "8,432",
        "Pressure cook, slow cook, rice, saute, steam, warm, yoghurt. 14 smart programs, UL certified. Best electric cooker.",
    ),
    (
        "pc-007",
        "Hawkins Futura Pressure Cooker 3 Litre Hard Anodized",
        "Home&Kitchen",
        "Hawkins",
        2095,
        2795,
        "25%",
        4.5,
        "7,654",
        "Hard anodized, non-stick interior, outer lid, encapsulated bottom. Great for induction cooktops.",
    ),
    (
        "pc-008",
        "TTK Prestige Manttra 5 Litre Aluminium Pressure Cooker",
        "Home&Kitchen",
        "Prestige",
        1345,
        1895,
        "29%",
        4.2,
        "11,234",
        "Anti-bulge lid, safety valve, ISI mark, aluminium body. Ideal for medium-size families.",
    ),
    (
        "pc-009",
        "Pigeon by Stovekraft Junior 3 Litre Aluminium Pressure Cooker",
        "Home&Kitchen",
        "Pigeon",
        695,
        995,
        "30%",
        4.2,
        "22,543",
        "Lightweight aluminium, hard anodized, pressure indicator. Best budget cooker under ₹700.",
    ),
    (
        "pc-010",
        "Prestige Svachh 5 Litre Inner Lid Pressure Cooker with Deep Lid",
        "Home&Kitchen",
        "Prestige",
        1795,
        2395,
        "25%",
        4.5,
        "13,210",
        "Deep lid prevents spills, easy clean spout, virgin aluminium body. Innovative spill-free design.",
    ),
    # ══════════════════════════════════════════════
    # WATER BOTTLES — Insulated & Sports
    # ══════════════════════════════════════════════
    (
        "wb-001",
        "Milton Thermosteel Flip Lid Flask 1000ml Insulated Water Bottle",
        "Home&Kitchen",
        "Milton",
        849,
        1295,
        "34%",
        4.4,
        "31,234",
        "Double-wall vacuum insulation, keeps hot 24hr / cold 24hr, food-grade stainless steel, leak-proof flip lid.",
    ),
    (
        "wb-002",
        "Cello Ozone 1000ml Stainless Steel Vacuum Insulated Water Bottle",
        "Home&Kitchen",
        "Cello",
        599,
        899,
        "33%",
        4.3,
        "24,543",
        "18/8 food-grade stainless steel, vacuum insulated, wide mouth, BPA-free lid. Best value insulated bottle.",
    ),
    (
        "wb-003",
        "Borosil Hydra Go 1 Litre Vacuum Insulated Sports Water Bottle",
        "Home&Kitchen",
        "Borosil",
        999,
        1499,
        "33%",
        4.5,
        "18,765",
        "18/8 stainless steel, 12hr hot / 24hr cold, leak-proof, lightweight 290g, sports nozzle. Best sports bottle.",
    ),
    (
        "wb-004",
        "Milton Unify Stainless Steel Hot and Cold Water Bottle 1000ml",
        "Home&Kitchen",
        "Milton",
        549,
        799,
        "31%",
        4.3,
        "28,432",
        "Stainless steel, keeps hot 6hr / cold 24hr, BPA-free, leak-proof. Everyday reliable water bottle.",
    ),
    (
        "wb-005",
        "Hydro Flask Standard Mouth 621ml Vacuum Insulated Water Bottle",
        "Home&Kitchen",
        "Hydro Flask",
        3495,
        4495,
        "22%",
        4.7,
        "9,876",
        "TempShield double-wall insulation, powder coat exterior, 18/8 pro-grade stainless steel, leakproof. Premium bottle.",
    ),
    (
        "wb-006",
        "Puma Water Bottle 750ml Sports Bottle with Flip Lid",
        "Home&Kitchen",
        "Puma",
        699,
        999,
        "30%",
        4.2,
        "14,321",
        "BPA-free Tritan plastic, flip top lid, easy grip design, dishwasher safe. Lightweight sports companion.",
    ),
    (
        "wb-007",
        "Wildcraft Bolt 750ml Sports Water Bottle",
        "Home&Kitchen",
        "Wildcraft",
        599,
        849,
        "29%",
        4.3,
        "12,432",
        "BPA-free material, ergonomic grip, wide mouth for ice cubes, easy clean. Great for gym and outdoors.",
    ),
    (
        "wb-008",
        "Nalgene Wide Mouth 1L HDPE Water Bottle",
        "Home&Kitchen",
        "Nalgene",
        1295,
        1695,
        "24%",
        4.6,
        "7,654",
        "BPA-free HDPE, dishwasher safe, wide 63mm mouth for ice, lifetime guarantee. Outdoor adventurer favourite.",
    ),
    (
        "wb-009",
        "Steel Lock Stainless Steel Water Bottle 1L with Carrying Pouch",
        "Home&Kitchen",
        "Steel Lock",
        449,
        699,
        "36%",
        4.2,
        "19,876",
        "Food-grade stainless steel, leak-proof, BPA-free, vacuum insulated, free carrying pouch. Budget pick.",
    ),
    (
        "wb-010",
        "Camelbak Eddy+ 750ml BPA-Free Water Bottle with Bite Valve",
        "Home&Kitchen",
        "Camelbak",
        1999,
        2695,
        "26%",
        4.5,
        "8,765",
        "Bite valve with hands-free drinking, self-sealing, dishwasher safe, BPA/BPS/BPF free. Best cycling bottle.",
    ),
    # ══════════════════════════════════════════════
    # COFFEE MAKERS — Premium & Variety
    # ══════════════════════════════════════════════
    (
        "cof-001",
        "Nespresso Essenza Mini by De'Longhi Coffee Machine with 12 Capsules",
        "Home&Kitchen",
        "Nespresso",
        14990,
        19990,
        "25%",
        4.6,
        "8,765",
        "19-bar pressure, 0.6L tank, 15-second heat-up, two cup sizes (espresso & lungo), energy saving. Best pod machine.",
    ),
    (
        "cof-002",
        "De'Longhi Dedica Style EC685.M Pump Espresso Machine",
        "Home&Kitchen",
        "De'Longhi",
        22990,
        29990,
        "23%",
        4.6,
        "5,432",
        "15-bar pump, thermoblock heating, manual milk frother, 3 filter options. Professional espresso at home.",
    ),
    (
        "cof-003",
        "Morphy Richards New Europa 800W Espresso and Cappuccino Coffee Maker",
        "Home&Kitchen",
        "Morphy Richards",
        5499,
        7499,
        "27%",
        4.3,
        "12,321",
        "800W, 4-cup capacity, steam nozzle for frothing milk, fast brewing, detachable drip tray.",
    ),
    (
        "cof-004",
        "Preethi Cafe Zest CM210 600W Drip Coffee Maker",
        "Home&Kitchen",
        "Preethi",
        2299,
        3299,
        "30%",
        4.3,
        "9,876",
        "600W, 6-cup glass carafe, permanent filter, anti-drip, keep-warm plate, borosilicate glass. Reliable brand.",
    ),
    (
        "cof-005",
        "French Press Coffee Maker 600ml Borosilicate Glass with Double Filter",
        "Home&Kitchen",
        "Bodum",
        1299,
        1999,
        "35%",
        4.4,
        "14,543",
        "Borosilicate glass, double mesh filter, chrome plated lid, dishwasher safe, 600ml capacity. Best French press.",
    ),
    (
        "cof-006",
        "InstaCuppa French Press Coffee Maker 600ml with Thermally Insulated Body",
        "Home&Kitchen",
        "InstaCuppa",
        1499,
        2299,
        "35%",
        4.5,
        "11,234",
        "Stainless steel thermal body, dual-wall insulation, triple filter system, 600ml. Best insulated French press.",
    ),
    (
        "cof-007",
        "Kaapi Machines BUDAN Automatic Pour Over Coffee Machine",
        "Home&Kitchen",
        "Kaapi Machines",
        8999,
        11999,
        "25%",
        4.4,
        "3,210",
        "1.2L capacity, shower head for even extraction, keep warm plate, programmable. Best pour-over machine.",
    ),
    (
        "cof-008",
        "Nespresso Vertuo Pop Coffee Machine with Aeroccino3 Milk Frother",
        "Home&Kitchen",
        "Nespresso",
        18990,
        23990,
        "21%",
        4.7,
        "4,321",
        "Centrifusion technology, 5 cup sizes (espresso to alto), automatic capsule recognition, one-touch.",
    ),
    # ══════════════════════════════════════════════
    # MICROWAVES — Solo and Grill types added
    # ══════════════════════════════════════════════
    (
        "mw-001",
        "LG 20L Solo Microwave Oven MS2043DB",
        "Home&Kitchen",
        "LG",
        7490,
        9990,
        "25%",
        4.3,
        "18,432",
        "20L capacity, 700W, 5 power levels, smart diagnosis, child lock, 1-year warranty. Best solo microwave.",
    ),
    (
        "mw-002",
        "Samsung 20L Solo Microwave Oven MS20A3010AL",
        "Home&Kitchen",
        "Samsung",
        7990,
        10990,
        "27%",
        4.3,
        "14,321",
        "20L, 1150W, easy clean coating, ceramic enamel interior, 5 power levels, defrost. Reliable solo microwave.",
    ),
    (
        "mw-003",
        "Panasonic 20L Solo Microwave Oven NN-ST26JMFDG",
        "Home&Kitchen",
        "Panasonic",
        7990,
        10990,
        "27%",
        4.4,
        "11,234",
        "20L, 800W, 10 power levels, auto cook menu, child lock, 360-degree turntable. Japanese precision.",
    ),
    (
        "mw-004",
        "IFB 23L Grill Microwave Oven 23PG4B",
        "Home&Kitchen",
        "IFB",
        8990,
        11990,
        "25%",
        4.4,
        "12,543",
        "23L, grill + microwave combo, stainless steel cavity, 51 autocook menus, steam clean. Best grill microwave.",
    ),
    (
        "mw-005",
        "LG 21L Grill Microwave Oven MH2144DB",
        "Home&Kitchen",
        "LG",
        8490,
        10990,
        "23%",
        4.3,
        "9,876",
        "21L, 700W microwave + grill, EasyClean, quartz heater for crispy grilling, child lock. Good grill microwave.",
    ),
    (
        "mw-006",
        "Godrej 20L Convection Microwave Oven GME 720 CF1 PZ",
        "Home&Kitchen",
        "Godrej",
        9499,
        12999,
        "27%",
        4.2,
        "7,654",
        "20L, convection + grill + microwave, 200 autocook menus, starter kit. Indian brand, great after-sales support.",
    ),
    # ══════════════════════════════════════════════
    # BLENDERS — premium additions
    # ══════════════════════════════════════════════
    (
        "bl-001",
        "Philips HL7575/00 600W Hand Blender with Whisk and Chopper",
        "Home&Kitchen",
        "Philips",
        3295,
        4895,
        "33%",
        4.4,
        "11,234",
        "600W ProMix technology, 2-speed settings, detachable arm, dishwasher safe, 500ml chopper. Best hand blender.",
    ),
    (
        "bl-002",
        "Bosch MSM66150 600W Hand Blender with Blending Wand",
        "Home&Kitchen",
        "Bosch",
        3499,
        4999,
        "30%",
        4.5,
        "8,765",
        "600W, ErgoMixx grip, 2-speed + turbo, dishwasher safe attachment, QuattroBlade technology. German precision.",
    ),
    (
        "bl-003",
        "Nutribullet 900W Personal Blender for Nutrient Extraction",
        "Home&Kitchen",
        "Nutribullet",
        5999,
        7999,
        "25%",
        4.5,
        "7,654",
        "900W motor, extractor blade pulverises seeds & stems, 600ml cup with flip-top lid. Best smoothie blender.",
    ),
    (
        "bl-004",
        "Sujata Powermatic Plus 900W Juicer Mixer Grinder with Blender Jar",
        "Home&Kitchen",
        "Sujata",
        5890,
        7890,
        "25%",
        4.5,
        "9,876",
        "900W motor, 3 jars including blender jar, overload protection, stainless steel blades. Best high-power blender.",
    ),
    # ══════════════════════════════════════════════
    # JUICERS — centrifugal & cold press
    # ══════════════════════════════════════════════
    (
        "jcr-001",
        "Philips HR1832/00 Viva Collection Juicer 500W",
        "Home&Kitchen",
        "Philips",
        2995,
        3995,
        "25%",
        4.3,
        "12,543",
        "500W, 1L pulp container, 2-speed, QuickClean technology, extra wide tube. Trusted Philips centrifugal juicer.",
    ),
    (
        "jcr-002",
        "Hurom H-AA Slow Juicer 150W Cold Press Juicer",
        "Home&Kitchen",
        "Hurom",
        18999,
        24999,
        "24%",
        4.6,
        "3,210",
        "150W, slow squeeze technology, 60RPM, preserves nutrients, fine/coarse strainer, quiet operation. Best cold press.",
    ),
    (
        "jcr-003",
        "Kuvings Whole Slow Juicer EVO820 240W",
        "Home&Kitchen",
        "Kuvings",
        22999,
        28999,
        "21%",
        4.7,
        "2,543",
        "240W, 60RPM, 82mm wide mouth, auto-cleaning, smart cap, 10-year motor warranty. Premium slow juicer.",
    ),
    # ══════════════════════════════════════════════
    # TOASTERS — pop-up and sandwich makers
    # ══════════════════════════════════════════════
    (
        "tst-001",
        "Philips HD2582/00 2-Slice Pop-Up Toaster 830W",
        "Home&Kitchen",
        "Philips",
        1995,
        2795,
        "29%",
        4.4,
        "18,432",
        "830W, 7 browning settings, reheat/defrost/cancel, extra wide slots, removable crumb tray. Best pop-up toaster.",
    ),
    (
        "tst-002",
        "Bajaj ATX 4 2-Slice Pop-Up Toaster",
        "Home&Kitchen",
        "Bajaj",
        1295,
        1795,
        "28%",
        4.3,
        "22,543",
        "700W, 7 settings, cancel/reheat/defrost, high lift, removable crumb tray, 2-year warranty. Best budget toaster.",
    ),
    (
        "tst-003",
        "Prestige PPTPKB 800W Pop-Up Toaster with 2 Slice",
        "Home&Kitchen",
        "Prestige",
        1195,
        1695,
        "30%",
        4.2,
        "16,543",
        "800W, 6 browning levels, extra-wide slots, anti-jam function, slide-out crumb tray. Trusted Prestige brand.",
    ),
    (
        "tst-004",
        "Bajaj Majesty New SWX 9 2-in-1 Grill Sandwich Maker and Toaster",
        "Home&Kitchen",
        "Bajaj",
        1299,
        1799,
        "28%",
        4.3,
        "24,321",
        "750W, 2-in-1 sandwich + grilling, non-stick plates, cool touch handle, indicator light. Best sandwich toaster.",
    ),
    (
        "tst-005",
        "Prestige PGMFB 800W Grill Sandwich Maker with Non-Stick Plates",
        "Home&Kitchen",
        "Prestige",
        1399,
        1999,
        "30%",
        4.4,
        "19,876",
        "800W, non-stick coating, floating hinge, indicator light, cool touch body. Great family sandwich maker.",
    ),
    (
        "tst-006",
        "Philips HD2145/40 Daily Collection Sandwich Maker 820W",
        "Home&Kitchen",
        "Philips",
        1795,
        2395,
        "25%",
        4.5,
        "14,321",
        "820W, non-stick plates, triangular sandwiches, easy clean, compact design. Best Philips sandwich maker.",
    ),
]


REVIEWS = {
    "pc-001": [
        (
            "Best pressure cooker for everyday use",
            "Prestige quality is legendary. Hard anodized surface is very durable.",
            4.5,
        ),
        ("Great value for money", "Cooks rice and dal perfectly. Safety features are reassuring.", 4.5),
        ("Must-have kitchen essential", "Very easy to use and clean. Teflon coating helps with sticky food.", 4.0),
    ],
    "pc-002": [
        ("Premium stainless steel quality", "Hawkins stainless steel feels premium. Tri-ply base heats evenly.", 5.0),
        ("Best pressure cooker I've owned", "5-year warranty shows confidence. Easy to clean stainless steel.", 4.5),
    ],
    "pc-003": [
        ("Perfect budget pressure cooker", "3L is great for 2-3 people. Cooks fast and safe.", 4.5),
        ("Reliable everyday cooker", "Good size for bachelor or couple. Easy to handle.", 4.0),
    ],
    "pc-004": [
        ("Great South Indian brand", "Butterfly is very popular in South India. Good quality at budget price.", 4.0),
        ("Cooks well and lasts long", "Outer lid design is easy to open and close. Good pressure maintenance.", 4.5),
    ],
    "pc-005": [
        (
            "Best stainless steel cooker",
            "Triply base makes huge difference in even cooking. Induction compatible.",
            4.5,
        ),
        ("Premium build quality", "Dishwasher safe is a great convenience. Vinod makes excellent cookware.", 4.5),
    ],
    "pc-006": [
        ("Best electric pressure cooker", "Instant Pot is a game changer! 7-in-1 makes it incredibly versatile.", 5.0),
        ("Worth every rupee", "Set it and forget it cooking. Yoghurt mode is surprisingly useful.", 5.0),
        ("Life-changing kitchen appliance", "Saves so much time. Slow cook and pressure cook in one pot.", 5.0),
    ],
    "pc-007": [
        (
            "Best small pressure cooker",
            "3L hard anodized Hawkins is perfect for smaller families. Induction ready.",
            4.5,
        ),
        ("Excellent quality", "Non-stick interior makes cleaning easy. Worth the premium price.", 4.5),
    ],
    "pc-008": [
        ("Good everyday cooker", "Anti-bulge lid is a smart safety feature. ISI mark gives confidence.", 4.0),
        ("Reliable Prestige product", "Good for medium families. Easy to use and maintain.", 4.0),
    ],
    "pc-009": [
        ("Best budget pressure cooker", "Under 700 and works perfectly. Hard anodized finish is good.", 4.0),
        ("Great starter cooker", "Good for students or bachelors. Small and lightweight.", 4.0),
    ],
    "pc-010": [
        ("Innovative spill-free design", "Deep lid truly prevents spills during cooking. Game changer feature!", 4.5),
        ("Best Prestige cooker", "Svachh design means less mess and cleaning. Very clever engineering.", 5.0),
    ],
    "wb-001": [
        ("Best insulated water bottle", "Milton is trusted brand. 24hr cold is genuine — tested with ice cubes.", 4.5),
        ("Excellent thermos bottle", "Flip lid is very convenient. No leaks at all. Great build quality.", 4.5),
    ],
    "wb-002": [
        ("Good value bottle", "Cello quality at budget price. Keeps water cold for 20+ hours.", 4.0),
        ("Reliable everyday bottle", "Leak-proof works great in bag. Good capacity at good price.", 4.5),
    ],
    "wb-003": [
        ("Best sports water bottle", "Borosil quality is excellent. Sports nozzle is very convenient for gym.", 4.5),
        ("Perfect gym companion", "Lightweight at 290g is noticeable. Keeps water cold throughout workout.", 4.5),
    ],
    "wb-004": [
        ("Good everyday bottle", "Milton reliability is great. Simple design that works perfectly.", 4.0),
        ("Decent insulated bottle", "Keeps beverages at right temperature. Good value for money.", 4.5),
    ],
    "wb-005": [
        ("Worth the premium price", "Hydro Flask is in a different league. Still ice-cold after 24 hours!", 5.0),
        ("Best water bottle ever", "TempShield technology really works. Powder coat is very durable.", 5.0),
    ],
    "wb-006": [
        ("Great Puma sports bottle", "Flip lid is super convenient during sports. BPA-free is reassuring.", 4.0),
        ("Good sports bottle", "Lightweight and easy to carry. Puma brand quality is solid.", 4.5),
    ],
    "wb-007": [
        ("Good outdoor bottle", "Wildcraft reliability is good. Wide mouth makes filling easy.", 4.5),
        ("Great for gym and trekking", "Ergonomic grip is very useful. Durable build for outdoor use.", 4.0),
    ],
    "wb-008": [
        ("Best adventure bottle", "Nalgene is the gold standard for outdoor bottles. Lifetime guarantee.", 4.5),
        ("Indestructible bottle", "Wide mouth makes it easy to add ice and clean. BPA-free.", 5.0),
    ],
    "wb-009": [
        ("Good budget bottle", "Vacuum insulated at this price is great value. Carrying pouch is useful.", 4.0),
        ("Decent budget pick", "Does the job well. Stainless steel is better than plastic.", 4.0),
    ],
    "wb-010": [
        ("Best cycling water bottle", "Camelbak bite valve is hands-free drinking made easy.", 4.5),
        ("Perfect for cycling and sports", "Self-sealing valve means no spills in bag. Dishwasher safe.", 4.5),
    ],
    "cof-001": [
        ("Best pod coffee machine", "Nespresso coffee quality is exceptional. 15-second heat up is impressive.", 5.0),
        ("Cafe quality at home", "Capsules are expensive but convenience is unmatched. Great espresso.", 4.5),
    ],
    "cof-002": [
        ("Best espresso machine under 25k", "De'Longhi quality shows. 15-bar pump makes real espresso shots.", 5.0),
        ("Professional-level espresso", "Manual frother takes practice but results are barista-level. Worth it.", 4.5),
    ],
    "cof-003": [
        ("Good affordable espresso maker", "Morphy Richards reliability is good. Makes decent espresso.", 4.0),
        ("Value coffee machine", "Steam nozzle froths milk well. Good for beginners.", 4.5),
    ],
    "cof-004": [
        (
            "Best Indian drip coffee maker",
            "Preethi brand is well-known in South India. Makes great filter coffee.",
            4.5,
        ),
        ("Good value coffee maker", "Permanent filter saves on paper filters. Keep-warm plate works.", 4.0),
    ],
    "cof-005": [
        ("Best French press", "Bodum is the classic French press brand. Makes rich bold coffee.", 4.5),
        ("Great manual coffee maker", "Double filter means no coffee grounds in cup. Easy to clean.", 4.5),
    ],
    "cof-006": [
        ("Best insulated French press", "Thermal body keeps coffee hot for 2 hours. Triple filter is excellent.", 4.5),
        ("Premium French press", "Stainless steel body is much better than glass. More durable.", 5.0),
    ],
    "cof-007": [
        (
            "Best pour-over machine",
            "Kaapi Machines is a great Indian brand. Even extraction produces great coffee.",
            4.5,
        ),
        (
            "Great for coffee enthusiasts",
            "Shower head design is key for even brewing. Makes café-quality filter coffee.",
            4.0,
        ),
    ],
    "cof-008": [
        ("Best Nespresso machine", "Vertuo system is incredibly convenient. 5 cup sizes in one machine.", 4.5),
        ("Premium pod coffee", "Aeroccino frother makes perfect lattes. Centrifusion makes great crema.", 5.0),
    ],
    "mw-001": [
        ("Best solo microwave", "LG quality at budget price. 20L is perfect for bachelors and couples.", 4.5),
        ("Great everyday microwave", "Smart Diagnosis app is surprisingly useful. Very easy to use.", 4.0),
    ],
    "mw-002": [
        ("Good Samsung solo microwave", "EasyClean coating makes maintenance much easier. Reliable brand.", 4.0),
        ("Reliable budget microwave", "Heats food evenly. Samsung quality is consistent.", 4.5),
    ],
    "mw-003": [
        ("Best solo microwave for quality", "Panasonic heats more evenly than Samsung/LG I've used before.", 4.5),
        ("Japanese precision in microwave", "10 power levels give great control. Auto cook menus are useful.", 4.5),
    ],
    "mw-004": [
        (
            "Best grill microwave",
            "IFB grill function produces crispy results. 51 autocook menus cover Indian food.",
            4.5,
        ),
        ("Great versatile microwave", "Stainless steel cavity is easy to clean. Steam clean is very convenient.", 4.0),
    ],
    "mw-005": [
        ("Good LG grill microwave", "Quartz heater gives quick intense heat. EasyClean coating saves time.", 4.0),
        ("Decent grill microwave", "Good combination of features at reasonable price. LG reliability.", 4.5),
    ],
    "mw-006": [
        (
            "Good Indian brand microwave",
            "200 autocook menus specifically designed for Indian cooking is excellent.",
            4.0,
        ),
        ("Godrej quality", "After-sales service is very good. 20L convection is great for baking.", 4.5),
    ],
    "bl-001": [
        ("Best hand blender", "Philips ProMix technology is noticeably better than cheaper blenders.", 4.5),
        ("Great kitchen tool", "Detachable arm makes cleaning very easy. Chopper attachment is useful.", 4.5),
    ],
    "bl-002": [
        ("Best premium hand blender", "Bosch ErgoMixx grip is very comfortable for long blending sessions.", 4.5),
        ("German engineering in kitchen", "QuattroBlade reduces splashing significantly. Very quiet motor.", 5.0),
    ],
    "bl-003": [
        ("Best smoothie maker", "Nutribullet 900W pulverises everything including seeds and stems. Amazing.", 5.0),
        ("Life-changing for healthy eating", "Makes nutrient-rich smoothies in 30 seconds. Easy to clean cup.", 4.5),
    ],
    "bl-004": [
        ("Powerful blender-mixer combo", "900W motor handles everything. Great value 3-in-1 appliance.", 4.5),
        ("Best Sujata appliance", "Blender jar is perfect for smoothies and lassi. Very durable brand.", 4.5),
    ],
    "jcr-001": [
        ("Best budget centrifugal juicer", "Philips QuickClean makes the dreaded cleaning very fast.", 4.5),
        ("Good everyday juicer", "Extra-wide tube handles whole fruits. 1L pulp container is generous.", 4.0),
    ],
    "jcr-002": [
        ("Best cold press juicer", "Hurom slow squeeze preserves more nutrients. Noticeably better taste.", 5.0),
        ("Worth the premium price", "Quiet operation is a huge plus. Easy to clean for a cold press.", 4.5),
    ],
    "jcr-003": [
        ("Best premium juicer", "Kuvings wide mouth is a game changer — no pre-cutting needed!", 5.0),
        ("10-year warranty speaks volumes", "Auto-cleaning feature saves so much time. Best juice quality.", 5.0),
    ],
    "tst-001": [
        (
            "Best pop-up toaster",
            "Philips 7 browning settings give perfect control. Extra wide slots fit thick bread.",
            4.5,
        ),
        ("Great toaster reliability", "Reheat and defrost modes are very useful daily. Easy crumb tray clean.", 4.5),
    ],
    "tst-002": [
        ("Best budget toaster", "Bajaj reliability at budget price. 7 settings give good control.", 4.5),
        ("Great starter toaster", "Good quality for the price. Toasts evenly. Easy to use.", 4.0),
    ],
    "tst-003": [
        ("Good Prestige toaster", "Anti-jam function is a nice safety feature. Toasts evenly.", 4.0),
        ("Reliable budget toaster", "Good build quality. 6 settings are enough for daily use.", 4.0),
    ],
    "tst-004": [
        ("Best sandwich toaster", "2-in-1 sandwich and grilling is very useful. Non-stick plates work great.", 4.5),
        ("Great family appliance", "Makes perfect toasties every time. Indicator light is helpful.", 4.5),
    ],
    "tst-005": [
        ("Best Prestige sandwich maker", "Floating hinge accommodates thick sandwiches. Non-stick is durable.", 4.5),
        ("Great everyday sandwich maker", "Makes perfect triangular sandwiches. Easy to clean non-stick plates.", 4.5),
    ],
    "tst-006": [
        ("Best Philips sandwich maker", "Philips quality at mid-range price. Non-stick plates are excellent.", 4.5),
        ("Compact and efficient", "Heats up quickly, makes perfect sandwiches. Cool-touch body is safe.", 5.0),
    ],
}


def load():
    with get_conn() as conn:
        with conn.cursor() as cur:
            p_in, p_skip = 0, 0
            for row in PRODUCTS:
                pid, name, cat, brand, price, orig, disc, rating, rating_count, desc = row
                try:
                    cur.execute(
                        """INSERT INTO products
                               (product_id, name, category, brand, price,
                                original_price, discount_pct, rating,
                                rating_count, description, availability)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (product_id) DO NOTHING""",
                        [pid, name, cat, brand, price, orig, disc, rating, rating_count, desc, True],
                    )
                    if cur.rowcount:
                        p_in += 1
                    else:
                        p_skip += 1
                except Exception as e:
                    print(f"  Product error [{pid}]: {e}")

            r_in, r_skip = 0, 0
            for pid, review_list in REVIEWS.items():
                for title, text, rat in review_list:
                    try:
                        cur.execute(
                            """INSERT INTO reviews
                                   (review_id, product_id, customer_name,
                                    rating, review_title, review_text)
                               VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (review_id) DO NOTHING""",
                            [str(uuid.uuid4()), pid, "Verified Buyer", rat, title, text],
                        )
                        if cur.rowcount:
                            r_in += 1
                        else:
                            r_skip += 1
                    except Exception as e:
                        print(f"  Review error [{pid}]: {e}")

    print(f"Products  — inserted: {p_in}, already existed: {p_skip}")
    print(f"Reviews   — inserted: {r_in}, already existed: {r_skip}")


def verify():
    cats = [
        ("mixer grinder", "name ILIKE '%mixer grinder%'"),
        ("electric kettle", "name ILIKE '%kettle%'"),
        ("air fryer", "name ILIKE '%air fryer%'"),
        ("pressure cooker", "name ILIKE '%pressure cooker%'"),
        ("microwave", "name ILIKE '%microwave%'"),
        ("water bottle", "name ILIKE '%water bottle%'"),
        ("coffee maker", "name ILIKE '%coffee%'"),
        ("juicer", "name ILIKE '%juicer%'"),
        ("blender", "name ILIKE '%blender%'"),
        ("toaster", "name ILIKE '%toaster%' OR name ILIKE '%sandwich maker%'"),
    ]
    print("\nCategory counts after seed:")
    with get_conn() as conn:
        with conn.cursor() as cur:
            for label, condition in cats:
                cur.execute(f"SELECT COUNT(*) FROM products WHERE {condition}")
                print(f"  {label:<18} {cur.fetchone()[0]}")


if __name__ == "__main__":
    print("Seeding kitchen appliances...")
    load()
    verify()
    print("\nDone.")
