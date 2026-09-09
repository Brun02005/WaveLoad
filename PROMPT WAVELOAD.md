Actúa como un Lead Software Architect, Product Manager y Senior Full-Stack Developer.



Tu objetivo es analizar completamente el proyecto actual ("WaveLoad v3"), evaluar su estado técnico, explorar alternativas de producto y ayudarme a decidir entre dos caminos: TERMINAR EL PROYECTO ACTUAL o PIVOTAR HACIA UN PRODUCTO NUEVO basado en su código.

TAMBIEN QUIERO QUE ANALICES LA DIRECCION DEL PROYECTO Y SI ES REALMENTE VIABLE HACERLO



Por favor, realiza las siguientes fases en orden:



--- FASE 1: AUDITORÍA TÉCNICA Y DIAGNÓSTICO DEL PROYECTO ---

1. Explora y analiza la estructura del proyecto (módulos principales, `main.py`, `ui`, `core`, `domain`, `infrastructure`, `ai`, `services`, `storage`, `workers`, etc.).

2. Identifica qué funcionalidades ya están implementadas, cuáles están a medias (stubs, TODOs, métodos incompletos) y qué partes presentan fallos o errores de estabilidad (inspecciona logs como `waveload_error.log` o dumps de fallos).

3. Evalúa la calidad de la arquitectura, patrones utilizados y la deuda técnica actual.



--- FASE 2: ANÁLISIS DE PRODUCTO Y ALTERNATIVAS ---

1. Analiza cuál es la propuesta de valor de WaveLoad v3 (descargas, gestión de librería audio/MP3, componentes IA, etc.).

2. Presenta una evaluación estratégica:

   - **Opción A (Finalizar WaveLoad v3):** ¿Qué falta exactamente para tener un MVP sólido y 100% funcional listo para producción/distribución? ¿Cuáles son los mayores riesgos técnicos?

   - **Opción B (Pivotar / Crear un Producto Nuevo):** Utilizando el código base existente (la arquitectura PySide6, servicios, almacenamiento, motor IA), ¿qué alternativas de productos innovadores o con mayor potencial comercial se podrían construir? (Ejemplos: herramientas para DJs/productores, transcripción/organización inteligente de audio, procesador batch para podcasts, conversor/estractor con IA, SaaS desktop, etc.).

   - **Opción C (Reducir alcance / MVP ultra magro):** ¿Cómo simplificar drásticamente el proyecto para terminarlo en tiempo récord eliminando lo innecesario?



--- FASE 3: RECOMENDACIÓN Y ROADMAP DE DECISIÓN ---

1. Dame tu recomendación experta sobre cuál de las opciones conviene seguir y por qué.

2. Para la opción recomendada, genera un Roadmap paso a paso detallando:

   - Tareas inmediatas (Fixes y limpieza).

   - Desarrollo de funcionalidades faltantes clave.

   - Plan de pruebas (QA) y empaquetado final (`PyInstaller` / `.spec`).



Para comenzar, haz un primer barrido del repositorio, lee los archivos clave y presenta el diagnóstico de la FASE 1 junto con tus preguntas iniciales.