-- Cierra TODAS las sesiones abiertas (invalida cualquier link con token que se haya compartido).
-- Cada usuario tendrá que volver a iniciar sesión una vez.
delete from sesiones;
