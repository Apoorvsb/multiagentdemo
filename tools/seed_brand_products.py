"""
Seed script — brand-specific flagship products for:
Apple, Samsung, Sony, HP, Dell, Lenovo, OnePlus, boAt

Run: python tools/seed_brand_products.py
"""

import sys, os, uuid
import psycopg2, psycopg2.extras

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST, port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB, user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


PRODUCTS = [

    # ══════════════════════════════════════════════
    # APPLE
    # ══════════════════════════════════════════════
    ("apple-001", "Apple AirPods Pro 2nd Generation with Active Noise Cancellation",
     "Electronics", "Apple", 24900, 29900, "17%", 4.8, "21,432",
     "H2 chip, Adaptive Transparency, Personalised Spatial Audio, MagSafe charging case, 6-hour battery."),

    ("apple-002", "Apple AirPods 3rd Generation with Lightning Charging Case",
     "Electronics", "Apple", 18500, 22900, "19%", 4.6, "14,321",
     "Spatial Audio, Adaptive EQ, skin-detect sensor, IPX4 sweat resistant, 6-hour battery. Best everyday earbuds."),

    ("apple-003", "Apple iPhone 15 Plus 128GB Black",
     "Electronics", "Apple", 89900, 99900, "10%", 4.7, "8,765",
     "6.7-inch Super Retina XDR, Dynamic Island, 48MP main camera, A16 Bionic, USB-C, 4383mAh. Best big-screen iPhone."),

    ("apple-004", "Apple iPhone 14 128GB Midnight",
     "Electronics", "Apple", 69900, 79900, "13%", 4.6, "18,543",
     "6.1-inch Super Retina XDR, A15 Bionic, 12MP dual camera, Emergency SOS via satellite, Crash Detection."),

    ("apple-005", "Apple iPhone 14 Pro 256GB Space Black",
     "Electronics", "Apple", 109900, 129900, "15%", 4.8, "11,234",
     "6.1-inch ProMotion Always-On display, Dynamic Island, A16 Bionic, 48MP Pro camera system, ProRes video."),

    ("apple-006", "Apple MacBook Air M3 Chip 8GB RAM 256GB SSD 13-inch",
     "Computers&Accessories", "Apple", 114900, 129900, "12%", 4.9, "6,543",
     "M3 chip, 18-hour battery, 15.3-inch Liquid Retina, Wi-Fi 6E, MagSafe 3, Midnight colour. Fastest thin laptop."),

    ("apple-007", "Apple MacBook Air M3 Chip 8GB RAM 256GB SSD 15-inch",
     "Computers&Accessories", "Apple", 134900, 149900, "10%", 4.8, "4,321",
     "Largest MacBook Air, 15.3-inch Liquid Retina, M3 chip, 18-hour battery, MagSafe 3, Wi-Fi 6E."),

    ("apple-008", "Apple iPad Pro M4 11-inch 256GB Wi-Fi Space Black",
     "Electronics", "Apple", 99900, 109900, "9%", 4.9, "5,432",
     "Ultra Retina XDR OLED, M4 chip, Apple Pencil Pro, 10MP Ultra Wide front camera, 5G ready. Pro tablet experience."),

    ("apple-009", "Apple iPad mini 6th Gen 64GB Wi-Fi Purple",
     "Electronics", "Apple", 46900, 52900, "11%", 4.7, "9,876",
     "8.3-inch Liquid Retina, A15 Bionic, USB-C, 5G optional, Apple Pencil 2 support, Center Stage camera."),

    ("apple-010", "Apple Watch Ultra 2 with Alpine Loop",
     "Electronics", "Apple", 89900, 99900, "10%", 4.9, "3,210",
     "49mm titanium case, Precision GPS, 36-hour battery, Action Button, brightest Apple Watch display. For adventurers."),

    ("apple-011", "Apple Watch SE 2nd Generation GPS 40mm Midnight Aluminium",
     "Electronics", "Apple", 29900, 34900, "14%", 4.7, "12,543",
     "Crash Detection, Fall Detection, Heart Rate, Sleep tracking, Water resistant 50m. Best value Apple Watch."),

    # ══════════════════════════════════════════════
    # SAMSUNG
    # ══════════════════════════════════════════════
    ("sam-s24-001", "Samsung Galaxy S24 5G 8GB RAM 128GB Onyx Black",
     "Electronics", "Samsung", 74999, 84999, "12%", 4.7, "9,876",
     "6.2-inch Dynamic AMOLED 2X 120Hz, Snapdragon 8 Gen 3, 50MP camera, 4000mAh, IP68, 7-year OS updates."),

    ("sam-s24-002", "Samsung Galaxy S24+ 5G 12GB RAM 256GB Marble Gray",
     "Electronics", "Samsung", 99999, 114999, "13%", 4.8, "5,432",
     "6.7-inch Dynamic AMOLED 2X, Snapdragon 8 Gen 3, 50MP + 10MP + 12MP cameras, 4900mAh, 45W fast charge."),

    ("sam-s24-003", "Samsung Galaxy S24 Ultra 5G 12GB RAM 256GB Titanium Gray",
     "Electronics", "Samsung", 134999, 154999, "13%", 4.9, "7,654",
     "6.8-inch QHD+ Dynamic AMOLED 2X, built-in S Pen, 200MP camera, Snapdragon 8 Gen 3, 5000mAh. Ultimate flagship."),

    ("sam-a55-001", "Samsung Galaxy A55 5G 8GB RAM 128GB Awesome Iceblue",
     "Electronics", "Samsung", 38999, 44999, "13%", 4.5, "13,432",
     "6.6-inch Super AMOLED 120Hz, Exynos 1480, 50MP OIS, IP67, 5000mAh, 25W, Android 14. Best mid-range."),

    ("sam-a35-001", "Samsung Galaxy A35 5G 8GB RAM 128GB Awesome Iceblue",
     "Electronics", "Samsung", 30999, 35999, "14%", 4.4, "18,765",
     "6.6-inch Super AMOLED 120Hz, Exynos 1380, 50MP + 8MP + 5MP, IP67, 5000mAh. Great value Samsung phone."),

    ("sam-a15-001", "Samsung Galaxy A15 5G 4GB RAM 128GB Blue Black",
     "Electronics", "Samsung", 15999, 19999, "20%", 4.3, "22,432",
     "6.5-inch Super AMOLED 90Hz, MediaTek Dimensity 6100+, 50MP, 5000mAh, side fingerprint. Budget 5G phone."),

    ("sam-tab-001", "Samsung Galaxy Tab S9 FE 6GB RAM 128GB Gray Wi-Fi",
     "Electronics", "Samsung", 34999, 42999, "19%", 4.5, "7,654",
     "10.9-inch TFT display, Exynos 1380, IP68, S Pen included, 8000mAh, 45W fast charge. Best Samsung tablet."),

    ("sam-tab-002", "Samsung Galaxy Tab A9+ 8GB RAM 128GB Wi-Fi Graphite",
     "Electronics", "Samsung", 24999, 29999, "17%", 4.3, "11,234",
     "11-inch LCD 90Hz, Snapdragon 695, Dolby Atmos Quad speakers, 7040mAh, kids mode. Best budget tablet."),

    ("sam-buds-001", "Samsung Galaxy Buds 2 Pro Active Noise Cancellation TWS Earbuds",
     "Electronics", "Samsung", 12999, 17999, "28%", 4.5, "8,765",
     "2.5-hour ANC with barge-in feature, 3D audio, Hi-Fi 24-bit, 8hr battery, IPX7. Premium Samsung earbuds."),

    ("sam-watch-001", "Samsung Galaxy Watch 6 Classic 43mm Bluetooth Black",
     "Electronics", "Samsung", 32999, 39999, "18%", 4.6, "5,432",
     "Rotating bezel, 1.3-inch Super AMOLED, BioActive sensor, advanced sleep tracking, 40-hour battery."),

    # ══════════════════════════════════════════════
    # SONY — Headphones focus
    # ══════════════════════════════════════════════
    ("sony-h-001", "Sony WH-1000XM5 Wireless Industry Leading Noise Cancelling Headphones",
     "Electronics", "Sony", 26990, 34990, "23%", 4.8, "14,321",
     "8 mics, 2 processors, 30-hr battery, Auto NC Optimizer, speak-to-chat, multipoint. Best ANC headphones ever."),

    ("sony-h-002", "Sony WH-1000XM4 Wireless Noise Cancelling Headphones",
     "Electronics", "Sony", 19990, 29990, "33%", 4.7, "28,543",
     "30-hour battery, 360 Reality Audio, Speak-to-Chat, DSEE Extreme, multipoint. Still the benchmark ANC headphone."),

    ("sony-h-003", "Sony WH-CH720N Wireless Noise Cancelling Headphones",
     "Electronics", "Sony", 7990, 11990, "33%", 4.4, "18,765",
     "Lightweight 192g, 35-hour battery, multipoint, DSEE, Quick Charge (3 min = 60 min), foldable. Best budget ANC."),

    ("sony-h-004", "Sony WH-CH520 Wireless Headphones 50 Hours Battery",
     "Electronics", "Sony", 3990, 5990, "33%", 4.3, "22,432",
     "50-hour battery, multipoint connection, 30mm drivers, DSEE, foldable compact design. Best budget Sony headphone."),

    ("sony-e-001", "Sony WF-1000XM5 True Wireless Industry Leading Noise Cancelling Earbuds",
     "Electronics", "Sony", 19990, 27990, "29%", 4.7, "9,876",
     "HD Noise Cancelling Processor QN2e, 8hr battery + 16hr case, LDAC, multipoint, IPX4. Best TWS earbuds."),

    ("sony-e-002", "Sony WF-1000XM4 True Wireless Noise Cancelling Earbuds",
     "Electronics", "Sony", 14990, 22990, "35%", 4.6, "17,654",
     "8hr battery + 16hr case, LDAC Hi-Res Audio, 360 Reality Audio, IPX4. Premium noise-cancelling TWS."),

    ("sony-e-003", "Sony LinkBuds S Truly Wireless Noise Cancelling Earbuds",
     "Electronics", "Sony", 11990, 16990, "29%", 4.5, "8,765",
     "4.8g ultra-light, ANC + Ambient Sound, IPX4, 6hr battery, multipoint, DSEE Extreme, LDAC. Lightest ANC TWS."),

    ("sony-e-004", "Sony WF-C700N Wireless Noise Cancelling Earbuds",
     "Electronics", "Sony", 7990, 11990, "33%", 4.4, "12,321",
     "20hr total playtime with case, ANC, Ambient Sound Mode, IPX4, multipoint. Best mid-range Sony TWS."),

    ("sony-e-005", "Sony WF-C500 Truly Wireless Headphones 20 Hours Battery",
     "Electronics", "Sony", 4990, 7990, "38%", 4.3, "15,432",
     "20-hour battery (10+10), IPX4, 5.8mm drivers, Voice Assistant. Best budget Sony TWS earbuds."),

    # ══════════════════════════════════════════════
    # HP — Laptops
    # ══════════════════════════════════════════════
    ("hp-001", "HP Spectre x360 14 Intel Core Ultra 7 16GB RAM 1TB SSD 2-in-1 Laptop",
     "Computers&Accessories", "HP", 164999, 184999, "11%", 4.7, "2,109",
     "2.8K OLED touch display, 360-degree hinge, OLED pen, Wi-Fi 6E, long battery life. HP's flagship premium laptop."),

    ("hp-002", "HP Envy x360 14 AMD Ryzen 7 7730U 16GB RAM 512GB SSD 2-in-1 Laptop",
     "Computers&Accessories", "HP", 89999, 104999, "14%", 4.5, "3,218",
     "14-inch WUXGA IPS touch, 360-degree hinge, HP Rechargeable MPP2.0 Tilt Pen, B&O audio. Premium convertible."),

    ("hp-003", "HP Omen 16 AMD Ryzen 7 7745HX RTX 4070 16GB RAM 1TB SSD Gaming Laptop",
     "Computers&Accessories", "HP", 129999, 149999, "13%", 4.6, "1,876",
     "16.1-inch QHD 165Hz IPS, OMEN Gaming Hub, Tempest Cooling, Cherry MX keyboard. Best HP gaming laptop."),

    ("hp-004", "HP ProBook 440 G10 Intel Core i5 13th Gen 8GB RAM 512GB SSD Business Laptop",
     "Computers&Accessories", "HP", 58990, 68990, "15%", 4.4, "2,543",
     "14-inch FHD IPS, HP Wolf Security, fast charge, spill-resistant keyboard. Reliable SMB business laptop."),

    ("hp-005", "HP 15s Intel Core i5 13th Gen 8GB RAM 512GB SSD Laptop",
     "Computers&Accessories", "HP", 47990, 54990, "13%", 4.3, "6,543",
     "15.6-inch FHD IPS micro-edge, anti-glare, Wi-Fi 6, HP Fast Charge, HP Audio Boost. Everyday home laptop."),

    ("hp-006", "HP Laptop 14s AMD Ryzen 3 7320U 8GB RAM 512GB SSD",
     "Computers&Accessories", "HP", 36990, 42990, "14%", 4.2, "5,432",
     "14-inch FHD IPS, micro-edge, HP Fast Charge, slim 16.9mm design. Entry-level laptop for students."),

    # ══════════════════════════════════════════════
    # DELL — Laptops
    # ══════════════════════════════════════════════
    ("dell-001", "Dell XPS 13 Intel Core i7 13th Gen 16GB RAM 512GB SSD 13.4-inch Laptop",
     "Computers&Accessories", "Dell", 134999, 154999, "13%", 4.7, "3,210",
     "13.4-inch OLED InfinityEdge touch display, Killer Wi-Fi 6E, Thunderbolt 4, premium aluminium build. Dell's best laptop."),

    ("dell-002", "Dell Vostro 15 3530 Intel Core i5 13th Gen 8GB RAM 512GB SSD Laptop",
     "Computers&Accessories", "Dell", 48990, 56990, "14%", 4.4, "4,321",
     "15.6-inch FHD anti-glare, backlit keyboard, spill-resistant, 3-year ProSupport, Windows 11 Pro. Business laptop."),

    ("dell-003", "Dell G15 5530 Intel Core i7 13th Gen RTX 4060 16GB RAM 512GB SSD Gaming Laptop",
     "Computers&Accessories", "Dell", 89999, 104999, "14%", 4.5, "3,210",
     "15.6-inch FHD 165Hz, Alienware Command Center, ComfortView Plus, Nahimic Audio. Best Dell gaming laptop."),

    ("dell-004", "Dell G16 7630 Intel Core i9 13th Gen RTX 4070 32GB RAM 1TB SSD Gaming Laptop",
     "Computers&Accessories", "Dell", 149999, 174999, "14%", 4.7, "1,543",
     "16-inch QHD+ 240Hz, MUX Switch, 3ms response, Cherry MX keyboard option. Flagship Dell gaming laptop."),

    ("dell-005", "Dell Inspiron 16 Intel Core i7 13th Gen 16GB RAM 512GB SSD 2-in-1 Laptop",
     "Computers&Accessories", "Dell", 89999, 104999, "14%", 4.5, "2,876",
     "16-inch FHD+ IPS touch, 360-degree, stylus support, QHD webcam, backlit keyboard. Best Dell 2-in-1."),

    ("dell-006", "Dell Latitude 7440 Intel Core i5 13th Gen 16GB RAM 512GB SSD Business Laptop",
     "Computers&Accessories", "Dell", 99999, 114999, "13%", 4.6, "1,234",
     "14-inch FHD IPS, vPro platform, 4G LTE optional, Windows 11 Pro. Premium enterprise-grade laptop."),

    # ══════════════════════════════════════════════
    # LENOVO — Laptops
    # ══════════════════════════════════════════════
    ("len-001", "Lenovo Legion 5 AMD Ryzen 7 7745HX RTX 4060 16GB RAM 512GB SSD Gaming Laptop",
     "Computers&Accessories", "Lenovo", 89999, 104999, "14%", 4.7, "5,432",
     "15.6-inch FHD 144Hz IPS, 135W TDP GPU, Coldfront 5.0 cooling, RGB TrueStrike keyboard. Best mid-range gaming laptop."),

    ("len-002", "Lenovo Legion 5 Pro AMD Ryzen 9 7945HX RTX 4070 32GB RAM 1TB SSD Gaming Laptop",
     "Computers&Accessories", "Lenovo", 139999, 164999, "15%", 4.8, "2,876",
     "16-inch QHD+ 165Hz, Legion AI Engine+, Coldfront 5.0, MUX Switch, per-key RGB. Premium gaming powerhouse."),

    ("len-003", "Lenovo Yoga Slim 7i Intel Core Ultra 5 16GB RAM 512GB SSD 14-inch Laptop",
     "Computers&Accessories", "Lenovo", 84999, 99999, "15%", 4.6, "3,210",
     "14-inch 2.8K OLED touch, AI-powered features, backlit keyboard, thunderbolt 4, 70Wh battery. Premium ultrabook."),

    ("len-004", "Lenovo IdeaPad 5 Pro AMD Ryzen 7 8845HS 16GB RAM 512GB SSD 16-inch Laptop",
     "Computers&Accessories", "Lenovo", 79999, 94999, "16%", 4.5, "4,321",
     "16-inch 2.5K IPS 120Hz, Dolby Atmos, backlit, fingerprint, Wi-Fi 6E, 75Wh battery. Best productivity laptop."),

    ("len-005", "Lenovo LOQ 15 Intel Core i5 13th Gen RTX 4050 8GB RAM 512GB SSD Gaming Laptop",
     "Computers&Accessories", "Lenovo", 64999, 76999, "16%", 4.4, "6,543",
     "15.6-inch FHD 144Hz IPS, Coldfront 5.0, AI Engine+, Legion TrueStrike keyboard. Budget gaming laptop 2024."),

    ("len-006", "Lenovo ThinkBook 15 Intel Core i5 13th Gen 16GB RAM 512GB SSD Business Laptop",
     "Computers&Accessories", "Lenovo", 62990, 74990, "16%", 4.5, "3,876",
     "15.6-inch FHD IPS, privacy shutter, fingerprint, IR camera, spill-resistant, Rapid Charge. SMB laptop."),

    # ══════════════════════════════════════════════
    # ONEPLUS — Phones
    # ══════════════════════════════════════════════
    ("op-001", "OnePlus 11 5G 8GB RAM 128GB Titan Black",
     "Electronics", "OnePlus", 56999, 61999, "8%", 4.6, "12,432",
     "6.7-inch AMOLED 120Hz, Snapdragon 8 Gen 2, Hasselblad-tuned 50MP triple camera, 5000mAh, 100W SUPERVOOC."),

    ("op-002", "OnePlus 11R 5G 8GB RAM 128GB Sonic Black",
     "Electronics", "OnePlus", 39999, 44999, "11%", 4.5, "8,765",
     "6.74-inch AMOLED 120Hz, Snapdragon 8+ Gen 1, 50MP triple camera, 5000mAh, 100W fast charge."),

    ("op-003", "OnePlus Nord 3 5G 8GB RAM 128GB Misty Green",
     "Electronics", "OnePlus", 33999, 37999, "11%", 4.5, "9,876",
     "6.74-inch AMOLED 120Hz, MediaTek Dimensity 9000, 50MP OIS, 5000mAh, 80W SUPERVOOC. Best mid-range OnePlus."),

    ("op-004", "OnePlus Nord CE 3 5G 8GB RAM 128GB Aqua Surge",
     "Electronics", "OnePlus", 26999, 29999, "10%", 4.4, "11,234",
     "6.7-inch AMOLED 120Hz, Snapdragon 782G, 50MP OIS, 5000mAh, 67W SUPERVOOC. Great value Nord phone."),

    ("op-005", "OnePlus Nord CE 3 Lite 5G 8GB RAM 128GB Pastel Lime",
     "Electronics", "OnePlus", 19999, 22999, "13%", 4.3, "16,543",
     "6.72-inch LCD 120Hz, Snapdragon 695, 108MP camera, 5000mAh, 67W SUPERVOOC. Best budget OnePlus phone."),

    ("op-006", "OnePlus Nord CE 4 5G 8GB RAM 256GB Celadon Marble",
     "Electronics", "OnePlus", 24999, 28999, "14%", 4.5, "7,654",
     "6.67-inch AMOLED 120Hz, Snapdragon 7s Gen 3, 50MP OIS, 5500mAh, 100W SUPERVOOC. Feature-packed mid-ranger."),

    ("op-007", "OnePlus 12 16GB RAM 512GB Flowy Emerald",
     "Electronics", "OnePlus", 74999, 84999, "12%", 4.7, "6,543",
     "6.82-inch AMOLED 120Hz, Snapdragon 8 Gen 3, Hasselblad 50MP + 64MP periscope, 5400mAh, 100W."),

    # ══════════════════════════════════════════════
    # BOAT — Earbuds and Headphones
    # ══════════════════════════════════════════════
    ("boat-001", "boAt Airdopes 800 ANC Active Noise Cancellation TWS Earbuds",
     "Electronics", "boAt", 3499, 5999, "42%", 4.3, "14,321",
     "ANC with 27dB noise reduction, 50H playtime, 12mm drivers, ENx Tech, Beast Mode, ASAP Charge, IPX5."),

    ("boat-002", "boAt Airdopes 500 ANC True Wireless Earbuds",
     "Electronics", "boAt", 2499, 4499, "44%", 4.2, "11,234",
     "ANC, 24H playtime, 10mm drivers, ENx quad mics, Beast Mode 50ms, IPX5, Instacharge. Best budget ANC TWS."),

    ("boat-003", "boAt Airdopes 400 TWS Earbuds with 40H Playtime",
     "Electronics", "boAt", 1299, 2499, "48%", 4.1, "19,876",
     "40H total playtime, 10mm drivers, ENx Tech, Beast Mode 65ms, IPX4, IWP. Best boAt budget earbuds."),

    ("boat-004", "boAt Rockerz 600 ANC Wireless Headphones",
     "Electronics", "boAt", 2499, 4499, "44%", 4.2, "8,765",
     "ANC up to 35dB, 80H playback, 40mm drivers, Beast Mode, soft padded earcups, ASAP Charge. Over-ear ANC."),

    ("boat-005", "boAt Rockerz 551 ANC Wireless Headphones 80H Battery",
     "Electronics", "boAt", 1999, 3999, "50%", 4.2, "12,432",
     "ANC, 80H battery, 40mm drivers, Signature sound, foldable design, physical noise isolation. Budget ANC headphone."),

    ("boat-006", "boAt Airdopes 131 True Wireless Earbuds 8mm Drivers",
     "Electronics", "boAt", 999, 1999, "50%", 4.1, "25,432",
     "8mm drivers, 14H playtime, ENx Tech, IPX4, lightweight 4.5g per earbud. Most affordable boAt TWS."),

    ("boat-007", "boAt Airdopes 441 v2 True Wireless Earbuds 42H Playback",
     "Electronics", "boAt", 1499, 2999, "50%", 4.2, "17,654",
     "42H total playtime, Beast Mode 80ms, ENx Tech dual mics, IPX5, IWP auto-connect. Upgrade budget earbuds."),

    ("boat-008", "boAt Rockerz 255 ANC Neckband Bluetooth Earphones",
     "Electronics", "boAt", 1599, 2999, "47%", 4.3, "14,321",
     "ANC neckband, 40H battery, IPX7 waterproof, ASAP Charge, dual pairing, Beast Mode. Best neckband earphones."),

    ("boat-009", "boAt Rockerz 480 Over Ear Bluetooth Headphones",
     "Electronics", "boAt", 1599, 2999, "47%", 4.2, "9,876",
     "Over-ear, 40H playtime, 40mm drivers, Beast Mode, foldable, padded cushions, fast charge. Affordable over-ear."),

    ("boat-010", "boAt Stone 650 Portable Bluetooth Speaker 10W",
     "Electronics", "boAt", 1499, 2999, "50%", 4.2, "21,234",
     "10W stereo, IPX5 water resistant, 8H battery, 360-degree sound, party mode, EQ modes, USB-C charging."),

    ("boat-011", "boAt Airdopes 181 Pro ANC True Wireless Earbuds",
     "Electronics", "boAt", 1899, 3499, "46%", 4.3, "10,543",
     "ANC, 50H total playtime, quad mics ENx, Beast Mode 60ms, IPX5, ASAP Charge, Bluetooth 5.3. Premium mid-range TWS."),

]


