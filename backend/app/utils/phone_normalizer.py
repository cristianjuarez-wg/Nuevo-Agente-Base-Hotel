"""
Utilidad para normalización de números de teléfono
"""
import re
from typing import Optional, Tuple


def normalize_phone(phone: str, country_code: str = "54") -> Optional[str]:
    """
    Normaliza un número de teléfono a formato estándar internacional
    
    Args:
        phone: Número de teléfono en cualquier formato
        country_code: Código de país por defecto (54 para Argentina)
    
    Returns:
        Teléfono normalizado en formato +XXXXXXXXXXX o None si es inválido
    
    Examples:
        "+54 911 1234 5678" → "+5491112345678"
        "911 1234 5678" → "+5491112345678"
        "+1 555 123 4567" → "+15551234567"
        "(011) 1234-5678" → "+54111234567"
    """
    if not phone:
        return None
    
    # Convertir a string y limpiar
    phone = str(phone).strip()
    
    if not phone:
        return None
    
    # Quitar espacios, guiones, paréntesis y otros caracteres
    clean = re.sub(r'[^\d+]', '', phone)
    
    # Si está vacío después de limpiar, retornar None
    if not clean:
        return None
    
    # Si no tiene +, agregar código de país
    if not clean.startswith('+'):
        # Si empieza con 00, reemplazar por +
        if clean.startswith('00'):
            clean = '+' + clean[2:]
        else:
            clean = f"+{country_code}{clean}"
    
    return clean


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
