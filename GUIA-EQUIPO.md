# HiTrendy — Guía del proyecto para el equipo

**Para:** los 6 integrantes.
**Tiempo de lectura:** 15 minutos.
**Para qué sirve:** que cualquiera del grupo pueda explicar qué es HiTrendy, para
qué sirve, cómo está armado y qué hizo cada quien — sin necesidad de saber
programar.

> **Cómo usar esta guía:** las secciones 1 a 5 las lee todo el mundo. Después cada
> quien se aprende su sección (6, 7, 8 o 9). La sección 12 es el salvavidas: son
> las preguntas típicas con su respuesta corta.

> **La regla más importante:** si te preguntan algo que no es de tu parte, no
> inventes. Contesta la idea general y pásale la palabra a quien lo llevó. Un
> equipo que sabe quién sabe qué se ve más profesional que uno donde todos
> contestan a medias.

---

## 1. Qué es HiTrendy, en una frase

**Un asistente que le crea contenido para redes sociales a un negocio pequeño,
pero conociendo a ese negocio en particular.**

Esa última parte es todo el punto. Cualquiera puede pedirle a una inteligencia
artificial "escríbeme un post para Instagram" y recibir algo genérico. HiTrendy
primero aprende cómo es el negocio —qué vende, a quién, con qué tono, en qué
país— y a partir de ahí escribe. La diferencia entre un asistente cualquiera y
uno que ya trabaja contigo hace meses.

---

## 2. El problema que resuelve

Una florería, una cafetería, una barbería. El dueño sabe de su negocio, no de
publicidad. Sabe que tiene que publicar, pero:

- No sabe qué escribir.
- No tiene tiempo de sentarse a inventar textos todos los días.
- No puede pagar una agencia.
- Lo que le sale de una IA genérica suena a robot y no se parece a su negocio.

HiTrendy le da: un texto listo, hecho para *su* negocio, que él puede corregir y
guardar. En menos de cinco minutos desde que entra por primera vez.

---

## 3. Cómo funciona, explicado sencillo

Cinco pasos. Este es el corazón de toda la presentación:

**1. El negocio se presenta.**
Al registrarse, el usuario llena un cuestionario corto de cuatro pantallas: qué
negocio tiene, dónde está, qué vende, a quién le vende, y cómo quiere sonar
(cercano, profesional, divertido). Eso queda guardado.

**2. El usuario pide algo.**
"Necesito un post para promocionar el café de temporada." Lo escribe como se lo
diría a una persona.

**3. El sistema arma la petición completa.**
Aquí está la magia, y es más simple de lo que parece: el sistema **no le manda a
la inteligencia artificial solo lo que el usuario escribió**. Le manda eso *más*
todo lo que ya sabe del negocio. Es como la diferencia entre decirle a un
diseñador "hazme un volante" y decirle "hazme un volante para mi cafetería de
barrio en Tegucigalpa, que atiende a gente que trabaja cerca, con tono cercano,
en estos colores, para promocionar el café de temporada".

**4. Vuelve un resultado ordenado, no un párrafo suelto.**
La respuesta no llega como un texto largo. Llega separada en piezas: el gancho, el
texto principal, la llamada a la acción, los hashtags, y una sugerencia de cómo
debería verse la imagen. Cada pieza es editable por separado.

**5. El usuario lo corrige y lo guarda.**
Queda guardado como un proyecto, con historial. Si mañana lo cambia y no le gusta,
puede volver a la versión anterior.

---

## 4. Las partes del sistema

Piensa en un restaurante. Es la comparación más fiel:

| En el restaurante | En HiTrendy | Quién lo llevó |
|---|---|---|
| **El salón y el menú** — lo que el cliente ve y toca | La aplicación web: las pantallas, los botones, el carrusel | Roberto |
| **La cocina** — donde se prepara todo, el cliente nunca entra | El servidor: recibe los pedidos, arma el contenido, guarda todo | Ewin |
| **Las puertas, el teléfono y los proveedores** — cómo entra y sale todo del restaurante | Las conexiones: seguridad, límites, llaves de acceso, servicios externos | Edware |
| **La decoración, la vajilla, la identidad del lugar** | El diseño: colores, tipografías, cómo se ve todo | Equipo de diseño |
| **El archivo del restaurante** — recetas, historial, inventario | La base de datos | Ewin |
| **El chef invitado** — se puede cambiar sin cerrar el restaurante | La inteligencia artificial | Edware |

