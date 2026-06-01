"""
Seed script — popular products across Electronics, Computers & Accessories,
and Home & Kitchen in all price ranges (budget → ultra-premium).
Run: python tools/seed_popular_products_v2.py
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

# (product_id, name, category, brand, price, original_price, discount_pct, rating, rating_count, description)
PRODUCTS = [

    # ══════════════════════════════════════════════════════════
    # ELECTRONICS — HEADPHONES & EARBUDS (all price ranges)
    # ══════════════════════════════════════════════════════════
    ("hd-bud-001", "Portronics Harmonics Z1 Wireless Earbuds 20H Battery",
     "Electronics", "Portronics", 399, 999, "60%", 3.9, "12,400",
     "TWS earbuds, 20H total playtime, BT 5.0, touch controls, IPX4. Best under ₹400."),

    ("hd-bud-002", "Noise Shots X5 Pro TWS Earbuds Quad Mic ENC",
     "Electronics", "Noise", 599, 1499, "60%", 4.0, "8,200",
     "Quad-mic ENC, 40H playtime, BT 5.3, IPX5, fast charge. Great budget TWS."),

    ("hd-bud-003", "boAt Airdopes 131 True Wireless Earbuds 8mm Drivers",
     "Electronics", "boAt", 999, 2990, "67%", 4.1, "45,000",
     "8mm drivers, 3.5H playback, BT 5.0, lightweight 4g each bud, IPX4."),

    ("hd-bud-004", "realme Buds T100 True Wireless Earbuds 28H Battery",
     "Electronics", "realme", 799, 1999, "60%", 4.0, "22,000",
     "AI ENC, 28H battery, BT 5.3, AI-powered noise cancellation, IPX4."),

    ("hd-neck-001", "Noise Tune Elite Wireless Neckband 60H Battery",
     "Electronics", "Noise", 499, 1299, "62%", 4.0, "18,500",
     "60H playtime, BT 5.0, magnetic earbuds, fast charge 10min=10H. Best neckband under ₹500."),

    ("hd-neck-002", "Boult Audio Bassbuds X1 Neckband Earphone 50H Battery",
     "Electronics", "Boult", 399, 999, "60%", 3.8, "9,800",
     "50H battery, BT 5.0, IPX5, 10mm drivers, magnetic earbuds."),

    ("hd-over-001", "Zebronics Zeb-Thunder Wireless Over Ear Headphone",
     "Electronics", "Zebronics", 499, 1299, "62%", 3.7, "14,200",
     "40H battery, BT 5.0, foldable design, FM radio, SD card slot."),

    ("hd-over-002", "Philips Audio TAH4205BK Over Ear Wireless Headphones",
     "Electronics", "Philips", 999, 2499, "60%", 4.1, "7,600",
     "29H playtime, 32mm drivers, BT 5.0, padded cushions, foldable."),

    ("hd-anc-001", "Jabra Evolve2 55 UC Wireless Headset ANC",
     "Electronics", "Jabra", 24999, 32000, "22%", 4.6, "3,200",
     "Advanced ANC, 36H battery, professional mic, multipoint, USB-A dongle."),

    ("hd-anc-002", "Bose QuietComfort 45 Wireless Noise Cancelling Headphones",
     "Electronics", "Bose", 29900, 35000, "15%", 4.7, "8,900",
     "World-class ANC, 24H battery, Aware mode, USB-C, foldable, 3 mic system."),

    ("hd-anc-003", "JBL Tune 770NC Adaptive Noise Cancelling Headphones",
     "Electronics", "JBL", 7999, 12999, "38%", 4.4, "5,600",
     "Adaptive ANC, 70H battery, multipoint, hands-free calls, fast charge."),

    ("hd-anc-004", "Sennheiser Momentum 4 Wireless ANC Headphones",
     "Electronics", "Sennheiser", 26990, 32990, "18%", 4.7, "2,100",
     "60H battery, adaptive ANC, Sennheiser sound signature, USB-C, premium build."),

    # ══════════════════════════════════════════════════════════
    # ELECTRONICS — SMART SPEAKERS & SOUNDBARS
    # ══════════════════════════════════════════════════════════
    ("spk-001", "Amazon Echo Pop Compact Smart Speaker Alexa",
     "Electronics", "Amazon", 2999, 4999, "40%", 4.4, "32,000",
     "Compact design, Alexa built-in, 2-inch driver, multi-room audio, smart home hub."),

    ("spk-002", "boAt Stone 200 5W Bluetooth Speaker IPX5",
     "Electronics", "boAt", 799, 1999, "60%", 4.0, "28,500",
     "5W, IPX5, BT 5.0, 8H battery, FM radio, micro SD, AUX in."),

    ("spk-003", "JBL Flip 6 Waterproof Portable Speaker 12H",
     "Electronics", "JBL", 9999, 14999, "33%", 4.7, "15,200",
     "IP67 waterproof, 12H battery, JBL Pro Sound, PartyBoost, USB-C."),

    ("spk-004", "Portronics Breeze 8 Wireless Speaker 10W",
     "Electronics", "Portronics", 599, 1499, "60%", 3.8, "6,700",
     "10W stereo, BT 5.0, 5H playtime, USB/AUX/FM, lightweight 350g."),

    ("spk-sb-001", "boAt Aavante Bar 1700D 120W Dolby Soundbar",
     "Electronics", "boAt", 7999, 14999, "47%", 4.3, "9,800",
     "120W Dolby Audio, 2.1ch, sub-woofer, BT 5.0, HDMI ARC, optical in."),

    ("spk-sb-002", "Sony HT-S40R 5.1ch Real Surround Sound Soundbar",
     "Electronics", "Sony", 18990, 24990, "24%", 4.5, "4,200",
     "600W total, 5.1ch, wireless rear speakers, BT, optical, HDMI ARC."),

    # ══════════════════════════════════════════════════════════
    # ELECTRONICS — SMART TVs
    # ══════════════════════════════════════════════════════════
    ("tv-001", "Redmi 32 inch HD Ready Smart TV 2023",
     "Electronics", "Redmi", 11999, 16999, "29%", 4.2, "45,000",
     "HD Ready, Android TV, 20W, Google Assistant, 3 HDMI, Chromecast built-in."),

    ("tv-002", "Samsung 43 inch Crystal 4K UHD Smart TV",
     "Electronics", "Samsung", 32990, 44990, "27%", 4.4, "22,000",
     "Crystal 4K, PurColor, Motion Xcelerator, OTS Lite, Tizen OS, AirPlay 2."),

    ("tv-003", "LG 55 inch OLED C3 4K Smart TV",
     "Electronics", "LG", 129990, 164990, "21%", 4.8, "8,500",
     "OLED evo, 4K 120Hz, Dolby Vision IQ, G-Sync, webOS23, 4 HDMI 2.1."),

    ("tv-004", "TCL 50 inch 4K QLED Android TV C635",
     "Electronics", "TCL", 37990, 54990, "31%", 4.3, "12,400",
     "QLED, 4K, AiPQ Engine, Dolby Vision, Dolby Atmos, Google TV, BT remote."),

    ("tv-005", "VU 32 inch HD Smart TV GloLED Series",
     "Electronics", "VU", 8999, 14999, "40%", 4.0, "18,900",
     "HD Ready, ActiVoice Remote, 24W, 3 HDMI, 2 USB, Android TV."),

    # ══════════════════════════════════════════════════════════
    # ELECTRONICS — CAMERAS
    # ══════════════════════════════════════════════════════════
    ("cam-001", "Canon EOS 1500D 24.1MP Digital SLR Camera",
     "Electronics", "Canon", 29990, 39990, "25%", 4.5, "9,800",
     "24.1MP APS-C, DIGIC 4+, Full HD, Wi-Fi, 9-point AF, 500-shot battery."),

    ("cam-002", "Sony ZV-E10 Mirrorless Camera for Content Creators",
     "Electronics", "Sony", 59990, 74990, "20%", 4.6, "5,600",
     "24.2MP APS-C, 4K video, real-time tracking AF, directional mic, vlog-ready."),

    ("cam-003", "GoPro HERO12 Black Action Camera 5.3K",
     "Electronics", "GoPro", 37990, 44990, "16%", 4.5, "4,200",
     "5.3K60, HyperSmooth 6.0, waterproof 10m, HDR, voice control, live streaming."),

    # ══════════════════════════════════════════════════════════
    # COMPUTERS — KEYBOARDS (all price ranges)
    # ══════════════════════════════════════════════════════════
    ("kb-001", "Zebronics Zeb-K16 USB Keyboard Slim",
     "Computers&Accessories", "Zebronics", 199, 499, "60%", 3.6, "28,900",
     "USB wired, slim design, 104 keys, plug and play, 1.5m cable."),

    ("kb-002", "Portronics Hydra 10 Wireless Keyboard Mouse Combo",
     "Computers&Accessories", "Portronics", 799, 1999, "60%", 4.0, "14,200",
     "2.4GHz wireless combo, 1600 DPI mouse, 12 months battery, compact 78 keys."),

    ("kb-003", "Logitech MK275 Wireless Keyboard Mouse Combo",
     "Computers&Accessories", "Logitech", 1795, 2495, "28%", 4.3, "42,000",
     "Spill-resistant keyboard, 1000 DPI optical mouse, 2.4 GHz, 24M keystrokes."),

    ("kb-004", "Keychron K2 Wireless Mechanical Keyboard",
     "Computers&Accessories", "Keychron", 7299, 8999, "19%", 4.6, "8,200",
     "Red/Blue/Brown switches, BT 5.1, hot-swappable, RGB, 75% layout, Mac/Win."),

    ("kb-005", "HyperX Alloy Origins Core TKL Mechanical Keyboard",
     "Computers&Accessories", "HyperX", 6999, 9999, "30%", 4.5, "5,400",
     "Red linear switches, TKL layout, RGB per-key, aircraft-grade aluminum frame."),

    ("kb-006", "Logitech MX Keys Advanced Wireless Keyboard",
     "Computers&Accessories", "Logitech", 9995, 12995, "23%", 4.6, "12,800",
     "Multi-device, backlit, 10-day battery, Easy Switch, USB-C, Flow cross-computer."),

    # ══════════════════════════════════════════════════════════
    # COMPUTERS — MICE
    # ══════════════════════════════════════════════════════════
    ("ms-001", "Zebronics Zeb-Comfort Wired Optical Mouse",
     "Computers&Accessories", "Zebronics", 149, 299, "50%", 3.5, "35,000",
     "USB wired, 1000 DPI, 3 buttons, plug-and-play, 1.5m braided cable."),

    ("ms-002", "Logitech B170 Wireless Mouse",
     "Computers&Accessories", "Logitech", 495, 799, "38%", 4.1, "98,000",
     "2.4GHz wireless, nano receiver, 12-month battery, 1000 DPI, 3-year durability."),

    ("ms-003", "Logitech G102 Lightsync Gaming Mouse 8000 DPI",
     "Computers&Accessories", "Logitech", 1495, 2495, "40%", 4.5, "55,000",
     "8000 DPI, 6 buttons, RGB, 200 IPS, 16.8M color, 85g lightweight."),

    ("ms-004", "Razer DeathAdder V3 Ergonomic Gaming Mouse",
     "Computers&Accessories", "Razer", 5999, 8999, "33%", 4.6, "8,900",
     "Focus Pro 30K sensor, 90H battery, 59g ultralight, 6 programmable buttons, HyperSpeed."),

    ("ms-005", "Logitech MX Master 3S Performance Wireless Mouse",
     "Computers&Accessories", "Logitech", 9995, 12995, "23%", 4.7, "18,400",
     "8K DPI, MagSpeed scroll, multi-device, USB-C, 70-day battery, quiet clicks."),

    # ══════════════════════════════════════════════════════════
    # COMPUTERS — MONITORS
    # ══════════════════════════════════════════════════════════
    ("mon-b-001", "Zebronics ZEB-A22FHD LED Monitor 21.5 inch FHD",
     "Computers&Accessories", "Zebronics", 5999, 8999, "33%", 3.8, "12,400",
     "21.5-inch FHD, 60Hz, HDMI+VGA, slim bezel, wall mountable, 250 nits."),

    ("mon-b-002", "AOC 22B2HM 21.5-inch FHD VA Monitor 75Hz",
     "Computers&Accessories", "AOC", 7999, 11999, "33%", 4.2, "9,600",
     "FHD VA panel, 75Hz, 4ms, FlickerFree, Low Blue Light, HDMI+VGA."),

    ("mon-m-001", "LG 27MP400-B 27-inch FHD IPS Monitor 75Hz",
     "Computers&Accessories", "LG", 14999, 19999, "25%", 4.4, "14,200",
     "27-inch IPS, FHD, 75Hz, AMD FreeSync, HDMI, sRGB 99%, HDR10, slim bezel."),

    ("mon-m-002", "Dell S2421HN 24-inch FHD IPS Monitor 75Hz",
     "Computers&Accessories", "Dell", 13999, 18499, "24%", 4.4, "11,800",
     "23.8-inch IPS, FHD, 75Hz, 2x HDMI, thin bezel, AMD FreeSync, TUV eye care."),

    ("mon-g-001", "Samsung Odyssey G5 27-inch WQHD 165Hz Curved",
     "Computers&Accessories", "Samsung", 24999, 34999, "29%", 4.5, "8,700",
     "WQHD 1440p, 165Hz, 1ms, 1000R curve, AMD FreeSync Premium, HDR10."),

    ("mon-g-002", "LG 27GN800-B UltraGear 27-inch WQHD 144Hz IPS",
     "Computers&Accessories", "LG", 27999, 36999, "24%", 4.6, "6,200",
     "WQHD, 144Hz, 1ms GtG, NVIDIA G-Sync, sRGB 99%, 2xHDMI, DP, USB hub."),

    # ══════════════════════════════════════════════════════════
    # COMPUTERS — SSDs & STORAGE
    # ══════════════════════════════════════════════════════════
    ("ssd-001", "WD Green 240GB 2.5-inch SATA SSD",
     "Computers&Accessories", "Western Digital", 1699, 2499, "32%", 4.4, "32,000",
     "240GB, 545MB/s read, SATA III, 3yr warranty, 80TBW, 7mm ultra-slim."),

    ("ssd-002", "Samsung 870 EVO 500GB 2.5-inch SATA SSD",
     "Computers&Accessories", "Samsung", 4499, 5999, "25%", 4.7, "28,400",
     "500GB, 560MB/s read, 530MB/s write, MKX controller, 5yr warranty, 300TBW."),

    ("ssd-003", "Samsung 980 Pro NVMe M.2 1TB PCIe 4.0 SSD",
     "Computers&Accessories", "Samsung", 8999, 13999, "36%", 4.8, "18,200",
     "1TB, 7000MB/s read, PCIe 4.0, PS5 compatible, heat spreader, 5yr warranty."),

    ("ssd-004", "Kingston A400 480GB SATA SSD",
     "Computers&Accessories", "Kingston", 2499, 3499, "29%", 4.4, "45,000",
     "480GB, 500MB/s read, 450MB/s write, 3yr warranty, reliable entry-level SSD."),

    ("ssd-005", "Seagate BarraCuda 1TB Internal HDD 7200RPM",
     "Computers&Accessories", "Seagate", 2999, 3999, "25%", 4.3, "38,000",
     "1TB, 7200RPM, 210MB/s, 2yr warranty. Best budget internal storage."),

    # ══════════════════════════════════════════════════════════
    # COMPUTERS — LAPTOPS (budget range)
    # ══════════════════════════════════════════════════════════
    ("lap-bud-001", "HP 15s Intel Celeron N4500 4GB RAM 256GB SSD",
     "Computers&Accessories", "HP", 25990, 32990, "21%", 3.8, "8,400",
     "15.6-inch HD, Windows 11 S, Intel UHD, 1yr warranty. Basic daily use laptop."),

    ("lap-bud-002", "Acer Aspire Lite AMD Ryzen 3 5300U 8GB 256GB SSD",
     "Computers&Accessories", "Acer", 29999, 38999, "23%", 4.1, "6,800",
     "15.6-inch FHD IPS, Ryzen 3, Radeon, fast charge, thin 18mm, 1yr warranty."),

    # ══════════════════════════════════════════════════════════
    # COMPUTERS — WEBCAMS & ACCESSORIES
    # ══════════════════════════════════════════════════════════
    ("wc-001", "Zebronics Zeb-Crystal Pro Full HD Webcam",
     "Computers&Accessories", "Zebronics", 799, 1999, "60%", 3.7, "9,800",
     "Full HD 1080p, built-in mic, auto light correction, USB plug-play, 90° FOV."),

    ("wc-002", "Logitech C920s HD Pro Webcam 1080p 30fps",
     "Computers&Accessories", "Logitech", 5995, 7995, "25%", 4.5, "22,000",
     "1080p/30fps, stereo mics, privacy shutter, auto light correction, Works with Teams."),

    ("hub-001", "AmazonBasics USB 3.0 4-Port Hub",
     "Computers&Accessories", "Amazon", 499, 999, "50%", 4.2, "45,000",
     "4 USB 3.0 ports, 5Gbps, SuperSpeed, bus-powered, plug-and-play, LED indicator."),

    ("hub-002", "Portronics Mport 13 USB C Hub 7-in-1",
     "Computers&Accessories", "Portronics", 1299, 2999, "57%", 4.1, "12,400",
     "7-in-1 USB-C hub, HDMI 4K, 100W PD, 3xUSB 3.0, SD+TF card, compact."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — AIR FRYERS
    # ══════════════════════════════════════════════════════════
    ("af-001", "INALSA Air Fryer Tasty Fry 1400W 4.2L",
     "Home&Kitchen", "INALSA", 2499, 4999, "50%", 4.0, "18,200",
     "4.2L, 1400W, 80-200°C, 30min timer, non-stick basket, 7 preset programs."),

    ("af-002", "Philips Air Fryer HD9200 1400W 4.1L NA",
     "Home&Kitchen", "Philips", 5995, 8995, "33%", 4.4, "28,500",
     "4.1L, 1400W, Rapid Air technology, 13-in-1 functions, recipe app, easy clean."),

    ("af-003", "Cosori Pro Air Fryer 5.5L 1700W Dual Blaze",
     "Home&Kitchen", "Cosori", 7999, 10999, "27%", 4.5, "9,800",
     "5.5L, 12 one-touch functions, shake reminder, 360° hot air, BPA-free."),

    ("af-004", "Instant Vortex 4-in-1 Air Fryer 5.7L 1500W",
     "Home&Kitchen", "Instant", 5499, 7999, "31%", 4.3, "14,200",
     "5.7L, air fry/bake/roast/reheat, EvenCrisp technology, touch display."),

    ("af-005", "AGARO Regency Air Fryer 12L Oven 1800W",
     "Home&Kitchen", "AGARO", 6999, 9999, "30%", 4.2, "11,600",
     "12L large capacity, 8 cooking functions, rotisserie, dehydrator, 1800W."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — MIXER GRINDERS
    # ══════════════════════════════════════════════════════════
    ("mx-001", "Bajaj GX 3 500W Mixer Grinder 3 Jars",
     "Home&Kitchen", "Bajaj", 1299, 2199, "41%", 3.9, "22,000",
     "500W, 3 stainless steel jars, 3 speed + pulse, anti-rust blades, 2yr warranty."),

    ("mx-002", "Philips HL7756 750W Mixer Grinder 3 Jars",
     "Home&Kitchen", "Philips", 2495, 3995, "38%", 4.2, "38,500",
     "750W, 3 jars, turbo speed, 5yr motor warranty, anti-overflow lid, smart lock."),

    ("mx-003", "Sujata Dynamix DX 900W Mixer Grinder",
     "Home&Kitchen", "Sujata", 3599, 4999, "28%", 4.5, "28,200",
     "900W industrial motor, wet/dry/chutney jars, 5yr warranty, 18000 RPM."),

    ("mx-004", "Bosch TrueMixx Pro 1000W Mixer Grinder",
     "Home&Kitchen", "Bosch", 5999, 7999, "25%", 4.6, "12,400",
     "1000W, 3 jars, EasyStart, MotorProtect, OptiFlow, 5yr warranty, 5 speeds."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — PRESSURE COOKERS & INSTANT POTS
    # ══════════════════════════════════════════════════════════
    ("pc-001", "Prestige Popular Aluminium Pressure Cooker 3L",
     "Home&Kitchen", "Prestige", 599, 999, "40%", 4.3, "32,000",
     "3L aluminium, ISI certified, gasket release, hard anodised, induction compatible."),

    ("pc-002", "Hawkins Contura Aluminium Pressure Cooker 3L",
     "Home&Kitchen", "Hawkins", 999, 1499, "33%", 4.5, "28,000",
     "3L, contoured body, ergonomic handle, safety valve, 5yr guarantee."),

    ("pc-003", "Instant Pot Duo 7-in-1 Electric Pressure Cooker 5.7L",
     "Home&Kitchen", "Instant", 6995, 9995, "30%", 4.6, "18,500",
     "5.7L, 7 functions: pressure cook/slow cook/rice/sauté/steam/warm/yogurt, 13 programs."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — MICROWAVES
    # ══════════════════════════════════════════════════════════
    ("mw-001", "Samsung 23L Solo Microwave Oven MS23K3513AK",
     "Home&Kitchen", "Samsung", 7490, 9990, "25%", 4.3, "22,000",
     "23L solo, 800W, ceramic enamel interior, anti-bacterial, 6 auto programs."),

    ("mw-002", "LG 28L Convection Microwave Oven MC2886BFUM",
     "Home&Kitchen", "LG", 14990, 19990, "25%", 4.5, "14,800",
     "28L convection, 900W, diet fry, intellowave, charcoal lighting, auto cook menu."),

    ("mw-003", "IFB 20L Solo Microwave 20PM MEC2B",
     "Home&Kitchen", "IFB", 5490, 7490, "27%", 4.2, "18,400",
     "20L, 800W, membrane keypad, multi-stage cooking, 51 auto-cook menu, child lock."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — WATER PURIFIERS
    # ══════════════════════════════════════════════════════════
    ("wp-001", "HUL Pureit Classic G2 Mineral RO+UV Water Purifier",
     "Home&Kitchen", "HUL Pureit", 7999, 11999, "33%", 4.2, "18,200",
     "RO+UV, 7-stage purification, 10L storage, auto shut-off, TDS controller."),

    ("wp-002", "Kent Grand Plus 8L RO+UV+UF+TDS Water Purifier",
     "Home&Kitchen", "Kent", 14999, 19999, "25%", 4.4, "22,400",
     "8L tank, multiple purification, mineral RO, zero water wastage, UV LED."),

    ("wp-003", "AO Smith Z8 10L UV+UF Wall Mounted Water Purifier",
     "Home&Kitchen", "AO Smith", 5999, 8999, "33%", 4.3, "9,800",
     "10L, UV+UF (no RO needed for low TDS), 8-stage, Biotron+, IDEM tech."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — BLENDERS & JUICERS
    # ══════════════════════════════════════════════════════════
    ("bl-001", "Nutribullet Pro 900W Personal Blender",
     "Home&Kitchen", "Nutribullet", 3999, 6999, "43%", 4.4, "12,800",
     "900W, 24oz cup, cyclonic action, high-torque blade, BPA-free, dishwasher safe."),

    ("bl-002", "Prestige Iris 550W Hand Blender",
     "Home&Kitchen", "Prestige", 799, 1499, "47%", 4.0, "14,500",
     "550W, 2-speed, stainless steel blade, detachable shaft, easy clean."),

    ("jc-001", "Philips Viva Collection HR1855 Juicer 500W",
     "Home&Kitchen", "Philips", 3495, 4995, "30%", 4.3, "9,800",
     "500W, 2-speed + pulse, 700ml jar, adjustable pulp control, anti-drip, 1yr warranty."),

    # ══════════════════════════════════════════════════════════
    # HOME & KITCHEN — COFFEE MAKERS
    # ══════════════════════════════════════════════════════════
    ("cf-001", "Morphy Richards New Europa 600W Coffee Maker",
     "Home&Kitchen", "Morphy Richards", 1499, 2499, "40%", 4.0, "18,200",
     "600W, 6-cup capacity, glass carafe, keep-warm plate, anti-drip, pause-n-pour."),

    ("cf-002", "De'Longhi Dedica Arte EC885 Espresso Machine",
     "Home&Kitchen", "DeLonghi", 21990, 28990, "24%", 4.5, "4,200",
     "15-bar pump, thermoblock, adjustable milk frother, 4 coffee types, 1.1L tank."),

    ("cf-003", "Nescafe Dolce Gusto Genio S Pod Coffee Machine",
     "Home&Kitchen", "Nescafe", 5990, 8990, "33%", 4.3, "8,400",
     "15-bar, 1500ml tank, hot/cold, capsule system, compact, 30s heat-up."),

]


def load():
    with get_conn() as conn:
        with conn.cursor() as cur:
            p_in, p_skip = 0, 0
            for row in PRODUCTS:
                (pid, name, cat, brand, price, orig, disc, rating, rcount, desc) = row
                try:
                    cur.execute("""
                        INSERT INTO products
                            (product_id, name, category, brand, price,
                             original_price, discount_pct, rating,
                             rating_count, description, availability)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (product_id) DO NOTHING
                    """, [pid, name, cat, brand, price, orig, disc,
                          rating, rcount, desc, True])
                    if cur.rowcount:
                        p_in += 1
                    else:
                        p_skip += 1
                except Exception as e:
                    print(f"  Error [{pid}]: {e}")

    print(f"Products — inserted: {p_in}, skipped (already exist): {p_skip}")


def verify():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT category, COUNT(*), MIN(price), MAX(price) FROM products GROUP BY category ORDER BY category")
            print("\nCategory breakdown:")
            for row in cur.fetchall():
                print(f"  {row[0]:<30} {row[1]:>4} products  ₹{row[2]:.0f}–₹{row[3]:.0f}")
            cur.execute("SELECT COUNT(*) FROM products WHERE price < 1000")
            print(f"\n  Under ₹1000: {cur.fetchone()[0]} products")
            cur.execute("SELECT COUNT(*) FROM products WHERE price BETWEEN 1000 AND 5000")
            print(f"  ₹1000–₹5000: {cur.fetchone()[0]} products")
            cur.execute("SELECT COUNT(*) FROM products WHERE price > 5000")
            print(f"  Above ₹5000: {cur.fetchone()[0]} products")


if __name__ == "__main__":
    print("Seeding popular products v2...")
    load()
    verify()
    print("\nDone.")
