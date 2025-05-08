# ambientacion/views.py

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
# from django.contrib import messages # Para mensajes de feedback al usuario
from core.models import Ambiente, Empresa, Establecimiento, Lote
from .forms import AmbienteAgronomoFormSet, EmpresaForm, ProcesarAmbientacionLoteForm, ProcesarDigitalizacionLoteForm
from django.contrib import messages # Importar messages
from .forms import EmpresaForm, EstablecimientoForm, SolicitudDigitalizacionLoteForm # Importar todos los forms
from django.db import transaction
from core.models import Tarea # Importar Tarea
from usuarios.models import Rol # Importar Rol
from django.contrib.contenttypes.models import ContentType # Para GenericForeignKey en Tarea
from django.contrib.auth.decorators import user_passes_test # Para verificar rol
from django.contrib.gis.gdal import DataSource, GDALException, SpatialReference # Para SRID
from django.contrib.gis.geos import GEOSGeometry, Polygon, MultiPolygon # Para conversión/validación
from django.contrib.gis.db.models.functions import Transform 
from django.core.files.storage import FileSystemStorage # Para manejo de archivos temporales
import tempfile # Para crear directorios/archivos temporales
import zipfile # Para descomprimir
import os
import shutil # Para borrar directorio temporal
import json # Para manejar el GeoJSON final
from django.contrib import messages
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from django.core.serializers import serialize # Para convertir a GeoJSON
from django.db.models import Count, Q # Para el conteo de lotes vigentes
# Corregir la importación de timezone
from django.utils import timezone  # Importación correcta de timezone de Django
# Remover la importación incorrecta de datetime
# from datetime import *
import json # Para manejar el GeoJSON final

os.environ['PROJ_LIB'] = r'C:\Program Files\QGIS 3.34.12\share\proj'

@login_required
def lista_empresas(request):
    empresas = Empresa.objects.filter(activo=True).order_by('nombre_razon_social')
    return render(request, 'ambientacion/lista_empresas.html', {'empresas': empresas})

@login_required
def crear_empresa(request):
    if request.method == 'POST':
        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save()
            # messages.success(request, f"Empresa '{empresa.nombre_razon_social}' creada con éxito.")
            return redirect('ambientacion:lista_empresas')
    else:
        form = EmpresaForm()
    return render(request, 'ambientacion/formulario_generico.html', {
        'form': form,
        'titulo_pagina': 'Nueva Empresa',
        'titulo_formulario': 'Registrar Nueva Empresa',
        'url_cancelar': 'ambientacion:lista_empresas' # Para el botón de cancelar
    })

@login_required
def detalle_empresa(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id, activo=True)

    # Obtener establecimientos y pre-calcular conteo de lotes vigentes para la tabla
    establecimientos = empresa.establecimientos.filter(activo=True).annotate(
        lotes_vigentes_count=Count('lotes', filter=Q(lotes__estado_version='VIGENTE', lotes__estado_workflow='ACTIVO'))
    ).order_by('nombre')

    # Obtener geometrías vigentes y activas para el mapa - Modificar esta consulta para incluir más estados
    lotes_qs = Lote.objects.filter(
        establecimiento__in=establecimientos,
        estado_version='VIGENTE',
        # estado_workflow='ACTIVO' # Eliminamos esta restricción para ver todos los lotes vigentes
    ).select_related('establecimiento')

    # Agregamos debug para verificar si hay lotes y sus estados
    print(f"Cantidad de lotes encontrados: {lotes_qs.count()}")
    for lote in lotes_qs:
        print(f"Lote: {lote.nombre}, Estado workflow: {lote.estado_workflow}")

    ambientes_qs = Ambiente.objects.filter(
        lote__in=lotes_qs,
        estado_version='VIGENTE',
        estado_workflow='ACTIVO'
    ).select_related('lote', 'lote__establecimiento') # Cargar relaciones para info

    # --- Serialización GeoJSON Controlada ---
    lotes_features = []
    for lote in lotes_qs:
        try:
            # Convertir geometría a WGS84 para Leaflet
            geom_4326 = lote.geometria.transform(4326, clone=True)
            
            # Incluimos info útil para el popup/tooltip
            lote_dict = {
                'id': lote.id,
                'nombre': lote.nombre,
                'id_entidad_conceptual': str(lote.id_entidad_conceptual),
                'establecimiento_nombre': lote.establecimiento.nombre,
                'superficie_calculada_has': lote.superficie_calculada_has
            }
            lotes_features.append({
                "type": "Feature",
                "geometry": json.loads(geom_4326.geojson),  # Usar geometría WGS84
                "properties": lote_dict
            })
        except Exception as e:
            print(f"Error al procesar lote {lote.id}: {e}")
    lotes_geojson_data = {"type": "FeatureCollection", "features": lotes_features}

    ambientes_features = []
    for ambiente in ambientes_qs:
        try:
            # Convertir geometría a WGS84
            geom_4326 = ambiente.geometria.transform(4326, clone=True)
            
            # Incluimos info útil + productividad para colorear
            ambiente_dict = {
                'id': ambiente.id,
                'nombre': ambiente.nombre,
                'id_entidad_conceptual': str(ambiente.id_entidad_conceptual),
                'productividad': ambiente.productividad, # Para colorear
                'superficie_has': ambiente.superficie_has,
                'tipo_suelo_nombre': ambiente.tipo_suelo_nombre,
                'lote_nombre': ambiente.lote.nombre, # Nombre del lote padre
                'establecimiento_nombre': ambiente.lote.establecimiento.nombre
            }
            ambientes_features.append({
                "type": "Feature",
                "geometry": json.loads(geom_4326.geojson),  # Usar geometría WGS84
                "properties": ambiente_dict
            })
        except Exception as e:
            print(f"Error al procesar ambiente {ambiente.id}: {e}")
    ambientes_geojson_data = {"type": "FeatureCollection", "features": ambientes_features}
    # --- Fin Serialización ---

    # Obtener Tareas relacionadas
    content_type_est = ContentType.objects.get_for_model(Establecimiento)
    tareas_relacionadas = Tarea.objects.filter(
        content_type=content_type_est,
        object_id__in=establecimientos.values_list('id', flat=True)
    ).select_related('rol_asignado', 'usuario_asignado_actualmente', 'creado_por').order_by('-fecha_creacion')[:15] # Limitar

    # Añadir más información al contexto para debugging
    context = {
        'empresa': empresa,
        'establecimientos': establecimientos, # Ya tienen 'lotes_vigentes_count' anotado
        'lotes_geojson': json.dumps(lotes_geojson_data), # Convertir a string JSON
        'ambientes_geojson': json.dumps(ambientes_geojson_data), # Convertir a string JSON
        'tareas_relacionadas': tareas_relacionadas,
        'lotes_count': lotes_qs.count(),  # Añadir conteo para verificación
    }
    return render(request, 'ambientacion/detalle_empresa.html', context)
# --- Vista Crear Establecimiento (ACTUALIZADA - Asegúrate que tenga el widget OSM) ---
@login_required
def crear_establecimiento(request, empresa_id):
    # ... (lógica existente) ...
    # Asegúrate que el form inicializa el mapa correctamente
    form = EstablecimientoForm(initial={'punto_referencia': 'SRID=32721;POINT(-56 -33)'})
    # ... (resto de la lógica) ...
    return render(request, 'ambientacion/formulario_establecimiento.html', {
        'form': form,
        'empresa': Empresa,
        'titulo_pagina': 'Nuevo Establecimiento',
        'titulo_formulario': f'Nuevo Establecimiento para {Empresa.nombre_razon_social}',
        'url_cancelar': 'ambientacion:detalle_empresa',
        'id_param_cancelar': Empresa.id
    })
