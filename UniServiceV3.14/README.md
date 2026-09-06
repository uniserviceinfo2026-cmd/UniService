# UniService

Aplicacion web para que estudiantes universitarios oferten servicios de
reparacion y mantenimiento a precios accesibles, reciban retroalimentacion
de sus clientes y participen en un foro de preguntas de la comunidad.

Hecha con Python (Flask) y SQLite. No necesita Node ni ninguna base de
datos externa: todo funciona con lo que trae este repositorio.

## Estructura

```
uniservice/
├── app.py              -> rutas y logica de la aplicacion
├── db.py                -> conexion y creacion de la base de datos
├── schema.sql            -> tablas y datos iniciales (categorias)
├── requirements.txt
├── templates/            -> vistas HTML (Jinja2)
└── static/
    └── css/style.css     -> estilos
```

## Requisitos

- Python 3.10 o superior

## Instalacion

1. Crear y activar un entorno virtual (opcional pero recomendado):

   ```
   python -m venv venv
   venv\Scripts\activate      (Windows)
   source venv/bin/activate   (Linux / Mac)
   ```

2. Instalar dependencias:

   ```
   pip install -r requirements.txt
   ```

3. Crear la base de datos (se genera el archivo uniservice.db):

   ```
   python db.py
   ```

4. Ejecutar la aplicacion:

   ```
   python app.py
   ```

5. Abrir en el navegador: http://127.0.0.1:5000

## Funcionalidades

- Registro e inicio de sesion de estudiantes.
- Publicar servicios (titulo, descripcion, precio, categoria, modalidad).
- Buscar y filtrar servicios por categoria o palabra clave.
- Dejar resenas y calificacion (1 a 5) a un servicio.
- Foro de preguntas al estilo Reddit: publicar preguntas, comentar y
  votar publicaciones hacia arriba o abajo.
- Perfil con los servicios y publicaciones propias.

## Notas

- Cambia el valor de `app.secret_key` en `app.py` antes de usarla en
  produccion.
- La base de datos es un solo archivo SQLite (`uniservice.db`); si
  quieres reiniciar los datos, borra ese archivo y vuelve a correr
  `python db.py`.
