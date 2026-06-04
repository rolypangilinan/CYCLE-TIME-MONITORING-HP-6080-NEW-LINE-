"""
QR Code Printer Module for SATO PW208NX
Prints kitting QR codes via Windows GDI (driver-rendered).

The QR code is generated as an image using the 'qrcode' library,
then printed through the Windows printer driver using win32ui GDI calls.
This approach lets the SATO driver handle all rendering and is confirmed
working on the PW208NX connected via USB.
"""

import win32print
import win32ui
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageWin


# ──────────────────────────────────────────────────────────────────────
#  Printer detection
# ──────────────────────────────────────────────────────────────────────

def get_sato_printer_name():
    """Find the SATO PW208NX printer name from installed printers."""
    printers = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )
    for printer in printers:
        printer_name = printer[2]
        if 'PW208' in printer_name.upper() or 'SATO' in printer_name.upper():
            return printer_name
    return None


def list_printers():
    """List all available printers on the system."""
    printers = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )
    return [{'name': p[2], 'description': p[1]} for p in printers]


# ──────────────────────────────────────────────────────────────────────
#  QR label image builder
# ──────────────────────────────────────────────────────────────────────

def _parse_qr_data(qr_data):
    """
    Parse QR data string into individual fields.
    QR format: "DD/MM/YY-KITTING_NO JOB_ORDER"
    Example:   "04/06/26-0001 3J73802302"

    Returns dict with keys: date, kit_no, jo_no, suffix
    """
    try:
        # Split by space: first part = "DD/MM/YY-KITTING_NO", second = JOB_ORDER
        parts = qr_data.split(' ', 1)
        date_kit = parts[0]           # "04/06/26-0001"
        jo_no = parts[1] if len(parts) > 1 else ''

        # Split date_kit by '-': date = "04/06/26", kit_no = "0001"
        dash_parts = date_kit.split('-', 1)
        date_str = dash_parts[0]      # "04/06/26"
        kit_no = dash_parts[1] if len(dash_parts) > 1 else ''

        return {
            'date': date_str,
            'kit_no': kit_no,
            'jo_no': jo_no,
            'suffix': kit_no,         # suffix = same as kitting number
        }
    except Exception:
        return {
            'date': qr_data,
            'kit_no': '',
            'jo_no': '',
            'suffix': '',
        }


def build_qr_label_image(qr_data):
    """
    Generate a label image matching the HIBLOW PHILIPPINES INC. format:
      - Header:  "HIBLOW PHILIPPINES INC."
      - Left:    QR code
      - Right:   DATE / KIT NO / JO NO / SUFFIX

    Args:
        qr_data: Text to encode in the QR code (e.g. "04/06/26-0001 3J73802302")

    Returns:
        PIL.Image - the label image ready to print
    """
    # Parse QR data into fields
    fields = _parse_qr_data(qr_data)

    # Generate QR code image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=5,
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_w, qr_h = qr_img.size

    # Label dimensions
    label_w = 480
    header_h = 36
    body_h = max(qr_h + 10, 160)
    label_h = header_h + body_h
    label = Image.new('RGB', (label_w, label_h), 'white')
    draw = ImageDraw.Draw(label)

    # Load fonts
    try:
        font_header = ImageFont.truetype("arialbd.ttf", 20)
        font_label = ImageFont.truetype("arialbd.ttf", 16)
        font_value = ImageFont.truetype("arialbd.ttf", 18)
    except OSError:
        try:
            font_header = ImageFont.truetype("arial.ttf", 20)
            font_label = ImageFont.truetype("arial.ttf", 16)
            font_value = ImageFont.truetype("arial.ttf", 18)
        except OSError:
            font_header = ImageFont.load_default()
            font_label = font_header
            font_value = font_header

    # ── Header: "HIBLOW PHILIPPINES INC." centered ──
    header_text = "HIBLOW PHILIPPINES INC."
    bbox = draw.textbbox((0, 0), header_text, font=font_header)
    text_w = bbox[2] - bbox[0]
    draw.text(((label_w - text_w) // 2, 8), header_text, fill='black', font=font_header)

    # ── QR code on left side ──
    qr_x = 10
    qr_y = header_h + 5
    label.paste(qr_img, (qr_x, qr_y))

    # ── Field labels + values on right side ──
    right_x = qr_x + qr_w + 15      # start of text area (right of QR)
    value_x = right_x + 90           # column for values (aligned)
    start_y = header_h + 12
    line_spacing = 34

    field_rows = [
        ("DATE:", fields['date']),
        ("KIT NO:", fields['kit_no']),
        ("JO NO:", fields['jo_no']),
        ("SUFFIX:", fields['suffix']),
    ]

    for i, (lbl, val) in enumerate(field_rows):
        y = start_y + i * line_spacing
        draw.text((right_x, y), lbl, fill='black', font=font_label)
        draw.text((value_x, y), val, fill='black', font=font_value)

    return label


# ──────────────────────────────────────────────────────────────────────
#  GDI print function (driver-rendered)
# ──────────────────────────────────────────────────────────────────────

def print_kitting_qr_code(qr_data, printer_name=None):
    """
    Print a kitting QR code label to the SATO PW208NX via Windows GDI.

    The printer driver handles all rendering. A QR code image is generated
    in Python, then sent to the driver as a bitmap.

    Args:
        qr_data:      Text to encode (e.g. "04/06/26-0001 3J73802302")
        printer_name:  Optional override. Auto-detects SATO printer if None.

    Returns:
        dict  {'success': bool, 'message': str}
    """
    try:
        if not printer_name:
            printer_name = get_sato_printer_name()

        if not printer_name:
            printers = list_printers()
            return {
                'success': False,
                'message': 'SATO PW208NX printer not found. '
                           f'Available: {[p["name"] for p in printers]}'
            }

        # Build label image
        label = build_qr_label_image(qr_data)

        # Print via Windows GDI
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        hdc.StartDoc("Kitting QR Code")
        hdc.StartPage()

        dib = ImageWin.Dib(label)
        dib.draw(hdc.GetHandleOutput(), (0, 0, label.size[0], label.size[1]))

        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()

        return {
            'success': True,
            'message': f'QR "{qr_data}" printed on {printer_name}'
        }

    except Exception as e:
        return {'success': False, 'message': f'Print error: {e}'}


# Keep for backward compatibility with cycleTimeMoni.py fallback logic
def print_kitting_qr_code_cpcl(qr_data, printer_name=None):
    """Fallback - just calls the main GDI print function."""
    return print_kitting_qr_code(qr_data, printer_name)


# ──────────────────────────────────────────────────────────────────────
#  Standalone test  --  run:  python qr_printer.py
# ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    TEST_DATA = "04/06/26-0001 3J73802302"

    print("=" * 50)
    print("  SATO PW208NX -- QR Code Print Test (GDI)")
    print("=" * 50)

    print("\n[1] Listing installed printers...")
    for p in list_printers():
        print(f"    - {p['name']}")

    sato = get_sato_printer_name()
    if not sato:
        print("\n[X] SATO PW208NX not found in printer list!")
        print("  Make sure the printer is ON, connected via USB,")
        print("  and the SATO driver is installed.")
        exit(1)

    print(f"\n[2] Found SATO printer: {sato}")
    print(f"[3] Printing test QR code: \"{TEST_DATA}\"")

    result = print_kitting_qr_code(TEST_DATA, sato)
    print(f"    Result: {result['message']}")
    print("\n" + (">>> SUCCESS" if result['success'] else ">>> FAILED"))
    print("=" * 50)
