# Forecasting de demanda y Booking Pace

Material de consultoría sobre cómo anticipar la demanda y leer el ritmo de reservas para
decidir precios con tiempo. Pensado para un hotel independiente.

## Qué es el forecasting de demanda

Es **estimar la demanda futura** analizando datos históricos + comportamiento de reservas
actual. Permite anticipar cuán lleno va a estar el hotel y, con eso, ajustar precios y
distribución ANTES de que sea tarde. Un buen forecast es la base del pricing dinámico.

> El costo de no hacerlo: incluso un error de forecast del 10% puede costar hasta un 6% del
> ingreso anual de habitaciones. La precisión importa.

## Datos que alimentan el forecast

**Internos (del propio hotel):**
- Ocupación, ADR y RevPAR históricos.
- Booking pace (ritmo de reservas) comparado con períodos previos.
- Segmentación de clientes (negocios vs. ocio).
- Analítica web y búsquedas.

**Externos (del mercado):**
- Eventos y congresos locales.
- Precios y disponibilidad de la competencia.
- Indicadores económicos y clima.
- Tendencias de búsqueda de la región.

## Booking Pace y Pickup (el corazón del método)

- **Booking pace (ritmo):** a qué velocidad entran las reservas para una fecha de llegada
  determinada, comparado con cómo venía en períodos anteriores. Un pace **más rápido** que lo
  histórico = demanda fuerte → justifica subir precio. Más lento = oportunidad de promoción.
- **Pickup:** cuántas reservas se sumaron (el cambio reciente). El pickup muestra cómo se mueve
  la demanda AHORA; el pace dice si vamos adelantados o atrasados respecto al forecast.

Ejemplo: si para un finde puntual las reservas vienen 15% por encima del ritmo del año pasado,
es señal clara de que se puede ajustar el precio hacia arriba.

## Tipos de forecast

- **Por segmento:** los de negocios reservan entre semana y con poca anticipación; los de ocio,
  fines de semana y con más anticipación. Conviene modelarlos por separado.
- **Por fecha:** detectar patrones por día de la semana y por temporada para afinar tarifas.

## Cómo lo aplica un hotel chico (pasos prácticos)

1. **Estandarizar la recolección de datos** (que el PMS registre todo igual y consistente).
2. **Combinar interno + externo**: histórico propio + inteligencia de mercado.
3. **Elegir la técnica adecuada**: series temporales si los patrones son estables; análisis de
   pickup para ventanas de reserva de 30-90 días.
4. **Actualizar el forecast seguido**, sobre todo en temporada alta.
5. **Comparar lo real vs. lo previsto** para ir afinando el modelo con el tiempo.
6. **Empezar simple** (series temporales + pickup) antes de pensar en machine learning.

> Los métodos manuales no alcanzan a seguir el ritmo de un mercado que fluctúa; incluso un
> forecast automatizado básico aporta mucho a una propiedad chica.

## Conexión con el precio

El forecast alimenta directamente el pricing dinámico: analizando el pace, el revenue manager
detecta si las reservas llegan más rápido o más lento que lo histórico y ajusta la tarifa —
estimulando reservas cuando la demanda está floja y capturando margen cuando se dispara.

## Fuentes

- RoomPriceGenie — Complete guide to hotel demand forecasting: https://roompricegenie.com/complete-guide-to-hotel-demand-forecasting/
- Lighthouse — Booking pickup and pace in revenue management: https://www.mylighthouse.com/resources/blog/booking-pickup-and-pace-revenue-management
- RoomMaster — Hotel demand forecasting: methods, models & reports: https://www.roommaster.com/blog/hotel-demand-forecasting
- Propeter — Booking pace analysis / pickup trends: https://propeter.com/booking-pace-analysis-for-hotels-understanding-pickup-trends-to-optimize-pricing/