# --- Vista para Iniciar Tarea de Digitalización ---
@login_required
def solicitar_digitalizacion_lote(request, establecimiento_id):
    establecimiento = get_object_or_404(Establecimiento, id=establecimiento_id, activo=True)
    # Lógica de permisos aquí también podría aplicar

    if request.method == 'POST':
        form = SolicitudDigitalizacionLoteForm(request.POST, request.FILES)
        if form.is_valid():
            # (Opcional) Lógica para guardar el archivo adjunto en MEDIA_ROOT
            archivo_referencia = request.FILES.get('archivo_referencia_lotes')
            if archivo_referencia:
                # Asegúrate de tener configurado MEDIA_ROOT y MEDIA_URL en settings.py
                # Aquí iría la lógica para guardar el archivo y obtener su path
                # Ejemplo simple (requiere definir una función guardar_archivo):
                # path_archivo = guardar_archivo(archivo_referencia, f"referencias_lotes/{establecimiento.id}/")
                # print(f"Archivo guardado en: {path_archivo}") # Solo para debug
                 messages.info(request, "Archivo adjunto recibido (lógica de guardado pendiente).") # Placeholder

            # Crear la Tarea para el Área GIS
            try:
                rol_gis = Rol.objects.get(id_rol=Rol.ROL_GIS)
                content_type_est = ContentType.objects.get_for_model(establecimiento)

                descripcion_tarea = f"Solicitud digitalización para Est. '{establecimiento.nombre}' (Empresa: {establecimiento.empresa.nombre_razon_social})."
                if form.cleaned_data.get('nombre_lote_referencia'):
                     descripcion_tarea += f" Ref Lote: {form.cleaned_data['nombre_lote_referencia']}."
                if form.cleaned_data.get('comentarios'):
                     descripcion_tarea += f"\nComentarios: {form.cleaned_data['comentarios']}"
                # Si guardaste el archivo, podrías añadir el path a la descripción o a comentarios internos

                Tarea.objects.create(
                    tipo_tarea = 'DIGITALIZAR_LOTES',
                    rol_asignado = rol_gis,
                    entidad_relacionada = establecimiento, # Vincula la tarea al establecimiento
                    descripcion = descripcion_tarea,
                    creado_por = request.user,
                    # Podrías añadir el path del archivo a comentarios_internos si prefieres
                    # comentarios_internos = f"Archivo adjunto: {path_archivo}" if path_archivo else ""
                )
                messages.success(request, f"Solicitud de digitalización enviada para el establecimiento '{establecimiento.nombre}'.")
            except Rol.DoesNotExist:
                messages.error(request, "No se pudo crear la tarea: El rol 'Área GIS' no está configurado.")
                # Considera no redirigir si hay error para que el usuario vea el mensaje
                return redirect(request.path) # Vuelve a la misma página
            except Exception as e:
                messages.error(request, f"Ocurrió un error al crear la tarea: {e}")
                # Considera no redirigir si hay error
                return redirect(request.path) # Vuelve a la misma página

            # Redirige al detalle de la empresa del establecimiento
            return redirect('ambientacion:detalle_empresa', empresa_id=establecimiento.empresa.id)
    else:
        form = SolicitudDigitalizacionLoteForm()

    return render(request, 'ambientacion/formulario_generico.html', {
        'form': form,
        'titulo_pagina': 'Solicitar Digitalización',
        'titulo_formulario': f'Solicitar Digitalización de Lotes para Establecimiento: {establecimiento.nombre}',
        'url_cancelar': 'ambientacion:detalle_empresa',
        'id_param_cancelar': establecimiento.empresa.id, # ID de la empresa, no del establecimiento
        'empresa': establecimiento.empresa  # Pasar la empresa completa como contexto
    })

# Función helper para verificar rol (puedes ponerla en un utils.py)
def es_rol_gis(user):
    if not user.is_authenticated:
        return False
    try:
        return user.perfil_pronutrition.rol.id_rol == Rol.ROL_GIS
    except: # Captura DoesNotExist u otros errores si el perfil/rol no existe
        return False

@login_required
@user_passes_test(es_rol_gis, login_url='/cuentas/login/') # Redirige si no es GIS
def vista_tareas_gis(request):
    rol_gis = Rol.objects.get(id_rol=Rol.ROL_GIS)
    # Tareas pendientes asignadas directamente al rol GIS
    tareas_pendientes = Tarea.objects.filter(
        rol_asignado=rol_gis,
        estado_tarea='PENDIENTE' # O los estados que consideres 'pendientes' para GIS
    ).order_by('fecha_creacion')

    # Tareas que quizás un GIS específico ya tomó (si implementas esa lógica)
    # tareas_asignadas_usuario = Tarea.objects.filter(
    #    usuario_asignado_actualmente=request.user,
    #    estado_tarea='ASIGNADA' # o 'EN_PROGRESO'
    # ).order_by('fecha_creacion')

    context = {
        'tareas_pendientes': tareas_pendientes,
        # 'tareas_asignadas_usuario': tareas_asignadas_usuario,
    }
    return render(request, 'ambientacion/tareas_gis.html', context)

