"""
Servicio de Clima - WeatherAPI Integration
Proporciona información climática de destinos turísticos
"""
import requests
from typing import Dict, Optional
from datetime import datetime, timedelta
from app.core.logging_config import get_logger
from app.config import settings

logger = get_logger(__name__)


class WeatherService:
    """Servicio para consultar clima de destinos turísticos"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'WEATHER_API_KEY', None)
        self.base_url = "http://api.weatherapi.com/v1"
        self._cache = {}
        self._cache_duration = timedelta(minutes=30)
        
        if not self.api_key:
            logger.warning("WEATHER_API_KEY not configured, weather service will be disabled")
        else:
            logger.info("WeatherService initialized with API key")
    
    def get_current_weather(self, city: str, country: str = None) -> Optional[Dict]:
        """
        Obtiene clima actual de una ciudad
        
        Args:
            city: Nombre de la ciudad
            country: País (opcional, ayuda a precisión)
        
        Returns:
            Dict con información del clima o None si no está disponible
        """
        if not self.api_key:
            logger.debug("Weather API key not configured, skipping weather fetch")
            return None
        
        try:
            # Construir query
            query = f"{city},{country}" if country else city
            
            # Verificar cache
            cache_key = query.lower().strip()
            if cache_key in self._cache:
                cached_data, cached_time = self._cache[cache_key]
                if datetime.now() - cached_time < self._cache_duration:
                    logger.debug("Weather cache HIT", query=query)
                    return cached_data
            
            # Llamar a API
            logger.info("Fetching weather from API", query=query)
            
            response = requests.get(
                f"{self.base_url}/current.json",
                params={
                    "key": self.api_key,
                    "q": query,
                    "lang": "es"
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                formatted_data = self._format_current_weather(data)
                
                # Guardar en cache
                self._cache[cache_key] = (formatted_data, datetime.now())
                
                logger.info("Weather fetched successfully",
                           city=formatted_data['city'],
                           temp=formatted_data['temperature'])
                
                return formatted_data
            else:
                logger.warning("Weather API error",
                             status_code=response.status_code,
                             query=query)
                return None
                
        except requests.Timeout:
            logger.warning("Weather API timeout", query=query)
            return None
        except Exception as e:
            logger.error("Error fetching weather",
                        query=query,
                        error=str(e))
            return None
    
    def get_forecast(self, city: str, country: str, days: int = 7) -> Optional[Dict]:
        """
        Obtiene pronóstico de clima
        
        Args:
            city: Ciudad
            country: País
            days: Días de pronóstico (1-14)
        
        Returns:
            Dict con pronóstico o None
        """
        if not self.api_key:
            return None
        
        try:
            query = f"{city},{country}"
            
            response = requests.get(
                f"{self.base_url}/forecast.json",
                params={
                    "key": self.api_key,
                    "q": query,
                    "days": min(days, 14),
                    "lang": "es"
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._format_forecast(data)
            
            return None
            
        except Exception as e:
            logger.error("Error fetching forecast",
                        city=city,
                        error=str(e))
            return None
    
    # Rango máximo de pronóstico de WeatherAPI en plan free.
    FORECAST_MAX_DAYS = 14

    # Nombres de meses en español (para el modo estacional).
    _MONTHS_ES = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]

    def get_weather_for_date(
        self, city: str, country: str = None, target_date=None
    ) -> Optional[Dict]:
        """
        Resuelve el clima del destino según la fecha consultada.

        - target_date None  → clima ACTUAL (¿cómo está hoy?).
        - dentro de FORECAST_MAX_DAYS → PRONÓSTICO real (forecast de la API).
        - fecha lejana (o pasada) → señal "seasonal": NO inventa datos; deja que el
          LLM aporte el promedio estacional típico, etiquetado como histórico.

        Returns un Dict con la key "mode" ∈ {"current", "forecast", "seasonal"}.
        """
        from datetime import date as _date

        # Sin fecha → comportamiento histórico: clima actual.
        if target_date is None:
            data = self.get_current_weather(city, country)
            if not data:
                return None
            data["mode"] = "current"
            return data

        # Normalizar a date
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        today = _date.today()
        days_until = (target_date - today).days

        # Dentro del rango de pronóstico → forecast real
        if 0 <= days_until <= self.FORECAST_MAX_DAYS:
            forecast = self.get_forecast(city, country or "", days=self.FORECAST_MAX_DAYS)
            if forecast:
                target_iso = target_date.isoformat()
                day = next(
                    (d for d in forecast.get("forecast", []) if d["date"] == target_iso),
                    None,
                )
                # Si no está el día exacto, usar el último disponible del forecast
                if day is None and forecast.get("forecast"):
                    day = forecast["forecast"][-1]
                if day:
                    return {
                        "mode": "forecast",
                        "city": forecast["city"],
                        "country": forecast["country"],
                        "date": day["date"],
                        "max_temp": day["max_temp"],
                        "min_temp": day["min_temp"],
                        "avg_temp": day["avg_temp"],
                        "condition": day["condition"],
                        "rain_chance": day["rain_chance"],
                    }
            # Forecast no disponible (sin API key, error) → caer a estacional
            return self._seasonal_signal(city, country, target_date)

        # Fecha lejana o pasada → promedio estacional (lo completa el LLM)
        return self._seasonal_signal(city, country, target_date)

    def _seasonal_signal(self, city: str, country: str, target_date) -> Dict:
        """Construye la señal de modo estacional (sin datos inventados)."""
        month_name = self._MONTHS_ES[target_date.month - 1]
        return {
            "mode": "seasonal",
            "city": city,
            "country": country or "",
            "month": month_name,
            "target_date": target_date.isoformat(),
        }

    def format_for_date(self, weather_data: Dict, compare_with_argentina: bool = False) -> str:
        """
        Formatea el resultado de get_weather_for_date para el contexto del agente,
        según el modo (current / forecast / seasonal).
        """
        if not weather_data:
            return ""

        mode = weather_data.get("mode", "current")

        if mode == "current":
            return self.format_for_agent(weather_data, compare_with_argentina)

        if mode == "forecast":
            return f"""
