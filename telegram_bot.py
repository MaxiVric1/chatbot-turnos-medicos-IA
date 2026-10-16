"""
Bot de Telegram para la gestión de turnos médicos (@GestionTurnosMedicosIA_bot).

Reutiliza la lógica y los datos de chatbot.py: mismo menú y mismo flujo
(DNI → especialidad → médico → día → hora → confirmación), pero con botones.
También se puede responder escribiendo el número de la opción, igual que en
la terminal.

Uso:
    python telegram_bot.py

El token se lee de la variable de entorno TELEGRAM_BOT_TOKEN o, si no está
definida, del archivo token_telegram.txt (junto a este script).
"""

import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import chatbot as cb

ARCHIVO_TOKEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_telegram.txt")

BIENVENIDA = "\n".join(linea.strip() for linea in cb.MENSAJE_BIENVENIDA.splitlines())
ENCABEZADO_MENU = "¿Qué querés hacer?"
OPCIONES_MENU = [
    ("reservar", "Reservar un turno"),
    ("cancelar", "Cancelar un turno"),
    ("ver", "Ver mis turnos"),
    ("modificar", "Modificar un turno"),
    ("historial", "Historial de turnos"),
    ("salir", "Salir"),
]
VOLVER_MENU = ("🏠 Menú principal", "nav:menu")
VOLVER_DIAS = ("⬅️ Elegir otro día", "nav:dias")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.WARNING)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Motor de la conversación
#
# Cada respuesta es una tupla (texto, botones), donde botones es una lista de
# (etiqueta, dato) o None. El estado de cada usuario es un diccionario que
# guarda en qué paso está y lo que eligió hasta el momento.
# ---------------------------------------------------------------------------

def ofrecer(estado, paso, texto, opciones, volver=VOLVER_MENU):
    """Muestra opciones numeradas como botones y recuerda cuáles son válidas."""
    estado["paso"] = paso
    estado["opciones"] = [dato for _, dato in opciones]
    estado["volver"] = volver[1] if volver else None
    botones = [(f"{i}. {etiqueta}", dato) for i, (etiqueta, dato) in enumerate(opciones, start=1)]
    if volver:
        botones.append((f"0. {volver[0]}", volver[1]))
    return texto, botones


def menu(estado, encabezado=ENCABEZADO_MENU):
    estado.clear()
    return ofrecer(estado, "menu", encabezado,
                   [(texto, f"m:{accion}") for accion, texto in OPCIONES_MENU], volver=None)


def traducir_numero(estado, texto):
    """Convierte un número escrito por el usuario en el dato del botón equivalente."""
    if not texto.isdigit():
        return None
    n = int(texto)
    if n == 0:
        return estado.get("volver")
    if 1 <= n <= len(estado.get("opciones", [])):
        return estado["opciones"][n - 1]
    return None


def manejar(estado, tipo, valor):
    """
    Recibe lo que mandó el usuario (tipo "texto" o "boton") y devuelve la lista
    de respuestas a enviar.
    """
    valor = valor.strip()
    paso = estado.get("paso")
    if paso is None and tipo == "boton" and valor.startswith("m:"):
        # Botón de un menú anterior (por ejemplo, después de reiniciar el bot): se acepta igual
        menu(estado)
        paso = "menu"
    elif paso is None or (tipo == "texto" and valor.lower() in ("hola", "menu", "menú", "inicio")):
        return [menu(estado, BIENVENIDA)]

    if tipo == "texto" and paso != "dni":
        dato = traducir_numero(estado, valor)
        if dato is None:
            minimo = 0 if estado.get("volver") else 1
            return [(f"No entendí esa opción. Tocá uno de los botones o escribí un número "
                     f"del {minimo} al {len(estado['opciones'])}.", None)]
        valor = dato
    elif tipo == "boton" and valor not in estado.get("opciones", []) and valor != estado.get("volver"):
        return [("⚠️ Esa opción ya no está vigente. Volvamos al menú.", None), menu(estado)]

    if valor == "nav:menu":
        return [menu(estado)]
    if valor == "nav:dias":
        return ofrecer_dias(estado, cb.cargar_datos())
    return PASOS[paso](estado, valor)