@login_required
@user_passes_test(es_rol_gis, login_url='/cuentas/login/')
def procesar_digitalizacion_lote(request, tarea_id):
    tarea = get_object_or_404(Tarea, id=tarea_id, rol_asignado__id_rol=Rol.ROL_GIS)
    establecimiento = None
    # Asegurarnos que la tarea esté vinculada a un Establecimiento
    if tarea.content_type == ContentType.objects.get_for_model(Establecimiento):
        establecimiento = tarea.entidad_relacionada
    else:
        messages.error(request, "La tarea seleccionada no está vinculada a un establecimiento válido.")
        return redirect('ambientacion:vista_tareas_gis')

    if tarea.estado_tarea == 'COMPLETADA':
         messages.warning(request, f"La tarea {tarea_id} ya fue completada.")
         # Podrías mostrar detalles de la tarea completada aquí si quieres

    form = ProcesarDigitalizacionLoteForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and form.is_valid():
        uploaded_file = request.FILES['archivo_shape']
        temp_dir = None # Directorio temporal para descomprimir/guardar
        shp_file_path = None
        fs = FileSystemStorage(location=tempfile.gettempdir()) # Usa el directorio temporal del sistema

        try:
            # 1. Guardar archivo temporalmente
            temp_file_name = fs.save(uploaded_file.name, uploaded_file)
            temp_file_path = fs.path(temp_file_name)

            # 2. Descomprimir si es ZIP
            if zipfile.is_zipfile(temp_file_path):
                temp_dir = tempfile.mkdtemp() # Crea un directorio temporal único
                with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                # Buscar el archivo .shp dentro del directorio descomprimido
                for filename in os.listdir(temp_dir):
                    if filename.lower().endswith('.shp'):
                        shp_file_path = os.path.join(temp_dir, filename)
                        break
                if not shp_file_path:
                    raise ValueError("No se encontró un archivo .shp dentro del ZIP.")
            elif temp_file_path.lower().endswith('.shp'):
                shp_file_path = temp_file_path
            else:
                raise ValueError("El archivo debe ser un .zip o un .shp.")

            # 3. Procesar el Shapefile con DataSource
            ds = DataSource(shp_file_path)
            if not ds:
                 raise ValueError(f"No se pudo abrir el archivo como fuente de datos GDAL: {shp_file_path}")

            layer = ds[0] # Asumimos una sola capa en el shapefile
            target_srid = 32721 # SRID de nuestra BD
            
            # 3.1 Manejar SRID del archivo 
            source_srid = getattr(layer, 'srs', None)
            if source_srid:
                source_srid = source_srid.srid
                print(f"SRID detectado en el Shapefile: {source_srid}")
            else:
                # No se detectó SRID en el archivo, asumimos WGS84 (EPSG:4326)
                source_srid = 4326
                print(f"SRID no detectado en el Shapefile. Asumiendo EPSG:{source_srid} (WGS84)")
                messages.warning(request, f"El archivo no tiene sistema de coordenadas definido. Se asume WGS84 (EPSG:{source_srid})")

            # 3.2 Analizar los campos disponibles en el Shapefile
            field_names = layer.fields
            print(f"Campos disponibles en el Shapefile: {field_names}")
            
            # 3.2 Determinar qué campo podría contener el nombre del lote
            # Posibles campos para el nombre del lote en orden de preferencia
            possible_name_fields = ['NOMBRE', 'nombre', 'Name', 'NAME', 'name', 'LABEL', 'label', 'ID', 'id']
            name_field = None
            for field in possible_name_fields:
                if field in field_names:
                    name_field = field
                    break

            lotes_creados_ok = []
            errores_procesamiento = []

            # 3.3 Verificar si hay un campo para nombre, si no, generaremos nombres
            if not name_field:
                messages.warning(request, f"No se encontró un campo de nombre en el Shapefile (se buscaron: {', '.join(possible_name_fields)}). Se generarán nombres automáticamente.")
                
            # Establecer un prefijo para nombres autogenerados
            base_name = form.cleaned_data.get('comentarios_gis', '') or 'Lote'
            if base_name == 'Lote' and establecimiento:
                base_name = f"Lote {establecimiento.nombre}"
                
            counter = 1  # Contador para nombres autogenerados

            for feature in layer:
                try:
                    # Intentar obtener el nombre del lote del campo identificado o usar autogenerado
                    if name_field:
                        nombre_lote = feature.get(name_field)
                        # Si el campo existe pero el valor es nulo o vacío
                        if not nombre_lote or nombre_lote.strip() == "":
                            nombre_lote = f"{base_name} {counter}"
                            counter += 1
                    else:
                        # No hay campo de nombre, usar autogenerado
                        nombre_lote = f"{base_name} {counter}"
                        counter += 1

                    geom = feature.geom # Obtener geometría
                    
                    # Asignar explícitamente SRID a la geometría si no lo tiene
                    if geom.srid is None:
                        geom.srid = source_srid
                    
                    # Transformar a SRID de destino (EPSG:32721) si es necesario
                    if geom.srid != target_srid:
                        try:
                            # Usar transform_to en lugar de transform para mejor manejo de errores
                            # (transform_to es un método de OGR que acepta SRID directamente)
                            from django.contrib.gis.gdal import SpatialReference
                            target_srs = SpatialReference(target_srid)
                            geom.transform(target_srs)
                        except Exception as srid_err:
                            errores_procesamiento.append(f"Feature FID {feature.fid} ({nombre_lote}): Error transformando SRID de {geom.srid} a {target_srid}. {srid_err}")
                            print(f"Error detallado de transformación: {srid_err}")
                            continue
                    
                    # Asegurar el SRID correcto (confirmación explícita)
                    geom.srid = target_srid

                    # Validaciones - usando is_valid() en lugar de valid
                    try:
                        is_valid = geom.is_valid() if hasattr(geom, 'is_valid') else True
                        if not is_valid:
                            errores_procesamiento.append(f"Feature FID {feature.fid} ({nombre_lote}): Geometría inválida.")
                            continue
                    except Exception as val_err:
                        # Si hay un error al verificar la validez, asumimos que es válida para continuar
                        print(f"Advertencia: No se pudo verificar la validez de la geometría: {val_err}")
                        
                    # Verificar tipo de geometría
                    if geom.geom_type not in ('Polygon', 'MultiPolygon'):
                        errores_procesamiento.append(f"Feature FID {feature.fid} ({nombre_lote}): Tipo de geometría no es Polígono/MultiPolígono ({geom.geom_type}).")
                        continue

                    # TODO: Validación de solapamiento con otros lotes (opcional pero recomendado)
                    # lotes_solapados = Lote.objects.filter(establecimiento=establecimiento, estado_version='VIGENTE', geometria__intersects=geom)
                    # if lotes_solapados.exists():
                    #     errores_procesamiento.append(f"Feature FID {feature.fid} ({nombre_lote}): Se solapa con lotes existentes.")
                    #     continue

                    # Convertir GDAL Polygon a GEOSGeometry para Django (y manejar tipos)
                    from django.contrib.gis.geos import GEOSGeometry, Polygon, MultiPolygon
                    
                    # Primero convertimos la geometría GDAL a texto WKT
                    geom_wkt = geom.wkt
                    
                    # Luego creamos una geometría GEOS (compatible con Django ORM)
                    geos_geom = GEOSGeometry(geom_wkt, srid=target_srid)
                    
                    # Si es un Polygon simple, lo convertimos a MultiPolygon
                    if isinstance(geos_geom, Polygon):
                        geos_geom = MultiPolygon([geos_geom], srid=target_srid)
                    
                    # Aseguramos que es un MultiPolygon y tiene el SRID correcto
                    if not isinstance(geos_geom, MultiPolygon):
                        errores_procesamiento.append(f"Feature FID {feature.fid} ({nombre_lote}): No se pudo convertir a MultiPolygon.")
                        continue
                    
                    # Validación de la geometría GEOS
                    if not geos_geom.valid:
                        errores_procesamiento.append(f"Feature FID {feature.fid} ({nombre_lote}): Geometría GEOS inválida.")
                        continue

                    # Crear el Lote con la geometría GEOS convertida
                    Lote.objects.create(
                        establecimiento=establecimiento,
                        nombre=str(nombre_lote).strip(),
                        geometria=geos_geom,  # Ahora usamos la geometría GEOS convertida
                        estado_version='VIGENTE',
                        estado_workflow='PENDIENTE_VALIDACION_PRODUCTOR',
                    )
                    lotes_creados_ok.append(str(nombre_lote).strip())

                except Exception as feat_err:
                    # Mejorar el mensaje de error para ser más específico
                    err_msg = f"Feature FID {feature.fid}"
                    if nombre_lote: err_msg += f" (destino: {nombre_lote})"
                    err_msg += f": Error al procesar - {feat_err}"
                    errores_procesamiento.append(err_msg)
                    print(f"Error detallado: {err_msg}")  # Log para debug

            # 4. Manejar Resultados del Procesamiento
            if errores_procesamiento:
                messages.error(request, f"Se encontraron errores al procesar el archivo: {'; '.join(errores_procesamiento)}")
                if not lotes_creados_ok: # Ninguno se creó
                     messages.warning(request, "No se crearon nuevos lotes debido a los errores.")
                     # No cambiamos estado de tarea, el GIS debe subir un archivo corregido
                else: # Algunos se crearon, otros no
                     messages.warning(request, f"Se crearon {len(lotes_creados_ok)} lotes ({', '.join(lotes_creados_ok)}), pero hubo errores con otros. Revise los errores y corrija si es necesario.")
                     # Aquí podrías decidir si completar la tarea o dejarla pendiente para corrección
                     tarea.estado_tarea = 'REQUIERE_CORRECCION' # Ejemplo
                     tarea.save()

            else: # Todo OK
                tarea.estado_tarea = 'COMPLETADA'
                # Ahora timezone.now() funcionará correctamente
                tarea.fecha_finalizacion = timezone.now()
                # Opcional: guardar comentarios del GIS en la tarea
                if form.cleaned_data.get('comentarios_gis'):
                    tarea.comentarios_internos = tarea.comentarios_internos + f"\n---\nGIS ({request.user.username}): {form.cleaned_data['comentarios_gis']}"
                tarea.save()

                # TODO: Crear la siguiente Tarea para VALIDAR_DIGITALIZACION_LOTES asignada al Cliente/Productor o Ing. Agrónomo
                # ... lógica para crear la siguiente tarea ...

                messages.success(request, f"Shapefile procesado con éxito. Se crearon {len(lotes_creados_ok)} lotes: {', '.join(lotes_creados_ok)}. Pendientes de validación por el productor.")
                return redirect('ambientacion:vista_tareas_gis')

        except GDALException as gdal_err:
             messages.error(request, f"Error de GDAL/OGR al procesar el archivo: {gdal_err}. ¿Es un Shapefile válido?")
        except ValueError as val_err:
             messages.error(request, f"Error de validación: {val_err}")
        except Exception as e:
             messages.error(request, f"Error inesperado: {e}")
             print(f"Error detallado: {type(e).__name__} - {e}")  # Imprimir más detalles del error
        finally:
            # 5. Limpiar archivos temporales
            try:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir) # Borra directorio descomprimido
                if fs.exists(temp_file_name):
                    fs.delete(temp_file_name) # Borra archivo subido original
            except Exception as clean_err:
                print(f"Advertencia: No se pudo limpiar archivos temporales: {clean_err}")
                # No relanzar el error de limpieza, el error original es más importante

        # Si llegamos aquí (por error), renderizamos el form de nuevo
        return render(request, 'ambientacion/procesar_digitalizacion.html', {'form': form, 'tarea': tarea, 'establecimiento': establecimiento})

    else: # Método GET
         return render(request, 'ambientacion/procesar_digitalizacion.html', {'form': form, 'tarea': tarea, 'establecimiento': establecimiento})

@login_required
@user_passes_test(es_rol_gis, login_url='/cuentas/login/')
def tomar_tarea_gis(request, tarea_id):
    if request.method == 'POST':
        tarea = get_object_or_404(Tarea, id=tarea_id, rol_asignado__id_rol=Rol.ROL_GIS)
        # Verificar si ya está tomada por otro o completada
        if tarea.estado_tarea == 'PENDIENTE':
            tarea.usuario_asignado_actualmente = request.user
            tarea.estado_tarea = 'ASIGNADA' # O 'EN_PROGRESO' si prefieres
            tarea.save()
            messages.success(request, f"Has tomado la tarea #{tarea.id}.")
        elif tarea.usuario_asignado_actualmente == request.user:
             messages.info(request, f"Ya habías tomado la tarea #{tarea.id}.")
        else:
            messages.warning(request, f"La tarea #{tarea.id} ya está asignada a otro usuario o no está pendiente.")
    else:
        messages.error(request, "Acción no permitida (solo POST).")

    return redirect('ambientacion:vista_tareas_gis') # Vuelve a la lista de tareas