🌤️ PRONÓSTICO para {weather_data['city']}, {weather_data['country']} el {weather_data['date']}:
- Temperatura: mín {weather_data['min_temp']}°C / máx {weather_data['max_temp']}°C (promedio {weather_data['avg_temp']}°C)
- Condición: {weather_data['condition']}
- Probabilidad de lluvia: {weather_data['rain_chance']}%

✅ Esto es un PRONÓSTICO real (fecha dentro del rango disponible). Usalo para recomendar qué llevar.
"""

        # mode == "seasonal" — señal para que el LLM aporte el promedio histórico
        return f"""
📅 FECHA LEJANA: el viaje a {weather_data['city']}{(', ' + weather_data['country']) if weather_data['country'] else ''} es en {weather_data['month']}, fuera del rango de pronóstico ({self.FORECAST_MAX_DAYS} días).

INSTRUCCIÓN: NO hay pronóstico disponible para esa fecha. Describí el clima TÍPICO de {weather_data['city']} en {weather_data['month']} (temperaturas promedio, si suele llover, qué ropa conviene), aclarando SIEMPRE que es un PROMEDIO ESTACIONAL HISTÓRICO y no un pronóstico exacto. Recomendá verificar el pronóstico real cuando se acerque la fecha.
"""

    def _format_current_weather(self, data: Dict) -> Dict:
        """Formatea respuesta de clima actual"""
        current = data['current']
        location = data['location']
        
        return {
            "city": location['name'],
            "country": location['country'],
            "temperature": current['temp_c'],
            "feels_like": current['feelslike_c'],
            "condition": current['condition']['text'],
            "humidity": current['humidity'],
            "wind_kph": current['wind_kph'],
            "is_day": current['is_day'] == 1,
            "icon": current['condition']['icon'],
            "last_updated": current['last_updated']
        }
    
    def _format_forecast(self, data: Dict) -> Dict:
        """Formatea pronóstico"""
        forecast_days = []
        
        for day in data['forecast']['forecastday']:
            forecast_days.append({
                "date": day['date'],
                "max_temp": day['day']['maxtemp_c'],
                "min_temp": day['day']['mintemp_c'],
                "avg_temp": day['day']['avgtemp_c'],
                "condition": day['day']['condition']['text'],
                "rain_chance": day['day']['daily_chance_of_rain'],
                "icon": day['day']['condition']['icon']
            })
        
        return {
            "city": data['location']['name'],
            "country": data['location']['country'],
            "forecast": forecast_days
        }
    
    def format_for_agent(self, weather_data: Dict, compare_with_argentina: bool = False) -> str:
        """
        Formatea clima para el contexto del agente IA
        
        Args:
            weather_data: Datos del clima
            compare_with_argentina: Si debe comparar con Argentina (PRE-VENTA)
        
        Returns:
            String formateado para el contexto del agente
        """
        if not weather_data:
            return ""
        
        formatted = f"""

