"""Seed famous electronics, computers, and kitchen appliances into products table."""
import sys
import os
import psycopg2

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
    # ── LAPTOPS ────────────────────────────────────────────────────────────────
    ("LT001", "Apple MacBook Air M2 (2023) 13-inch Laptop", "Computers&Accessories|Laptops", "Apple", 114900, 119900, "4%", 4.8, "15,320", "Apple M2 chip, 8GB RAM, 256GB SSD, 18hr battery, Liquid Retina display, MagSafe charging"),
    ("LT002", "Dell XPS 15 (2023) Intel Core i7 Laptop", "Computers&Accessories|Laptops", "Dell", 149990, 179990, "17%", 4.6, "4,210", "Intel Core i7-13700H, 16GB RAM, 512GB SSD, 15.6 OLED display, NVIDIA GeForce RTX 4060"),
    ("LT003", "HP Pavilion 15 Intel Core i5 Laptop", "Computers&Accessories|Laptops", "HP", 54990, 69990, "21%", 4.4, "22,140", "Intel Core i5-1235U, 16GB RAM, 512GB SSD, 15.6 FHD IPS display, Windows 11"),
    ("LT004", "Lenovo IdeaPad Slim 5 AMD Ryzen 5 Laptop", "Computers&Accessories|Laptops", "Lenovo", 52990, 64990, "18%", 4.5, "18,760", "AMD Ryzen 5 7530U, 16GB RAM, 512GB SSD, 15.6 FHD display, 10hr battery"),
    ("LT005", "ASUS VivoBook 16X OLED Laptop", "Computers&Accessories|Laptops", "ASUS", 79990, 99990, "20%", 4.6, "8,430", "Intel Core i7-12700H, 16GB RAM, 512GB SSD, 16 inch 2.8K OLED display, NVIDIA RTX 3050"),
    ("LT006", "Apple MacBook Pro M3 Pro 14-inch Laptop", "Computers&Accessories|Laptops", "Apple", 199900, 219900, "9%", 4.9, "6,540", "Apple M3 Pro chip, 18GB unified memory, 512GB SSD, Liquid Retina XDR, 22hr battery"),
    ("LT007", "Acer Aspire Lite AMD Ryzen 3 Thin & Light Laptop", "Computers&Accessories|Laptops", "Acer", 34990, 44990, "22%", 4.2, "31,200", "AMD Ryzen 3 7320U, 8GB RAM, 512GB SSD, 15.6 FHD display, Windows 11 Home"),
    ("LT008", "MSI Cyborg 15 Gaming Laptop", "Computers&Accessories|Laptops", "MSI", 74990, 89990, "17%", 4.5, "5,670", "Intel Core i5-12450H, 16GB RAM, 512GB SSD, RTX 4060, 144Hz FHD display, per-key RGB"),
    ("LT009", "Samsung Galaxy Book4 Pro 360 Laptop", "Computers&Accessories|Laptops", "Samsung", 139990, 164990, "15%", 4.6, "3,120", "Intel Core Ultra 7, 16GB RAM, 512GB SSD, 16 inch 3K AMOLED touchscreen, S Pen included"),
    ("LT010", "Lenovo ThinkPad E14 Gen 5 Business Laptop", "Computers&Accessories|Laptops", "Lenovo", 67990, 84990, "20%", 4.5, "7,890", "Intel Core i5-1335U, 16GB RAM, 512GB SSD, 14 inch FHD IPS, fingerprint reader, Rapid Charge"),

    # ── SMARTPHONES ────────────────────────────────────────────────────────────
    ("SP001", "Apple iPhone 15 Pro Max 256GB", "Electronics|Smartphones", "Apple", 134900, 159900, "16%", 4.8, "28,450", "A17 Pro chip, 48MP camera system, titanium design, USB-C, Action Button, 4K ProRes video"),
    ("SP002", "Samsung Galaxy S24 Ultra 256GB", "Electronics|Smartphones", "Samsung", 129999, 154999, "16%", 4.7, "19,870", "200MP camera, Snapdragon 8 Gen 3, S Pen, 6.8 QHD+ display, 5000mAh battery"),
    ("SP003", "OnePlus 12 256GB", "Electronics|Smartphones", "OnePlus", 64999, 74999, "13%", 4.6, "14,320", "Snapdragon 8 Gen 3, 50MP Hasselblad camera, 100W SUPERVOOC, 5400mAh, 120Hz LTPO AMOLED"),
    ("SP004", "Google Pixel 8 Pro 256GB", "Electronics|Smartphones", "Google", 106999, 119999, "11%", 4.6, "8,760", "Google Tensor G3, 50MP camera with AI features, 120Hz LTPO display, 7yrs OS updates"),
    ("SP005", "Xiaomi 14 Ultra 512GB", "Electronics|Smartphones", "Xiaomi", 99999, 114999, "13%", 4.5, "6,230", "Snapdragon 8 Gen 3, Leica 1-inch main camera, 90W wired + 80W wireless charging"),
    ("SP006", "Samsung Galaxy A55 5G 256GB", "Electronics|Smartphones", "Samsung", 34999, 42999, "19%", 4.5, "42,100", "Exynos 1480, 50MP OIS camera, 120Hz Super AMOLED, IP67, 5000mAh, 25W fast charging"),
    ("SP007", "Apple iPhone 15 128GB", "Electronics|Smartphones", "Apple", 69900, 79900, "13%", 4.7, "35,670", "A16 Bionic, 48MP camera, Dynamic Island, USB-C, Emergency SOS via satellite"),
    ("SP008", "Realme GT 6 256GB", "Electronics|Smartphones", "Realme", 39999, 47999, "17%", 4.4, "11,450", "Snapdragon 8s Gen 3, 120Hz AMOLED, 120W SuperVOOC, Sony LYT-808 sensor"),

    # ── TABLETS ────────────────────────────────────────────────────────────────
    ("TB001", "Apple iPad Pro M4 11-inch WiFi 256GB", "Electronics|Tablets", "Apple", 99900, 114900, "13%", 4.8, "9,870", "Apple M4 chip, Ultra Retina XDR OLED, Apple Pencil Pro compatible, thinnest Apple product ever"),
    ("TB002", "Samsung Galaxy Tab S9 FE WiFi 128GB", "Electronics|Tablets", "Samsung", 36999, 48999, "24%", 4.5, "14,320", "Exynos 1380, 10.9 inch TFT display, S Pen included, 8000mAh, IP68, DeX support"),
    ("TB003", "Apple iPad Air M2 11-inch WiFi 128GB", "Electronics|Tablets", "Apple", 59900, 66900, "10%", 4.7, "12,100", "Apple M2 chip, Liquid Retina display, 10hr battery, USB-C, Apple Pencil compatible"),
    ("TB004", "Lenovo Tab P12 Pro WiFi 256GB", "Electronics|Tablets", "Lenovo", 54999, 69999, "21%", 4.4, "3,450", "Snapdragon 870, 12.6 inch AMOLED, 10200mAh, quad speakers, stylus included"),

    # ── SMART TVs ──────────────────────────────────────────────────────────────
    ("TV001", "Samsung 55-inch 4K Neo QLED Smart TV", "Electronics|Televisions", "Samsung", 89990, 129990, "31%", 4.7, "8,760", "Neo QLED 4K, Quantum HDR 32x, Object Tracking Sound, 120Hz, Gaming Hub, Tizen OS"),
    ("TV002", "LG 55-inch OLED C3 4K Smart TV", "Electronics|Televisions", "LG", 139990, 179990, "22%", 4.8, "6,540", "OLED evo panel, Dolby Vision IQ, 120Hz, G-Sync & FreeSync, webOS 23, ThinQ AI"),
    ("TV003", "Sony Bravia 55-inch 4K OLED XR TV", "Electronics|Televisions", "Sony", 149990, 184990, "19%", 4.7, "5,210", "XR OLED panel, Cognitive Processor XR, Dolby Atmos, HDMI 2.1, Google TV"),
    ("TV004", "Mi 55-inch 4K Ultra HD Smart TV X Series", "Electronics|Televisions", "Xiaomi", 43999, 59999, "27%", 4.4, "18,900", "4K UHD, Dolby Vision, Dolby Atmos, 30W speakers, PatchWall, Android TV"),
    ("TV005", "OnePlus 65-inch Y1S Pro 4K Smart TV", "Electronics|Televisions", "OnePlus", 54999, 74999, "27%", 4.5, "11,230", "4K QLED, 30W audio, Gamma Engine, Android TV 11, Bluetooth 5.0, 4 HDMI ports"),

    # ── CAMERAS ────────────────────────────────────────────────────────────────
    ("CM001", "Sony Alpha ZV-E10 Mirrorless Camera with 16-50mm Lens", "Electronics|Cameras", "Sony", 67990, 84990, "20%", 4.7, "5,670", "24.2MP APS-C sensor, 4K video, vlog-optimised, real-time eye AF, flip-out screen"),
    ("CM002", "Canon EOS R50 Mirrorless Camera with 18-45mm Lens", "Electronics|Cameras", "Canon", 74990, 89990, "17%", 4.6, "4,320", "24.2MP CMOS, Dual Pixel CMOS AF II, 4K video, compact lightweight design, WiFi"),
    ("CM003", "GoPro Hero 12 Black Action Camera", "Electronics|Cameras", "GoPro", 34990, 44990, "22%", 4.6, "9,870", "5.3K video, HyperSmooth 6.0, waterproof 10m, 27MP photos, night effects"),
    ("CM004", "Nikon Z30 Mirrorless Camera with 16-50mm Lens", "Electronics|Cameras", "Nikon", 66990, 79990, "16%", 4.5, "2,890", "20.9MP APS-C, 4K UHD video, horizontal flip-out display, no EVF, great for vlogging"),

    # ── WIRELESS EARBUDS ───────────────────────────────────────────────────────
    ("EB001", "Apple AirPods Pro 2nd Generation", "Electronics|Earbuds", "Apple", 24900, 29900, "17%", 4.8, "34,560", "Active noise cancellation, Adaptive Audio, Transparency mode, H2 chip, USB-C, 30hr total"),
    ("EB002", "Samsung Galaxy Buds3 Pro", "Electronics|Earbuds", "Samsung", 17999, 22999, "22%", 4.6, "8,760", "ANC, 360 Audio, blade design, IP57, 6hr playback + 18hr case, Galaxy AI features"),
    ("EB003", "Sony WF-1000XM5 True Wireless Earbuds", "Electronics|Earbuds", "Sony", 19990, 24990, "20%", 4.7, "11,450", "Industry-leading ANC, LDAC, 8hr + 24hr case, multipoint, speak-to-chat"),
    ("EB004", "boAt Airdopes 141 TWS Earbuds", "Electronics|Earbuds", "boAt", 999, 2990, "67%", 4.5, "89,450", "42hr total battery, BEAST mode gaming, ENx tech, IPX4, Bluetooth 5.1"),
    ("EB005", "Nothing Ear 2 TWS Earbuds", "Electronics|Earbuds", "Nothing", 8999, 11999, "25%", 4.5, "14,230", "Dual chamber design, ANC up to 40dB, LHDC 5.0, 6.3hr + 22.5hr, IP54"),

    # ── SMART SPEAKERS ─────────────────────────────────────────────────────────
    ("SS001", "Amazon Echo Dot 5th Gen Smart Speaker", "Electronics|Speakers", "Amazon", 4499, 5499, "18%", 4.6, "45,670", "Alexa built-in, improved bass, temperature sensor, motion detection, Eero built-in"),
    ("SS002", "Apple HomePod mini Smart Speaker", "Electronics|Speakers", "Apple", 10900, 10900, "0%", 4.7, "12,340", "360-degree audio, S5 chip, room sensing, Intercom, smart home hub, Thread support"),
    ("SS003", "JBL Flip 6 Portable Bluetooth Speaker", "Electronics|Speakers", "JBL", 7999, 11999, "33%", 4.7, "28,900", "IP67 waterproof, 12hr battery, PartyBoost, powerful JBL Original Pro Sound"),
    ("SS004", "Sony SRS-XB100 Portable Bluetooth Speaker", "Electronics|Speakers", "Sony", 3490, 4990, "30%", 4.5, "19,870", "IP67, 16hr battery, clear audio, compact design, USB-C charging, strap hole"),

    # ── MONITORS ───────────────────────────────────────────────────────────────
    ("MN001", "LG 27-inch UltraGear 4K UHD IPS Gaming Monitor", "Computers&Accessories|Monitors", "LG", 44990, 59990, "25%", 4.6, "6,780", "4K UHD, 144Hz, 1ms GTG, HDMI 2.1, G-Sync compatible, HDR600, Nano IPS"),
    ("MN002", "Samsung 27-inch Odyssey G5 Curved Gaming Monitor", "Computers&Accessories|Monitors", "Samsung", 24999, 34999, "29%", 4.5, "11,230", "1440p QHD, 165Hz, 1ms, 1000R curve, HDR10, AMD FreeSync Premium"),
    ("MN003", "Dell 27-inch S2722QC 4K USB-C Monitor", "Computers&Accessories|Monitors", "Dell", 34999, 44999, "22%", 4.6, "8,540", "4K UHD IPS, USB-C 65W charging, 3-sided bezel-less, AMD FreeSync, built-in speakers"),
    ("MN004", "BenQ PD2706UA 27-inch 4K Designer Monitor", "Computers&Accessories|Monitors", "BenQ", 54990, 69990, "21%", 4.7, "3,210", "4K IPS, USB-C 96W, Thunderbolt 3, color accuracy for design, built-in KVM switch"),

    # ── KEYBOARDS & MICE ───────────────────────────────────────────────────────
    ("KB001", "Logitech MX Keys Advanced Wireless Keyboard", "Computers&Accessories|Keyboards", "Logitech", 9495, 11995, "21%", 4.7, "14,560", "Smart illumination, multi-device, USB-C rechargeable, 10-day battery, easy-switch"),
    ("KB002", "Keychron K2 Pro Mechanical Keyboard", "Computers&Accessories|Keyboards", "Keychron", 8999, 10999, "18%", 4.6, "9,870", "QMK/VIA compatible, hot-swappable, Bluetooth 5.1 + USB-C, RGB backlight, compact 75%"),
    ("MS001", "Logitech MX Master 3S Wireless Mouse", "Computers&Accessories|Mice", "Logitech", 8995, 11495, "22%", 4.8, "18,760", "8K DPI, MagSpeed scroll, USB-C, app-specific customization, silent clicks, multi-device"),
    ("MS002", "Razer DeathAdder V3 HyperSpeed Gaming Mouse", "Computers&Accessories|Mice", "Razer", 5999, 7999, "25%", 4.6, "7,340", "Focus X 26K DPI optical sensor, 59g ultra-lightweight, 300hr battery, HyperSpeed wireless"),

    # ── STORAGE ────────────────────────────────────────────────────────────────
    ("SD001", "Samsung 990 Pro 1TB NVMe M.2 SSD", "Computers&Accessories|Storage", "Samsung", 9999, 13999, "29%", 4.8, "22,100", "Read 7450MB/s, Write 6900MB/s, PCIe 4.0, thermal control, 600TBW, 5yr warranty"),
    ("SD002", "WD Black SN850X 1TB NVMe M.2 SSD", "Computers&Accessories|Storage", "Western Digital", 8499, 11999, "29%", 4.7, "14,560", "Read 7300MB/s, PCIe Gen4, 600TBW, Xbox compatible, game mode acceleration"),
    ("SD003", "Seagate Expansion 2TB Portable External HDD", "Computers&Accessories|Storage", "Seagate", 3999, 5499, "27%", 4.5, "31,450", "USB 3.0, plug and play, compact design, compatible with PC and Mac, 3yr rescue"),
    ("SD004", "SanDisk 256GB Ultra USB 3.0 Flash Drive", "Computers&Accessories|Storage", "SanDisk", 1299, 1999, "35%", 4.6, "45,230", "Read up to 130MB/s, USB 3.0, retractable design, SecureAccess software included"),

    # ── SMART WATCHES ──────────────────────────────────────────────────────────
    ("SW001", "Apple Watch Series 9 GPS 45mm", "Electronics|Smartwatches", "Apple", 44900, 49900, "10%", 4.8, "19,870", "S9 chip, Double Tap gesture, Always-On Retina display, ECG, crash detection, carbon neutral"),
    ("SW002", "Samsung Galaxy Watch 6 Classic 47mm", "Electronics|Smartwatches", "Samsung", 34999, 41999, "17%", 4.6, "11,230", "Rotating bezel, advanced health tracking, BioActive sensor, 40hr battery, IP68"),
    ("SW003", "Garmin Fenix 7S Pro Multisport GPS Watch", "Electronics|Smartwatches", "Garmin", 84990, 99990, "15%", 4.7, "4,560", "Solar charging, up to 22 days battery, topographic maps, advanced training metrics"),
    ("SW004", "Noise ColorFit Pro 5 Smart Watch", "Electronics|Smartwatches", "Noise", 2999, 7999, "63%", 4.3, "56,780", "1.46 AMOLED, SpO2, heart rate, 7-day battery, Bluetooth calling, 100+ watch faces"),

    # ── KITCHEN APPLIANCES ─────────────────────────────────────────────────────
    ("KA001", "Philips HD9252/90 Air Fryer XXL", "Home&Kitchen|Airfryers", "Philips", 12995, 18995, "32%", 4.6, "14,320", "1.4kg capacity, Rapid Air technology, Fat Removal Technology, 7 presets, digital touchscreen"),
    ("KA002", "Instant Pot Duo 7-in-1 Electric Pressure Cooker 6L", "Home&Kitchen|Cookers", "Instant Pot", 8995, 12995, "31%", 4.7, "28,450", "Pressure cooker, slow cooker, rice cooker, steamer, sauté, yogurt maker, warmer"),
    ("KA003", "Tefal EasyFry Precision 2-in-1 Air Fryer & Grill", "Home&Kitchen|Airfryers", "Tefal", 11995, 16995, "29%", 4.5, "9,870", "4.2L + 1.2L grill, EasyClick accessories, 8 presets, 99-min timer, non-stick"),
    ("KA004", "Bajaj Majesty 1000TSS Pop-up Toaster", "Home&Kitchen|Toasters", "Bajaj", 1495, 2295, "35%", 4.5, "22,100", "2-slice, 6-stage browning, removable crumb tray, wide bread slots, auto pop-up"),
    ("KA005", "Bosch TFB4402V Sandwich Toaster", "Home&Kitchen|Toasters", "Bosch", 2495, 3495, "29%", 4.4, "8,760", "Non-stick coating, floating hinge, indicator lights, cool-touch handle, drip tray"),
    ("KA006", "Prestige Electric Kettle PKOSS 1.5L", "Home&Kitchen|Kettles", "Prestige", 799, 1499, "47%", 4.5, "34,560", "1500W, auto cut-off, 360° cordless base, concealed heating element, boil-dry protection"),
    ("KA007", "Philips HR2776/00 Hand Blender", "Home&Kitchen|Blenders", "Philips", 2495, 3495, "29%", 4.6, "19,230", "700W, 2-speed, ProMix technology, stainless steel blending shaft, dishwasher safe"),
    ("KA008", "Hamilton Beach Professional Juicer Mixer Grinder 750W", "Home&Kitchen|Mixers", "Hamilton Beach", 4995, 7495, "33%", 4.5, "11,450", "750W, 3 jars, 4 blades, anti-drip spout, overload protection, 5yr motor warranty"),
    ("KA009", "LG 28L Convection Microwave Oven MC2886BRUM", "Home&Kitchen|Microwaves", "LG", 17990, 22990, "22%", 4.6, "8,320", "Convection + grill, auto cook menu, diet fry, intellowave, charcoal light heater"),
    ("KA010", "IFB 25L Convection Microwave Oven 25SC4", "Home&Kitchen|Microwaves", "IFB", 11990, 15990, "25%", 4.5, "14,780", "Convection, 301 auto cook menus, steam clean, tact control, multi-stage cooking"),
    ("KA011", "Dyson V15 Detect Absolute Cordless Vacuum", "Home&Kitchen|Vacuums", "Dyson", 59900, 72900, "18%", 4.7, "6,540", "Laser dust detection, HEPA filtration, 60min run time, LCD screen, 5 cleaning modes"),
    ("KA012", "Eureka Forbes Trendy Zip 1000-Watt Vacuum Cleaner", "Home&Kitchen|Vacuums", "Eureka Forbes", 4999, 7499, "33%", 4.3, "23,450", "1000W, 1L dust bag, blower function, 3-stage filtration, 6m power cord"),
    ("KA013", "Havells PT3101 1500W Dry Iron", "Home&Kitchen|Irons", "Havells", 799, 1299, "38%", 4.5, "31,200", "1500W, non-stick soleplate, pilot indicator light, 360° swivel cord, ISI marked"),
    ("KA014", "Philips GC2999/20 Steam Iron", "Home&Kitchen|Irons", "Philips", 2495, 3495, "29%", 4.6, "18,760", "2400W, SteamGlide Advanced soleplate, 45g/min steam, anti-drip, anti-calc, 2.3m cord"),
    ("KA015", "Morphy Richards Evoke 600W Pop Up Toaster", "Home&Kitchen|Toasters", "Morphy Richards", 1895, 2895, "35%", 4.5, "14,560", "2-slice, 7-stage browning, removable crumb tray, frozen setting, reheat function"),

    # ── REFRIGERATORS ──────────────────────────────────────────────────────────
    ("RF001", "Samsung 253L Double Door Refrigerator RT28C3122S8", "Home&Kitchen|Refrigerators", "Samsung", 26490, 33490, "21%", 4.5, "8,760", "Digital Inverter Technology, All Around Cooling, auto defrost, 5yr compressor warranty"),
    ("RF002", "LG 260L Double Door Refrigerator GL-S292RDSX", "Home&Kitchen|Refrigerators", "LG", 27990, 34990, "20%", 4.6, "9,870", "Smart Inverter, Multi Air Flow, smart diagnosis, auto smart connect, 10yr compressor"),
    ("RF003", "Haier 320L Double Door Refrigerator HEB-32TDS", "Home&Kitchen|Refrigerators", "Haier", 29990, 37990, "21%", 4.4, "5,430", "Twin Inverter, Twin Cooling, antibacterial gasket, 1hr icing technology"),

    # ── WASHING MACHINES ───────────────────────────────────────────────────────
    ("WM001", "LG 7Kg 5 Star Inverter Fully-Automatic Front Load Washing Machine", "Home&Kitchen|WashingMachines", "LG", 34990, 44990, "22%", 4.6, "12,340", "AI Direct Drive, 6 Motion DD, ThinQ, steam wash, child lock, 1400 RPM"),
    ("WM002", "Samsung 7Kg Fully-Automatic Top Load Washing Machine WA70BG4441YY", "Home&Kitchen|WashingMachines", "Samsung", 21490, 27490, "22%", 4.5, "18,760", "Ecobubble, Digital Inverter Motor, 5-star, diamond drum, 8 wash programs"),
    ("WM003", "Bosch 8Kg Fully Automatic Front Loading Washing Machine", "Home&Kitchen|WashingMachines", "Bosch", 44990, 57990, "22%", 4.7, "7,890", "EcoSilence Drive, ActiveWater Plus, AntiVibration, 1200 RPM, 15 programs, A+++"),

    # ── WATER PURIFIERS ────────────────────────────────────────────────────────
    ("WP001", "Kent Grand Plus 9L RO+UV+UF Water Purifier", "Home&Kitchen|WaterPurifiers", "Kent", 14999, 19999, "25%", 4.5, "14,560", "9L tank, 20L/hr purification, multi-stage purification, zero water wastage, TDS control"),
    ("WP002", "Aquaguard Aura RO+UV+MTDS Water Purifier", "Home&Kitchen|WaterPurifiers", "Eureka Forbes", 17490, 22490, "22%", 4.5, "9,870", "6L tank, e-boiling+ technology, mineral fortification, taste adjuster, auto shut-off"),

    # ── ROUTERS & NETWORKING ───────────────────────────────────────────────────
    ("NW001", "TP-Link Deco XE75 Pro Wi-Fi 6E Mesh System 2-Pack", "Computers&Accessories|Networking", "TP-Link", 18999, 24999, "24%", 4.6, "4,320", "Wi-Fi 6E, 6600Mbps, 2.4+5+6GHz, 5400 sq.ft coverage, seamless roaming, parental controls"),
    ("NW002", "Netgear Nighthawk AX3000 Dual Band WiFi 6 Router", "Computers&Accessories|Networking", "Netgear", 10999, 14999, "27%", 4.5, "6,780", "AX3000, 4 LAN ports, USB 3.0, 160MHz channel, OFDMA, BSS coloring, MU-MIMO"),
    ("NW003", "Mi Router 4A Gigabit Edition", "Computers&Accessories|Networking", "Xiaomi", 2099, 2999, "30%", 4.4, "34,560", "Gigabit port, 4 antennas, MU-MIMO, beamforming, parental controls, Mi Home app"),

    # ── POWER BANKS ────────────────────────────────────────────────────────────
    ("PB001", "Anker 24000mAh Power Bank 140W", "Electronics|PowerBanks", "Anker", 5999, 7999, "25%", 4.7, "11,230", "140W USB-C PD, charge MacBook, 2 USB-C + 1 USB-A, digital display, airline safe"),
    ("PB002", "Mi 20000mAh Power Bank 3i", "Electronics|PowerBanks", "Xiaomi", 1999, 2999, "33%", 4.5, "56,780", "20000mAh, 18W fast charge, triple output, dual input, 12 layer protection, BIS certified"),
    ("PB003", "Ambrane 27000mAh Power Bank PF-270", "Electronics|PowerBanks", "Ambrane", 2499, 3999, "38%", 4.4, "22,100", "27000mAh, 65W PD, 3 output ports, 2 input ports, digital display, fast charge support"),
]