# --- Utilidades del motor --------------------------------------------------

def turno_del_usuario(datos, estado):
    """El turno elegido, si sigue existiendo y es del DNI ingresado."""
    for t in cb.turnos_de(datos, estado["dni"]):
        if t["id"] == estado.get("turno_id"):
            return t
    return None


def horarios_elegibles(estado, datos):
    """
    Horarios que se pueden elegir con el médico seleccionado, o con todos los de
    la especialidad si se eligió "Cualquier médico disponible". Al modificar, si
    el médico actual está entre los elegidos, se incluye el horario actual para
    poder mantenerlo.
    Devuelve (con_quien, horarios, actual, combinado).
    """
    combinado = estado["medico_id"] == "todos"
    if combinado:
        especialidad = cb.buscar_por_id(datos["especialidades"], estado["esp_id"])
        medicos = [m for m in datos["medicos"] if m["especialidad_id"] == especialidad["id"]]
        con_quien = f"cualquier médico de {especialidad['nombre']}"
    else:
        medicos = [cb.buscar_por_id(datos["medicos"], estado["medico_id"])]
        con_quien = medicos[0]["nombre"]

    horarios = cb.horarios_libres(medicos)
    actual = None
    if estado["accion"] == "modificar":
        turno = turno_del_usuario(datos, estado)
        if turno and any(m["id"] == turno["medico_id"] for m in medicos):
            actual = (turno["medico_id"], turno["fecha"], turno["hora"])
            horarios.append({"medico_id": turno["medico_id"], "fecha": turno["fecha"], "hora": turno["hora"]})
    return con_quien, horarios, actual, combinado


def horario_elegido(estado):
    return {"medico_id": estado["medico_turno"], "fecha": estado["fecha"], "hora": estado["hora"]}


def etiqueta_dia(datos, fecha, horarios, actual=None, combinado=False):
    """
    Botón de un día. Con "Cualquier médico disponible" se nombra a los médicos
    que atienden ese día (solo el apellido, para que el botón no quede largo).
    """
    if not combinado:
        return cb.texto_dia(datos, fecha, horarios, actual)
    ids = {h["medico_id"] for h in horarios if h["fecha"] == fecha}
    apellidos = sorted(cb.buscar_por_id(datos["medicos"], i)["nombre"].split()[-1] for i in ids)
    texto = f"{cb.formatear_dia(fecha)} · {' y '.join(apellidos)}"
    if actual and actual[1] == fecha:
        texto += " ← tu turno actual"
    return texto


def etiqueta_turno(datos, turno):
    """Versión corta de un turno para que entre en un botón."""
    especialidad = cb.buscar_por_id(datos["especialidades"], turno["especialidad_id"])
    dia_mes = f"{turno['fecha'][8:10]}/{turno['fecha'][5:7]}"
    return f"#{turno['id']} · {dia_mes} {turno['hora']} · {especialidad['nombre']}"


# --- Pasos -----------------------------------------------------------------

def paso_menu(estado, valor):
    accion = valor.split(":", 1)[1]
    if accion == "salir":
        estado.clear()
        return [("¡Gracias por comunicarte! Que tengas un buen día. 👋\n"
                 "Cuando quieras volver, escribí /start.", None)]
    estado["accion"] = accion
    estado["paso"] = "dni"
    estado["opciones"] = []
    estado["volver"] = VOLVER_MENU[1]
    return [("Por favor, ingresá tu DNI (solo números, sin puntos).", [VOLVER_MENU])]


def paso_dni(estado, valor):
    dni = valor.replace(".", "").replace(" ", "")
    if not cb.dni_valido(dni):
        return [("Ese DNI no es válido. Tiene que tener solo números y entre 7 y 8 dígitos. "
                 "Probá de nuevo.", [VOLVER_MENU])]
    estado["dni"] = dni
    datos = cb.cargar_datos()
    respuestas = [(aviso, None) for aviso in cb.textos_recordatorio(datos, dni)]

    accion = estado["accion"]
    if accion == "reservar":
        respuestas.append(ofrecer_especialidades(estado, datos))
    elif accion in ("cancelar", "modificar"):
        respuestas += ofrecer_turnos(estado, datos)
    elif accion == "ver":
        respuestas += ver_turnos(estado, datos)
    elif accion == "historial":
        respuestas += ver_historial(estado, datos)
    return respuestas