╔══════════════════════════════════════════════════════════════════════╗
║  INFORMACIÓN CLIMÁTICA DEL DESTINO                                  ║
╚══════════════════════════════════════════════════════════════════════╝

🌤️ CLIMA ACTUAL EN {weather_data['city'].upper()}, {weather_data['country']}:
- Temperatura: {weather_data['temperature']}°C (sensación térmica: {weather_data['feels_like']}°C)
- Condición: {weather_data['condition']}
- Humedad: {weather_data['humidity']}%
- Viento: {weather_data['wind_kph']} km/h
"""
        
        # Comparación con Argentina si se solicita (PRE-VENTA)
        if compare_with_argentina:
            try:
                argentina_weather = self.get_current_weather("Buenos Aires", "Argentina")
                if argentina_weather:
                    temp_diff = weather_data['temperature'] - argentina_weather['temperature']
                    comparison = "más fresco" if temp_diff < 0 else "más cálido"
                    
                    formatted += f"""
📍 COMPARACIÓN CON ARGENTINA (Buenos Aires):
- Temperatura actual en Argentina: {argentina_weather['temperature']}°C
- Diferencia: {abs(temp_diff):.1f}°C {comparison}
"""
            except Exception as e:
                logger.error("Error comparing with Argentina weather", error=str(e))
        
        # Recomendaciones
        formatted += self._get_recommendations(weather_data)
        
        formatted += """
⚠️ Nota: Información climática aproximada. Verifica pronóstico actualizado antes de viajar.
"""
        
        return formatted
    
    def _get_recommendations(self, weather: Dict) -> str:
        """Genera recomendaciones según el clima"""
        temp = weather['temperature']
        condition = weather['condition'].lower()
        
        recommendations = "\n💡 RECOMENDACIONES PARA EL VIAJERO:\n"
        
        # Temperatura
        if temp < 10:
            recommendations += "- 🧥 Abrigo grueso, bufanda, guantes y gorro\n"
            recommendations += "- 👢 Calzado abrigado e impermeable\n"
        elif temp < 20:
            recommendations += "- 🧥 Abrigo ligero o chaqueta\n"
            recommendations += "- 👕 Ropa en capas (fácil de quitar/poner)\n"
        elif temp < 30:
            recommendations += "- 👕 Ropa ligera y cómoda\n"
            recommendations += "- 🧴 Protector solar recomendado\n"
        else:
            recommendations += "- 👕 Ropa muy ligera, preferiblemente de algodón\n"
            recommendations += "- 🧴 Protector solar IMPRESCINDIBLE\n"
            recommendations += "- 🧢 Gorra o sombrero\n"
            recommendations += "- 💧 Mantente muy bien hidratado\n"
        
        # Condición climática
        if 'lluv' in condition or 'torment' in condition:
            recommendations += "- ☔ Paraguas o impermeable IMPRESCINDIBLE\n"
            recommendations += "- 👟 Calzado impermeable\n"
        elif 'nublado' in condition or 'nube' in condition:
            recommendations += "- ☁️ Paraguas recomendado (puede llover)\n"
        
        if temp > 25:
            recommendations += "- 😎 Lentes de sol\n"
        
        return recommendations
    
    def clear_cache(self):
        """Limpia el cache de clima"""
        self._cache.clear()
        logger.info("Weather cache cleared")


# Instancia global
weather_service = WeatherService()
