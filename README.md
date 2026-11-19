# PVPC Plug Cost

Integración personalizada para Home Assistant que calcula el coste variable de la energía consumida por un enchufe inteligente usando el precio horario PVPC de España.

Crea, para cada enchufe, sensores de coste y energía con acumulado diario y por periodo de facturación.

## Características

- Una entrada de integración por enchufe; puedes añadir tantos como quieras.
- Sensores independientes por enchufe, agrupados bajo el dispositivo del enchufe.
- Coste diario y coste del periodo de facturación.
- Energía diaria y energía del periodo de facturación (kWh).
- Día de facturación configurable, con ajuste automático a meses de 28, 29, 30 o 31 días.
- Sensor opcional de coste instantáneo en €/h, deshabilitado por defecto.
- Persistencia de los acumulados tras reinicios de Home Assistant, con guardado periódico (cada minuto como máximo) y al apagar.
- Compatible con estadísticas de largo plazo y con el Dashboard de Energía.

## Requisitos

- Home Assistant `2025.8.0` o posterior.
- Para tarifa PVPC, la integración oficial [PVPC Hourly Pricing](https://www.home-assistant.io/integrations/pvpc_hourly_pricing/) configurada, normalmente con el sensor `sensor.esios_pvpc`.
- Un enchufe inteligente que exponga un sensor de potencia en W o kW.

## Fuente del precio

La integración no consulta ESIOS directamente. Lee el precio actual del sensor creado por la integración oficial [PVPC Hourly Pricing](https://www.home-assistant.io/integrations/pvpc_hourly_pricing/), normalmente `sensor.esios_pvpc`.

Para una tarifa fija se puede usar un `input_number` con unidad `€/kWh`; en ese caso no es necesario tener configurada la integración oficial.

## Instalación con HACS

1. En HACS, abre **Integraciones** y añade como repositorio personalizado `https://github.com/ryosoftware/pvpc_plug_cost`.
2. Selecciona la categoría **Integration**.
3. Instala **PVPC Plug Cost** y reinicia Home Assistant.

## Instalación manual

Copia la carpeta `custom_components/pvpc_plug_cost` dentro de la carpeta `custom_components` de tu configuración de Home Assistant y reinicia.

```text
/config/custom_components/pvpc_plug_cost/
```

## Configuración

1. Ve a **Ajustes → Dispositivos y servicios → Añadir integración**.
2. Busca **PVPC Plug Cost**.
3. Indica:
   - Nombre, por ejemplo `Lavadora`.
   - Sensor de potencia del enchufe, en W o kW.
   - Sensor de precio PVPC, por ejemplo `sensor.esios_pvpc`. También se acepta un `input_number` con unidad `€/kWh` para usar una tarifa fija.
   - Día de facturación, de 1 a 31.
   - Intervalo de muestreo, por defecto 60 segundos.
4. Repite el proceso para cada enchufe adicional.

El día de facturación determina cuándo se reinicia el contador mensual. Si eliges un día que no existe en un mes concreto, se usa el último día de ese mes.

### Tarifa fija

Si no usas PVPC, crea un helper `input_number` con la tarifa en `€/kWh` y selecciónalo como entidad de precio. La integración valida la unidad y usa su valor actual para calcular el coste.

## Entidades creadas

Para una entrada llamada `Lavadora`:

| Entidad | Descripción |
|---|---|
| `sensor.lavadora_cost_hour` | Coste variable acumulado en la hora en curso |
| `sensor.lavadora_energy_hour` | Energía acumulada en la hora en curso |
| `sensor.lavadora_cost_last_hour` | Coste variable de la última hora completa |
| `sensor.lavadora_energy_last_hour` | Energía de la última hora completa |
| `sensor.lavadora_cost_today` | Coste variable acumulado hoy |
| `sensor.lavadora_cost_month` | Coste variable del periodo de facturación |
| `sensor.lavadora_energy_today` | Energía acumulada hoy |
| `sensor.lavadora_energy_month` | Energía del periodo de facturación |
| `sensor.lavadora_cost_year` | Coste variable acumulado en el año en curso |
| `sensor.lavadora_energy_year` | Energía acumulada en el año en curso |
| `sensor.lavadora_energy_total` | Energía total acumulada desde la instalación |
| `sensor.lavadora_cost_total` | Coste variable total acumulado desde la instalación |
| `sensor.lavadora_cost_rate` | Coste instantáneo €/h, deshabilitado por defecto |

El prefijo depende del nombre del dispositivo. Los `entity_id` usan claves en inglés (`cost_today`, `energy_total`, etc.) para que sean estables e independientes del idioma de Home Assistant; los nombres visibles sí se traducen. Las entradas creadas con versiones anteriores conservan los `entity_id` que ya tenían.

`cost_last_hour` y `energy_last_hour` muestran la hora de reloj anterior: a las 10:25, el periodo de 09:00 a 10:00. Solo avanzan cuando Home Assistant observa el cambio de hora mientras está funcionando; si estuvo parado al cruzar la hora, conservan la última hora que sí se completó en marcha. El atributo `last_hour_start` indica el inicio del periodo mostrado.

Cada sensor incluye atributos de diagnóstico: entidad de potencia, entidad de precio, potencia actual, precio actual, coste instantáneo, día de facturación, estado, última muestra e inicio de la última hora completa.

## Dashboard de Energía

Los sensores recomendados para el Dashboard son `energy_total` y `cost_total`, porque son acumulados monotónicos y no se reinician. Los sensores de energía y coste por hora, última hora, día, periodo de facturación y año son informativos y no generan estadísticas de largo plazo. Si actualizas desde una versión anterior, Home Assistant puede mostrar un aviso `state_class_removed` para esos sensores; es esperado.

## Cálculo

Para cada intervalo entre muestras:

```text
energía = potencia media (kW) × tiempo (h)
coste   = energía (kWh) × precio PVPC (€/kWh)
```

La potencia se integra con método trapezoidal. Los intervalos se dividen en los cambios de hora, medianoche y inicio del periodo de facturación para asignar correctamente energía y coste a cada contador.

Los acumulados empiezan a contar desde el momento en que se configura la integración. No se reconstruye el consumo anterior a la instalación. Tras actualizar a una versión con acumulados horarios, anuales o totales, estos empiezan en cero y no reconstruyen periodos anteriores.

## Limitaciones

- El coste calculado es **solo el término variable de energía PVPC**. No incluye impuestos, peajes, término de potencia, alquiler de contador ni otros cargos fijos.
- La precisión depende de la frecuencia con la que el enchufe actualiza la potencia y del intervalo de muestreo.
- La potencia se interpola linealmente entre lecturas. Si el enchufe solo informa cambios, el coste puede sobreestimarse o subestimarse ligeramente.
- No se recupera el consumo ocurrido mientras Home Assistant o el enchufe estuvieron desconectados.
- No se crea un sensor de total agregado de varios enchufes. Si lo necesitas, puedes crear un sensor de plantilla que sume los sensores de coste individuales.

## Desarrollo y pruebas

Las pruebas del cálculo puro no necesitan Home Assistant:

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas de integración usan el arnés oficial de Home Assistant:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Validación básica de sintaxis:

```bash
python3 -m compileall custom_components
```

## Licencia

MIT.

## Home Assistant URL única: 

https://my.home-assistant.io/redirect/marketplace_repository/?owner=ryosoftware&repository=https%3A%2F%2Fgithub.com%2Fryosoftware%2Fpvpc_plug_cost&category=integration
