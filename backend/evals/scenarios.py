"""
Escenarios de evaluación del agente Aura — derivados de cómo un USUARIO REAL rompe el agente.

Cada escenario es una conversación multi-turno. Cada turno tiene:
  - user:  el mensaje del usuario (con typos, charla informal, varias preguntas, etc. — a
           propósito; así prueba como un huésped real, no como un test de camino feliz).
  - expect: aserciones determinísticas (todas opcionales). Claves soportadas:
       route                 "preventa" | "casual" | "postsale"  (rama del flujo)
       tool_called           str | [str]   tool(s) que DEBEN invocarse este turno
       tool_not_called       str | [str]   tool(s) que NO deben invocarse
       card                  str | [str]   tipo(s) de card que DEBE adjuntarse
       no_card               str | [str]   tipo(s) de card que NO debe adjuntarse
       response_contains     str | [str]   substring(s) que la respuesta DEBE contener (case-insensitive)
       response_not_contains str | [str]   substring(s) PROHIBIDOS en la respuesta
       price_from_tool       True          todo "USD X" en la respuesta debe ser un precio que
                                            una tool (consultar_disponibilidad/calcular_precio_promo)
                                            devolvió en el escenario — detecta precios inventados

Tipos de card: "room", "date_picker", "menu_interactive", "table_reservation".
Tools del hotel: consultar_disponibilidad, crear_reserva, consultar_reserva, info_hotel,
  info_pago, como_llegar, promos_vigentes, calcular_precio_promo, ver_carta,
  armar_pedido_carta, reservar_mesa, comprar_voucher.

Cada escenario puede declarar `session_prefix` (ej. "wa_549..." para simular WhatsApp).
"""

# Fechas futuras estables para los escenarios (evitan "la fecha ya pasó").
CI = "2026-08-20"   # check-in
CO = "2026-08-24"   # check-out