REVIEWS = {
    "apple-001": [
        ("Best earbuds ever made", "AirPods Pro 2 ANC is exceptional. Transparency mode sounds natural. H2 chip shows.", 5.0),
        ("Worth every rupee", "Personalised Spatial Audio is incredible for movies. Battery life is great.", 5.0),
        ("Apple at its best", "Seamless switching between iPhone/Mac/iPad. MagSafe case is very convenient.", 4.5),
    ],
    "apple-002": [
        ("Great everyday earbuds", "Spatial Audio makes music immersive. Comfortable fit. 6 hours is enough.", 4.5),
        ("Good AirPods experience", "Easy pairing, great sound, reliable. Sweat resistant for workouts.", 4.5),
    ],
    "apple-003": [
        ("Best big-screen iPhone", "The larger battery life is a huge upgrade. Dynamic Island is fun.", 4.5),
        ("Great iPhone 15 Plus", "USB-C was a long time coming. 48MP camera delivers stunning photos.", 5.0),
    ],
    "apple-004": [
        ("Reliable everyday iPhone", "A15 Bionic handles everything smoothly. Great camera for the price.", 4.5),
        ("Great value iPhone", "Crash Detection is reassuring. Camera is excellent, especially portraits.", 4.5),
    ],
    "apple-005": [
        ("Pro iPhone experience", "ProMotion Always-On display is beautiful. 48MP camera is studio quality.", 5.0),
        ("Best iPhone 14 model", "Dynamic Island is brilliant. ProRes video quality is exceptional.", 4.5),
    ],
    "apple-006": [
        ("Fastest laptop I've used", "M3 chip is insanely fast. Wi-Fi 6E makes network transfers instant.", 5.0),
        ("MacBook Air M3 is perfect", "18-hour battery is real-world accurate. Midnight colour is stunning.", 5.0),
        ("Best laptop for 2024", "Silent fanless design, blazing fast, gorgeous display. Perfect laptop.", 5.0),
    ],
    "apple-007": [
        ("15-inch is the ideal size", "Large display with portability of an Air. M3 handles everything.", 5.0),
        ("Stunning big MacBook Air", "15.3-inch Liquid Retina is gorgeous. Great for Figma and coding.", 4.5),
    ],
    "apple-008": [
        ("iPad Pro M4 is astonishing", "OLED display is breathtaking. M4 chip is faster than most laptops.", 5.0),
        ("Best tablet available", "Apple Pencil Pro is a revelation. Ultra Retina XDR makes everything pop.", 5.0),
    ],
    "apple-009": [
        ("Perfect compact tablet", "8.3-inch is ideal size. A15 Bionic makes it very fast. Center Stage works.", 4.5),
        ("Great iPad mini", "USB-C was needed. Apple Pencil 2 works brilliantly. Compact and powerful.", 5.0),
    ],
    "apple-010": [
        ("Ultimate adventure watch", "Precision GPS is incredibly accurate. 36-hour battery is real. Action Button.", 5.0),
        ("Best smartwatch period", "Titanium feels premium. Brightest display outdoors. Worth the premium.", 5.0),
    ],
    "apple-011": [
        ("Best value Apple Watch", "Crash Detection has saved a family member. Sleep tracking is very accurate.", 4.5),
        ("Perfect everyday smartwatch", "Everything an Apple Watch should be at a fair price. Health features great.", 4.5),
    ],
    "sam-s24-001": [
        ("Best compact flagship 2024", "Snapdragon 8 Gen 3 screams. 7-year update promise is industry-leading.", 5.0),
        ("Excellent S24", "Night mode photos are stunning. AI features like Circle to Search are very useful.", 4.5),
    ],
    "sam-s24-002": [
        ("S24+ is the sweet spot", "Big battery, big screen, no compromise. AI Galaxy features are impressive.", 5.0),
        ("Best Samsung flagship experience", "45W charging tops up fast. Camera zoom is excellent.", 4.5),
    ],
    "sam-s24-003": [
        ("S24 Ultra is unmatched", "200MP camera is insane. S Pen integration is seamless. Best phone of 2024.", 5.0),
        ("Ultimate Samsung flagship", "Built-in S Pen changes how I use my phone. Titanium frame feels premium.", 5.0),
    ],
    "sam-a55-001": [
        ("Best mid-range Samsung phone", "IP67 at this price is incredible. Super AMOLED 120Hz is silky smooth.", 4.5),
        ("Excellent Galaxy A55", "Exynos 1480 handles gaming well. 5000mAh lasts all day easily.", 4.5),
    ],
    "sam-a35-001": [
        ("Great value phone", "120Hz Super AMOLED at this price is remarkable. IP67 is reassuring.", 4.5),
        ("Solid mid-range phone", "Great camera quality for the price. Long battery life.", 4.0),
    ],
    "sam-a15-001": [
        ("Best budget 5G phone", "5G connectivity at under 16k is amazing. Super AMOLED display is gorgeous.", 4.5),
        ("Great entry Samsung phone", "Smooth display, decent camera, good battery. Excellent for students.", 4.0),
    ],
    "sam-tab-001": [
        ("Best Samsung tablet value", "S Pen included is great value. IP68 means no worry about spills.", 4.5),
        ("Great work tablet", "45W fast charge is fast. Exynos 1380 handles everything smoothly.", 4.5),
    ],
    "sam-tab-002": [
        ("Perfect family tablet", "11-inch size is great for kids and adults. Quad speakers are impressive.", 4.0),
        ("Good budget tablet", "Kids mode is very well implemented. 7040mAh battery lasts days.", 4.5),
    ],
    "sam-buds-001": [
        ("Best Samsung earbuds", "2.5-hour ANC mode is very effective. 3D audio is immersive.", 4.5),
        ("Premium TWS experience", "Hi-Fi 24-bit audio quality is noticeable. IPX7 in the shower too!", 5.0),
    ],
    "sam-watch-001": [
        ("Best Samsung watch", "Rotating physical bezel is so satisfying. Sleep tracking is very accurate.", 4.5),
        ("Love the classic design", "BioActive sensor tracks health stats all day. Battery lasts 40 hours.", 5.0),
    ],
    "sony-h-001": [
        ("Gold standard ANC headphone", "XM5 ANC is in a class of its own. 8 microphones deliver perfect ANC.", 5.0),
        ("Best headphone money can buy", "Sound quality is reference-level. Speak-to-chat is genius. Buy it!", 5.0),
        ("Absolutely worth it", "Auto NC Optimizer adjusts ANC to your environment automatically. Wow.", 5.0),
    ],
    "sony-h-002": [
        ("Still the best ANC headphone", "XM4 remains unbeaten at this price. 30-hour battery is real.", 5.0),
        ("Better than Bose QC45", "Sound profile is more detailed. Multipoint connection works perfectly.", 4.5),
        ("Industry standard ANC", "Had these for 2 years — still flawless. Speak-to-Chat is daily use feature.", 4.5),
    ],
    "sony-h-003": [
        ("Best budget ANC headphone", "35-hour battery with ANC is unbelievable. Multipoint is very useful.", 4.5),
        ("Amazing lightweight headphone", "192g is feather-light. 3-minute quick charge for 60 mins is a lifesaver.", 4.5),
    ],
    "sony-h-004": [
        ("Best budget Sony headphone", "50-hour battery is hard to believe. Sound quality is excellent for price.", 4.5),
        ("Great value headphone", "Multipoint connection for 2 devices works well. Compact foldable design.", 4.0),
    ],
    "sony-e-001": [
        ("Best TWS earbuds 2024", "WF-1000XM5 ANC is remarkable in such a small form factor. LDAC is special.", 5.0),
        ("Sony TWS perfection", "8+16 hour battery is more than enough. Multipoint switching is seamless.", 5.0),
    ],
    "sony-e-002": [
        ("Best premium TWS earbuds", "LDAC brings out incredible detail in music. IPX4 for gym use.", 4.5),
        ("Excellent noise cancellation", "ANC rivals over-ear headphones. 360 Reality Audio is immersive.", 5.0),
    ],
    "sony-e-003": [
        ("Lightest ANC earbuds", "4.8g per earbud is incredibly light — forget they are there all day.", 4.5),
        ("Great everyday earbuds", "LinkBuds S ANC is surprisingly good. LDAC audio quality is excellent.", 4.5),
    ],
    "sony-e-004": [
        ("Best mid-range TWS", "20-hour total battery is great. ANC is effective for daily commute.", 4.5),
        ("Great value Sony earbuds", "Multipoint works perfectly between phone and laptop. Clear call quality.", 4.0),
    ],
    "sony-e-005": [
        ("Best budget Sony TWS", "10+10 hour battery in this price range is great. IPX4 for rain/sweat.", 4.0),
        ("Good starter TWS earbuds", "Comfortable fit, decent sound, reliable connection. Value for money.", 4.5),
    ],
    "hp-001": [
        ("Best premium HP laptop", "Spectre x360 OLED display is jaw-dropping. 360-degree is smooth.", 5.0),
        ("HP's finest laptop", "OLED pen is responsive. Wi-Fi 6E makes data transfer very fast.", 4.5),
    ],
    "hp-002": [
        ("Excellent 2-in-1 laptop", "Ryzen 7 handles everything from design to coding. B&O audio impressive.", 4.5),
        ("Great convertible laptop", "Touch display is responsive. 360-degree hinge is very solid.", 4.5),
    ],
    "hp-003": [
        ("Best HP gaming laptop", "RTX 4070 handles every game at ultra settings easily. Cooling is excellent.", 5.0),
        ("Omen quality shows", "Cherry MX keyboard is a premium addition. QHD 165Hz is butter smooth.", 4.5),
    ],
    "hp-004": [
        ("Reliable business laptop", "HP Wolf Security gives IT team peace of mind. Build quality is solid.", 4.5),
        ("Great HP ProBook", "Fast charge to 50% in 30 minutes is very useful. Good spill-resistant keyboard.", 4.0),
    ],
    "hp-005": [
        ("Good everyday laptop", "FHD IPS anti-glare is easy on eyes all day. Fast charge is convenient.", 4.0),
        ("Decent HP laptop", "Wi-Fi 6 is noticeably faster than older laptops. Good value for money.", 4.5),
    ],
    "hp-006": [
        ("Great student laptop", "Good performance for college work. 14-inch is portable size. Slim design.", 4.0),
        ("Good budget HP", "Ryzen 3 handles basic tasks well. 512GB SSD boots fast.", 4.0),
    ],
    "dell-001": [
        ("Best premium laptop ever", "XPS 13 OLED InfinityEdge is the most beautiful laptop display.", 5.0),
        ("Dell's finest laptop", "Thunderbolt 4 for dual 4K displays. Killer Wi-Fi 6E is insanely fast.", 5.0),
    ],
    "dell-002": [
        ("Reliable Dell Vostro", "3-year ProSupport means you're covered. Build quality is very solid.", 4.5),
        ("Good business laptop", "Backlit keyboard with spill-resistant is essential for business use.", 4.0),
    ],
    "dell-003": [
        ("Best Dell gaming laptop", "RTX 4060 + 165Hz is a fantastic combo. Alienware Command Center is useful.", 4.5),
        ("Great gaming performance", "ComfortView Plus reduces eye strain for long gaming sessions.", 4.5),
    ],
    "dell-004": [
        ("Flagship Dell gaming", "RTX 4070 + 32GB RAM handles any game or workload. QHD 240Hz is incredible.", 5.0),
        ("Worth the premium", "MUX Switch gives GPU full bandwidth. Cherry MX keyboard is a delight.", 4.5),
    ],
    "dell-005": [
        ("Best Dell 2-in-1", "16-inch touch display makes creative work enjoyable. QHD webcam is sharp.", 4.5),
        ("Great versatile laptop", "Stylus support adds creative flexibility. 360-degree hinge is sturdy.", 4.0),
    ],
    "dell-006": [
        ("Premium enterprise laptop", "vPro platform with 4G LTE is essential for field teams. Very durable.", 4.5),
        ("Best Dell business laptop", "Windows 11 Pro with enterprise features. 512GB NVMe is very fast.", 5.0),
    ],
    "len-001": [
        ("Best gaming laptop under 90k", "Legion 5 gaming performance is unmatched at this price. 135W GPU TDP!", 5.0),
        ("Lenovo Legion is legendary", "Coldfront 5.0 keeps temperatures well controlled. RGB keyboard is great.", 4.5),
        ("Excellent mid-range gaming", "RTX 4060 handles 1080p ultra settings easily. 144Hz is smooth.", 4.5),
    ],
    "len-002": [
        ("Gaming laptop perfection", "Legion 5 Pro QHD 165Hz is stunning. RTX 4070 is future-proof.", 5.0),
        ("Best premium gaming laptop", "32GB RAM handles everything. MUX Switch gives max GPU performance.", 5.0),
    ],
    "len-003": [
        ("Best premium ultrabook", "2.8K OLED is the most beautiful laptop display I've seen. Very fast.", 5.0),
        ("Great Yoga Slim 7i", "AI features for productivity are genuinely useful. Thunderbolt 4 is fast.", 4.5),
    ],
    "len-004": [
        ("Best productivity laptop", "2.5K 120Hz IPS is excellent for design work. Dolby Atmos sounds great.", 4.5),
        ("Excellent IdeaPad 5 Pro", "Ryzen 7 8845HS performance is phenomenal. Great battery life.", 4.5),
    ],
    "len-005": [
        ("Best budget gaming laptop", "RTX 4050 for under 65k is incredible value. Coldfront 5.0 keeps it cool.", 4.5),
        ("Great Lenovo LOQ value", "LOQ is the budget gaming laptop to beat in 2024. 144Hz smooth.", 4.0),
    ],
    "len-006": [
        ("Great ThinkBook laptop", "Privacy shutter and IR camera are essential for video calls. Solid build.", 4.5),
        ("Reliable SMB laptop", "Spill-resistant keyboard and Rapid Charge are very practical features.", 4.0),
    ],
    "op-001": [
        ("Best OnePlus flagship", "Hasselblad camera tuning is excellent. 100W SUPERVOOC charges in 25 mins.", 5.0),
        ("OnePlus 11 is incredible", "Snapdragon 8 Gen 2 is blazing fast. Display is stunning.", 4.5),
    ],
    "op-002": [
        ("Best value OnePlus", "11R offers flagship-level performance at mid-range price. 100W charging.", 4.5),
        ("Great everyday phone", "8+ Gen 1 is very powerful. AMOLED 120Hz is silky smooth.", 4.5),
    ],
    "op-003": [
        ("Best mid-range phone 2023", "Dimensity 9000 is a flagship chip in a Nord phone! Incredible value.", 5.0),
        ("Excellent Nord 3", "50MP OIS camera takes excellent photos. 80W charges in 45 minutes.", 4.5),
    ],
    "op-004": [
        ("Great Nord CE 3", "Snapdragon 782G is perfect for daily use and gaming. OIS camera is good.", 4.5),
        ("Good value mid-range", "67W charging is very fast. 120Hz AMOLED is smooth and vibrant.", 4.0),
    ],
    "op-005": [
        ("Best budget 5G phone", "108MP camera produces impressive shots. 67W charging is impressive.", 4.5),
        ("Great value phone under 20k", "5G on a budget is the future. 120Hz LCD is surprisingly smooth.", 4.0),
    ],
    "op-006": [
        ("Nord CE 4 is excellent", "100W charging in this price range is amazing. Snapdragon 7s Gen 3 flies.", 4.5),
        ("Great upgrade for Nord users", "AMOLED 120Hz display is gorgeous. 5500mAh battery is huge.", 4.5),
    ],
    "op-007": [
        ("OnePlus 12 is a beast", "Snapdragon 8 Gen 3 + 100W SUPERVOOC is an unbeatable combo.", 5.0),
        ("Best flagship OnePlus", "64MP periscope zoom delivers exceptional detail. Hasselblad colours are great.", 4.5),
    ],
    "boat-001": [
        ("Best boAt ANC earbuds", "27dB ANC is effective for commuting. 50H playtime is remarkable.", 4.5),
        ("Great upgrade to Airdopes 141", "ANC makes a huge difference in noisy environments. Good value.", 4.0),
    ],
    "boat-002": [
        ("Best budget ANC earbuds in India", "ANC for under 2500 is mind-blowing. Works great in metro trains.", 4.5),
        ("Impressive ANC performance", "ENx quad mics make calls crystal clear. Beast Mode is noticeably faster.", 4.0),
    ],
    "boat-003": [
        ("Great budget earbuds", "40H playtime is hard to believe at this price. ENx for clear calls.", 4.0),
        ("Best boAt earbuds under 1500", "Comfortable fit, good bass, reliable connection. Daily driver.", 4.0),
    ],
    "boat-004": [
        ("Best boAt over-ear ANC", "35dB ANC is effective. 80H battery means weekly charging only.", 4.5),
        ("Excellent value ANC headphone", "Padded earcups are comfortable for long sessions. ASAP Charge works.", 4.0),
    ],
    "boat-005": [
        ("Great budget ANC headphone", "ANC at this price is unreal. 80H battery with ANC is exceptional.", 4.0),
        ("Good value headphone", "Foldable design is convenient for travel. Physical noise isolation helps.", 4.0),
    ],
    "boat-006": [
        ("Most affordable TWS", "For under 1000, this delivers good sound. ENx for clear calls.", 4.0),
        ("Great starter TWS", "Lightweight and comfortable. IPX4 for gym use. Decent bass.", 4.0),
    ],
    "boat-007": [
        ("Great upgrade earbuds", "42H total battery is excellent. Beast Mode 80ms good for gaming.", 4.0),
        ("Good mid-range boAt TWS", "IWP auto-connect is convenient. ENx dual mics are clear.", 4.5),
    ],
    "boat-008": [
        ("Best ANC neckband", "ANC neckband is very comfortable for long wear. IPX7 for rain and sweat.", 4.5),
        ("Great neckband earphones", "40H battery with ANC is exceptional. ASAP Charge saves the day.", 4.0),
    ],
    "boat-009": [
        ("Comfortable over-ear headphones", "40H playtime means never carrying a charger. Sound quality is good.", 4.0),
        ("Good boAt over-ear", "Padded cushions are comfortable. Beast Mode is useful for gaming.", 4.0),
    ],
    "boat-010": [
        ("Great portable speaker", "10W stereo fills a room. IPX5 means no worry outdoors. Party mode is fun.", 4.5),
        ("Best boAt speaker under 1500", "360-degree sound is excellent. USB-C charging is convenient.", 4.0),
    ],
    "boat-011": [
        ("Best boAt ANC upgrade", "50H total with ANC is incredible. Bluetooth 5.3 is faster and stable.", 4.5),
        ("Premium boAt earbuds", "Quad ENx mics make office calls clear. Beast Mode 60ms for gaming.", 4.0),
    ],
}