Las dos ideas que hay que entender de este cuadro:

**El salón y la cocina están separados.** La aplicación web no sabe cómo se hace el
contenido, solo lo pide. La cocina no sabe cómo se ve la pantalla, solo entrega el
resultado. Eso permite cambiar el diseño sin tocar la cocina, y cambiar la cocina
sin rediseñar la pantalla.

**El chef es reemplazable.** El sistema no está casado con una empresa de
inteligencia artificial. Se puede cambiar por otra sin reescribir el proyecto. Eso
es una decisión de arquitectura, no un accidente.

---

## 5. Quién hizo qué

| Persona | Área | En una frase |
|---|---|---|
| **Ewin** | Desarrollo principal | Construyó la cocina: cómo se genera el contenido, cómo se guarda y cómo se organiza todo |
| **Edware** | Conexiones y configuración | Construyó las puertas: seguridad, límites de uso, y la conexión con los servicios externos |
| **Roberto** | Interfaz e integración | Construyó el salón y lo conectó con la cocina, junto con Ewin |
| **Equipo de diseño (3)** | Identidad visual | Definieron cómo se ve, cómo se siente y cómo se lee todo el producto |

---

## 6. Ewin — la cocina

### Qué hiciste

Todo lo que pasa "del lado de adentro": recibir un pedido, prepararlo, guardarlo y
poder recuperarlo después.

### Las cuatro cosas que debes poder explicar

**1. El sistema le pone reglas a la inteligencia artificial.**

La IA no puede responder lo que quiera. Antes de aceptar una respuesta, el sistema
revisa que venga con todas las piezas que debe traer: gancho, texto, llamada a la
acción, hashtags, sugerencia visual. Si falta algo o viene desordenado, se rechaza.

*Analogía:* es un formulario, no una hoja en blanco. La IA tiene que llenar
casillas, no escribir una carta. Por eso el resultado siempre se puede mostrar
bonito y editar por partes.

**2. Nunca se cobra dos veces.**

Cada vez que se genera contenido, eso cuesta dinero real. Si al usuario se le va
el internet y el botón se presiona dos veces, el sistema reconoce que es el mismo
pedido y devuelve el resultado que ya tenía, en vez de generar (y pagar) otra vez.

*Analogía:* como cuando pagas en un datáfono, se corta la señal, y el sistema del
banco reconoce que es la misma compra en lugar de cobrarte doble.

**3. Todo tiene historial.**

Cuando el usuario edita un contenido guardado, la versión anterior no se pierde.
Puede volver atrás. Un proyecto se puede duplicar para hacer una variante, y se
puede exportar.

**4. Cada cosa en su lugar.**

El sistema está dividido en áreas que no se meten unas con otras: los usuarios por
un lado, los negocios por otro, las conversaciones por otro, las plantillas por
otro. Eso es lo que permite que el proyecto haya crecido tanto sin volverse un
nudo.

### Si te preguntan

- *"¿Qué pasa si la IA responde cualquier cosa?"* → No llega al usuario. El sistema
  revisa que la respuesta traiga todas sus piezas; si no, la rechaza.
- *"¿Y si el usuario da doble clic?"* → Se reconoce como el mismo pedido y no se
  genera dos veces.
- *"¿Se puede recuperar algo borrado por error?"* → Sí, hay historial de versiones.

---

## 7. Edware — las puertas y las llaves

### Qué hiciste

Todo lo que conecta el sistema con el mundo de afuera, y todo lo que lo protege.

### Las cinco cosas que debes poder explicar

**1. El sistema funciona sin pagar nada.**

Esta es la más impresionante y la más fácil de explicar. El proyecto trae un modo
en el que **todo funciona sin conectar ni una sola cuenta de pago**: la IA, las
imágenes, el correo, el almacenamiento. Se ve completo, se navega completo, se
demuestra completo. Cuando se quiera conectar a los servicios reales, es cambiar
una configuración, no reprogramar.

*Analogía:* es una maqueta de casa que tiene la luz funcionando con baterías. Le
puedes conectar la corriente real cuando quieras, pero mientras tanto se ve y se
usa igual.

