"""
Chatbot de gestión de turnos médicos.
Corre en la terminal y usa datos.json como base de datos.
"""

import json
import os
import secrets
import string
from datetime import datetime, date, timedelta

ARCHIVO_DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos.json")
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
VENTANA_MINUTOS = 60  # Separación mínima entre dos turnos del mismo DNI en el mismo día
SEMANAS_AGENDA = 3    # Cantidad de semanas hacia adelante para las que se ofrecen turnos
LARGO_CODIGO = 8      # Largo del código de confirmación de cada reserva
OPCION_CUALQUIERA = "Cualquier médico disponible"


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def cargar_datos():
    """
    Lee el archivo JSON y le agrega a cada médico sus horarios generados
    dinámicamente para las próximas semanas (ver generar_horarios).
    """
    try:
        with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except FileNotFoundError:
        print(f"❌ No se encontró el archivo {ARCHIVO_DATOS}.")
        raise SystemExit(1)
    except json.JSONDecodeError:
        print("❌ El archivo datos.json está dañado o tiene un formato inválido.")
        raise SystemExit(1)

    # Reservas antiguas sin código de confirmación: se les asigna uno y se guarda
    sin_codigo = [t for t in datos["turnos_reservados"] if not t.get("codigo")]
    for t in sin_codigo:
        t["codigo"] = generar_codigo(datos)
    if sin_codigo:
        guardar_datos(datos)

    generar_horarios(datos)
    return datos