def ofrecer_especialidades(estado, datos):
    return ofrecer(estado, "especialidad", "¿Qué especialidad necesitás?",
                   [(e["nombre"], f"e:{e['id']}") for e in datos["especialidades"]])


def paso_especialidad(estado, valor):
    datos = cb.cargar_datos()
    especialidad = cb.buscar_por_id(datos["especialidades"], int(valor[2:]))
    medicos = [m for m in datos["medicos"]
               if m["especialidad_id"] == especialidad["id"] and any(h["disponible"] for h in m["horarios"])]
    if not medicos:
        return [(f"Lo siento, no hay turnos disponibles en {especialidad['nombre']} por el momento.", None),
                ofrecer_especialidades(estado, datos)]
    estado["esp_id"] = especialidad["id"]

    opciones = [(f"{m['nombre']} ({sum(h['disponible'] for h in m['horarios'])} libres)", f"d:{m['id']}")
                for m in medicos]
    if len(medicos) > 1:
        opciones.append((cb.OPCION_CUALQUIERA, "d:todos"))
    return [ofrecer(estado, "medico", "¿Con qué médico querés atenderte?", opciones)]


def ofrecer_turnos(estado, datos):
    turnos = cb.turnos_de(datos, estado["dni"])
    if not turnos:
        return [(f"No encontré turnos reservados para el DNI {estado['dni']}.", None), menu(estado)]
    verbo = "cancelar" if estado["accion"] == "cancelar" else "modificar"
    return [ofrecer(estado, "turno", f"¿Qué turno querés {verbo}?",
                    [(etiqueta_turno(datos, t), f"t:{t['id']}") for t in turnos])]


def paso_turno(estado, valor):
    datos = cb.cargar_datos()
    estado["turno_id"] = int(valor[2:])
    turno = turno_del_usuario(datos, estado)
    if turno is None:
        return [("Ese turno ya no existe.", None), menu(estado)]

    if estado["accion"] == "cancelar":
        return [ofrecer(estado, "confirmar",
                        f"¿Seguro que querés cancelar el turno {cb.describir_turno(datos, turno)}?",
                        [("✅ Sí, cancelar el turno", "c:si"), ("❌ No", "c:no")], volver=None)]

    # Modificar: elegir médico dentro de la misma especialidad
    especialidad = cb.buscar_por_id(datos["especialidades"], turno["especialidad_id"])
    estado["esp_id"] = especialidad["id"]
    opciones = []
    medicos = [m for m in datos["medicos"] if m["especialidad_id"] == especialidad["id"]]
    for m in medicos:
        libres = sum(h["disponible"] for h in m["horarios"])
        marca = " ← actual" if m["id"] == turno["medico_id"] else ""
        opciones.append((f"{m['nombre']} ({libres} libres){marca}", f"d:{m['id']}"))
    if len(medicos) > 1:
        opciones.append((cb.OPCION_CUALQUIERA, "d:todos"))
    return [ofrecer(estado, "medico", "¿Con qué médico querés atenderte?", opciones)]


def paso_medico(estado, valor):
    eleccion = valor[2:]
    estado["medico_id"] = "todos" if eleccion == "todos" else int(eleccion)
    return ofrecer_dias(estado, cb.cargar_datos())


def ofrecer_dias(estado, datos):
    con_quien, horarios, actual, combinado = horarios_elegibles(estado, datos)
    if not horarios:
        return [(f"No hay horarios disponibles con {con_quien}. Probá con otro profesional.", None),
                menu(estado)]
    fechas = sorted({h["fecha"] for h in horarios})
    opciones = [(etiqueta_dia(datos, f, horarios, actual, combinado), f"f:{f}") for f in fechas]
    return [ofrecer(estado, "dia", "¿Qué día querés atenderte?", opciones)]


def paso_dia(estado, valor):
    estado["fecha"] = valor[2:]
    return ofrecer_horas(estado, cb.cargar_datos())


