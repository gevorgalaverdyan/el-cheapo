"""Generate the receipt fixture set.

    uv run python tests/fixtures/make_receipts.py

Writes images and PDFs into tests/fixtures/receipts/ plus a manifest recording
what each one should extract to. The manifest is what turns these from "try it
and see" into a measurable accuracy check -- see tests/test_receipts_live.py.

Each fixture targets a specific way receipt reading goes wrong: a tip line that
invites picking the wrong total, a subtotal above the total, a faded thermal
print, a sideways photo, a missing date.
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
OUT = HERE / "receipts"

# Monospace reads like a real receipt and survives downscaling better.
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]


def load_font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


RECEIPTS = [
    {
        "name": "loblaws_groceries",
        "format": "jpg",
        "tests": "total vs subtotal, printed date",
        "expect": {"amount": "38.36", "merchant": "Loblaws", "date": "2026-09-10"},
        "lines": [
            "        LOBLAWS",
            "  2280 Dundas St W, Toronto",
            "      (416) 555-0142",
            "",
            "BANANAS 1.2kg          2.47",
            "MILK 2% 2L             5.99",
            "SOURDOUGH LOAF         6.50",
            "COFFEE BEANS 340G     18.99",
            "",
            "SUBTOTAL              33.95",
            "HST 13%                4.41",
            "TOTAL                 38.36",
            "",
            "VISA ************4412",
            "2026-09-10  18:42",
            "  THANK YOU",
        ],
    },
    {
        "name": "tim_hortons_coffee",
        "format": "png",
        "tests": "small simple receipt",
        "expect": {"amount": "4.52", "merchant": "Tim Hortons", "date": "2026-09-11"},
        "lines": [
            "     TIM HORTONS #2841",
            "    401 Bay St, Toronto",
            "",
            "LARGE DOUBLE DOUBLE    2.49",
            "BOSTON CREAM           1.51",
            "",
            "SUBTOTAL               4.00",
            "HST                    0.52",
            "TOTAL                  4.52",
            "",
            "DEBIT   2026-09-11 08:14",
        ],
    },
    {
        "name": "restaurant_with_tip",
        "format": "jpg",
        "tests": "tip line -- must take the final total, not the pre-tip one",
        "expect": {"amount": "97.75", "merchant": "Canoe", "date": "2026-09-06"},
        "lines": [
            "          CANOE",
            "  66 Wellington St W, 54th Fl",
            "",
            "TASTING MENU x2       68.00",
            "WINE PAIRING          12.00",
            "",
            "SUBTOTAL              80.00",
            "HST 13%               10.40",
            "AMOUNT                90.40",
            "TIP                    7.35",
            "",
            "TOTAL CHARGED         97.75",
            "",
            "AMEX ****1007",
            "Sep 6, 2026  21:33",
        ],
    },
    {
        "name": "petro_canada_gas",
        "format": "pdf",
        "tests": "PDF, fuel receipt with per-litre pricing",
        "expect": {"amount": "71.84", "merchant": "Petro-Canada", "date": "2026-09-08"},
        "lines": [
            "       PETRO-CANADA",
            "   1900 Eglinton Ave E",
            "",
            "PUMP 04",
            "REGULAR UNLEADED",
            "LITRES              44.62",
            "PRICE/L             1.610",
            "",
            "FUEL TOTAL          71.84",
            "",
            "CREDIT  2026-09-08  07:21",
        ],
    },
    {
        "name": "amazon_invoice",
        "format": "pdf",
        "tests": "emailed invoice layout, order date vs delivery date",
        "expect": {"amount": "156.43", "merchant": "Amazon", "date": "2026-09-02"},
        "lines": [
            "amazon.ca",
            "Order Confirmation",
            "",
            "Order #702-4418822-9931047",
            "Order Date: September 2, 2026",
            "Delivery estimate: September 5, 2026",
            "",
            "Anker 737 Power Bank      129.99",
            "USB-C Cable 2m             14.49",
            "",
            "Items:                    144.48",
            "Shipping:                   0.00",
            "Estimated tax:             11.95",
            "Order Total:              156.43",
        ],
    },
    {
        "name": "faded_thermal",
        "format": "jpg",
        "tests": "low contrast thermal print, blurred -- robustness",
        "expect": {"amount": "23.10", "merchant": "Shoppers Drug Mart", "date": None},
        "faded": True,
        "lines": [
            "   SHOPPERS DRUG MART",
            "     #1204 Queen W",
            "",
            "VITAMIN D 1000IU      12.99",
            "TOOTHPASTE             7.46",
            "",
            "SUBTOTAL              20.45",
            "HST                    2.65",
            "TOTAL                 23.10",
        ],
    },
    {
        "name": "sideways_photo",
        "format": "jpg",
        "tests": "photographed sideways -- rotation robustness",
        "expect": {"amount": "18.75", "merchant": "Kinton Ramen", "date": None},
        "rotate": 90,
        "lines": [
            "     KINTON RAMEN",
            "    51 Baldwin Street",
            "",
            "SPICY GARLIC RAMEN    16.59",
            "",
            "SUBTOTAL              16.59",
            "HST                    2.16",
            "TOTAL                 18.75",
        ],
    },
    {
        "name": "handwritten_note",
        "format": "png",
        "tests": "scrap of paper, no structure at all",
        "expect": {"amount": "34.00", "merchant": None, "date": None},
        "lines": [
            "",
            "  cab home from airport",
            "",
            "     $34",
            "",
        ],
    },
    {
        "name": "presto_transit",
        "format": "png",
        "tests": "transit top-up -- category inference without an obvious merchant type",
        "expect": {"amount": "40.00", "merchant": "PRESTO", "date": "2026-09-09"},
        "lines": [
            "        PRESTO",
            "   Transit Fare Card",
            "",
            "LOAD AMOUNT           40.00",
            "NEW BALANCE           62.35",
            "",
            "CARD ****8823",
            "2026-09-09  17:55",
        ],
    },
    {
        "name": "usd_receipt",
        "format": "jpg",
        "tests": "foreign currency on a single-currency setup -- what does it do?",
        "expect": {"amount": "45.00", "merchant": "Blue Bottle Coffee", "date": None},
        "lines": [
            "   BLUE BOTTLE COFFEE",
            "     Brooklyn, NY, USA",
            "",
            "COLD BREW 12OZ      USD 6.50",
            "BEANS 12OZ         USD 32.00",
            "",
            "SUBTOTAL           USD 38.50",
            "NY TAX              USD 3.42",
            "TIP                 USD 3.08",
            "TOTAL              USD 45.00",
        ],
    },
    {
        "name": "no_date_receipt",
        "format": "png",
        "tests": "no date printed -- should fall back to today",
        "expect": {"amount": "12.99", "merchant": "Book City", "date": None},
        "lines": [
            "       BOOK CITY",
            "    348 Danforth Ave",
            "",
            "PAPERBACK             11.50",
            "HST                    1.49",
            "TOTAL                 12.99",
        ],
    },
    {
        "name": "not_an_expense",
        "format": "jpg",
        "tests": "a poster, not a receipt -- should extract nothing",
        "expect": {"amount": None, "merchant": None, "date": None},
        "lines": [
            "    LOST CAT",
            "",
            "  Orange tabby, answers",
            "     to 'Mango'",
            "",
            "  Call 416-555-0188",
            "",
            "  Last seen near",
            "  Trinity Bellwoods",
        ],
    },
]


def render(receipt: dict) -> Image.Image:
    font = load_font(17)
    lines = receipt["lines"]
    padding = 26
    line_height = 25

    width = 430
    height = padding * 2 + line_height * len(lines)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    ink = (110, 110, 110) if receipt.get("faded") else (20, 20, 20)
    y = padding
    for line in lines:
        draw.text((padding, y), line, font=font, fill=ink)
        y += line_height

    if receipt.get("faded"):
        # Thermal paper that has been in a wallet for a week.
        pixels = image.load()
        random.seed(7)
        for _ in range(5000):
            x, y = random.randrange(width), random.randrange(height)
            shade = random.randrange(170, 255)
            pixels[x, y] = (shade, shade, shade)
        image = image.filter(ImageFilter.GaussianBlur(0.8))

    if receipt.get("rotate"):
        image = image.rotate(receipt["rotate"], expand=True)

    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []

    for receipt in RECEIPTS:
        image = render(receipt)
        suffix = receipt["format"]
        path = OUT / f"{receipt['name']}.{suffix}"

        if suffix == "pdf":
            image.convert("RGB").save(path, "PDF", resolution=150.0)
            mime = "application/pdf"
        elif suffix == "png":
            image.save(path, "PNG")
            mime = "image/png"
        else:
            image.convert("RGB").save(path, "JPEG", quality=88)
            mime = "image/jpeg"

        manifest.append(
            {
                "file": path.name,
                "mime_type": mime,
                "tests": receipt["tests"],
                "expect": receipt["expect"],
            }
        )
        print(f"  {path.name:<28} {path.stat().st_size:>7} bytes   {receipt['tests']}")

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(manifest)} receipts written to {OUT}")


if __name__ == "__main__":
    main()
