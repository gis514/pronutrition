from django import forms
from core.models import Empresa, Establecimiento
from django.contrib.gis import forms as gis_forms
from django import forms
from django.forms import modelformset_factory # Para crear el Formset
from core.models import Ambiente, Lote # Y otros modelos necesarios
from django.contrib.gis import forms as gis_forms
class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ['nombre_razon_social', 'nombre_fantasia', 'rut', 'direccion', 'telefono', 'email_contacto']

class EstablecimientoForm(forms.ModelForm):
    class Meta:
        model = Establecimiento
        fields = ['nombre', 'ubicacion_descriptiva', 'punto_referencia', 'activo']
        widgets = {
            # Widget modificado para evitar problemas de integridad
            'punto_referencia': gis_forms.OSMWidget(attrs={
                'map_width': 800,
                'map_height': 500,
                'default_lat': -33,
                'default_lon': -56,
                'default_zoom': 6,
                # Desactivar la verificación de integridad
                'no_integrity_check': True
            })
        }

class SolicitudDigitalizacionLoteForm(forms.Form):
    nombre_lote_referencia = forms.CharField(
        label="Nombre de Referencia para Lote(s)",
        max_length=100,
        required=False,
        help_text="Ej: 'Lotes nuevos zona este', 'Lote frente a ruta'"
    )
    archivo_referencia_lotes = forms.FileField(
        label="Archivo de Referencia (Opcional)",
        required=False,
        help_text="Sube un archivo KMZ, KML, GPX, o un ZIP con Shapefiles como guía."
    )
    comentarios = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        label="Comentarios Adicionales",
        required=False,
        help_text="Cualquier detalle importante para el equipo GIS."
    )

class ProcesarDigitalizacionLoteForm(forms.Form):
    archivo_shape = forms.FileField(
        label="Archivo Shapefile (.zip o .shp)",
        required=True,
        help_text="Sube un archivo .zip que contenga los archivos .shp, .shx, .dbf (y opcionalmente .prj) o el archivo .shp directamente si los otros están en el mismo directorio implicitamente."
    )
    comentarios_gis = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        label="Comentarios del GIS (Opcional)",
        required=False
    )

class ProcesarAmbientacionLoteForm(forms.Form): # Nuevo nombre por claridad
    archivo_shape_ambientes = forms.FileField(
        label="Archivo Shapefile de Ambientes (.zip o .shp)",
        required=True,
        help_text="Sube un .zip con (.shp, .shx, .dbf, [.prj]) o solo el .shp. Las geometrías deben estar DENTRO del lote asociado a esta tarea."
    )
    comentarios_gis = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        label="Comentarios del GIS (Opcional)",
        required=False
    )


# Formulario para los atributos que edita el Agrónomo
class AmbienteAgronomoForm(forms.ModelForm):
    class Meta:
        model = Ambiente
        # Campos que el agrónomo puede editar/completar:
        fields = [
            'nombre', # Permitir ajustar nombre si es necesario
            'descripcion',
            'categoria',
            'productividad',
            'subindice_productividad',
            'relieve',
            'tipo_suelo_nombre',
            # 'subindice_suelo_1', # Descomentar si se usan
            # 'subindice_suelo_2',
            'pendiente_elevada',
            'erosion_suelo',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 2}),
            # Podrías usar Select para campos con choices si son muchos
            # 'productividad': forms.Select(),
            # 'relieve': forms.TextInput(attrs={'placeholder': 'Ej: Plano, Ondulado'}),
        }
        # Puedes añadir labels personalizados si quieres
        labels = {
            'subindice_productividad': 'Subíndice Prod. (Texto)',
            'tipo_suelo_nombre': 'Tipo Suelo',
            'pendiente_elevada': 'Pend. Elevada?',
            'erosion_suelo': 'Erosión Suelo?'
        }

# Crear un Formset basado en el formulario anterior
# extra=0 significa que no mostrará formularios vacíos extra para añadir nuevos ambientes aquí
AmbienteAgronomoFormSet = modelformset_factory(
    Ambiente, form=AmbienteAgronomoForm, extra=0
)