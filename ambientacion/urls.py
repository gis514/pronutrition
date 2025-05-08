# ambientacion/urls.py
from django.urls import path
from . import views

app_name = 'ambientacion'

urlpatterns = [
    # Empresas
    path('empresas/', views.lista_empresas, name='lista_empresas'),
    path('empresa/crear/', views.crear_empresa, name='crear_empresa'),
    path('empresa/<int:empresa_id>/', views.detalle_empresa, name='detalle_empresa'),
    
    # Establecimientos
    path('establecimiento/crear/<int:empresa_id>/', views.crear_establecimiento, name='crear_establecimiento'),
    path('establecimiento/<int:establecimiento_id>/', views.detalle_establecimiento, name='detalle_establecimiento'),
    path('establecimiento/<int:establecimiento_id>/solicitar-digitalizacion/', views.solicitar_digitalizacion_lote, name='solicitar_digitalizacion_lote'),
    
    # Lotes
    path('lote/<int:lote_id>/validar/', views.validar_lote, name='validar_lote'),
    path('lote/<int:lote_id>/ambientar/', views.subir_ambientes_lote, name='subir_ambientes_lote'),
    path('lote/<int:lote_id>/validar_ambientes/', views.validar_enriquecer_ambientes, name='validar_enriquecer_ambientes'),
    # Tareas GIS
    path('tareas-gis/', views.vista_tareas_gis, name='vista_tareas_gis'),
    path('tareas/agronomo/', views.vista_tareas_agronomo, name='vista_tareas_agronomo'),
    path('tarea/<int:tarea_id>/procesar/', views.procesar_digitalizacion_lote, name='procesar_digitalizacion_lote'),
    path('tarea/<int:tarea_id>/tomar/', views.tomar_tarea_gis, name='tomar_tarea_gis'),
]