@login_required
def detalle_establecimiento(request, establecimiento_id):
    establecimiento = get_object_or_404(Establecimiento.objects.select_related('empresa'),
                                        id=establecimiento_id, activo=True)
    empresa = establecimiento.empresa

    # Lotes vigentes para el mapa y listados
    lotes_vigentes = Lote.objects.filter(
        establecimiento=establecimiento,
        estado_version='VIGENTE'
    ).order_by('nombre')
    
    # Anotamos el conteo de ambientes vigentes para cada lote (para evitar el error en template)
    from django.db.models import Count, Q
    lotes_vigentes = lotes_vigentes.annotate(
        ambientes_vigentes_count=Count('ambientes', 
                                      filter=Q(ambientes__estado_version='VIGENTE', 
                                               ambientes__estado_workflow='ACTIVO'))
    )

    # Separar lotes por estado para mostrarlos en secciones diferentes
    lotes_pendientes_validacion = lotes_vigentes.filter(estado_workflow='PENDIENTE_VALIDACION_PRODUCTOR')
    lotes_listos_ambientar = lotes_vigentes.filter(estado_workflow__in=['VALIDADO_PRODUCTOR', 'CON_AMBIENTACION_EN_PROCESO'])
    lotes_activos = lotes_vigentes.filter(estado_workflow='ACTIVO')

    # Preparar GeoJSON para el mapa (todos los lotes vigentes del establecimiento)
    lotes_features = []
    for lote in lotes_vigentes:
        # Convertir geometría a WGS84 para Leaflet
        geom_4326 = lote.geometria.transform(4326, clone=True)
        
        lote_dict = {
            'id': lote.id, 'nombre': lote.nombre,
            'id_entidad_conceptual': str(lote.id_entidad_conceptual),
            'superficie_calculada_has': lote.superficie_calculada_has,
            'estado_workflow': lote.get_estado_workflow_display(), # Pasamos el texto legible
            'estado_workflow_code': lote.estado_workflow # Pasamos el código para lógica JS/CSS
        }
        lotes_features.append({
            "type": "Feature",
            "geometry": json.loads(geom_4326.geojson),  # Usar geometría transformada
            "properties": lote_dict
        })
    lotes_geojson_data = {"type": "FeatureCollection", "features": lotes_features}

    # Tareas específicas de este establecimiento
    content_type_est = ContentType.objects.get_for_model(Establecimiento)
    tareas_establecimiento = Tarea.objects.filter(
        content_type=content_type_est, object_id=establecimiento.id
    ).select_related('rol_asignado', 'usuario_asignado_actualmente', 'creado_por').order_by('-fecha_creacion')[:10]

    # Obtener todos los ambientes pendientes de validación para mostrar en una sección específica
    # Útil para que los ingenieros agrónomos puedan ver rápidamente qué necesita validación
    ambientes_pendientes = Ambiente.objects.filter(
        lote__establecimiento=establecimiento,
        estado_version='VIGENTE',
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).select_related('lote')
    
    # Agrupar ambientes pendientes por lote para fácil visualización
    from collections import defaultdict
    lotes_con_ambientes_pendientes = {}
    for ambiente in ambientes_pendientes:
        lote = ambiente.lote
        if lote not in lotes_con_ambientes_pendientes:
            lotes_con_ambientes_pendientes[lote] = 0
        lotes_con_ambientes_pendientes[lote] += 1

    # Obtener todos los ambientes activos para la lista modal
    ambientes_activos = Ambiente.objects.filter(
        lote__establecimiento=establecimiento,
        estado_version='VIGENTE'
    ).select_related('lote').order_by('lote', 'nombre')
    
    # Agrupar ambientes por lote para los modales
    ambientes_por_lote = defaultdict(list)
    for ambiente in ambientes_activos:
        ambientes_por_lote[ambiente.lote.id].append(ambiente)

    context = {
        'establecimiento': establecimiento,
        'empresa': empresa,
        'lotes_pendientes_validacion': lotes_pendientes_validacion,
        'lotes_listos_ambientar': lotes_listos_ambientar,
        'lotes_activos': lotes_activos,
        'lotes_geojson': json.dumps(lotes_geojson_data),
        'tareas_establecimiento': tareas_establecimiento,
        'ROL_CLIENTE': Rol.ROL_CLIENTE, # Pasamos constantes de Rol para chequear en template
        'ROL_ING_AGRONOMO': Rol.ROL_ING_AGRONOMO,
        'ROL_GIS': Rol.ROL_GIS,
        'ambientes_pendientes': ambientes_pendientes,
        'lotes_con_ambientes_pendientes': lotes_con_ambientes_pendientes,
        'ambientes_por_lote': ambientes_por_lote,
    }
    return render(request, 'ambientacion/detalle_establecimiento.html', context)


# --- Vista para VALIDAR Lote (Esqueleto) ---
@login_required
# @user_passes_test(lambda u: u.perfil_pronutrition.rol.id_rol in [Rol.ROL_CLIENTE, Rol.ROL_ING_AGRONOMO]) # Permitir a Cliente o Ing. Agrónomo
def validar_lote(request, lote_id):
    lote = get_object_or_404(Lote, id=lote_id, estado_workflow='PENDIENTE_VALIDACION_PRODUCTOR')
    establecimiento = lote.establecimiento
    empresa = establecimiento.empresa

    # Convertir geometría a WGS84 para Leaflet
    geom_4326 = None
    if lote.geometria:
        try:
            geom_4326 = lote.geometria.transform(4326, clone=True)
        except Exception as e:
            print(f"Error al transformar geometría: {e}")
    
    if request.method == 'POST':
        accion = request.POST.get('accion') # Necesitarás botones con name="accion" value="aprobar/rechazar"

        if accion == 'aprobar':
            lote.estado_workflow = 'VALIDADO_PRODUCTOR' # O 'CON_AMBIENTACION_EN_PROCESO'
            lote.save()

            # Marcar tarea anterior como completada (si la había)
            # ...

            # Crear tarea para GIS para ambientar ESTE lote
            try:
                rol_gis = Rol.objects.get(id_rol=Rol.ROL_GIS)
                content_type_lote = ContentType.objects.get_for_model(Lote)
                Tarea.objects.create(
                    tipo_tarea = 'CREAR_ACTUALIZAR_AMBIENTACION',
                    rol_asignado = rol_gis,
                    entidad_relacionada = lote, # ¡Vinculada al Lote!
                    descripcion = f"Ambientar Lote '{lote.nombre}' (Est: {establecimiento.nombre})",
                    creado_por = request.user
                )
                messages.success(request, f"Lote '{lote.nombre}' aprobado. Tarea de ambientación generada para GIS.")
            except Exception as e:
                messages.error(request, f"Error al crear tarea GIS para ambientación: {e}")

            return redirect('ambientacion:detalle_establecimiento', establecimiento_id=establecimiento.id)

        elif accion == 'rechazar':
            # Cambiar estado a corrección, generar tarea para GIS, etc.
            lote.estado_workflow = 'EN_CORRECCION_GIS' # Necesitarías este estado
            lote.save()
            # Crear tarea CORREGIR_GEOMETRIA_LOTE para GIS con comentarios
            messages.warning(request, f"Lote '{lote.nombre}' marcado para corrección.")
            return redirect('ambientacion:detalle_establecimiento', establecimiento_id=establecimiento.id)

    # Mostrar detalles del lote y botones de Aprobar/Rechazar
    context = {
        'lote': lote,
        'establecimiento': establecimiento,
        'empresa': empresa,
        'lote_geojson': geom_4326.geojson if geom_4326 else None
    }
    return render(request, 'ambientacion/validar_lote_form.html', context)


def es_rol_validador(user): # Cliente o Agrónomo
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol in [Rol.ROL_CLIENTE, Rol.ROL_ING_AGRONOMO]
    except: return False

def es_rol_ambientador(user): # GIS o Agrónomo
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol in [Rol.ROL_GIS, Rol.ROL_ING_AGRONOMO]
    except: return False