def guardar_datos(datos):
    """
    Escribe el diccionario en el archivo JSON. Los horarios generados no se
    guardan: solo persisten la configuración de los médicos y las reservas.
    """
    a_guardar = dict(datos)
    a_guardar["medicos"] = [{k: v for k, v in m.items() if k != "horarios"} for m in datos["medicos"]]
    with open(ARCHIVO_DATOS, "w", encoding="utf-8") as f:
        json.dump(a_guardar, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Generación dinámica de turnos
# ---------------------------------------------------------------------------

def generar_horarios(datos):
    """
    Arma la lista `horarios` de cada médico a partir de sus `dias_atencion` y
    `horas_atencion`, desde hoy hasta dentro de SEMANAS_AGENDA semanas.
    Descarta los horarios que ya pasaron y marca como no disponibles los que
    ya están reservados.
    """
    ahora = datetime.now()
    hoy = ahora.date()
    reservados = {(t["medico_id"], t["fecha"], t["hora"]) for t in datos["turnos_reservados"]}
    dias_normalizados = [d.lower() for d in DIAS_SEMANA]

    for medico in datos["medicos"]:
        dias = []
        for dia in medico["dias_atencion"]:
            if dia.lower() not in dias_normalizados:
                print(f"❌ Día de atención inválido para {medico['nombre']} en datos.json: '{dia}'.")
                raise SystemExit(1)
            dias.append(dias_normalizados.index(dia.lower()))

        medico["horarios"] = []
        for i in range(SEMANAS_AGENDA * 7):
            dia_actual = hoy + timedelta(days=i)
            if dia_actual.weekday() not in dias:
                continue
            fecha = dia_actual.strftime("%Y-%m-%d")
            for hora in sorted(medico["horas_atencion"]):
                if datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M") <= ahora:
                    continue  # el horario de hoy ya pasó
                medico["horarios"].append({
                    "medico_id": medico["id"],
                    "fecha": fecha,
                    "hora": hora,
                    "disponible": (medico["id"], fecha, hora) not in reservados,
                })


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def bot(mensaje):
    print(f"\n🤖 Bot: {mensaje}")


def pedir(mensaje=""):
    return input(f"👤 Vos{(' (' + mensaje + ')') if mensaje else ''}: ").strip()


def formatear_dia(fecha):
    """'2026-10-19' -> 'Lunes 19/10/2026'."""
    f = datetime.strptime(fecha, "%Y-%m-%d")
    return f"{DIAS_SEMANA[f.weekday()]} {f.strftime('%d/%m/%Y')}"


def formatear_fecha(fecha, hora):
    """'2026-10-19', '08:00' -> 'Lunes 19/10/2026 a las 08:00 hs'."""
    return f"{formatear_dia(fecha)} a las {hora} hs"


def a_minutos(hora):
    """'08:30' -> 510."""
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def dni_valido(dni):
    """El DNI debe tener solo números y entre 7 y 8 dígitos."""
    return dni.isdigit() and 7 <= len(dni) <= 8


def pedir_dni():
    """
    Pide un DNI hasta que sea válido y muestra el recordatorio de turnos de mañana.
    Devuelve None si el usuario cancela.
    """
    bot("Por favor, ingresá tu DNI (solo números, sin puntos). Escribí 'salir' para volver al menú.")
    while True:
        dni = pedir("DNI").replace(".", "").replace(" ", "")
        if dni.lower() == "salir":
            return None
        if dni_valido(dni):
            mostrar_recordatorio(dni)
            return dni
        bot("Ese DNI no es válido. Tiene que tener solo números y entre 7 y 8 dígitos. Probá de nuevo.")


def elegir_opcion(opciones, titulo):
    """
    Muestra una lista numerada y devuelve el índice elegido.
    Devuelve None si el usuario elige volver (0).
    """
    bot(titulo)
    for i, texto in enumerate(opciones, start=1):
        print(f"    {i}. {texto}")
    print("    0. Volver")
    while True:
        eleccion = pedir("número")
        if eleccion.isdigit():
            n = int(eleccion)
            if n == 0:
                return None
            if 1 <= n <= len(opciones):
                return n - 1
        bot(f"Opción inválida. Ingresá un número entre 0 y {len(opciones)}.")


def confirmar(pregunta):
    bot(f"{pregunta} (s/n)")
    while True:
        r = pedir().lower()
        if r in ("s", "si", "sí"):
            return True
        if r in ("n", "no"):
            return False
        bot("Respondé 's' para sí o 'n' para no.")


def buscar_por_id(lista, id_buscado):
    for elemento in lista:
        if elemento["id"] == id_buscado:
            return elemento
    return None


def siguiente_id_turno(datos):
    ids = [t["id"] for t in datos["turnos_reservados"]]
    return max(ids, default=0) + 1


def generar_codigo(datos):
    """Genera un código alfanumérico de LARGO_CODIGO caracteres que no esté en uso."""
    alfabeto = string.ascii_uppercase + string.digits
    en_uso = {t.get("codigo") for t in datos["turnos_reservados"]}
    while True:
        codigo = "".join(secrets.choice(alfabeto) for _ in range(LARGO_CODIGO))
        if codigo not in en_uso:
            return codigo


def turnos_de(datos, dni, cuales="proximos"):
    """
    Turnos reservados por un DNI, ordenados por fecha y hora.
    cuales: "proximos" (de hoy en adelante), "pasados" (antes de hoy) o "todos".
    """
    hoy = date.today().strftime("%Y-%m-%d")
    turnos = [t for t in datos["turnos_reservados"] if t["dni"] == dni]
    if cuales == "proximos":
        turnos = [t for t in turnos if t["fecha"] >= hoy]
    elif cuales == "pasados":
        turnos = [t for t in turnos if t["fecha"] < hoy]
    return sorted(turnos, key=lambda t: (t["fecha"], t["hora"]))


def describir_turno(datos, turno):
    medico = buscar_por_id(datos["medicos"], turno["medico_id"])
    especialidad = buscar_por_id(datos["especialidades"], turno["especialidad_id"])
    return (f"#{turno['id']} [Código {turno['codigo']}] - {especialidad['nombre']} con {medico['nombre']} - "
            f"{formatear_fecha(turno['fecha'], turno['hora'])}")


def ficha_turno(datos, turno):
    """Datos de un turno próximo en formato de ficha."""
    medico = buscar_por_id(datos["medicos"], turno["medico_id"])
    especialidad = buscar_por_id(datos["especialidades"], turno["especialidad_id"])
    return (f"    Reserva N°:   #{turno['id']}\n"
            f"    Código:       {turno['codigo']}\n"
            f"    Especialidad: {especialidad['nombre']}\n"
            f"    Médico:       {medico['nombre']}\n"
            f"    Horario:      {formatear_fecha(turno['fecha'], turno['hora'])}")


def ficha_historial(datos, turno):
    """Datos de un turno pasado en formato de ficha."""
    medico = buscar_por_id(datos["medicos"], turno["medico_id"])
    especialidad = buscar_por_id(datos["especialidades"], turno["especialidad_id"])
    return (f"    Código:       {turno['codigo']}\n"
            f"    Especialidad: {especialidad['nombre']}\n"
            f"    Médico:       {medico['nombre']}\n"
            f"    Fecha y hora: {formatear_fecha(turno['fecha'], turno['hora'])}")


def mostrar_ficha_turno(datos, turno):
    """Imprime los datos de un turno en formato de ficha."""
    print("\n" + ficha_turno(datos, turno))


def horario_libre(datos, medico_id, fecha, hora):
    """True si nadie reservó ese horario del médico."""
    return not any(t["medico_id"] == medico_id and t["fecha"] == fecha and t["hora"] == hora
                   for t in datos["turnos_reservados"])


def crear_turno(datos, dni, medico_id, especialidad_id, fecha, hora):
    """Agrega una reserva nueva con su código de confirmación, la guarda y la devuelve."""
    turno = {
        "id": siguiente_id_turno(datos),
        "dni": dni,
        "medico_id": medico_id,
        "especialidad_id": especialidad_id,
        "fecha": fecha,
        "hora": hora,
        "codigo": generar_codigo(datos),
        "fecha_reserva": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    datos["turnos_reservados"].append(turno)
    guardar_datos(datos)
    return turno


def aplicar_modificacion(datos, turno, medico_id, fecha, hora):
    """
    Cambia médico, fecha y hora de una reserva y la guarda. El código de
    confirmación se mantiene; el horario anterior queda libre y el nuevo ocupado.
    """
    turno["medico_id"] = medico_id
    turno["fecha"] = fecha
    turno["hora"] = hora
    turno["fecha_modificacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guardar_datos(datos)


def buscar_conflicto(datos, dni, fecha, hora, excluir_id=None):
    """
    Devuelve el turno del DNI que queda a menos de VENTANA_MINUTOS del horario
    indicado (mismo día), o None si no hay conflicto. `excluir_id` permite
    ignorar el turno que se está modificando.
    """
    nuevo = a_minutos(hora)
    for t in datos["turnos_reservados"]:
        if t["dni"] != dni or t["fecha"] != fecha or t["id"] == excluir_id:
            continue
        if abs(a_minutos(t["hora"]) - nuevo) < VENTANA_MINUTOS:
            return t
    return None


def texto_conflicto(datos, conflicto):
    return ("❌ No es posible tomar ese horario: ya tenés un turno ese mismo día a menos de 1 hora:\n"
            f"    {describir_turno(datos, conflicto)}\n"
            "    Elegí un horario con al menos 1 hora de diferencia.")


def avisar_conflicto(datos, conflicto):
    bot(texto_conflicto(datos, conflicto))


def horarios_libres(medicos):
    """Horarios disponibles de uno o varios médicos, juntos y ordenados por fecha y hora."""
    libres = [{"medico_id": h["medico_id"], "fecha": h["fecha"], "hora": h["hora"]}
              for m in medicos for h in m["horarios"] if h["disponible"]]
    return sorted(libres, key=lambda h: (h["fecha"], h["hora"]))


def clave_horario(horario):
    """(medico_id, fecha, hora): identifica un horario de un médico."""
    return horario["medico_id"], horario["fecha"], horario["hora"]


def texto_dia(datos, fecha, horarios, actual=None, combinado=False):
    """Opción de la lista de días. Si combina varios médicos, nombra a los que atienden ese día."""
    del_dia = [h for h in horarios if h["fecha"] == fecha]
    texto = f"{formatear_dia(fecha)} ({len(del_dia)} horario{'s' if len(del_dia) != 1 else ''})"
    if combinado:
        nombres = sorted({buscar_por_id(datos["medicos"], h["medico_id"])["nombre"] for h in del_dia})
        texto += " - " + ", ".join(nombres)
    if actual and actual[1] == fecha:
        texto += " ← tu turno actual"
    return texto


def texto_hora(datos, horario, actual=None, combinado=False):
    """Opción de la lista de horas. Si combina varios médicos, indica con quién es el turno."""
    texto = f"{horario['hora']} hs"
    if combinado:
        texto += f" - {buscar_por_id(datos['medicos'], horario['medico_id'])['nombre']}"
    if actual == clave_horario(horario):
        texto += " ← actual (mantener)"
    return texto


def horarios_del_dia(datos, horarios, fecha):
    """Horarios de una fecha ordenados por hora y, a igual hora, por nombre del médico."""
    return sorted((h for h in horarios if h["fecha"] == fecha),
                  key=lambda h: (h["hora"], buscar_por_id(datos["medicos"], h["medico_id"])["nombre"]))


def elegir_dia_y_hora(datos, dni, con_quien, horarios, excluir_id=None, actual=None, combinado=False):
    """
    Selección en dos pasos: primero el día y después la hora dentro de ese día.
    `horarios` son los horarios elegibles (cada uno con su medico_id), `con_quien`
    es el texto que se muestra en la pregunta, `actual` (medico_id, fecha, hora)
    marca el turno que se está modificando y `combinado` indica que los horarios
    son de varios médicos, por lo que se muestra el nombre del médico en cada uno.
    Si el horario elegido choca con otro turno del DNI, se avisa y se vuelve a
    pedir la hora. Devuelve el horario elegido, o None si el usuario vuelve atrás
    desde la lista de días.
    """
    fechas = sorted({h["fecha"] for h in horarios})
    while True:
        textos_dias = [texto_dia(datos, f, horarios, actual, combinado) for f in fechas]
        idx = elegir_opcion(textos_dias, f"¿Qué día querés atenderte con {con_quien}?")
        if idx is None:
            return None
        fecha = fechas[idx]

        del_dia = horarios_del_dia(datos, horarios, fecha)
        textos_horas = [texto_hora(datos, h, actual, combinado) for h in del_dia]
        while True:
            idx = elegir_opcion(textos_horas,
                                f"Horarios disponibles el {formatear_dia(fecha)} (0 para elegir otro día):")
            if idx is None:
                break  # vuelve a la lista de días
            horario = del_dia[idx]
            conflicto = buscar_conflicto(datos, dni, horario["fecha"], horario["hora"], excluir_id)
            if conflicto is None:
                return horario
            avisar_conflicto(datos, conflicto)


# ---------------------------------------------------------------------------
# Recordatorio
# ---------------------------------------------------------------------------

def textos_recordatorio(datos, dni):
    """Un aviso por cada turno que el DNI tiene para mañana."""
    manana = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    avisos = []
    for t in turnos_de(datos, dni):
        if t["fecha"] == manana:
            medico = buscar_por_id(datos["medicos"], t["medico_id"])
            especialidad = buscar_por_id(datos["especialidades"], t["especialidad_id"])
            avisos.append(f"⚠️  Recordatorio: tenés un turno mañana con {medico['nombre']} "
                          f"a las {t['hora']} hs ({especialidad['nombre']}).")
    return avisos


def mostrar_recordatorio(dni):
    """Si el DNI tiene turnos para mañana, muestra un aviso por cada uno."""
    for aviso in textos_recordatorio(cargar_datos(), dni):
        print("\n" + aviso)


# ---------------------------------------------------------------------------
# Reservar turno
# ---------------------------------------------------------------------------

def reservar_turno():
    datos = cargar_datos()

    dni = pedir_dni()
    if dni is None:
        return

    # 1. Especialidad
    especialidades = datos["especialidades"]
    idx = elegir_opcion([e["nombre"] for e in especialidades], "¿Para qué especialidad necesitás el turno?")
    if idx is None:
        return
    especialidad = especialidades[idx]

    # 2. Médico
    medicos = [m for m in datos["medicos"] if m["especialidad_id"] == especialidad["id"]]
    medicos_con_turnos = [m for m in medicos if any(h["disponible"] for h in m["horarios"])]
    if not medicos_con_turnos:
        bot(f"Lo siento, no hay turnos disponibles en {especialidad['nombre']} por el momento.")
        return
    opciones = [f"{m['nombre']} ({m['matricula']}) - "
                f"{sum(h['disponible'] for h in m['horarios'])} turnos libres" for m in medicos_con_turnos]
    if len(medicos_con_turnos) > 1:
        opciones.append(OPCION_CUALQUIERA)
    idx = elegir_opcion(
        opciones,
        f"Estos son los profesionales de {especialidad['nombre']}. ¿Con quién querés atenderte?",
    )
    if idx is None:
        return
    combinado = idx == len(medicos_con_turnos)
    candidatos = medicos_con_turnos if combinado else [medicos_con_turnos[idx]]
    con_quien = f"cualquier médico de {especialidad['nombre']}" if combinado else candidatos[0]["nombre"]

    # 3. Día y horario
    horario = elegir_dia_y_hora(datos, dni, con_quien, horarios_libres(candidatos), combinado=combinado)
    if horario is None:
        return
    medico = buscar_por_id(datos["medicos"], horario["medico_id"])

    # 4. Confirmación
    bot("Este es el resumen de tu turno:\n"
        f"    DNI:          {dni}\n"
        f"    Especialidad: {especialidad['nombre']}\n"
        f"    Profesional:  {medico['nombre']}\n"
        f"    Fecha y hora: {formatear_fecha(horario['fecha'], horario['hora'])}")
    if not confirmar("¿Confirmás la reserva?"):
        bot("Reserva cancelada. No se guardó ningún turno.")
        return

    # 5. Guardar (el horario queda ocupado porque pasa a estar en turnos_reservados)
    turno = crear_turno(datos, dni, medico["id"], especialidad["id"], horario["fecha"], horario["hora"])
    bot(f"✅ ¡Listo! Tu turno quedó reservado. Número de turno: #{turno['id']}.\n"
        f"    🔑 Tu código de confirmación es: {turno['codigo']}. "
        "Guardalo para presentarlo en el consultorio.\n"
        "    Recordá llegar 10 minutos antes con tu DNI.")


# ---------------------------------------------------------------------------
# Cancelar turno
# ---------------------------------------------------------------------------

def cancelar_turno():
    datos = cargar_datos()

    dni = pedir_dni()
    if dni is None:
        return

    turnos_dni = turnos_de(datos, dni)
    if not turnos_dni:
        bot(f"No encontré turnos reservados para el DNI {dni}.")
        return

    idx = elegir_opcion(
        [describir_turno(datos, t) for t in turnos_dni],
        f"Encontré {len(turnos_dni)} turno(s) para el DNI {dni}. ¿Cuál querés cancelar?",
    )
    if idx is None:
        return
    turno = turnos_dni[idx]

    if not confirmar(f"¿Seguro que querés cancelar el turno {describir_turno(datos, turno)}?"):
        bot("No se canceló ningún turno.")
        return

    # Al quitar la reserva, el horario vuelve a figurar como disponible
    datos["turnos_reservados"].remove(turno)
    guardar_datos(datos)
    bot("✅ Tu turno fue cancelado correctamente y el horario quedó liberado.")


# ---------------------------------------------------------------------------
# Modificar turno
# ---------------------------------------------------------------------------

def modificar_turno():
    datos = cargar_datos()

    dni = pedir_dni()
    if dni is None:
        return

    turnos_dni = turnos_de(datos, dni)
    if not turnos_dni:
        bot(f"No encontré turnos reservados para el DNI {dni}.")
        return

    idx = elegir_opcion(
        [describir_turno(datos, t) for t in turnos_dni],
        f"Encontré {len(turnos_dni)} turno(s) para el DNI {dni}. ¿Cuál querés modificar?",
    )
    if idx is None:
        return
    turno = turnos_dni[idx]
    especialidad = buscar_por_id(datos["especialidades"], turno["especialidad_id"])
    medico_actual = buscar_por_id(datos["medicos"], turno["medico_id"])

    # 1. Médico (dentro de la misma especialidad)
    medicos = [m for m in datos["medicos"] if m["especialidad_id"] == especialidad["id"]]
    opciones = []
    for m in medicos:
        libres = sum(h["disponible"] for h in m["horarios"])
        actual = " ← actual" if m["id"] == medico_actual["id"] else ""
        opciones.append(f"{m['nombre']} ({m['matricula']}) - {libres} turnos libres{actual}")
    if len(medicos) > 1:
        opciones.append(OPCION_CUALQUIERA)
    idx = elegir_opcion(
        opciones,
        f"Elegí el profesional de {especialidad['nombre']} (podés mantener el actual):",
    )
    if idx is None:
        return
    combinado = idx == len(medicos)
    candidatos = medicos if combinado else [medicos[idx]]
    con_quien = f"cualquier médico de {especialidad['nombre']}" if combinado else candidatos[0]["nombre"]

    # 2. Día y horario (si el médico actual está entre los elegidos, se ofrece mantener el horario actual)
    opciones_horario = horarios_libres(candidatos)
    actual = None
    if any(m["id"] == medico_actual["id"] for m in candidatos):
        actual = (turno["medico_id"], turno["fecha"], turno["hora"])
        opciones_horario.append({"medico_id": turno["medico_id"], "fecha": turno["fecha"], "hora": turno["hora"]})
    if not opciones_horario:
        bot(f"No hay horarios disponibles con {con_quien}. Probá con otro profesional.")
        return

    nuevo = elegir_dia_y_hora(datos, dni, con_quien, opciones_horario, excluir_id=turno["id"],
                              actual=actual, combinado=combinado)
    if nuevo is None:
        return
    if clave_horario(nuevo) == actual:
        bot("No hiciste ningún cambio: elegiste el mismo médico y el mismo horario.")
        return
    medico = buscar_por_id(datos["medicos"], nuevo["medico_id"])

    # 3. Confirmación
    bot(f"Estos son los cambios de tu turno (código {turno['codigo']}):\n"
        f"    Antes:   {medico_actual['nombre']} - {formatear_fecha(turno['fecha'], turno['hora'])}\n"
        f"    Después: {medico['nombre']} - {formatear_fecha(nuevo['fecha'], nuevo['hora'])}")
    if not confirmar("¿Confirmás la modificación?"):
        bot("No se modificó el turno.")
        return

    # 4. Guardar: al actualizar la reserva, el horario anterior queda libre y el nuevo ocupado
    aplicar_modificacion(datos, turno, medico["id"], nuevo["fecha"], nuevo["hora"])
    bot(f"✅ Tu turno #{turno['id']} fue modificado correctamente.\n"
        f"    🔑 Tu código de confirmación sigue siendo: {turno['codigo']}.")


# ---------------------------------------------------------------------------
# Ver mis turnos
# ---------------------------------------------------------------------------

def ver_mis_turnos():
    datos = cargar_datos()

    dni = pedir_dni()
    if dni is None:
        return

    turnos_dni = turnos_de(datos, dni)
    if not turnos_dni:
        bot(f"No tenés turnos reservados para el DNI {dni}.")
        return

    bot(f"Tenés {len(turnos_dni)} turno(s) reservado(s):")
    for turno in turnos_dni:
        mostrar_ficha_turno(datos, turno)


# ---------------------------------------------------------------------------
# Historial de turnos
# ---------------------------------------------------------------------------

def ver_historial():
    datos = cargar_datos()

    dni = pedir_dni()
    if dni is None:
        return

    pasados = turnos_de(datos, dni, "pasados")
    if not pasados:
        bot(f"No tenés turnos anteriores en tu historial para el DNI {dni}.")
        return

    bot(f"Este es tu historial: {len(pasados)} turno(s) anterior(es), del más reciente al más antiguo:")
    for turno in reversed(pasados):
        print("\n" + ficha_historial(datos, turno))


# ---------------------------------------------------------------------------
# Menú principal
# ---------------------------------------------------------------------------

MENSAJE_BIENVENIDA = (
    "¡Bienvenido/a al Sistema de Gestión de Turnos Médicos! 🏥\n"
    "    Estamos aquí para ayudarte a gestionar tus citas de forma rápida y sencilla, "
    "las 24 horas del día.\n"
    "    ¿En qué podemos ayudarte hoy?"
)


def mostrar_menu(encabezado="¿Qué querés hacer?"):
    bot(f"{encabezado}\n"
        "    1. Reservar un turno\n"
        "    2. Cancelar un turno\n"
        "    3. Ver mis turnos\n"
        "    4. Modificar un turno\n"
        "    5. Historial de turnos\n"
        "    6. Salir")


def main():
    print("=" * 60)
    print("        🏥  CENTRO MÉDICO - Asistente de Turnos")
    print("=" * 60)

    encabezado = MENSAJE_BIENVENIDA  # la primera vez el menú va con la bienvenida
    while True:
        mostrar_menu(encabezado)
        encabezado = "¿Qué querés hacer?"
        opcion = pedir("opción").lower()

        if opcion in ("1", "reservar"):
            reservar_turno()
        elif opcion in ("2", "cancelar"):
            cancelar_turno()
        elif opcion in ("3", "ver", "ver mis turnos"):
            ver_mis_turnos()
        elif opcion in ("4", "modificar"):
            modificar_turno()
        elif opcion in ("5", "historial"):
            ver_historial()
        elif opcion in ("6", "salir", "chau"):
            bot("¡Gracias por comunicarte! Que tengas un buen día. 👋")
            break
        else:
            bot("No entendí esa opción. Ingresá un número del 1 al 6.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
        bot("Sesión finalizada. ¡Hasta luego! 👋")
