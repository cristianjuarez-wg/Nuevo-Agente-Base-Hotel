# KPIs de Revenue Management hotelero

Material de consultoría para el asesor de gerencia. Define los indicadores clave de revenue
management, sus fórmulas y cómo interpretarlos. Pensado para un hotel chico/independiente.

## Concepto

Revenue management es vender **la habitación correcta, al huésped correcto, en el momento
correcto, al precio correcto y por el canal correcto**, combinando análisis de datos,
forecasting y pricing para maximizar el ingreso y la rentabilidad.

## Los tres indicadores fundamentales ("The Big Three")

### Ocupación (Occupancy Rate)
Porcentaje de habitaciones disponibles que se vendieron en un período.

```
Ocupación (%) = Habitaciones vendidas / Habitaciones disponibles × 100
```

### ADR — Average Daily Rate (Tarifa media diaria)
Ingreso medio por cada habitación **ocupada**. Mide el precio promedio efectivo.

```
ADR = Ingreso por habitaciones / Habitaciones vendidas (ocupadas)
```

### RevPAR — Revenue per Available Room (Ingreso por habitación disponible)
Ingreso por cada habitación **disponible** (vendida o no). Es la métrica más completa de las
tres porque combina precio y ocupación en un solo número.

```
RevPAR = Ingreso por habitaciones / Habitaciones disponibles
   (equivale a:  ADR × Ocupación)
```

## La tensión clave: ADR vs. Ocupación

El arte del revenue management es **balancear precio y ocupación**. Un ADR muy alto con
ocupación baja puede rendir menos que un ADR moderado con ocupación alta. Ejemplo:

- Hotel A: ADR USD 300 × 50% ocupación → **RevPAR USD 150**
- Hotel B: ADR USD 250 × 80% ocupación → **RevPAR USD 200**

El hotel B factura más por habitación disponible aunque cobre menos por noche. Por eso **RevPAR
es mejor brújula que mirar ADR u ocupación por separado**.

## Indicadores avanzados (visión de rentabilidad total)

### TRevPAR — Total Revenue per Available Room
Ingreso TOTAL del hotel (no solo habitaciones: incluye restaurante, bar, estacionamiento,
spa, etc.) por habitación disponible.

```
TRevPAR = Ingreso total del hotel / Habitaciones disponibles
```
Útil cuando el hotel tiene servicios adicionales: muestra cuánto aporta cada habitación más
allá del alojamiento. No descuenta costos.

### GOPPAR — Gross Operating Profit per Available Room
Ganancia operativa bruta (ingresos menos gastos operativos) por habitación disponible.
Definido por HSMAI. Es el indicador que conecta las decisiones comerciales con la
**rentabilidad real**, porque sí considera los costos.

```
GOPPAR = Gross Operating Profit (GOP) / Habitaciones disponibles
```
A diferencia de RevPAR y TRevPAR (que miran solo ingreso), GOPPAR refleja la salud financiera
y la eficiencia operativa.

### RevPASH — Revenue per Available Seat Hour
Para puntos de venta de F&B (restaurante): ingreso por asiento disponible por hora. Mide la
eficiencia del restaurante, no de las habitaciones.

## Cómo interpretarlos (no dar el número "pelado")

- **Comparar siempre contra un referente**: el mismo período del año anterior, el presupuesto,
  o la temporada (un 60% de ocupación es malo en alta temporada y excelente en baja).
- **Mirar la tendencia**, no solo el valor puntual: ¿el RevPAR sube o baja respecto al mes pasado?
- **Cruzar las tres**: si la ocupación sube pero el RevPAR no, probablemente se está bajando
  demasiado el precio (canibalizando ADR).
- **Subir de RevPAR a GOPPAR cuando se pueda**: vender más no sirve si cada venta cuesta
  demasiado (comisiones de OTA, costos operativos). La rentabilidad vive en GOPPAR.

## Aplicación práctica para un hotel chico

1. Medir RevPAR, ocupación y ADR **a diario** (resultados pasados y reservas on-the-books a futuro).
2. Empezar por RevPAR como número guía; sumar TRevPAR si hay restaurante/servicios con ingreso relevante.
3. Estimar GOPPAR al menos mensual para no confundir "facturar mucho" con "ganar".

## Fuentes

- Xotels — Hotel KPI (RevPAR, GOPPAR, TRevPAR, RevPASH): https://www.xotels.com/en/revenue-management/revenue-management-book/hotel-kpi
- AltexSoft — RevPAR, Occupancy, ADR and other hotel metrics: https://www.altexsoft.com/blog/revpar-occupancy-rate-adr-hotel-metrics/
- Mews — RevPAR vs ADR: https://www.mews.com/en/blog/revpar-vs-adr
- RevPARGenius — RevPAR, GOPPAR, RGI, MPI explained: https://revpargenius.com/insights/revpar-goppar-rgi-mpi-hotel-metrics
- Key Data — The Big Three: Occupancy, ADR and RevPAR: https://www.keydatadashboard.com/blog/the-big-three-occupancy-adr-and-revpar
- RoomPriceGenie — RevPAR vs TRevPAR vs GOPPAR: https://roompricegenie.com/revpar-vs-trevpar-vs-goppar/
