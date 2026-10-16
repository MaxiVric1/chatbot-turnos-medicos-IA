# Sistema de Gestión de Turnos Médicos

Chatbot para reservar y administrar turnos médicos. Funciona de dos formas, con la misma lógica y los mismos datos:

- **En la terminal** (`chatbot.py`): Python puro, sin librerías externas.
- **En Telegram** (`telegram_bot.py`): el bot [@GestionTurnosMedicosIA_bot](https://t.me/GestionTurnosMedicosIA_bot).

## Qué se puede hacer

1. **Reservar un turno:** se ingresa el DNI y se elige la especialidad, el médico (o "Cualquier médico disponible"), el día y la hora. Al confirmar, se entrega un código de confirmación de 8 caracteres.
2. **Cancelar un turno.**
3. **Ver mis turnos:** muestra los turnos de hoy en adelante.
4. **Modificar un turno:** permite cambiar de médico u horario dentro de la misma especialidad. El código de confirmación se mantiene.
5. **Historial de turnos:** muestra los turnos de días anteriores.

Reglas:

- El DNI debe tener solo números, de 7 u 8 dígitos.
- Si la persona tiene un turno para el día siguiente, se le muestra un recordatorio al ingresar su DNI.
- Una misma persona no puede tener dos turnos el mismo día con menos de 1 hora de diferencia.
- Los turnos disponibles se calculan cada vez que se usa el programa, para las próximas 3 semanas. No se ofrecen horarios que ya pasaron ni horarios reservados.

## Archivos

| Archivo | Contenido |
|---|---|
| `chatbot.py` | Lógica del sistema y versión de terminal. |
| `telegram_bot.py` | Versión de Telegram, que usa la lógica de `chatbot.py`. |
| `datos.json` | Base de datos: especialidades, médicos con sus días y horas de atención, y turnos reservados. |
| `token_telegram.txt` | Token del bot de Telegram. **No se sube al repositorio**, ver más abajo. |

## Requisitos

- Python 3.10 o superior.
- Solo para Telegram: la librería [python-telegram-bot](https://python-telegram-bot.org/).

## Instalación

```bash
git clone <url-del-repositorio>
cd <carpeta-del-proyecto>

# Solo si se va a usar la versión de Telegram
python -m pip install python-telegram-bot
```

## Cómo correrlo

### Terminal

```bash
python chatbot.py
```

Para elegir cada opción se escribe su número. Con `0` se vuelve atrás y con `Ctrl+C` se sale.

### Telegram

1. Configurar el token del bot, de una de estas dos formas:
   - Crear un archivo `token_telegram.txt` junto a `telegram_bot.py`, con el token como único contenido.
   - O definir la variable de entorno `TELEGRAM_BOT_TOKEN`:
     ```bash
     # Windows (PowerShell)
     $env:TELEGRAM_BOT_TOKEN = "TU_TOKEN"
     # Linux / macOS
     export TELEGRAM_BOT_TOKEN="TU_TOKEN"
     ```
   El token se obtiene de [@BotFather](https://t.me/BotFather) en Telegram.
2. Iniciar el bot:
   ```bash
   python telegram_bot.py
   ```
3. En Telegram, abrir el bot y escribir `/start`. Las opciones aparecen como botones, y también se puede responder con el número de la opción. Con `/menu` se vuelve al menú principal.

El bot responde mientras `telegram_bot.py` esté corriendo. Para detenerlo, usar `Ctrl+C`.

## Datos

Todos los datos de `datos.json` (médicos, matrículas, DNIs y reservas) son ficticios y se usan solo como ejemplo.

Para agregar o cambiar un médico, editar su entrada en `datos.json`:

```json
{
  "id": 1,
  "nombre": "Dra. Laura Fernández",
  "especialidad_id": 1,
  "matricula": "MN-10450",
  "dias_atencion": ["Lunes", "Miércoles", "Viernes"],
  "horas_atencion": ["08:00", "08:30", "09:00"]
}
```

## Seguridad

`token_telegram.txt` está incluido en `.gitignore` para que el token no se suba al repositorio. Quien tenga el token puede controlar el bot. Si se llega a publicar, hay que generar uno nuevo con `/revoke` en @BotFather.
