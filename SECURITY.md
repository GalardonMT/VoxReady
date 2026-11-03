# Seguridad

## Reporte responsable

No publiques vulnerabilidades, credenciales, datos personales ni detalles de infraestructura en issues públicos. Comunica el hallazgo al responsable técnico autorizado del proyecto, incluyendo versión, componente afectado, pasos mínimos de reproducción e impacto estimado.

## Manejo de secretos

- Guarda secretos en el gestor de secretos del ambiente o en un `.env` local ignorado por Git.
- No uses variables `NEXT_PUBLIC_*` para secretos: Next.js las incorpora al navegador.
- Rota inmediatamente cualquier credencial expuesta y revisa el historial Git, logs y artefactos de CI.
- Usa tokens diferentes para backend–worker y worker–visión, con al menos 32 caracteres aleatorios.
- No compartas el ZIP de entrega junto con un `.env` real.

## Alcance de soporte

Solo la versión identificada por un commit y un manifiesto SHA-256 puede considerarse una entrega auditable. Una auditoría de código no reemplaza pruebas de penetración sobre la infraestructura desplegada, revisión de permisos cloud ni validación de datos reales.