def ofrecer_horas(estado, datos):
    _, horarios, actual, combinado = horarios_elegibles(estado, datos)
    del_dia = cb.horarios_del_dia(datos, horarios, estado["fecha"])
    if not del_dia:
        return [("Ese día ya no tiene horarios disponibles.", None)] + ofrecer_dias(estado, datos)
    opciones = [(cb.texto_hora(datos, h, actual, combinado), f"h:{h['medico_id']}:{h['hora']}") for h in del_dia]
    return [ofrecer(estado, "hora", "¿En qué horario querés atenderte?", opciones, volver=VOLVER_DIAS)]


def paso_hora(estado, valor):
    datos = cb.cargar_datos()
    _, medico_id, hora = valor.split(":", 2)
    elegido = {"medico_id": int(medico_id), "fecha": estado["fecha"], "hora": hora}
    _, horarios, actual, _ = horarios_elegibles(estado, datos)
    modificando = estado["accion"] == "modificar"

    if elegido not in horarios:
        return [("Ese horario ya no está disponible.", None)] + ofrecer_horas(estado, datos)
    if modificando and actual == cb.clave_horario(elegido):
        return [("No hiciste ningún cambio: elegiste el mismo médico y el mismo horario.", None), menu(estado)]
    fecha = elegido["fecha"]
    conflicto = cb.buscar_conflicto(datos, estado["dni"], fecha, hora,
                                    excluir_id=estado.get("turno_id") if modificando else None)
    if conflicto:
        return [(cb.texto_conflicto(datos, conflicto), None)] + ofrecer_horas(estado, datos)

    estado["hora"] = hora
    estado["medico_turno"] = elegido["medico_id"]
    medico = cb.buscar_por_id(datos["medicos"], elegido["medico_id"])
    if modificando:
        turno = turno_del_usuario(datos, estado)
        if turno is None:
            return [("Ese turno ya no existe.", None), menu(estado)]
        medico_actual = cb.buscar_por_id(datos["medicos"], turno["medico_id"])
        texto = (f"Estos son los cambios de tu turno (código {turno['codigo']}):\n"
                 f"Antes:   {medico_actual['nombre']} - {cb.formatear_fecha(turno['fecha'], turno['hora'])}\n"
                 f"Después: {medico['nombre']} - {cb.formatear_fecha(fecha, hora)}\n\n"
                 "¿Confirmás la modificación?")
    else:
        especialidad = cb.buscar_por_id(datos["especialidades"], estado["esp_id"])
        texto = ("Este es el resumen de tu turno:\n"
                 f"DNI:          {estado['dni']}\n"
                 f"Especialidad: {especialidad['nombre']}\n"
                 f"Profesional:  {medico['nombre']}\n"
                 f"Fecha y hora: {cb.formatear_fecha(fecha, hora)}\n\n"
                 "¿Confirmás la reserva?")
    return [ofrecer(estado, "confirmar", texto, [("✅ Confirmar", "c:si"), ("❌ Cancelar", "c:no")], volver=None)]


def paso_confirmar(estado, valor):
    acepta = valor == "c:si"
    accion = estado["accion"]
    datos = cb.cargar_datos()

    if accion == "reservar":
        if not acepta:
            return [("Reserva cancelada. No se guardó ningún turno.", None), menu(estado)]
        respuesta = confirmar_reserva(estado, datos)
    elif accion == "cancelar":
        if not acepta:
            return [("No se canceló ningún turno.", None), menu(estado)]
        respuesta = confirmar_cancelacion(estado, datos)
    else:
        if not acepta:
            return [("No se modificó el turno.", None), menu(estado)]
        respuesta = confirmar_modificacion(estado, datos)
    return [(respuesta, None), menu(estado)]


