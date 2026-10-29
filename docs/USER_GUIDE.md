# Guía básica de usuario — 8D PRO

## Roles
| Rol | Puede |
|---|---|
| Consulta | Ver casos, alertas, catálogo y lecciones **publicadas** |
| Ingeniero de calidad | Crear y editar casos, contención, alertas (borrador), causas y validaciones, acciones, verificaciones de eficacia, lecciones (borrador), generar documentos y exportar Excel |
| Gerente de calidad | Además: aprobar/rechazar/reabrir disciplinas, emitir alertas, aprobar acciones y criterios de eficacia, revisar/publicar/retirar lecciones, cancelar casos, bitácora de la organización |
| Administrador | Además: usuarios y roles |

Reglas de segregación: quien envía una acción a aprobación no la aprueba; el autor de una lección no la revisa.

## Flujo de un caso
1. **Casos 8D → + Nuevo caso.** Se asigna el folio `8D-<planta>-<año>-<n>`; tú quedas como responsable y líder.
2. En **Flujo 8D**, cada disciplina muestra sus requisitos (✓/✕). Guarda borradores cuando quieras; **Enviar a revisión** solo se activa sin pendientes y con la disciplina anterior aprobada. El gerente **aprueba** o **rechaza** (con motivo). Una disciplina enviada o aprobada congela sus datos; **Reabrir** (gerente, con motivo) la devuelve a edición.
3. **D0** origen, severidad, fecha objetivo de cierre, respuesta de emergencia · **D1** equipo (≥ 3, con líder) · **D2** 5W/es-no-es.
4. **D3** acciones de contención (implementar/verificar exige evidencia) y **alerta de calidad**: se prellena desde el caso; agrega fotos NOK/OK y la emite el gerente (PDF con QR). Para cambiarla: **Nueva revisión** (la anterior queda sustituida, no se borra).
5. **D4** Ishikawa 6M: agrega causas propias o de la biblioteca (las sugerencias son hipótesis). En la **matriz** registra cada validación; confirmar o descartar exige método, evidencia y justificación.
6. **D5** una acción **correctiva** por cada causa raíz (responsable y fecha) y un **criterio de eficacia** (indicador, denominador explícito, límite, días mínimos con producción) aprobado por el gerente.
7. **D6** implementa: **Enviar a aprobación** con evidencia o excepción justificada → otra persona aprueba. Registra **verificaciones** de eficacia: deja vacío lo que no se midió (un dato faltante nunca cuenta como cero); el sistema calcula la regla y solo permite «eficaz» si los datos lo respaldan. El resultado no se edita: una nueva medición es otra verificación.
8. **D7** acciones preventivas/sistémicas, actualización de AMEF/plan de control/instrucciones/capacitación y despliegue horizontal (o la justificación de por qué no aplica).
9. **D8** crea la **lección aprendida** desde el caso (se prellena), complétala y envíala a revisión; con la lección aprobada y el resumen de cierre, la aprobación de D8 **cierra el caso**. Un caso cerrado solo se reabre reabriendo D8.

## Lecciones aprendidas
Estados: borrador → en revisión → aprobada → publicada → (sustituida | retirada). Solo el borrador se edita; para cambiar una
publicada crea una **nueva revisión** (la publicada sigue vigente hasta publicar la nueva). **Reutilizar en un caso** registra
cómo se evaluó y aplicó en el caso destino sin modificar la lección ni su caso de origen.

## Documentos y reportes
- Caso → **Documentos y archivos**: vista previa (marca «VISTA PREVIA», no se registra) y emisión del **8D completo**, **avance** y **auditoría** (gerente); **Excel** del caso. Cada emisión crea una revisión nueva y la anterior queda «sustituida». **Verificar** recalcula la huella SHA-256 del archivo.
- **Reportes**: indicadores con su definición (se muestran «Datos insuficientes» cuando no hay muestra mínima), exportación de casos y de bitácora (gerente).
- El SHA-256 demuestra integridad del archivo, **no** es firma electrónica.

## Archivos
PNG, JPEG o PDF de hasta 10 MB; el tipo se valida por contenido. Se guardan en almacenamiento privado y se descargan solo con sesión y permiso.

## Cuenta y administración
- **Contraseña** (encabezado): cambia la tuya; se cierran tus otras sesiones.
- **Administración**: usuarios, rol, plantas visibles (vacío = todas), restablecer contraseña, alta de plantas y logo de la organización (aparece en los PDF nuevos).
- En D4, abre una causa y usa **+ Subcausa** para desglosarla; los **5 porqués** se registran en su propia tarjeta.
- En la lección, la tarjeta **Antes y después** exige al menos una foto de cada lado (sube una nueva o elige una imagen del caso, con leyenda).

## Contención, correos y concentrado
- En **D3**, después de emitir la alerta, usa **Iniciar contención**: se avisa a logística por correo (detener material para re-inspección) con la alerta en PDF. Registra cada **lote revisado** y **finaliza** con el resultado.
- Al **emitir la alerta** se envía al equipo del 8D y a la lista de difusión. Los destinatarios se configuran en **Administración › Notificaciones**, donde también hay un correo de prueba y la bandeja de salida.
- En el **Ishikawa** captura las **incidencias** de cada causa; el sistema muestra además en cuántos 8D anteriores apareció.
- **Concentrado**: todos los 8D con sus hitos (D3 24 h, D4 48 h, D5–D7 7 días, D8 14 días desde la fecha de reporte); se exporta a Excel.