**2. El sistema se niega a arrancar mal configurado.**

Si alguien intenta poner el proyecto en producción con la configuración de
pruebas, **no enciende**. Da un mensaje claro de qué está mal. Está hecho a
propósito.

*Analogía:* un carro que no arranca si la puerta está abierta. Molesta un segundo,
pero evita un accidente.

**3. Nadie puede abusar del sistema.**

Las partes caras y sensibles —iniciar sesión, registrarse, generar contenido—
tienen un límite de cuántas veces se pueden usar en un rato. Si alguien intenta
mil veces seguidas, el sistema le dice "espera un momento" en vez de caerse o
gastar dinero.

**4. Las llaves ajenas se guardan bajo llave.**

Cuando un usuario conecta su cuenta de Instagram, el sistema recibe una credencial
que da acceso a esa cuenta. Esa credencial **se guarda cifrada**. Ni siquiera
alguien que lograra ver la base de datos podría usarla.

*Analogía:* es la diferencia entre guardar la llave de la casa de un vecino en un
cajón, o guardarla dentro de una caja fuerte adentro del cajón.

**5. Se puede cambiar el proveedor de inteligencia artificial.**

Hay un solo lugar en todo el proyecto donde se decide qué IA se usa. Cambiarla es
cambiar una línea de configuración. No hay que tocar nada más.

### Si te preguntan

- *"¿Cuánto cuesta operar esto?"* → Puede correr en cero. Y cuando se conecta a
  servicios reales, hay un límite de gasto diario por usuario.
- *"¿Es seguro?"* → Contraseñas protegidas, límites contra abuso, credenciales de
  terceros cifradas, y una configuración que no permite arrancar mal.
- *"¿Y si esa empresa de IA sube los precios o cierra?"* → Se cambia por otra. El
  proyecto no depende de una sola.

---

## 8. Roberto — el salón

### Qué hiciste

Todo lo que el usuario ve y toca, y la conexión de eso con la cocina.

### Las cuatro cosas que debes poder explicar

**1. El carrusel de plantillas recomendadas.**

En la pantalla principal hay una vitrina que se desliza con las plantillas
sugeridas para ese negocio en particular. No son plantillas al azar: el sistema
compara la plataforma que usa el negocio, su objetivo y su categoría, y muestra
primero las que más coinciden. Cada tarjeta explica en una línea *por qué* se la
está recomendando.

Sobre cómo está hecho: **el deslizamiento lo hace el propio navegador**, no una
librería descargada de internet. Eso significa que funciona con el dedo en el
celular exactamente como el usuario espera, funciona con el teclado para quien no
usa mouse, y no le agrega peso a la página.

*Analogía:* en vez de construir una banda transportadora propia, se usó la que ya
venía instalada en el edificio. Funciona mejor y no hay que darle mantenimiento.

**2. Si algo falla, la pantalla no se rompe.**

Si el sistema de recomendaciones no responde, la sección **no queda vacía**:
muestra el catálogo normal. Si una imagen no carga, aparece un espacio del mismo
tamaño en vez de que se descuadre todo. Si el negocio todavía no ha configurado su
plataforma, no se muestra un error, se muestran plantillas generales.

*Analogía:* un restaurante que se queda sin un ingrediente y sirve el plato con la
alternativa, en vez de cerrar la cocina.

**3. El arreglo del login.**

Había un problema real: la aplicación se quedaba trabada en la pantalla de inicio
de sesión. Eran dos causas distintas:

- Cuando el servidor no contestaba, la pantalla se quedaba esperando *para
  siempre*. Se corrigió: si no hay respuesta clara, se muestra el formulario. Una
  pantalla que no protege nada no debería poder atrapar a nadie.
- Si alguien había empezado un registro y no lo terminó, el sistema lo mandaba de
  vuelta al registro **cada vez que intentaba entrar**, durante un día completo. Se
  corrigió: ahora aparece un aviso amable — "tienes un registro sin terminar,
  ¿quieres continuarlo?" — y el usuario decide. Un borrador es una oferta, no un
  desvío obligatorio.

**4. Todo pasa por un solo punto.**

Toda la comunicación entre la pantalla y la cocina pasa por un único lugar del
código. Ninguna pantalla habla con el servidor por su cuenta. Eso significa que si
mañana cambia algo de cómo se conversa con el servidor, se arregla una sola vez y
no en veinte pantallas distintas.

