from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin # O LeafletGeoAdmin
from .models import Empresa, Establecimiento, Lote, Ambiente, Tarea

admin.site.register(Empresa)
admin.site.register(Establecimiento)
# Para Lote y Ambiente, usamos OSMGeoAdmin para ver/editar geometrías
@admin.register(Lote)
class LoteAdmin(GISModelAdmin): # o admin.ModelAdmin si no quieres mapa inicialmente
    list_display = ('nombre', 'establecimiento', 'estado_version', 'version_numero', 'estado_workflow')
    list_filter = ('estado_version', 'estado_workflow', 'establecimiento')
    # default_lat = -33 # Latitud aproximada de Uruguay
    # default_lon = -56 # Longitud aproximada de Uruguay
    # default_zoom = 6

@admin.register(Ambiente)
class AmbienteAdmin(GISModelAdmin): # o admin.ModelAdmin
    list_display = ('nombre', 'lote', 'estado_version', 'version_numero', 'estado_workflow')
    list_filter = ('estado_version', 'estado_workflow', 'lote__establecimiento')

admin.site.register(Tarea)