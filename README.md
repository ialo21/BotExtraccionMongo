# BotExtraccionMongo

Robot automatizado para extraer logs de MongoDB Atlas, generar IPE (Informe de Proceso de Extracción) y subir resultados a Google Drive.

## Estructura del proyecto

```
RobotExtraccionMongo/
├── assets/
│   └── CDBD_IPE_MongoAtlas_.xlsx  # Plantilla Excel para el informe IPE
├── src/
│   ├── evidence.py                # Capturas de pantalla
│   ├── ipe.py                     # Generación automática de IPE
│   ├── mongo_atlas.py             # Navegación y descarga de logs
│   ├── drive.py                   # Subida de resultados a Google Drive
│   └── ...
├── output/
│   └── ejecuciones/               # Resultados por timestamp
│       └── robot-extraccion-mongo/
│           └── YYYYMMDD_HHMMSS/
│               ├── logs/          # Capturas intermedias y run.log
│               └── resultados/    # Logs descargados, capturas finales e IPE
│                   ├── mongod-audit-log/  # Evidencias de audit log
│                   └── mongod/            # Evidencias de log general
├── main.py
├── config.py
└── requirements.txt
```

## Configuración inicial

### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 2. Configurar plantilla IPE
- Coloca tu archivo `CDBD_IPE_MongoAtlas_.xlsx` en la carpeta `assets/`
- La plantilla debe tener:
  - **Hoja 1** con las celdas de cabecera (I3, F4, F5, C11, C17)
  - **Fila 26** (celda D26) como punto de inicio para insertar "Captura 1"
  - **Espaciado de 36 filas** entre cada captura (D26, D62, D98)

### 3. Configurar Google OAuth (Gmail + Drive)

El bot necesita acceso a Gmail (para OTP) y Google Drive (para subir resultados).

1. **Generar credenciales OAuth**: En Google Cloud Console, crea un proyecto y habilita Gmail API y Drive API
2. **Configurar `.env`** con tus credenciales:
   ```env
   GMAIL_CLIENT_ID=tu_client_id.apps.googleusercontent.com
   GMAIL_CLIENT_SECRET=tu_client_secret
   GMAIL_PROJECT_ID=tu_project_id
   ```

3. **Generar token de autorización**:
   ```bash
   python generate_token.py
   ```
   Esto abrirá el navegador para autorizar acceso a Gmail y Drive. El token se guardará en `token.json`.

   **IMPORTANTE**: Si ya tenías un `token.json` generado ANTES de agregar Drive, debes:
   - Eliminar el archivo `token.json`
   - Ejecutar `python generate_token.py` nuevamente para obtener permisos de Drive

### 4. Configurar variables de entorno
Crea un archivo `.env` con:
```env
MONGO_USER=tu_usuario@interseguro.com.pe
MONGO_PASSWORD=tu_password
ANTICAPTCHA_API_KEY=tu_api_key
HEADLESS=False
DRIVE_PARENT_FOLDER_ID=1CKY8Wq8hKtcgifHb26krW9ajctX4j-HR
```

## Proceso de extracción

El bot ejecuta los siguientes pasos automáticamente:

1. **Login** en MongoDB Atlas
2. **Navegación** al cluster configurado
3. **Acceso** a la sección de logs
4. **Descarga** de `mongod-audit-log` (con capturas de evidencia)
5. **Generación** de IPE para `mongod-audit-log`
6. **Descarga** de `mongod` (con capturas de evidencia)
7. **Generación** de IPE para `mongod`
8. **Subida** de todos los resultados a Google Drive

### Estructura de salida local

Cada ejecución genera una carpeta timestamped:
```
resultados/
├── mongod-audit-log/
│   ├── *.png (capturas de evidencia)
│   ├── vis-data-prd-shard-00-01...MONGODB_AUDIT_LOG.log.gz
│   └── CDBD_IPE_MongoAtlas_mongod-audit-log_<ddmm-ddmm>.xlsx
└── mongod/
    ├── *.png (capturas de evidencia)
    ├── vis-data-prd-shard-00-01...mongodb.log.gz
    └── CDBD_IPE_MongoAtlas_mongod_<ddmm-ddmm>.xlsx
```

### Generación de IPE

El bot genera dos IPEs (uno por cada tipo de log):
1. Escribe datos en celdas específicas (fecha, usuario, objetivo)
2. Inserta capturas PNG en orden cronológico desde la fila 26, columna D (D26, D62, D98)
3. Guarda el archivo con nomenclatura específica del proceso

### Subida a Google Drive

Los resultados se suben automáticamente siguiendo esta estructura:
```
[PADRE: 1CKY8Wq8hKtcgifHb26krW9ajctX4j-HR]/
└── [AÑO]/              # ej: 2026
    └── [TRIMESTRE]/    # ej: 1Q, 2Q, 3Q, 4Q
        └── MONGODB/
            └── [TIMESTAMP]/     # ej: 20260303_235200
                ├── mongod-audit-log/
                └── mongod/
```

El año y trimestre se determinan automáticamente según la mayoría de días del periodo extraído.