def es_rol_gis(user): # Solo GIS
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol == Rol.ROL_GIS
    except: return False
@login_required
@user_passes_test(es_rol_ambientador, login_url='/cuentas/login/') # Permitir a GIS o Ing. Agrónomo
def subir_ambientes_lote(request, lote_id):
    # Obtenemos la versión VIGENTE del lote que está listo para ambientar
    lote = get_object_or_404(Lote.objects.select_related('establecimiento'),
                             id=lote_id, estado_version='VIGENTE',
                             estado_workflow__in=['VALIDADO_PRODUCTOR', 'CON_AMBIENTACION_EN_PROCESO', 'ACTIVO', 'EN_CORRECCION_GIS'])
                             # Permitimos cargar/recargar ambientes en varios estados post-validación

    form = ProcesarAmbientacionLoteForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and form.is_valid():
        uploaded_file = request.FILES['archivo_shape_ambientes']
        # Definimos variables fuera del try para el finallynte
        temp_dir = None
        temp_file_name = None
        shp_file_path = None
        # Usamos FileSystemStorage en un directorio temporal seguro
        fs_location = tempfile.mkdtemp() # Crea un dir temporal seguro
        fs = FileSystemStorage(location=fs_location)

        try:
            # 1. Guardar archivo temporalmente en el dir seguro
            temp_file_name = fs.save(uploaded_file.name, uploaded_file)
            temp_file_path = fs.path(temp_file_name)

            # 2. Descomprimir si es ZIP
            if zipfile.is_zipfile(temp_file_path):
                # Descomprimir en el mismo directorio temporal seguro
                with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
                    zip_ref.extractall(fs_location)
                # Buscar el archivo .shp dentro del directorio descomprimido
                shp_file_path = next((os.path.join(fs_location, f) for f in os.listdir(fs_location) if f.lower().endswith('.shp')), None)
                if not shp_file_path: raise ValueError("No se encontró un archivo .shp dentro del ZIP.")
                # Borrar el ZIP original después de descomprimir
                fs.delete(temp_file_name)
                temp_file_name = None # Ya no necesitamos borrarlo en finallynte
            elif temp_file_path.lower().endswith('.shp'):
                # Es un SHP directo, usar su path
                shp_file_path = temp_file_path
            else:
                raise ValueError("El archivo debe ser un .zip o un .shp.")

            # 3. Procesar el Shapefile de Ambientes
            ds = DataSource(shp_file_path)
            if not ds: raise ValueError(f"No se pudo abrir el archivo como fuente de datos GDAL: {shp_file_path}")

            layer = ds[0]
            target_srid = 32721 # SRID de la base de datos
            source_srid = getattr(layer.srs, 'srid', None) # SRID del archivo origen

            ambientes_creados_ok = []
            errores_procesamiento = []
            lote_geom = lote.geometria # Geometría del lote padre para validación

            # --- Transacción Atómica ---
            with transaction.atomic():
                # Opcional: Marcar ambientes VIGENTES anteriores de este lote como HISTORICOS antes de crear los nuevos
                # Esto asegura que solo la última carga esté vigente.
                ambientes_anteriores = Ambiente.objects.filter(lote=lote, estado_version='VIGENTE')
                if ambientes_anteriores.exists():
                     print(f"Marcando {ambientes_anteriores.count()} ambientes anteriores del lote {lote.nombre} como históricos.")
                     ambientes_anteriores.update(estado_version='HISTORICO', estado_workflow='HISTORICO_WF')

                # Procesar cada feature (ambiente) en el shapefile
                for feature_index, feature in enumerate(layer):
                    nombre_ambiente = None
                    categoria_ambiente = None # Ejemplo de otro atributo
                    try:
                        # --- Obtener atributos y geometría ---
                        # Intentar obtener nombre (prioridad a mayúsculas luego minúsculas)
                        nombre_ambiente = feature.get('NOMBRE') or feature.get('nombre') or f"Ambiente_{feature_index + 1}"
                        categoria_ambiente = feature.get('CATEGORIA') or feature.get('categoria')

                        geom_gdal = feature.geom # Geometría GDAL

                        # Asignar SRID origen si no lo tiene
                        if geom_gdal.srid is None:
                            geom_gdal.srid = source_srid if source_srid else 4326 # Asumir WGS84 si no hay SRID
                            print(f"Asignando SRID {geom_gdal.srid} a Feature {feature_index+1}")

                        # Transformar a SRID de destino si es necesario
                        if geom_gdal.srid != target_srid:
                            try:
                                target_srs_obj = SpatialReference(target_srid)
                                geom_gdal.transform(target_srs_obj)
                            except Exception as srid_err:
                                raise ValueError(f"Error transformando SRID de {geom_gdal.srid} a {target_srid}: {srid_err}")

                        # Validar tipo y validez de geometría GDAL
                        if geom_gdal.geom_type.name not in ('Polygon', 'MultiPolygon'):
                            raise TypeError(f"Tipo geometría no es Polígono/MultiPolígono ({geom_gdal.geom_type.name}).")
                        
                        # Verificamos si hay método is_valid - no usar valid directamente
                        if hasattr(geom_gdal, 'is_valid'):
                            if not geom_gdal.is_valid():
                                raise ValueError("Geometría GDAL inválida.")
                        # Si no tiene método para validar, continuamos sin verificar

                        # Convertir a GEOSGeometry para Django
                        # Primero convertimos la geometría GDAL a texto WKT
                        geom_wkt = geom_gdal.wkt
                        
                        # Luego creamos una geometría GEOS (compatible con Django ORM)
                        geos_geom = GEOSGeometry(geom_wkt, srid=target_srid)
                        
                        # Si es un Polygon simple, lo convertimos a MultiPolygon
                        if isinstance(geos_geom, Polygon):
                            geos_geom = MultiPolygon([geos_geom], srid=target_srid)
                        
                        # Aseguramos que es un MultiPolygon y tiene el SRID correcto
                        if not isinstance(geos_geom, MultiPolygon):
                             raise TypeError("No se pudo convertir a MultiPolygon GEOS.")
                        if not geos_geom.valid:
                             # Intentar corregir geometría inválida (buffer(0))
                             corrected_geom = geos_geom.buffer(0)
                             if corrected_geom.valid and isinstance(corrected_geom, MultiPolygon):
                                 print(f"Geometría corregida para FID {feature_index+1}")
                                 geos_geom = corrected_geom
                             else:
                                 raise ValueError("Geometría GEOS inválida, no se pudo corregir.")

                        # --- Validaciones Adicionales ---
                        if not lote_geom.contains(geos_geom):
                            raise ValueError(f"Geometría NO contenida completamente dentro del Lote '{lote.nombre}'.")

                        # TODO: Validación de no solapamiento con otros ambientes de ESTE MISMO LOTE Y CARGA

                        # --- Crear Ambiente (Versión 1) ---
                        Ambiente.objects.create(
                            lote=lote, # ¡Se asigna el lote del contexto!
                            nombre=str(nombre_ambiente).strip(),
                            geometria=geos_geom,
                            categoria=str(categoria_ambiente).strip() if categoria_ambiente else None,
                            # Se heredan otros atributos del lote si son iguales? No por defecto.
                            estado_version='VIGENTE',
                            estado_workflow='PENDIENTE_VALIDACION_AGRONOMO',
                        )
                        ambientes_creados_ok.append(str(nombre_ambiente).strip())

                    except (TypeError, ValueError, GDALException, Exception) as feat_err:
                        err_msg = f"Feature {feature_index + 1}"
                        if nombre_ambiente: err_msg += f" ('{nombre_ambiente}')"
                        err_msg += f": Error al procesar - {feat_err}"
                        errores_procesamiento.append(err_msg)
                        print(f"Error detallado: {err_msg}") # Log para debug
                        # Continuar con el siguiente feature si falla uno

            # --- Fin Transacción ---

            # 4. Manejar Resultados del Procesamiento
            if errores_procesamiento:
                error_summary = "; ".join(errores_procesamiento)
                messages.error(request, f"Se encontraron errores al procesar: {error_summary}")
                if not ambientes_creados_ok:
                     messages.warning(request, "No se crearon nuevos ambientes debido a los errores.")
                else:
                     messages.warning(request, f"Se crearon {len(ambientes_creados_ok)} ambientes ({', '.join(ambientes_creados_ok)}), pero hubo errores con otros. Revise los errores.")
                # No cambiamos estado de tarea, el usuario debe subir un archivo corregido o revisar

            else: # Todo OK
                # Opcional: Marcar la tarea original de ambientación (si la había) como completada
                try:
                    content_type_lote = ContentType.objects.get_for_model(Lote)
                    tarea_ambientacion_original = Tarea.objects.filter(
                        content_type=content_type_lote,
                        object_id=lote.id,
                        tipo_tarea='CREAR_ACTUALIZAR_AMBIENTACION',
                        estado_tarea='PENDIENTE' # Buscar la tarea pendiente específica
                    ).first()
                    if tarea_ambientacion_original:
                        tarea_ambientacion_original.estado_tarea = 'COMPLETADA'
                        tarea_ambientacion_original.fecha_finalizacion = timezone.now()
                        if form.cleaned_data.get('comentarios_gis'):
                             tarea_ambientacion_original.comentarios_internos = (tarea_ambientacion_original.comentarios_internos or '') + f"\n---\nGIS ({request.user.username}): {form.cleaned_data['comentarios_gis']}"
                        tarea_ambientacion_original.save()
                except Exception as e_task_complete:
                     print(f"Advertencia: No se pudo completar la tarea original de ambientación: {e_task_complete}")


                # --- Crear Tarea para Ingeniero Agrónomo para Validar/Enriquecer ---
                try:
                    rol_agronomo = Rol.objects.get(id_rol=Rol.ROL_ING_AGRONOMO)
                    content_type_lote = ContentType.objects.get_for_model(Lote)
                    Tarea.objects.create(
                        tipo_tarea = 'VALIDAR_ENRIQUECER_AMBIENTACION',
                        rol_asignado = rol_agronomo,
                        entidad_relacionada = lote, # Vinculada al Lote
                        descripcion = f"Validar y enriquecer atributos de {len(ambientes_creados_ok)} ambiente(s) para Lote '{lote.nombre}'.",
                        creado_por = request.user
                    )
                    messages.success(request, f"Archivo de ambientes procesado. Se crearon {len(ambientes_creados_ok)} ambientes para '{lote.nombre}'. Tarea de validación agronómica generada.")
                except Rol.DoesNotExist:
                     messages.error(request, "Rol Ingeniero Agrónomo no encontrado. No se pudo crear tarea de validación.")
                except Exception as e_task_create:
                     messages.error(request, f"Error al crear tarea de validación: {e_task_create}")

                # Cambiar estado del lote a 'CON_AMBIENTACION_EN_PROCESO' o similar
                lote.estado_workflow = 'CON_AMBIENTACION_EN_PROCESO' # Indicar que tiene ambientes pendientes de validación
                lote.save(update_fields=['estado_workflow'])

                return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)


        # --- Manejo de Excepciones Generales y Limpieza ---
        except GDALException as gdal_err: messages.error(request, f"Error GDAL/OGR: {gdal_err}")
        except ValueError as val_err: messages.error(request, f"Error de datos: {val_err}")
        except Exception as e: messages.error(request, f"Error inesperado durante el proceso: {e}")
        finally:
            # Limpiar directorio temporal seguro
            try:
                if fs_location and os.path.exists(fs_location):
                    shutil.rmtree(fs_location)
                    print(f"Directorio temporal {fs_location} eliminado.")
            except Exception as clean_err:
                print(f"Advertencia: No se pudo limpiar directorio temporal {fs_location}: {clean_err}")

        # Si hubo error (excepto éxito que redirige), re-renderizar form
        context = {'form': form, 'lote': lote}
        return render(request, 'ambientacion/subir_ambientes_lote_form.html', context)

    else: # Método GET
        # Convertir geometría a WGS84 para Leaflet
        geom_4326 = None
        if lote.geometria:
            try:
                geom_4326 = lote.geometria.transform(4326, clone=True)
            except Exception as e:
                print(f"Error al transformar geometría: {e}")
                
        context = {
            'form': form, 
            'lote': lote,
            # Añadir geometría convertida a WGS84 pre-serializada para usar en JS
            'lote_geojson': geom_4326.geojson if geom_4326 else None
        }
        return render(request, 'ambientacion/subir_ambientes_lote_form.html', context)



