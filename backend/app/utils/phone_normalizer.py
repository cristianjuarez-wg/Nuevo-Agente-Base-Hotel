"""
Utilidad para normalización de números de teléfono.

Motor principal: `phonenumbers` (libphonenumber de Google), que produce formato
canónico E.164 y resuelve correctamente el "9" móvil argentino (un número cargado
con o sin el 9, con 0 o 15, converge al MISMO E.164). Si la librería no puede
parsear, se cae a una normalización regex de mejor esfuerzo (defensivo).

Para el matching tolerante (teléfonos ya guardados con formato viejo) ver
`phone_match_key` / `phones_match`.
"""
import re
from typing import Optional, Tuple

try:
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, PhoneNumberType
    _HAS_PHONENUMBERS = True
except Exception:  # noqa: BLE001 — sin la librería, usamos el fallback regex
    _HAS_PHONENUMBERS = False

# Región por defecto cuando el número viene sin código de país (Argentina).
_DEFAULT_REGION = "AR"


def _normalize_regex(phone: str, country_code: str) -> Optional[str]:
    """Fallback histórico: limpia separadores y antepone el código de país."""
    clean = re.sub(r'[^\d+]', '', phone)
    if not clean:
        return None
    if not clean.startswith('+'):
        if clean.startswith('00'):
            clean = '+' + clean[2:]
        else:
            clean = f"+{country_code}{clean}"
    return clean


def normalize_phone(phone: str, country_code: str = "54") -> Optional[str]:
    """
    Normaliza un número de teléfono a formato canónico internacional (E.164).

    Usa `phonenumbers` cuando está disponible; si falla el parseo, cae al método
    regex histórico. NUNCA lanza: ante un input inválido devuelve None.

    Args:
        phone: Número de teléfono en cualquier formato
        country_code: Código de país por defecto (54 para Argentina) — usado solo
            por el fallback regex; el parseo principal usa la región AR.

    Returns:
        Teléfono en E.164 (+XXXXXXXXXXX) o None si es inválido.

    Examples (Argentina, todos convergen al mismo canónico):
        "+543417207797"      → "+5493417207797"
        "+5493417207797"     → "+5493417207797"
        "3417207797"         → "+5493417207797"
        "0341 15 7207797"    → "+5493417207797"
        "+1 555 123 4567"    → "+15551234567"
    """
    if not phone:
        return None
    phone = str(phone).strip()
    if not phone:
        return None

    if _HAS_PHONENUMBERS:
        try:
            # Si ya trae +, phonenumbers ignora la región; si no, asume AR.
            parsed = phonenumbers.parse(phone, _DEFAULT_REGION)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
            # Número no estrictamente válido pero parseable (ej. de prueba):
            # devolvemos su E.164 de mejor esfuerzo si tiene país + nacional.
            if parsed.country_code and parsed.national_number:
                return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        except Exception:  # noqa: BLE001 — caemos al fallback regex
            pass

    return _normalize_regex(phone, country_code)


def phone_match_key(phone: str) -> Optional[str]:
    """
    Clave de comparación tolerante: los últimos 10 dígitos del número.

    Descarta '+', código de país, el '9' móvil argentino, el '0'/'15' y cualquier
    separador. Dos números equivalentes (uno con '9', otro sin) comparten clave.
    Sirve para machear contra teléfonos YA guardados con formato viejo sin migrar la DB.

    Returns:
        Cadena de hasta 10 dígitos, o None si no hay suficientes dígitos.
    """
    if not phone:
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) < 8:
        return None
    return digits[-10:]


def phones_match(a: Optional[str], b: Optional[str]) -> bool:
    """True si dos teléfonos son equivalentes según `phone_match_key`."""
    ka, kb = phone_match_key(a or ""), phone_match_key(b or "")
    return bool(ka) and ka == kb


def to_ar_whatsapp(phone: Optional[str]) -> Optional[str]:
    """Devuelve el número en el formato que WhatsApp Argentina necesita: con el "9" móvil.

    `normalize_phone` NO inserta el 9 cuando el número parece un fijo válido (ej.
    +543417207797 lo ve como fijo de Rosario), pero para WhatsApp un número argentino debe
    ir como +549<área><número>. Esta función, específica del canal WhatsApp, primero
    normaliza a E.164 y luego, si es argentino (+54) con 10 dígitos nacionales sin el 9,
    inserta el 9. Números no argentinos o que ya tienen el 9 quedan igual.

    Ejemplos:
        +543417207797  → +5493417207797
        +5493417207797 → +5493417207797 (sin cambio)
        +15551234567   → +15551234567   (no AR, sin cambio)
    """
    if not phone:
        return phone
    e164 = normalize_phone(phone) or phone
    m = re.match(r'^\+54(\d+)$', e164)
    if not m:
        return e164
    nacional = m.group(1)
    # Ya es móvil con 9 (+549 + 10 dígitos = 11 dígitos arrancando en 9): sin cambio.
    if nacional.startswith("9") and len(nacional) == 11:
        return e164
    # Nacional de 10 dígitos sin el 9 → insertarlo para que WhatsApp lo entregue.
    if len(nacional) == 10:
        return "+549" + nacional
    return e164