def confirmar_reserva(estado, datos):
    # Se vuelve a validar por si otro usuario tomó el horario mientras tanto
    _, horarios, _, _ = horarios_elegibles(estado, datos)
    if horario_elegido(estado) not in horarios:
        return "❌ Lo siento, ese horario acaba de ser reservado por otra persona. Probá con otro."
    conflicto = cb.buscar_conflicto(datos, estado["dni"], estado["fecha"], estado["hora"])
    if conflicto:
        return cb.texto_conflicto(datos, conflicto)
    turno = cb.crear_turno(datos, estado["dni"], estado["medico_turno"], estado["esp_id"],
                           estado["fecha"], estado["hora"])
    return (f"✅ ¡Listo! Tu turno quedó reservado. Número de turno: #{turno['id']}.\n"
            f"🔑 Tu código de confirmación es: {turno['codigo']}. "
            "Guardalo para presentarlo en el consultorio.\n"
            "Recordá llegar 10 minutos antes con tu DNI.")


def confirmar_cancelacion(estado, datos):
    turno = turno_del_usuario(datos, estado)
    if turno is None:
        return "Ese turno ya no existe."
    datos["turnos_reservados"].remove(turno)
    cb.guardar_datos(datos)
    return "✅ Tu turno fue cancelado correctamente y el horario quedó liberado."


def confirmar_modificacion(estado, datos):
    turno = turno_del_usuario(datos, estado)
    if turno is None:
        return "Ese turno ya no existe."
    _, horarios, _, _ = horarios_elegibles(estado, datos)
    if horario_elegido(estado) not in horarios:
        return "❌ Lo siento, ese horario acaba de ser reservado por otra persona. Probá con otro."
    conflicto = cb.buscar_conflicto(datos, estado["dni"], estado["fecha"], estado["hora"], excluir_id=turno["id"])
    if conflicto:
        return cb.texto_conflicto(datos, conflicto)
    cb.aplicar_modificacion(datos, turno, estado["medico_turno"], estado["fecha"], estado["hora"])
    return (f"✅ Tu turno #{turno['id']} fue modificado correctamente.\n"
            f"🔑 Tu código de confirmación sigue siendo: {turno['codigo']}.")


def ver_turnos(estado, datos):
    turnos = cb.turnos_de(datos, estado["dni"])
    if not turnos:
        return [(f"No tenés turnos reservados para el DNI {estado['dni']}.", None), menu(estado)]
    texto = (f"Tenés {len(turnos)} turno(s) reservado(s):\n\n"
             + "\n\n".join(cb.ficha_turno(datos, t) for t in turnos))
    return [(texto, None), menu(estado)]


def ver_historial(estado, datos):
    pasados = cb.turnos_de(datos, estado["dni"], "pasados")
    if not pasados:
        return [(f"No tenés turnos anteriores en tu historial para el DNI {estado['dni']}.", None), menu(estado)]
    texto = (f"Este es tu historial: {len(pasados)} turno(s) anterior(es), del más reciente al más antiguo:\n\n"
             + "\n\n".join(cb.ficha_historial(datos, t) for t in reversed(pasados)))
    return [(texto, None), menu(estado)]


PASOS = {
    "menu": paso_menu,
    "dni": paso_dni,
    "especialidad": paso_especialidad,
    "turno": paso_turno,
    "medico": paso_medico,
    "dia": paso_dia,
    "hora": paso_hora,
    "confirmar": paso_confirmar,
}


# ---------------------------------------------------------------------------
# Conexión con Telegram
# ---------------------------------------------------------------------------

ICONOS_ELECCION = {"m": "📋", "e": "🩺", "d": "👨‍⚕️", "t": "🗂️", "f": "📅", "h": "🕐"}


def resumen_eleccion(dato, etiqueta):
    """
    Texto corto que reemplaza a un mensaje con botones una vez elegida una opción.
    Ej.: ("f:2026-10-20", "3. Martes 20/10/2026 (3 horarios)") -> "📅 Elegiste: Martes 20/10/2026"
    """
    limpio = re.sub(r"^\d+\.\s*", "", etiqueta)       # número de la opción
    limpio = re.sub(r"\s*←.*$", "", limpio)            # marcas "← actual"
    limpio = re.sub(r"\s*\([^)]*\)$", "", limpio)      # "(3 horarios)", "(26 libres)"
    if dato.startswith("f:"):
        limpio = limpio.split(" · ")[0]                 # apellidos de los médicos del día
    icono = ICONOS_ELECCION.get(dato.split(":", 1)[0], "👉")
    propio = re.match(r"^([^\w\s#]+)\s+(.+)$", limpio)  # opciones que ya traen ícono: "✅ Confirmar"
    if propio:
        icono, limpio = propio.groups()
    return f"{icono} Elegiste: {limpio}"