*Bonus:* la aplicación está en **español, inglés y portugués**.

### Si te preguntan

- *"¿Por qué no usaron una librería de carrusel?"* → Porque el navegador ya lo hace
  mejor: gestos táctiles, teclado y rendimiento, sin peso extra.
- *"¿Qué pasa si la recomendación falla?"* → Se muestra el catálogo normal. El
  usuario ni se entera.
- *"¿Cómo supieron qué arreglar en el login?"* → Se reprodujo el problema y se
  encontró que eran dos causas distintas, no una.

---

## 9. Equipo de diseño gráfico

Ustedes ya saben lo que hicieron. Esta sección es solo para conectar su trabajo
con lo que se ve en pantalla, que es la pregunta que probablemente reciban.

### La idea que hay que saber explicar: el sistema de colores

En este proyecto **ningún programador escoge un color**.

Existe una lista oficial de colores y estilos —la paleta de la marca— y toda la
aplicación se construye tomando de ahí. Un programador no puede escribir "este
botón va morado"; tiene que decir "este botón usa el color principal", y el color
principal está definido en un solo lugar, por diseño.

Esto tiene dos consecuencias que vale la pena decir en voz alta:

1. **Cambiar la identidad visual completa es cambiar una lista.** Si mañana la
   marca cambia de morado a verde, se edita en un lugar y cambia toda la
   aplicación.
2. **Un programador no puede romper el diseño sin darse cuenta**, porque no tiene
   colores sueltos que tocar.

*Analogía:* es como una obra donde el arquitecto dejó definida la paleta de
pinturas y los obreros solo pueden pedir "pintura de pared" o "pintura de
detalle". Nadie mezcla su propio color en el balde.

### Cómo se aplicó en lo último que se agregó

El carrusel nuevo del dashboard **no usó ni un color nuevo**. Fondo, borde,
sombra, botón y forma redondeada: todo salió de la paleta que ustedes definieron.
Por eso se ve como si siempre hubiera estado ahí.

También vienen del diseño las proporciones de las miniaturas: vertical alargada
para reels y stories, vertical corta para posts y anuncios. No son medidas
inventadas por el código.

### Lo demás que definieron y está aplicado

- El tono de voz de todos los textos de la aplicación.
- Los estados: qué se ve mientras carga, qué se ve cuando no hay nada, qué se ve
  cuando algo falla.
- La accesibilidad: contraste legible, y la aplicación **respeta la configuración
  del usuario que pide menos animaciones** (hay gente a quien el movimiento en
  pantalla le causa mareo).

---

## 10. Las cinco ideas que hacen que este proyecto se vea serio

Si solo se recuerdan cinco cosas de toda la guía, que sean estas. Cualquiera del
equipo debería poder decirlas.

**1. La IA llena un formulario, no escribe una carta.**
La respuesta tiene que traer piezas definidas. Si no las trae, se rechaza. Por eso
el resultado siempre se puede editar por partes y nunca sale algo raro.

**2. Siempre hay un plan B.**
Casi ninguna falla rompe la pantalla. Si las recomendaciones no cargan, se muestra
el catálogo. Si no hay conexión a la IA, hay un modo de demostración. Si no hay
servidor de imágenes, se guardan localmente. El sistema se degrada, no se cae.

**3. No se cobra dos veces.**
Un mismo pedido repetido se reconoce y no se vuelve a generar. Importa porque cada
generación cuesta dinero real.

**4. El motor de IA es reemplazable.**
No hay dependencia de una sola empresa. Cambiarlo es configuración, no
reprogramación.

**5. Funciona sin conectar nada.**
Se puede clonar el proyecto y verlo funcionando completo sin una sola cuenta de
pago. Eso es lo que hace que se pueda demostrar en cualquier computadora.

---

## 11. Cómo se demuestra en vivo (5 minutos)

Este es el guion. Vale la pena que los tres de programación lo puedan narrar.

1. **Entrada** — La página de inicio. Sencilla a propósito: solo dos acciones.
2. **Registro y cuestionario** — Se llenan las cuatro pantallas del negocio.
   *Dato que impresiona:* si cierras el navegador a la mitad, al volver retomas
   donde ibas. El avance se guarda en el servidor, no en el navegador.