def seed():
    with get_conn() as conn:
        with conn.cursor() as cur:
            inserted = 0
            skipped = 0
            for row in PRODUCTS:
                (pid, name, category, brand, price, original_price,
                 discount_pct, rating, rating_count, description, availability) = row
                cur.execute(
                    """INSERT INTO products
                       (product_id, name, category, brand, price, original_price,
                        discount_pct, rating, rating_count, description, availability)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (product_id) DO NOTHING""",
                    [pid, name, category, brand, price, original_price,
                     discount_pct, rating, rating_count, description, availability],
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1

    print(f"Inserted {inserted} products, skipped {skipped} duplicates.")

    # Summary by category
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT SPLIT_PART(category, '|', 2) AS cat, COUNT(*) AS n
                FROM products
                WHERE product_id LIKE ANY(ARRAY[
                    'LT%','SP%','TB%','TV%','CM%','EB%','SS%','MN%',
                    'KB%','MS%','SD%','SW%','KA%','RF%','WM%','WP%',
                    'NW%','PB%'
                ])
                GROUP BY cat ORDER BY n DESC
            """)
            print("\nSeeded products by category:")
            for row in cur.fetchall():
                print(f"  {row[0] or 'General':<30} {row[1]} products")


if __name__ == "__main__":
    seed()
