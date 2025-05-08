# planificacion/urls.py
from django.urls import path
from . import views

app_name = 'planificacion'

urlpatterns = [
# Renombramos la URL anterior, ahora recibe los parámetros en el POST
path('planificar/', views.planificar_usos_seleccionados, name='planificar_usos_seleccionados'),
# Mantenemos la de selección
path('', views.seleccionar_para_planificar, name='seleccionar_para_planificar'),
]