def es_agronomo_o_admin(user):
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol in [Rol.ROL_ING_AGRONOMO, Rol.ROL_ADMIN_SISTEMA]
    except: return False

@login_required
@user_passes_test(es_agronomo_o_admin, login_url='/cuentas/login/')
def validar_enriquecer_ambientes(request, lote_id):
    lote = get_object_or_404(Lote.objects.select_related('establecimiento__empresa'),
                             id=lote_id, estado_version='VIGENTE')

    # Buscamos ambientes de este lote pendientes de validación
    queryset_ambientes_pendientes = Ambiente.objects.filter(
        lote=lote,
        estado_version='VIGENTE',
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).order_by('nombre') # O por ID, o como prefieras ordenarlos en el formset

    # Preparamos GeoJSON para el mapa CON TRANSFORMACIÓN A 4326
    ambientes_geojson_4326 = serialize('geojson',
                                       queryset_ambientes_pendientes.annotate(
                                           geom_4326=Transform('geometria', 4326) # Transforma al vuelo
                                       ),
                                       geometry_field='geom_4326', # Usa el campo transformado
                                       fields=('nombre', 'id', 'productividad')) # Campos para popup/estilo

    if request.method == 'POST':
        formset = AmbienteAgronomoFormSet(request.POST, queryset=queryset_ambientes_pendientes)

        if formset.is_valid():
            with transaction.atomic():
                instancias = formset.save(commit=False)
                for ambiente_instance in instancias:
                    # Marcar como ACTIVO al guardar los cambios
                    ambiente_instance.estado_workflow = 'ACTIVO'
                    # Podríamos guardar quién y cuándo valida/enriquece
                    # ambiente_instance.usuario_validador = request.user
                    # ambiente_instance.fecha_validacion = timezone.now()
                    ambiente_instance.save() # Guardar cada instancia

                # (Opcional) Completar la tarea que inició este proceso
                try:
                    content_type_lote = ContentType.objects.get_for_model(Lote)
                    tarea_validar = Tarea.objects.filter(
                        content_type=content_type_lote,
                        object_id=lote.id,
                        tipo_tarea='VALIDAR_ENRIQUECER_AMBIENTACION',
                        estado_tarea='PENDIENTE' # O asignada al usuario actual
                    ).first()
                    if tarea_validar:
                        tarea_validar.estado_tarea = 'COMPLETADA'
                        tarea_validar.fecha_finalizacion = timezone.now()
                        # Podríamos asignar el usuario que completó
                        # tarea_validar.usuario_asignado_actualmente = request.user
                        tarea_validar.save()
                except Exception as e_task:
                    print(f"Advertencia: No se pudo completar tarea de validación para Lote {lote.id}: {e_task}")

                messages.success(request, f"Se validaron y guardaron los atributos para {len(instancias)} ambiente(s) del lote '{lote.nombre}'.")
                return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)
        else:
            # Si el formset no es válido, mostrar errores
            messages.error(request, "Por favor, corrija los errores en el formulario.")

    else: # Método GET
        # Inicializar el formset con los ambientes pendientes
        formset = AmbienteAgronomoFormSet(queryset=queryset_ambientes_pendientes)

    context = {
        'lote': lote,
        'formset': formset,
        'ambientes_geojson': ambientes_geojson_4326, # GeoJSON en 4326 para el mapa
        'titulo_pagina': f"Validar Ambientes Lote {lote.nombre}",
        'titulo_formulario': f"Validar y Enriquecer Ambientes - Lote {lote.nombre}",
    }
    return render(request, 'ambientacion/validar_ambientes.html', context)

# --- Vista para Solicitar Corrección GIS (Ejemplo si se hace con botón separado) ---
# Si se hace con un botón en la pantalla de validación, esta vista separada no es necesaria,
# se manejaría en el POST de 'validar_enriquecer_ambientes'.
# def solicitar_correccion_ambiente(request, ambiente_id):
#    ambiente = get_object_or_404(Ambiente, id=ambiente_id, ...)
#    if request.method == 'POST':
#       ambiente.estado_workflow = 'EN_CORRECCION_GIS'
#       ambiente.save()
#       # Crear Tarea CORREGIR_GEOMETRIA_AMBIENTE para GIS vinculada a este ambiente
#       Tarea.objects.create(...)
#       messages.warning(request, "Solicitud de corrección enviada a GIS.")
#       return redirect(...)
#    # Mostrar form para comentarios de corrección
#    return render(...)