SCENARIOS = [
    {
        "id": "S1",
        "name": "Reserva web con charla informal previa",
        "turns": [
            {"user": "Holalala! cómo andás? todo bien por ahí?",
             "expect": {"route": "casual", "no_card": ["room", "menu_interactive"]}},
            {"user": "Todo bien, acá mirando una serie. Y me agarraron ganas de escaparme a Barilocheee!",
             "expect": {"route": "preventa"}},
            {"user": f"Dale, fijate disponibilidad del {CI} al {CO} para 2 adultos.",
             "expect": {"tool_called": "consultar_disponibilidad", "card": "room",
                        "no_card": "date_picker"}},
            {"user": "Quiero reservar la King.",
             "expect": {"no_card": "menu_interactive",
                        "response_not_contains": ["no disponible"]}},
        ],
    },
    {
        "id": "S2",
        "name": "Varias preguntas en un solo mensaje",
        "turns": [
            {"user": "Buenas! a qué hora es el check-in, el desayuno está incluido, y ahh tienen estacionamiento?",
             "expect": {"tool_called": "info_hotel",
                        "response_not_contains": ["no tengo información"]}},
        ],
    },
    {
        "id": "S3",
        "name": "¿La promo aplica a mis fechas? (no afirmar sin verificar)",
        "turns": [
            {"user": f"Hola! disponibilidad del {CI} al {CO} para 2 adultos por favor.",
             "expect": {"tool_called": "consultar_disponibilidad", "card": "room"}},
            {"user": "Buenísimo. Y la promo de estacionamiento, aplica para esas fechas?",
             "expect": {"route": "preventa",
                        "tool_called": ["promos_vigentes", "calcular_precio_promo"]}},
        ],
        "tool_called_any": True,  # con que llame UNA de las dos de promo, OK
    },
    {
        "id": "S4",
        "name": "Referencia a turno previo: no re-ofrecer disponibilidad",
        "turns": [
            {"user": f"Disponibilidad del {CI} al {CO} para 2 adultos.",
             "expect": {"tool_called": "consultar_disponibilidad"}},
            {"user": "ya te di las fechas más arriba... otra vez vas a chequear?",
             "expect": {"no_card": "date_picker",
                        "response_not_contains": ["¿querés que vea la disponibilidad",
                                                  "querés que chequee la disponibilidad"]}},
        ],
    },
    {
        "id": "S5",
        "name": "Mesa 'la noche' = cena (no 'no disponible')",
        "turns": [
            {"user": f"Quiero reservar una mesa la noche del {CI} para 2 personas, una cena romántica.",
             "expect": {"tool_called": "reservar_mesa", "card": "table_reservation",
                        "response_not_contains": ["no disponible", "no hay turno"]}},
        ],
    },
    {
        "id": "S6",
        "name": "Acuse de confirmación de mesa (felicitar, no pedir HTL-)",
        "turns": [
            {"user": "Confirmé mi reserva de mesa MESA-TEST.",
             "expect": {"route": "casual",
                        "response_not_contains": ["HTL-", "formato HTL"]}},
        ],
    },
    {
        "id": "S7",
        "name": "WhatsApp: no pedir teléfono (ya lo tiene de la sesión)",
        "session_prefix": "wa_5491155551234",
        "turns": [
            {"user": f"Hola! disponibilidad del {CI} al {CO} para 2 adultos.",
             "expect": {"tool_called": "consultar_disponibilidad"}},
            {"user": "Reservo la King. Soy Cristian Juárez.",
             "expect": {"response_not_contains": ["tu número de teléfono", "un teléfono de contacto",
                                                  "me pasás tu teléfono"]}},
        ],
    },
    {
        "id": "S8",
        "name": "Precio no inventado al confirmar habitación tras varios turnos",
        "turns": [
            {"user": f"Disponibilidad del {CI} al {CO} para 1 adulto.",
             "expect": {"tool_called": "consultar_disponibilidad"}},
            {"user": "Antes de decidir, tenés info de excursiones al Cerro Catedral?",
             "expect": {"tool_called": "info_hotel"}},
            {"user": "Bueno, me quedo con la King. Cuánto era el total?",
             "expect": {"response_not_contains": ["no disponible"],
                        "price_from_tool": True}},  # el precio que diga debe ser el REAL de la tool
        ],
    },
    {
        "id": "S9",
        "name": "No listar habitaciones con guiones en el texto",
        "turns": [
            {"user": f"Hola, qué habitaciones tenés del {CI} al {CO} para 2 adultos?",
             "expect": {"tool_called": "consultar_disponibilidad", "card": "room",
                        "response_not_contains": ["- King", "- Twin", "• King"]}},
        ],
    },
    {
        "id": "S10",
        "name": "Carta del restaurante (caso legítimo: SÍ debe aparecer)",
        "turns": [
            {"user": "Hola! me mostrás la carta del restaurante?",
             "expect": {"card": "menu_interactive"}},
        ],
    },
    {
        "id": "S11",
        "name": "Saludo puro = casual, sin tools ni cards",
        "turns": [
            {"user": "Holaaa, cómo va todo? buen lunes!",
             "expect": {"route": "casual", "no_card": ["room", "date_picker", "menu_interactive"],
                        "tool_not_called": ["consultar_disponibilidad", "crear_reserva"]}},
        ],
    },
    {
        "id": "S12",
        "name": "Off-topic / tarea ajena: casual, no la resuelve",
        "turns": [
            {"user": "che, cuánto es 248 por 17?",
             "expect": {"route": "casual", "response_not_contains": ["4216"]}},
        ],
    },
    {
        "id": "S13",
        "name": "Cambio de contexto: reserva hotel y luego mesa",
        "turns": [
            {"user": f"Reservá la King del {CI} al {CO} para 2 adultos. Soy Ana López, mi tel 1133334444.",
             "expect": {"tool_called": "crear_reserva", "tool_not_called": "reservar_mesa"}},
            {"user": "Genial! y reservame también una mesa para cenar el primer día.",
             "expect": {"tool_called": "reservar_mesa", "card": "table_reservation",
                        "tool_not_called": "consultar_disponibilidad"}},
        ],
    },
    {
        "id": "S14",
        "name": "Datos de contacto en desorden, todo junto",
        "turns": [
            {"user": f"Quiero la Twin del {CI} al {CO} para 2.",
             "expect": {"tool_called": ["consultar_disponibilidad", "crear_reserva"]}},
            {"user": "te paso los datos: lucas modric, mail lucas@mail.com, cel 11 5566 7788",
             "expect": {"tool_called": "crear_reserva",
                        "response_contains": ["HTL-"]}},
        ],
        "tool_called_any": True,
    },
    {
        "id": "S15",
        "name": "Pedido de comida por texto (precarga la carta)",
        "turns": [
            {"user": "tienen para comer algo? se me antojan unas milanesas napolitanas",
             "expect": {"card": "menu_interactive"}},
        ],
    },
    {
        "id": "S18",
        "name": "Post-venta tras reservar: no re-pedir código + acciones reales",
        "turns": [
            {"user": f"Reservá la Twin del {CI} al {CO} para 2 adultos. Soy Raúl Tarufetti, tel 3415612451, mail wg@wigou.co.",
             "expect": {"tool_called": "crear_reserva", "response_contains": ["HTL-"]}},
            {"user": "¿qué puedo hacer con este código?",
             # No debe re-pedir el código (lo creó en la sesión) ni prometer autoservicio falso.
             "expect": {"response_not_contains": ["formato HTL-XXXX", "check-in rápido",
                                                  "check in rápido", "modificar la reserva online",
                                                  "cancelar online"]}},
        ],
    },
    {
        "id": "S19",
        "name": "Post-venta: servicios sin inventar (no sauna/spa)",
        "tool_called_any": True,  # con que llame UNA tool de info (consultar_info_hotel o info_hotel)
        "turns": [
            {"user": f"Reservá la King del {CI} al {CO} para 2 adultos. Soy Ana Gómez, tel 1166667777.",
             "expect": {"tool_called": "crear_reserva"}},
            {"user": "qué servicios adicionales tengo?",
             # Debe consultar info (post-venta usa consultar_info_hotel; pre-venta usa info_hotel)
             # y NUNCA inventar spa/sauna. (palabra completa: "spa" no debe matchear "espacio")
             "expect": {"tool_called": ["consultar_info_hotel", "info_hotel"],
                        "response_not_contains_word": ["sauna", "spa"]}},
        ],
    },
    {
        "id": "S20",
        "name": "Post-venta: pedir un servicio inexistente (sauna) — honestidad sin contradicción",
        "tool_called_any": True,  # el T1 es setup: vale consultar disp o reservar directo
        "turns": [
            {"user": f"Reservá la King del {CI} al {CO} para 2 adultos. Soy Leo Díaz, tel 1144445555.",
             "expect": {"tool_called": ["crear_reserva", "consultar_disponibilidad"]}},
            {"user": "quiero reservar un turno en el sauna",
             # Debe ser honesta: NO confirmar un sauna que no existe (puede nombrarlo para negarlo).
             "expect": {"response_not_contains": ["te reservo el sauna", "turno de sauna confirmado",
                                                  "reservé tu turno", "tu turno de sauna"]}},
        ],
    },
    {
        "id": "S21",
        "name": "Post-venta: fotos de la habitación reservada (muestra card)",
        "turns": [
            {"user": f"Reservá la Twin del {CI} al {CO} para 2 adultos. Soy Sol Ruiz, tel 1155556666.",
             "expect": {"tool_called": "crear_reserva"}},
            {"user": "me mostrás fotos de la habitación que reservé?",
             "expect": {"tool_called": "ver_fotos_habitacion", "card": "room_photos",
                        "response_not_contains": ["no tengo acceso a imágenes",
                                                  "no tengo acceso a fotos"]}},
        ],
    },
    {
        "id": "S22",
        "name": "Declara alergia tras reservar (la registra, no proyecta recurrencia)",
        "tool_called_any": True,  # post-venta: registrar_preferencia; pre-venta: guardar_preferencia
        "turns": [
            {"user": f"Reservá la Twin del {CI} al {CO} para 2 adultos. Soy Tomás Vega, tel 1177778888.",
             "expect": {"tool_called": ["crear_reserva"]}},
            {"user": "me olvidé de decirte que soy alérgico al maní",
             "expect": {"tool_called": ["registrar_preferencia", "guardar_preferencia"],
                        "response_not_contains": ["de siempre", "de vuelta", "tenerte de vuelta"]}},
        ],
    },
    {
        "id": "S23",
        "name": "Preferencia dietética tras reservar (se guarda)",
        "tool_called_any": True,
        "turns": [
            {"user": f"Reservá la King del {CI} al {CO} para 2 adultos. Soy Vera Sosa, tel 1188889999.",
             "expect": {"tool_called": ["crear_reserva"]}},
            {"user": "ah, soy vegetariana, tenelo en cuenta",
             "expect": {"tool_called": ["registrar_preferencia", "guardar_preferencia"]}},
        ],
    },
    {
        "id": "S24",
        "name": "Mesa 'el primer día de mi estadía' usa el check-in de la reserva (no fecha random)",
        "turns": [
            {"user": f"Reservá la Twin del {CI} al {CO} para 2 adultos. Soy Bruno Lima, tel 1166660001.",
             "expect": {"tool_called": "crear_reserva"}},
            {"user": "quiero reservar una mesa para cenar el primer día de mi estadía",
             # La mesa debe usar la fecha del CHECK-IN (CI), no hoy ni otra fecha.
             "expect": {"tool_called": "reservar_mesa", "card": "table_reservation",
                        "response_contains": [CI[-2:]]}},  # menciona el día del check-in
        ],
    },
    {
        "id": "S25",
        "name": "Restaurante disponible en post-venta (huésped reconocido por sesión)",
        "turns": [
            {"user": f"Reservá la King del {CI} al {CO} para 2 adultos. Soy Carla Ortiz, tel 1166660002.",
             "expect": {"tool_called": "crear_reserva"}},
            {"user": "me mostrás la carta del restaurante?",
             "expect": {"route": "postsale", "tool_called": "ver_carta", "card": "menu_interactive"}},
        ],
    },
    {
        "id": "S17",
        "name": "Charla casual NO dispara la carta (página≠gin Athos)",
        "turns": [
            {"user": "Holala, qué tal todo por Bariloche? mucho frío?",
             "expect": {"route": "casual", "no_card": "menu_interactive"}},
            {"user": "Bien, en una call de trabajo. Trabajo en Wigou, te paso la página web?",
             "expect": {"route": "casual", "no_card": "menu_interactive"}},
        ],
    },
    {
        "id": "S16",
        "name": "Familia + llegada al aeropuerto: traslado verificado con tool (no de memoria)",
        "turns": [
            {"user": f"Hola! disponibilidad del {CI} al {CO} para 2 adultos, 1 niño y 1 bebé en cuna.",
             # Al recomendar para familia con bebé, mencionar que el bebé no ocupa plaza.
             "expect": {"tool_called": "consultar_disponibilidad", "card": "room",
                        "response_contains": ["cuna"]}},
            {"user": "El Family Plan me interesa. Vamos a estar llegando al aeropuerto a las 9 de la mañana.",
             # El traslado SÍ existe (proveedor amigo con tarifa preferencial), pero Aura debe
             # CONSULTARLO con info_hotel, no responder de memoria.
             "expect": {"tool_called": "info_hotel"}},
        ],
    },
]
