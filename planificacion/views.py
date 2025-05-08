# planificacion/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.contrib.gis.db.models.functions import Transform
from django.core.serializers import serialize
import json
from django.db import transaction
from core.models import Empresa, Establecimiento, Lote, Ambiente
from usuarios.models import Rol
from .models import UsoDeSuelo
from .forms import FiltroSeleccionPlanificacionForm, UsoDeSueloFormSet # Necesitaremos el Formset después

# Helper (asegúrate que esté definido)
def es_agronomo_o_admin(user):
    if not user.is_authenticated: return False
    try: return user.perfil_pronutrition.rol.id_rol in [Rol.ROL_ING_AGRONOMO, Rol.ROL_ADMIN_SISTEMA]
    except: return False

@login_required
@user_passes_test(es_agronomo_o_admin, login_url='/cuentas/login/')
def seleccionar_para_planificar(request):
    lote_seleccionado = None
    ambientes_lote = Ambiente.objects.none()
    ambientes_geojson = "null"
    
    # Debug info
    debug_info = {
        'request_params': dict(request.GET.items()),
        'empresa_id': None,
        'establecimiento_id': None,
        'lote_id': None,
        'establecimientos_count': 0,
        'lotes_count': 0,
        'form_valid': False
    }
    
    # Obtener parámetros de la solicitud
    empresa_id = request.GET.get('empresa')
    establecimiento_id = request.GET.get('establecimiento')
    lote_id = request.GET.get('lote')
    
    debug_info['empresa_id'] = empresa_id
    debug_info['establecimiento_id'] = establecimiento_id
    debug_info['lote_id'] = lote_id
    
    # Crear formulario con datos GET o vacío
    form = FiltroSeleccionPlanificacionForm(request.GET or None)
    
    # Si hay una empresa seleccionada, cargar establecimientos relacionados
    if empresa_id:
        try:
            # Obtener establecimientos antes de asignar al queryset
            establecimientos = Establecimiento.objects.filter(
                empresa_id=int(empresa_id), 
                activo=True
            ).order_by('nombre')
            
            debug_info['establecimientos_count'] = establecimientos.count()
            debug_info['establecimientos_list'] = list(establecimientos.values('id', 'nombre'))
            
            # Asignar al formulario
            form.fields['establecimiento'].queryset = establecimientos
        except (ValueError, TypeError) as e:
            debug_info['error_establecimientos'] = str(e)
            
    # Si hay un establecimiento seleccionado, cargar lotes relacionados
    if establecimiento_id:
        print("Cargando lotes para el establecimiento:", establecimiento_id)
        try:
            # Obtener lotes antes de asignar al queryset
            lotes = Lote.objects.filter(
                establecimiento_id=int(establecimiento_id), 
                estado_version='VIGENTE', 
                estado_workflow='ACTIVO'
            ).order_by('nombre')
            
            debug_info['lotes_count'] = lotes.count()
            debug_info['lotes_list'] = list(lotes.values('id', 'nombre'))
            
            # Asignar al formulario
            form.fields['lote'].queryset = lotes
            print(lotes)
        except (ValueError, TypeError) as e:
            debug_info['error_lotes'] = str(e)
    
    # Procesar el formulario si es válido
    debug_info['form_valid'] = form.is_valid()
    
    if form.is_valid():
        # Obtener datos limpios
        empresa = form.cleaned_data['empresa']
        establecimiento = form.cleaned_data['establecimiento']
        lote_seleccionado = form.cleaned_data['lote']
        año_zafra = form.cleaned_data['año_zafra']
        tipo_zafra = form.cleaned_data['tipo_zafra']
        
        debug_info['cleaned_data'] = {
            'empresa': str(empresa),
            'establecimiento': str(establecimiento),
            'lote': str(lote_seleccionado),
            'año_zafra': año_zafra,
            'tipo_zafra': tipo_zafra
        }
        
        # Cargar ambientes del lote seleccionado
        if lote_seleccionado:
            ambientes_lote = Ambiente.objects.filter(
                lote=lote_seleccionado,
                estado_version='VIGENTE',
                estado_workflow='ACTIVO'
            ).order_by('nombre')
            
            debug_info['ambientes_count'] = ambientes_lote.count()
            
            # Generar GeoJSON para el mapa
            if ambientes_lote.exists():
                try:
                    ambientes_geojson_4326 = serialize('geojson',
                                                ambientes_lote.annotate(
                                                    geom_4326=Transform('geometria', 4326)
                                                ),
                                                geometry_field='geom_4326',
                                                fields=('nombre', 'id', 'productividad', 'superficie_has'))
                    # Validamos que sea un GeoJSON válido
                    parsed_json = json.loads(ambientes_geojson_4326)
                    ambientes_geojson = json.dumps(parsed_json)
                except Exception as e:
                    debug_info['error_geojson'] = str(e)
                    ambientes_geojson = "null"
    else:
        debug_info['form_errors'] = form.errors.as_json()
    
    # Imprimir debug info al log
    print("DEBUG INFO:", json.dumps(debug_info, indent=2, default=str))
    
    context = {
        'form_filtros': form,
        'lote_seleccionado': lote_seleccionado,
        'ambientes_lote': ambientes_lote,
        'ambientes_geojson': ambientes_geojson,
        'año_zafra_seleccionado': request.GET.get('año_zafra'),
        'tipo_zafra_seleccionado': request.GET.get('tipo_zafra'),
        'empresa_id': empresa_id,
        'establecimiento_id': establecimiento_id,
        'debug_info': debug_info,  # Pasar debug info al template
    }
    
    return render(request, 'planificacion/seleccionar_ambientes.html', context)