def load():
    with get_conn() as conn:
        with conn.cursor() as cur:
            p_in, p_skip = 0, 0
            for row in PRODUCTS:
                (pid, name, cat, brand, price, orig, disc,
                 rating, rating_count, desc) = row
                try:
                    cur.execute(
                        """INSERT INTO products
                               (product_id, name, category, brand, price,
                                original_price, discount_pct, rating,
                                rating_count, description, availability)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (product_id) DO NOTHING""",
                        [pid, name, cat, brand, price, orig, disc,
                         rating, rating_count, desc, True],
                    )
                    if cur.rowcount: p_in += 1
                    else: p_skip += 1
                except Exception as e:
                    print(f"  Product error [{pid}]: {e}")

            r_in, r_skip = 0, 0
            for pid, review_list in REVIEWS.items():
                for title, text, rat in review_list:
                    rid = str(uuid.uuid4())
                    try:
                        cur.execute(
                            """INSERT INTO reviews
                                   (review_id, product_id, customer_name,
                                    rating, review_title, review_text)
                               VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (review_id) DO NOTHING""",
                            [rid, pid, "Verified Buyer", rat, title, text],
                        )
                        if cur.rowcount: r_in += 1
                        else: r_skip += 1
                    except Exception as e:
                        print(f"  Review error [{pid}]: {e}")

    print(f"Products  — inserted: {p_in}, already existed: {p_skip}")
    print(f"Reviews   — inserted: {r_in}, already existed: {r_skip}")


def verify():
    with get_conn() as conn:
        with conn.cursor() as cur:
            brands = ['Apple','Samsung','Sony','HP','Dell','Lenovo','OnePlus','boAt']
            print("\nBrand breakdown after seed:")
            for b in brands:
                cur.execute("SELECT COUNT(*) FROM products WHERE brand ILIKE %s", [b])
                print(f"  {b:<10} {cur.fetchone()[0]} products")


if __name__ == "__main__":
    print("Seeding brand-specific products...")
    load()
    verify()
    print("\nDone.")