def teclado(botones):
    if not botones:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(etiqueta, callback_data=dato)] for etiqueta, dato in botones])


async def enviar(update: Update, context: ContextTypes.DEFAULT_TYPE, respuestas):
    for texto, botones in respuestas:
        mensaje = await context.bot.send_message(update.effective_chat.id, texto, reply_markup=teclado(botones))
        if botones:
            # Se recuerda el último mensaje con botones para poder resumirlo después
            context.chat_data["teclado"] = {"id": mensaje.message_id, "botones": botones}


async def resumir_mensaje(context: ContextTypes.DEFAULT_TYPE, chat_id, mensaje_id, botones, dato):
    """
    Reemplaza un mensaje con botones por el resumen de lo elegido. Si no se
    eligió ninguna de sus opciones (por ejemplo, al escribir /start), solo se
    le quitan los botones.
    """
    etiqueta = next((e for e, d in botones if d == dato), None) if dato else None
    try:
        if etiqueta:
            await context.bot.edit_message_text(resumen_eleccion(dato, etiqueta),
                                                chat_id=chat_id, message_id=mensaje_id)
        else:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=mensaje_id, reply_markup=None)
    except BadRequest:
        pass  # el mensaje ya no se puede editar (muy viejo o ya modificado)


async def resumir_ultimo_teclado(update: Update, context: ContextTypes.DEFAULT_TYPE, dato=None):
    ultimo = context.chat_data.pop("teclado", None)
    if ultimo:
        await resumir_mensaje(context, update.effective_chat.id, ultimo["id"], ultimo["botones"], dato)


async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await resumir_ultimo_teclado(update, context)
    await enviar(update, context, [menu(context.user_data, BIENVENIDA)])


async def comando_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await resumir_ultimo_teclado(update, context)
    await enviar(update, context, [menu(context.user_data)])


async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estado = context.user_data
    texto = update.message.text.strip()
    # Si el usuario escribió el número de una opción, se identifica cuál era antes de avanzar
    dato = traducir_numero(estado, texto) if estado.get("paso") not in (None, "dni") else None

    respuestas = manejar(estado, "texto", texto)
    # Los botones anteriores quedan obsoletos si se eligió una opción o si llegan botones nuevos
    if dato is not None or any(botones for _, botones in respuestas):
        await resumir_ultimo_teclado(update, context, dato)
    await enviar(update, context, respuestas)


async def recibir_boton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # El mensaje con botones se reemplaza por un resumen corto de lo elegido
    mensaje = query.message
    if mensaje is not None and getattr(mensaje, "reply_markup", None):
        botones = [(b.text, b.callback_data) for fila in mensaje.reply_markup.inline_keyboard for b in fila]
        await resumir_mensaje(context, update.effective_chat.id, mensaje.message_id, botones, query.data)
        ultimo = context.chat_data.get("teclado")
        if ultimo and ultimo["id"] == mensaje.message_id:
            context.chat_data.pop("teclado")

    await enviar(update, context, manejar(context.user_data, "boton", query.data))


async def manejar_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Error procesando un mensaje", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        context.user_data.clear()
        await context.bot.send_message(update.effective_chat.id,
                                       "Ocurrió un error inesperado. Escribí /start para empezar de nuevo.")


def leer_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip()
    try:
        with open(ARCHIVO_TOKEN, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("❌ No se encontró el token. Definí la variable de entorno TELEGRAM_BOT_TOKEN "
              f"o creá el archivo {ARCHIVO_TOKEN} con el token del bot.")
        raise SystemExit(1)


def main():
    app = Application.builder().token(leer_token()).build()
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("menu", comando_menu))
    app.add_handler(CallbackQueryHandler(recibir_boton))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_texto))
    app.add_error_handler(manejar_error)

    print("🤖 Bot @GestionTurnosMedicosIA_bot en marcha. Presioná Ctrl+C para detenerlo.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
