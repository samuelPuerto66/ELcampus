# Facturación electrónica (DIAN): qué preguntar antes de construirla

Este documento no es asesoría tributaria. Es la lista de preguntas que hay
que llevarle **al contador del negocio**, y lo que el sistema tendría que
cambiar según lo que responda. Conviene hacerlo **antes de diciembre**: si
el negocio está obligado y no factura como debe, las sanciones de la DIAN
pueden ir desde multas hasta el cierre temporal del establecimiento, y no
es algo para descubrir en plena temporada alta.

Por qué no está programado todavía: la forma de hacerlo depende por
completo de las respuestas (si aplica, qué documento, qué impuestos, con
qué proveedor). Construirlo a ciegas sería escribir código que después hay
que botar.

## Las preguntas para el contador

1. **¿El negocio está obligado a facturar electrónicamente?** Depende de
   cómo está inscrito el dueño o la empresa en el RUT: si es responsable de
   IVA, si está en el Régimen Simple de Tributación, y de cuánto factura al
   año.

2. **Si está obligado: ¿qué documento se entrega en cada venta?**
   - En el mostrador, normalmente un **documento equivalente electrónico
     POS** (el tiquete de la caja, pero electrónico).
   - Cuando el cliente pide factura a su nombre (una empresa, por ejemplo),
     una **factura electrónica de venta** con sus datos.
   - Preguntar desde qué monto el cliente puede exigir factura en vez del
     tiquete.

3. **¿Qué impuesto lleva cada cosa?** Hoy el sistema maneja precios finales
   sin separar impuestos. Para facturar hay que saber, producto por
   producto:
   - En el supermercado: IVA del 19 %, del 5 %, o productos excluidos o
     exentos (muchos de la canasta familiar).
   - En el restaurante y el bar: si se cobra el impuesto nacional al
     consumo, o si va incluido en el Régimen Simple.

4. **¿Con qué proveedor tecnológico?** La factura no se le manda directo a
   la DIAN desde la caja: pasa por un proveedor autorizado. Preguntar si el
   contador ya trabaja con uno (es común que lo tenga), porque el sistema
   se conectaría a ese.

5. **¿Ya existe una resolución de numeración?** Es el rango de números que
   la DIAN autoriza para las facturas. Sin ella no se puede emitir nada.

6. **¿Cómo se maneja una venta anulada?** Con factura electrónica, una
   venta ya emitida no se "borra": se emite una nota crédito.

7. **¿Cómo va la propina en la factura?** No es ingreso del negocio, así
   que normalmente se muestra aparte del valor de la venta.

## Lo que cambiaría en el sistema

Según las respuestas, esto es lo que habría que construir:

| Si el contador dice… | Hay que agregar |
|---|---|
| Sí está obligado | Conexión con el proveedor: al cobrar, la venta se manda y se guarda el número que devuelve la DIAN |
| Cada producto lleva su impuesto | Un campo de tarifa en productos y platos, y cargarlo en todo el catálogo |
| El cliente puede pedir factura a su nombre | En la caja, un paso opcional para escribir su documento, nombre y correo |
| Las anulaciones van con nota crédito | Que "Anular venta" emita la nota crédito en vez de solo marcarla |
| Hay que entregar tiquete impreso | Impresora térmica con el código QR que exige la DIAN |

Y una regla que el diseño tiene que cumplir sí o sí: **si se cae el
internet, la caja tiene que seguir cobrando** y mandar los documentos
cuando vuelva la conexión. El sistema ya funciona así con los pedidos del
mesero, así que la idea es la misma.

## Lo que ya está listo

- Cada venta tiene el campo `factura_electronica_id`, reservado para el
  número que devuelva la DIAN.
- Las ventas nunca se borran y los precios quedan congelados al cobrar:
  lo que se facturó siempre se puede reconstruir tal cual.
- Las anulaciones, los descuentos y las correcciones ya quedan con quién,
  cuándo y por qué, que es lo que también pide una auditoría.

## Siguiente paso

Llevarle este documento al contador y anotar sus respuestas aquí mismo.
Con las respuestas en la mano, la integración se puede planear en firme.