# Helper para rol Agrónomo o Admin
def es_agronomo_o_admin(user):
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol in [Rol.ROL_ING_AGRONOMO, Rol.ROL_ADMIN_SISTEMA]
    except: return False

@login_required
@user_passes_test(es_agronomo_o_admin, login_url='/cuentas/login/')
def validar_enriquecer_ambientes(request, lote_id):
    # Obtenemos el Lote vigente asociado a esta validación
    lote = get_object_or_404(Lote.objects.select_related('establecimiento__empresa'),
                             id=lote_id, estado_version='VIGENTE')

    # CAMBIO: Mostrar mensaje más claro si ya no quedan ambientes pendientes
    # Verificación explícita de ambientes pendientes
    ambientes_pendientes_count = Ambiente.objects.filter(
        lote=lote, 
        estado_version='VIGENTE', 
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).count()
    
    if ambientes_pendientes_count == 0 and request.method == 'GET':
        messages.info(request, f"No hay ambientes pendientes de validación para el lote '{lote.nombre}'. " +
                              "Si acabas de procesar algunos ambientes, ya han sido marcados como activos.")
        return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)

    # Buscamos ambientes de este lote que estén pendientes de validación por el agrónomo
    queryset_ambientes_pendientes = Ambiente.objects.filter(
        lote=lote,
        estado_version='VIGENTE',
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).order_by('nombre')
    
    # RESTO DEL CÓDIGO IGUAL...
    # Preparamos GeoJSON para el mapa CON TRANSFORMACIÓN A 4326
    # Usamos annotate para crear el campo transformado al vuelo
    ambientes_geojson_4326 = serialize('geojson',
                                       queryset_ambientes_pendientes.annotate(
                                           geom_4326=Transform('geometria', 4326) # ¡Transformación aquí!
                                       ),
                                       geometry_field='geom_4326', # Usamos el campo transformado
                                       fields=('nombre', 'id', 'productividad')) # Campos básicos para el mapa

    if request.method == 'POST':
        # Procesamos el Formset enviado
        # Pasamos el queryset original para que sepa qué instancias actualizar
        formset = AmbienteAgronomoFormSet(request.POST, queryset=queryset_ambientes_pendientes)

        if formset.is_valid():
            try:
                with transaction.atomic(): # Asegurar atomicidad
                    instancias = formset.save(commit=False)
                    count_activos = 0
                    for ambiente_instance in instancias:
                        # Marcar como ACTIVO al guardar los cambios
                        ambiente_instance.estado_workflow = 'ACTIVO'
                        ambiente_instance.save() # Guardar cada instancia
                        count_activos += 1

                    # (Opcional pero recomendado) Completar la tarea que inició este proceso
                    try:
                        content_type_lote = ContentType.objects.get_for_model(Lote)
                        tarea_validar = Tarea.objects.filter(
                            content_type=content_type_lote,
                            object_id=lote.id,
                            tipo_tarea='VALIDAR_ENRIQUECER_AMBIENTACION',
                            estado_tarea='PENDIENTE'
                        ).first()
                        if tarea_validar:
                            tarea_validar.estado_tarea = 'COMPLETADA'
                            tarea_validar.fecha_finalizacion = timezone.now()
                            tarea_validar.usuario_asignado_actualmente = request.user # Marcar quién la completó
                            tarea_validar.save()
                    except Exception as e_task:
                         # No bloquear la operación principal si falla la actualización de tarea
                         print(f"Advertencia: No se pudo completar tarea de validación para Lote {lote.id}: {e_task}")

                    # Actualizar estado del Lote padre a ACTIVO si ya no tiene ambientes pendientes
                    if not Ambiente.objects.filter(lote=lote, estado_version='VIGENTE', estado_workflow='PENDIENTE_VALIDACION_AGRONOMO').exists():
                        lote.estado_workflow = 'ACTIVO'
                        lote.save(update_fields=['estado_workflow'])
                        messages.info(request, f"Todos los ambientes del lote '{lote.nombre}' han sido validados. El lote ahora está ACTIVO.")
                    else:
                         messages.success(request, f"Se guardaron los atributos para {count_activos} ambiente(s) del lote '{lote.nombre}'.")

                    return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)

            except Exception as e_atomic:
                 messages.error(request, f"Error al guardar los cambios: {e_atomic}")
                 # El formset ya tendrá los errores si la validación falló antes de la transacción

        else:
            # Si el formset no es válido, mostrar errores
            messages.error(request, "Por favor, corrija los errores en los formularios de ambientes.")
            # El template volverá a renderizar el formset con los errores específicos por campo/formulario

    else: # Método GET
        # Inicializar el formset con los ambientes pendientes
        formset = AmbienteAgronomoFormSet(queryset=queryset_ambientes_pendientes)

    context = {
        'lote': lote,
        'formset': formset,
        'ambientes_geojson': ambientes_geojson_4326, # GeoJSON en 4326 para el mapa
        'titulo_pagina': f"Validar Ambientes Lote {lote.nombre}",
        'titulo_formulario': f"Validar y Enriquecer Ambientes - Lote {lote.nombre}",
    }
    return render(request, 'ambientacion/validar_ambientes.html', context)


# Helper para rol Agrónomo
def es_rol_agronomo(user):
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol == Rol.ROL_ING_AGRONOMO
    except: return False

@login_required
@user_passes_test(es_rol_agronomo, login_url='/cuentas/login/')
def vista_tareas_agronomo(request):
    rol_agronomo = Rol.objects.get(id_rol=Rol.ROL_ING_AGRONOMO)
    tareas_pendientes = Tarea.objects.filter(
        rol_asignado=rol_agronomo,
        estado_tarea='PENDIENTE'
    ).select_related(
        'content_type',
        'creado_por',
    ).order_by('fecha_creacion')

    # Necesitamos obtener el objeto real para el enlace
    for tarea in tareas_pendientes:
        tarea.objeto_real = tarea.entidad_relacionada
    
    # Lista de establecimientos para el filtro
    establecimientos = Establecimiento.objects.filter(activo=True).select_related('empresa').order_by('empresa__nombre_razon_social', 'nombre')
    
    # Procesar filtro por establecimiento
    establecimiento_seleccionado = None
    lotes_con_ambientes_pendientes = {}
    
    if 'establecimiento_id' in request.GET and request.GET['establecimiento_id']:
        try:
            establecimiento_id = int(request.GET['establecimiento_id'])
            establecimiento_seleccionado = Establecimiento.objects.get(id=establecimiento_id)
            
            # Buscar ambientes pendientes en este establecimiento
            ambientes_pendientes = Ambiente.objects.filter(
                lote__establecimiento=establecimiento_seleccionado,
                estado_version='VIGENTE',
                estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
            ).select_related('lote')
            
            # Agrupar por lote
            from collections import defaultdict
            lotes_conteo = defaultdict(int)
            for ambiente in ambientes_pendientes:
                lotes_conteo[ambiente.lote] += 1
                
            lotes_con_ambientes_pendientes = dict(lotes_conteo)
            
        except (ValueError, Establecimiento.DoesNotExist):
            pass

    context = {
        'tareas_pendientes': tareas_pendientes,
        'establecimientos': establecimientos,
        'establecimiento_seleccionado': establecimiento_seleccionado,
        'lotes_con_ambientes_pendientes': lotes_con_ambientes_pendientes
    }
    return render(request, 'ambientacion/tareas_agronomo.html', context)

