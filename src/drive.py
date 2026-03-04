"""
Integración con Google Drive para subir resultados de extracciones.

Estructura de carpetas:
    [PADRE]/[AÑO]/[TRIMESTRE]/MONGODB/[FECHA_EJECUCION]/[mongod|mongod-audit-log]/
"""
from pathlib import Path
from datetime import date
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import config


# Scope completo para listar carpetas existentes y reutilizarlas
_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_service():
    """Crea un servicio de Drive autenticado usando el token.json compartido."""
    creds = Credentials.from_authorized_user_file(str(config.GMAIL_TOKEN_PATH), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config.GMAIL_TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _determinar_anno_trimestre(start: date, end: date) -> tuple[str, str]:
    """
    Determina el año y trimestre predominante del periodo.
    
    Args:
        start: Fecha de inicio del periodo
        end: Fecha de fin del periodo
    
    Returns:
        (año, trimestre) ej: ("2026", "1Q")
    """
    from datetime import timedelta
    
    # Calcular el punto medio del periodo
    dias_total = (end - start).days
    fecha_media = start + timedelta(days=dias_total // 2)
    
    anno = str(fecha_media.year)
    mes = fecha_media.month
    
    # Determinar trimestre: 1-3 -> 1Q, 4-6 -> 2Q, 7-9 -> 3Q, 10-12 -> 4Q
    if mes <= 3:
        trimestre = "1Q"
    elif mes <= 6:
        trimestre = "2Q"
    elif mes <= 9:
        trimestre = "3Q"
    else:
        trimestre = "4Q"
    
    return anno, trimestre


def _buscar_o_crear_carpeta(service, nombre: str, parent_id: str) -> str:
    """
    Busca una carpeta por nombre en un padre específico, o la crea si no existe.
    
    Args:
        service: Servicio de Drive
        nombre: Nombre de la carpeta a buscar/crear
        parent_id: ID de la carpeta padre
    
    Returns:
        ID de la carpeta encontrada o creada
    """
    # Buscar carpeta existente
    query = f"name='{nombre}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)',
        pageSize=1
    ).execute()
    
    items = results.get('files', [])
    
    if items:
        return items[0]['id']
    
    # Crear carpeta si no existe
    file_metadata = {
        'name': nombre,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    
    folder = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()
    
    print(f"  → Carpeta creada en Drive: {nombre}")
    return folder['id']


def _subir_archivo(service, file_path: Path, parent_id: str) -> str:
    """
    Sube un archivo a Drive.
    
    Args:
        service: Servicio de Drive
        file_path: Path local del archivo
        parent_id: ID de la carpeta padre en Drive
    
    Returns:
        ID del archivo subido
    """
    file_metadata = {
        'name': file_path.name,
        'parents': [parent_id]
    }
    
    media = MediaFileUpload(str(file_path), resumable=True)
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return {
        "id": file['id'],
        "url": f"https://drive.google.com/file/d/{file['id']}/view",
    }


def subir_archivo_a_drive(file_path: Path, parent_id: str) -> dict[str, str]:
    """Helper público para subir un archivo puntual a una carpeta de Drive."""
    service = _get_service()
    return _subir_archivo(service, file_path, parent_id)


def _subir_directorio_recursivo(service, local_dir: Path, parent_id: str) -> None:
    """
    Sube recursivamente todo el contenido de un directorio local a Drive.
    
    Args:
        service: Servicio de Drive
        local_dir: Path local del directorio
        parent_id: ID de la carpeta padre en Drive
    """
    for item in local_dir.iterdir():
        if item.is_file():
            print(f"    → Subiendo: {item.name}")
            _subir_archivo(service, item, parent_id)
        elif item.is_dir():
            # Crear subcarpeta y subir recursivamente
            subfolder_id = _buscar_o_crear_carpeta(service, item.name, parent_id)
            _subir_directorio_recursivo(service, item, subfolder_id)


def subir_resultados_a_drive(
    resultados_dir: Path,
    run_ts: str,
    start: date,
    end: date
) -> dict[str, dict[str, str]]:
    """
    Sube los resultados de una ejecución a Google Drive siguiendo la estructura:
    [PADRE]/[AÑO]/[TRIMESTRE]/MONGODB/[run_ts]/mongod-audit-log/...
                                              /mongod/...
    
    Args:
        resultados_dir: Path local de la carpeta resultados/
        run_ts: Timestamp de la ejecución (ej: "20260303_235200")
        start: Fecha de inicio del periodo
        end: Fecha de fin del periodo
    
    Returns:
        Diccionario con IDs y URLs de Drive:
        {
            "mongod-audit-log": {"id": "...", "url": "..."},
            "mongod": {"id": "...", "url": "..."}
        }
    """
    if not config.DRIVE_PARENT_FOLDER_ID:
        print("  [aviso] DRIVE_PARENT_FOLDER_ID no configurado. Omitiendo subida a Drive.")
        return {}
    
    print("\n[N/N] Subiendo resultados a Google Drive...")
    
    try:
        service = _get_service()
        
        # Determinar año y trimestre
        anno, trimestre = _determinar_anno_trimestre(start, end)
        print(f"  → Periodo: {anno} - {trimestre}")
        
        # Navegar/crear estructura de carpetas
        carpeta_anno = _buscar_o_crear_carpeta(service, anno, config.DRIVE_PARENT_FOLDER_ID)
        carpeta_trimestre = _buscar_o_crear_carpeta(service, trimestre, carpeta_anno)
        carpeta_mongodb = _buscar_o_crear_carpeta(service, "MONGODB", carpeta_trimestre)
        carpeta_ejecucion = _buscar_o_crear_carpeta(service, run_ts, carpeta_mongodb)
        
        # Subir contenido de resultados_dir (mongod-audit-log/ y mongod/)
        print(f"  → Subiendo archivos desde: {resultados_dir}")
        _subir_directorio_recursivo(service, resultados_dir, carpeta_ejecucion)
        
        # Construir URLs de las carpetas específicas
        carpeta_audit_id = _buscar_o_crear_carpeta(service, "mongod-audit-log", carpeta_ejecucion)
        carpeta_mongod_id = _buscar_o_crear_carpeta(service, "mongod", carpeta_ejecucion)
        
        info = {
            "mongod-audit-log": {
                "id": carpeta_audit_id,
                "url": f"https://drive.google.com/drive/folders/{carpeta_audit_id}",
            },
            "mongod": {
                "id": carpeta_mongod_id,
                "url": f"https://drive.google.com/drive/folders/{carpeta_mongod_id}",
            },
            "execution_folder": {
                "id": carpeta_ejecucion,
                "url": f"https://drive.google.com/drive/folders/{carpeta_ejecucion}",
            },
        }
        
        print("  ✓ Resultados subidos exitosamente a Drive")
        return info
        
    except Exception as e:
        print(f"  [error] No se pudo subir a Drive: {e}")
        print(f"  → Los archivos locales están disponibles en: {resultados_dir}")
        return {}