3. **Pantalla principal** — Aquí está el carrusel de plantillas recomendadas para
   ese negocio, con el "por qué" de cada una.
4. **Pedir contenido** — Se escribe la petición en lenguaje normal y vuelve el
   resultado separado en piezas editables.
5. **Editar y guardar** — Se corrige algo, se guarda, se muestra el historial de
   versiones.
6. **Ajustes** — Perfil del negocio, identidad de marca, idioma, y cuánto se ha
   consumido.

---

## 12. Preguntas típicas y respuestas cortas

**¿En qué se diferencia de solo usar ChatGPT?**
En que HiTrendy ya conoce el negocio. No hay que explicarle cada vez quién eres,
qué vendes y cómo quieres sonar. Además el resultado viene ordenado y editable, y
queda guardado con historial.

**¿La IA la hicieron ustedes?**
No, y hacerlo habría sido un error. Se usa un modelo ya entrenado, igual que uno no
fabrica su propio motor para vender carros. El trabajo está en cómo se le habla al
modelo, en cómo se valida lo que responde, y en todo lo que rodea eso.

**¿Y si la IA se equivoca o inventa?**
Dos protecciones: la respuesta tiene que cumplir un formato o se rechaza, y todo
lo que llega al usuario es editable. El sistema propone, el usuario decide.

**¿Qué pasa si se cae el internet a mitad de un pedido?**
El pedido no se duplica ni se cobra dos veces, y el trabajo que ya iba guardado se
conserva.

**¿Se puede publicar directo a Instagram?**
En esta versión no, y fue una decisión, no un olvido. Publicar automáticamente
exige permisos, revisiones y responsabilidades que no correspondían a un primer
lanzamiento. Sí existe la conexión de la cuenta, preparada para ese siguiente paso.

**¿Cuánta gente aguanta?**
Las tareas pesadas —generar imágenes, generar video— no se hacen mientras el
usuario espera: se ponen en una fila y las procesa un ayudante aparte. Ese ayudante
se puede multiplicar si crece la demanda, sin cambiar el resto.

**¿Cuánto tiempo tomó?**
Está construido por etapas, cada una con su documentación y sus pruebas. La
documentación del proyecto está en el mismo repositorio, no en una carpeta aparte.

**¿Está terminado?**
El producto funciona de punta a punta. Quedan cuatro pruebas automáticas
desactualizadas —revisan pantallas que después se rediseñaron— y conectar los
servicios de pago reales cuando se quiera salir a producción.

---

## 13. Qué falta (y por qué está bien decirlo)

Ser honesto sobre lo pendiente se ve mejor que fingir que no existe. Si preguntan:

- **El producto funciona completo** y se puede demostrar de principio a fin.
- **Hay cuatro pruebas automáticas desactualizadas.** No son fallas del producto:
  son pruebas escritas para una versión anterior de unas pantallas que después se
  rediseñaron. La prueba sigue buscando un botón que ahora se llama distinto. Está
  verificado que fallaban igual desde antes de los últimos cambios.
- **Falta conectar los servicios reales de pago** para salir a producción. Hoy
  corre en modo de demostración, que es exactamente lo que se necesita para
  presentarlo.

---

## 14. Diccionario rápido

| Si escuchas... | Significa... |
|---|---|
| **Backend / servidor** | La cocina. Donde se prepara todo, el usuario no lo ve |
| **Frontend / interfaz** | El salón. Las pantallas y botones que el usuario sí ve |
| **Base de datos** | El archivo. Donde queda guardado todo |
| **Plantilla** | Un formato de publicación listo para adaptar |
| **Proyecto** | Un contenido ya generado y guardado por el usuario |
| **Modo demostración** | Todo funciona sin conectar cuentas de pago |
| **Plan B / respaldo** | Lo que se muestra cuando algo no está disponible |
| **Proveedor** | Un servicio externo: la IA, el correo, el almacenamiento |
| **Migración** | Un cambio ordenado y reversible en la estructura del archivo |
| **Prueba automática** | Un robot que revisa que el sistema siga funcionando después de cada cambio |
| **Carrusel** | La vitrina que se desliza mostrando plantillas |
| **Historial de versiones** | Poder volver a como estaba antes de un cambio |