def is_whatsapp_capable(phone: str) -> bool:
    """
    Heurística: ¿el número parece un móvil válido (asumible alcanzable por WhatsApp)?

    Usa `phonenumbers` para validar y mirar el tipo de línea. NO consulta a WhatsApp;
    es un indicador de formato, no de existencia real de la cuenta.
    """
    if not phone or not _HAS_PHONENUMBERS:
        return False
    try:
        parsed = phonenumbers.parse(phone, _DEFAULT_REGION)
        if not phonenumbers.is_valid_number(parsed):
            return False
        ntype = phonenumbers.number_type(parsed)
        return ntype in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE)
    except Exception:  # noqa: BLE001
        return False


def extract_country_code(phone: str) -> Optional[str]:
    """
    Extrae el código de país de un número de teléfono normalizado
    
    Args:
        phone: Número de teléfono normalizado (+XXXXXXXXXXX)
    
    Returns:
        Código de país sin el + o None si no se puede extraer
    
    Examples:
        "+5491112345678" → "54"
        "+15551234567" → "1"
    """
    if not phone or not phone.startswith('+'):
        return None
    
    # Códigos de país comunes (1-3 dígitos)
    # Intentar extraer código de país
    phone_digits = phone[1:]  # Quitar el +
    
    # Códigos de 1 dígito (USA, Canadá)
    if phone_digits[0] == '1':
        return '1'
    
    # Códigos de 2 dígitos (la mayoría de países)
    if len(phone_digits) >= 2:
        two_digit = phone_digits[:2]
        if two_digit in ['54', '55', '56', '57', '58', '52', '34', '44', '49', '33', '39', '81', '82', '86']:
            return two_digit
    
    # Códigos de 3 dígitos
    if len(phone_digits) >= 3:
        return phone_digits[:3]
    
    return None


def split_phone_components(phone: str) -> Optional[Tuple[str, str]]:
    """
    Divide un número de teléfono en código de país y número local
    
    Args:
        phone: Número de teléfono normalizado
    
    Returns:
        Tupla (country_code, local_number) o None si es inválido
    
    Examples:
        "+5491112345678" → ("54", "91112345678")
        "+15551234567" → ("1", "5551234567")
    """
    country_code = extract_country_code(phone)
    if not country_code:
        return None
    
    local_number = phone[len(country_code) + 1:]  # +1 por el símbolo +
    
    return (country_code, local_number)


def validate_phone(phone: str) -> bool:
    """
    Valida si un número de teléfono normalizado es válido
    
    Args:
        phone: Número de teléfono normalizado
    
    Returns:
        True si es válido, False en caso contrario
    
    Criteria:
        - Debe empezar con +
        - Debe tener entre 8 y 15 dígitos después del +
        - Solo debe contener dígitos después del +
    """
    if not phone or not isinstance(phone, str):
        return False
    
    if not phone.startswith('+'):
        return False
    
    digits = phone[1:]
    
    # Verificar que solo contenga dígitos
    if not digits.isdigit():
        return False
    
    # Verificar longitud (8-15 dígitos es el rango estándar internacional)
    if len(digits) < 8 or len(digits) > 15:
        return False
    
    return True


def format_phone_display(phone: str, format_type: str = 'international') -> str:
    """
    Formatea un número de teléfono para visualización
    
    Args:
        phone: Número de teléfono normalizado
        format_type: Tipo de formato ('international', 'national', 'compact')
    
    Returns:
        Número formateado para visualización
    
    Examples:
        "+5491112345678", 'international' → "+54 9 11 1234 5678"
        "+5491112345678", 'national' → "9 11 1234 5678"
        "+5491112345678", 'compact' → "+5491112345678"
    """
    if not phone or not validate_phone(phone):
        return phone or ""
    
    if format_type == 'compact':
        return phone
    
    components = split_phone_components(phone)
    if not components:
        return phone
    
    country_code, local_number = components
    
    if format_type == 'international':
        # Formato: +XX X XXX XXXX XXXX
        if country_code == '54':  # Argentina
            if len(local_number) >= 10:
                return f"+{country_code} {local_number[0]} {local_number[1:3]} {local_number[3:7]} {local_number[7:]}"
        elif country_code == '1':  # USA/Canada
            if len(local_number) == 10:
                return f"+{country_code} ({local_number[:3]}) {local_number[3:6]}-{local_number[6:]}"
        
        # Formato genérico
        return f"+{country_code} {local_number}"
    
    elif format_type == 'national':
        # Sin código de país
        if country_code == '54':  # Argentina
            if len(local_number) >= 10:
                return f"{local_number[0]} {local_number[1:3]} {local_number[3:7]} {local_number[7:]}"
        elif country_code == '1':  # USA/Canada
            if len(local_number) == 10:
                return f"({local_number[:3]}) {local_number[3:6]}-{local_number[6:]}"
        
        return local_number
    
    return phone