@login_required
@user_passes_test(es_agronomo_o_admin, login_url='/cuentas/login/')
def validar_enriquecer_ambientes(request, lote_id):
    lote = get_object_or_404(Lote.objects.select_related('establecimiento__empresa'),
                             id=lote_id, estado_version='VIGENTE')

    # Buscamos ambientes de este lote pendientes de validación
    queryset_ambientes_pendientes = Ambiente.objects.filter(
        lote=lote,
        estado_version='VIGENTE',
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).order_by('nombre') # O por ID, o como prefieras ordenarlos en el formset

    # Preparamos GeoJSON para el mapa con transformación directa
    try:
        # Obtener todos los ambientes pendientes
        ambientes_pendientes = Ambiente.objects.filter(
            lote=lote,
            estado_version='VIGENTE',
            estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
        )
        
        print(f"Ambientes pendientes encontrados: {ambientes_pendientes.count()}")
        
        # Transformar las geometrías a WGS84 (EPSG:4326)
        ambientes_features = []
        for ambiente in ambientes_pendientes:
            try:
                # Convertir geometría a WGS84
                geom_4326 = ambiente.geometria.transform(4326, clone=True)
                
                # Crear diccionario con propiedades
                ambiente_dict = {
                    'id': ambiente.id,
                    'nombre': ambiente.nombre,
                    'superficie_has': ambiente.superficie_has,
                    'productividad': ambiente.productividad,
                    'tipo_suelo_nombre': ambiente.tipo_suelo_nombre
                }
                
                # Añadir feature al array
                ambientes_features.append({
                    "type": "Feature",
                    "geometry": json.loads(geom_4326.geojson),
                    "properties": ambiente_dict
                })
            except Exception as e:
                print(f"Error al procesar ambiente {ambiente.id}: {e}")
                
        # Crear el objeto GeoJSON final
        ambientes_geojson_data = {"type": "FeatureCollection", "features": ambientes_features}
    except Exception as e:
        print(f"Error al preparar GeoJSON: {e}")
        ambientes_geojson_data = {"type": "FeatureCollection", "features": []}
    
    if request.method == 'POST':
        formset = AmbienteAgronomoFormSet(request.POST, queryset=queryset_ambientes_pendientes)

        if formset.is_valid():
            with transaction.atomic():
                instancias = formset.save(commit=False)
                for ambiente_instance in instancias:
                    # Marcar como ACTIVO al guardar los cambios
                    ambiente_instance.estado_workflow = 'ACTIVO'
                    # Podríamos guardar quién y cuándo valida/enriquece
                    # ambiente_instance.usuario_validador = request.user
                    # ambiente_instance.fecha_validacion = timezone.now()
                    ambiente_instance.save() # Guardar cada instancia

                # (Opcional) Completar la tarea que inició este proceso
                try:
                    content_type_lote = ContentType.objects.get_for_model(Lote)
                    tarea_validar = Tarea.objects.filter(
                        content_type=content_type_lote,
                        object_id=lote.id,
                        tipo_tarea='VALIDAR_ENRIQUECER_AMBIENTACION',
                        estado_tarea='PENDIENTE' # O asignada al usuario actual
                    ).first()
                    if tarea_validar:
                        tarea_validar.estado_tarea = 'COMPLETADA'
                        tarea_validar.fecha_finalizacion = timezone.now()
                        # Podríamos asignar el usuario que completó
                        # tarea_validar.usuario_asignado_actualmente = request.user
                        tarea_validar.save()
                except Exception as e_task:
                    print(f"Advertencia: No se pudo completar tarea de validación para Lote {lote.id}: {e_task}")

                messages.success(request, f"Se validaron y guardaron los atributos para {len(instancias)} ambiente(s) del lote '{lote.nombre}'.")
                return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)
        else:
            # Si el formset no es válido, mostrar errores
            messages.error(request, "Por favor, corrija los errores en el formulario.")

    else: # Método GET
        # Inicializar el formset con los ambientes pendientes
        formset = AmbienteAgronomoFormSet(queryset=queryset_ambientes_pendientes)

    context = {
        'lote': lote,
        'formset': formset,
        'ambientes_geojson': json.dumps(ambientes_geojson_data),  # Convertir a string JSON
        'titulo_pagina': f"Validar Ambientes Lote {lote.nombre}",
        'titulo_formulario': f"Validar y Enriquecer Ambientes - Lote {lote.nombre}",
    }
    return render(request, 'ambientacion/validar_ambientes.html', context)

@login_required
@user_passes_test(es_agronomo_o_admin, login_url='/cuentas/login/')
def validar_enriquecer_ambientes(request, lote_id):
    lote = get_object_or_404(Lote.objects.select_related('establecimiento__empresa'),
                             id=lote_id, estado_version='VIGENTE')

    # CAMBIO: Mostrar mensaje más claro si ya no quedan ambientes pendientes
    # Verificación explícita de ambientes pendientes
    ambientes_pendientes_count = Ambiente.objects.filter(
        lote=lote, 
        estado_version='VIGENTE', 
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).count()
    
    if ambientes_pendientes_count == 0 and request.method == 'GET':
        messages.info(request, f"No hay ambientes pendientes de validación para el lote '{lote.nombre}'. " +
                              "Si acabas de procesar algunos ambientes, ya han sido marcados como activos.")
        return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)

    # Buscamos ambientes de este lote que estén pendientes de validación por el agrónomo
    queryset_ambientes_pendientes = Ambiente.objects.filter(
        lote=lote,
        estado_version='VIGENTE',
        estado_workflow='PENDIENTE_VALIDACION_AGRONOMO'
    ).order_by('nombre')
    
    # RESTO DEL CÓDIGO IGUAL...
    # Preparamos GeoJSON para el mapa CON TRANSFORMACIÓN A 4326
    # Usamos annotate para crear el campo transformado al vuelo
    ambientes_geojson_4326 = serialize('geojson',
                                       queryset_ambientes_pendientes.annotate(
                                           geom_4326=Transform('geometria', 4326) # ¡Transformación aquí!
                                       ),
                                       geometry_field='geom_4326', # Usamos el campo transformado
                                       fields=('nombre', 'id', 'productividad')) # Campos básicos para el mapa

    if request.method == 'POST':
        # Procesamos el Formset enviado
        # Pasamos el queryset original para que sepa qué instancias actualizar
        formset = AmbienteAgronomoFormSet(request.POST, queryset=queryset_ambientes_pendientes)

        if formset.is_valid():
            try:
                with transaction.atomic(): # Asegurar atomicidad
                    instancias = formset.save(commit=False)
                    count_activos = 0
                    for ambiente_instance in instancias:
                        # Marcar como ACTIVO al guardar los cambios
                        ambiente_instance.estado_workflow = 'ACTIVO'
                        ambiente_instance.save() # Guardar cada instancia
                        count_activos += 1

                    # (Opcional pero recomendado) Completar la tarea que inició este proceso
                    try:
                        content_type_lote = ContentType.objects.get_for_model(Lote)
                        tarea_validar = Tarea.objects.filter(
                            content_type=content_type_lote,
                            object_id=lote.id,
                            tipo_tarea='VALIDAR_ENRIQUECER_AMBIENTACION',
                            estado_tarea='PENDIENTE'
                        ).first()
                        if tarea_validar:
                            tarea_validar.estado_tarea = 'COMPLETADA'
                            tarea_validar.fecha_finalizacion = timezone.now()
                            tarea_validar.usuario_asignado_actualmente = request.user # Marcar quién la completó
                            tarea_validar.save()
                    except Exception as e_task:
                         # No bloquear la operación principal si falla la actualización de tarea
                         print(f"Advertencia: No se pudo completar tarea de validación para Lote {lote.id}: {e_task}")

                    # Actualizar estado del Lote padre a ACTIVO si ya no tiene ambientes pendientes
                    if not Ambiente.objects.filter(lote=lote, estado_version='VIGENTE', estado_workflow='PENDIENTE_VALIDACION_AGRONOMO').exists():
                        lote.estado_workflow = 'ACTIVO'
                        lote.save(update_fields=['estado_workflow'])
                        messages.info(request, f"Todos los ambientes del lote '{lote.nombre}' han sido validados. El lote ahora está ACTIVO.")
                    else:
                         messages.success(request, f"Se guardaron los atributos para {count_activos} ambiente(s) del lote '{lote.nombre}'.")

                    return redirect('ambientacion:detalle_establecimiento', establecimiento_id=lote.establecimiento.id)

            except Exception as e_atomic:
                 messages.error(request, f"Error al guardar los cambios: {e_atomic}")
                 # El formset ya tendrá los errores si la validación falló antes de la transacción

        else:
            # Si el formset no es válido, mostrar errores
            messages.error(request, "Por favor, corrija los errores en los formularios de ambientes.")
            # El template volverá a renderizar el formset con los errores específicos por campo/formulario

    else: # Método GET
        # Inicializar el formset con los ambientes pendientes
        formset = AmbienteAgronomoFormSet(queryset=queryset_ambientes_pendientes)

    context = {
        'lote': lote,
        'formset': formset,
        'ambientes_geojson': ambientes_geojson_4326, # GeoJSON en 4326 para el mapa
        'titulo_pagina': f"Validar Ambientes Lote {lote.nombre}",
        'titulo_formulario': f"Validar y Enriquecer Ambientes - Lote {lote.nombre}",
    }
    return render(request, 'ambientacion/validar_ambientes.html', context)