@login_required
@user_passes_test(es_agronomo_o_admin, login_url='/cuentas/login/')
def planificar_usos_seleccionados(request):
    if request.method != 'POST':
        # Si no es POST, redirigir a la pantalla de selección
        messages.warning(request, "Por favor, seleccione primero los ambientes a planificar.")
        return redirect('planificacion:seleccionar_para_planificar')

    # Recuperar IDs de ambientes seleccionados y parámetros de zafra del POST
    ambientes_ids = request.POST.getlist('ambientes_seleccionados')
    año_zafra = request.POST.get('año_zafra')
    tipo_zafra = request.POST.get('tipo_zafra')

    if not ambientes_ids or not año_zafra or not tipo_zafra:
         messages.error(request, "Faltan datos necesarios (ambientes, año o tipo de zafra).")
         return redirect('planificacion:seleccionar_para_planificar')

    try:
        año_zafra = int(año_zafra)
        # Validar tipo_zafra si es necesario
        if tipo_zafra not in [c[0] for c in UsoDeSuelo.ZAFRA_CHOICES]:
             raise ValueError("Tipo de zafra inválido")
    except ValueError:
         messages.error(request, "Año o tipo de zafra inválido.")
         return redirect('planificacion:seleccionar_para_planificar')


    # Obtener los objetos Ambiente seleccionados
    ambientes_seleccionados = Ambiente.objects.filter(
        id__in=ambientes_ids,
        estado_version='VIGENTE',
        estado_workflow='ACTIVO'
    ).select_related('lote') # Para info de contexto

    if not ambientes_seleccionados.exists():
         messages.warning(request, "No se encontraron ambientes válidos con los IDs seleccionados.")
         return redirect('planificacion:seleccionar_para_planificar')

    # Asumimos que todos pertenecen al mismo lote (podríamos verificar)
    lote_contexto = ambientes_seleccionados.first().lote

    # Crear o obtener instancias de UsoDeSuelo para los seleccionados
    usos_suelo_pks = []
    for amb in ambientes_seleccionados:
        uso, created = UsoDeSuelo.objects.get_or_create(
            ambiente=amb, año=año_zafra, zafra=tipo_zafra,
            defaults={'creado_por': request.user}
        )
        usos_suelo_pks.append(uso.pk)

    queryset_usos = UsoDeSuelo.objects.filter(pk__in=usos_suelo_pks).select_related('ambiente')

    # Crear y procesar el Formset
    formset = UsoDeSueloFormSet(request.POST or None, queryset=queryset_usos)

    if request.method == 'POST' and 'guardar_planificacion' in request.POST: # Verificar si se envió el formset
        if formset.is_valid():
            try:
                with transaction.atomic():
                    instancias = formset.save(commit=False)
                    count_saved = 0
                    for uso_instance in instancias:
                        # Guardar solo si se especificó un uso
                        if uso_instance.tipo_uso and uso_instance.tipo_uso.strip():
                            uso_instance.save()
                            count_saved += 1
                        elif uso_instance.pk: # Si existía y se vació, borrarlo? Opcional
                            # uso_instance.delete()
                            pass
                    messages.success(request, f"Se guardó la planificación para {count_saved} ambiente(s) del lote '{lote_contexto.nombre}' para la zafra {tipo_zafra} {año_zafra}/{año_zafra+1}.")
                    # Redirigir a la selección o al detalle del establecimiento
                    return redirect('planificacion:seleccionar_para_planificar')
            except Exception as e:
                messages.error(request, f"Error al guardar la planificación: {e}")
        else:
            messages.error(request, "Por favor corrija los errores en el formulario.")
    
    context = {
        'lote': lote_contexto,
        'año_zafra': año_zafra,
        'tipo_zafra': tipo_zafra,
        'zafra_display': dict(UsoDeSuelo.ZAFRA_CHOICES).get(tipo_zafra),
        'formset': formset,
        'titulo_pagina': f"Planificar Ambientes Lote {lote_contexto.nombre} - Zafra {tipo_zafra} {año_zafra}/{año_zafra+1}",
    }
    # Usamos el mismo template que antes, pero ahora solo muestra los seleccionados
    return render(request, 'planificacion/planificar_usos.html', context)
