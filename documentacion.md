# Especificación de Requerimientos y Diseño Conceptual
## Proyecto: Sistema de Monitoreo Analítico para Máquina 3 (SCADA Jageg)

Este documento detalla la estructura formal de objetivos, alcances y plan de ejecución para el desarrollo de la capa de backend y analítica utilizando **FastAPI**, **SQLAlchemy** y **WebSockets**. El sistema actuará como un "Gemelo Digital" de datos de la Máquina 3 (Extrusión de tela no tejida) enfocado exclusivamente en la visualización avanzada, análisis de históricos y gestión de alertas, sin interacción directa ni modificación sobre el hardware o software del PLC actual.

---

## 1. Declaración de Objetivos

### Objetivo Principal
Desarrollar una plataforma web de supervisión, análisis de tendencias e históricos, y monitoreo en tiempo real basada en un backend asíncrono con **FastAPI** para la Máquina 3 de extrusión de polietileno (Capas S1, S2 y Meltblown). El sistema transformará las cadenas de datos numéricos crudos y registros del proceso industrial en gráficos dinámicos, tableros visuales interactivos y un módulo inteligente de alertas tempranas, optimizando la interpretación operativa y facilitando la auditoría de procesos por parte del operador sin intervenir en la programación existente del controlador industrial.

### Objetivos Secundarios
1. **Emulación Asíncrona del Proceso (Gemelo de Datos):** Diseñar un motor lógico basado en tareas en segundo plano que replique de manera realista las inercias físicas del proceso, tales como las curvas de temperatura de las 6 zonas de extrusión y la dinámica de dosificación en gramos por revolución ($G/R$).
2. **Modelado Eficiente de Series Temporales:** Estructurar modelos de base de datos relacionales optimizados mediante **SQLAlchemy** para almacenar snapshots de variables analógicas y digitales, garantizando consultas analíticas de históricos rápidas y fluidas.
3. **Módulo Centralizado de Alertas e Incidencias:** Implementar un motor de reglas en el backend capaz de contrastar en tiempo real los valores de proceso ($PV$) contra sus consignas ($SP$), detectando desviaciones térmicas o fallas mecánicas e integrando un registro histórico con flujos de reconocimiento (Acknowledge).
4. **Tubería de Datos en Tiempo Real (Real-Time Pipeline):** Implementar canales de comunicación bidireccional mediante **WebSockets** para transmitir telemetría instantánea desde el simulador backend hacia el frontend, mitigando la sobrecarga de la base de datos por polling HTTP constante.
5. **Abstracción de Capas Industriales:** Aislar por completo la arquitectura de software de la red de campo real (Siemens CPU 315-2 DP / Variadores MM440), de modo que el software sea 100% autónomo y simule con exactitud las variables descritas en la ingeniería del SCADA actual.

---

## 2. Pasos a Seguir para el Desarrollo (Hoja de Ruta)

### Fase 1: Arquitectura de Persistencia y Modelado (SQLAlchemy)
* **Paso 1.1:** Configurar el motor de base de datos (PostgreSQL / SQLite) y la sesión asíncrona de SQLAlchemy en FastAPI.
* **Paso 1.2:** Crear los modelos para las **Variables Térmicas** (Capas S1, S2 y Meltblown), incluyendo campos para marcas de tiempo, valores de proceso ($PV_1$ a $PV_6$) y setpoints ($SP_1$ a $SP_6$).
* **Paso 1.3:** Crear los modelos para la **Dosificación de Materia Prima**, contemplando RPM de motores (`M_Stock_RPM`), relaciones de dosificación ($G/R$) y porcentajes de aditivos/colorantes (`%_M_C#1_M`).
* **Paso 1.4:** Crear el modelo de **Log de Alertas**, con marcas de tiempo de inicio, fin, componente, descripción técnica, criticidad y estado de aceptación.

### Fase 2: Motor de Simulación y Gemelo Digital (`asyncio`)
* **Paso 2.1:** Implementar bucles de control asíncronos (`asyncio.sleep`) en tareas residentes en memoria dentro de FastAPI para simular el ciclo continuo de la planta.
* **Paso 2.2:** Programar algoritmos matemáticos de aproximación para simular la inercia térmica (ej. cuando cambia un $SP$, el $PV$ aumenta/disminuye gradualmente simulando transferencia de calor con ruido estocástico menor).
* **Paso 2.3:** Simular las dependencias mecánicas: el flujo de revoluciones y consumo de aditivos condicionado a las velocidades maestras de los variadores representados en la configuración.

### Fase 3: Pipeline de Tiempo Real y Motor de Reglas
* **Paso 3.1:** Construir el router de WebSockets (`/ws/telemetria`) bajo un patrón de diseño Pub/Sub para despachar tramas JSON consolidadas cada 1.0 segundos.
* **Paso 3.2:** Integrar el motor de evaluación de umbrales dentro del ciclo de simulación para inyectar alertas en la base de datos de manera inmediata cuando un valor rompa las tolerancias industriales toleradas.

### Fase 4: Endpoints de Consulta y API RESTful
* **Paso 4.1:** Desarrollar endpoints orientados al análisis de tendencias (`GET /api/v1/analitica/historicos`) parametrizados con filtros estrictos de rangos de fechas y componentes.
* **Paso 4.2:** Construir endpoints para la gestión de alarmas (`GET /api/v1/alertas/activas` y `PATCH /api/v1/alertas/{id}/reconocer`).

### Fase 5: Pruebas de Estrés y Validación Operativa
* **Paso 5.1:** Diseñar endpoints de testing ocultos para inyectar fallas artificiales en los variadores de velocidad (`SUCTION S1`, `OIL PUMP`) o desvíos abruptos de temperatura para certificar la resiliencia del frontend y backend de manera integrada.
* **Paso 5.2:** Validar la velocidad de renderizado de las consultas SQL frente a volúmenes simulados de datos de series temporales.