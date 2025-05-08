# planificacion/forms.py
from django import forms
from core.models import Empresa, Establecimiento, Lote
from .models import UsoDeSuelo # Para choices de zafra
import datetime

class FiltroSeleccionPlanificacionForm(forms.Form):
    # Usaremos campos dependientes (posiblemente con AJAX/htmx después para mejorar)
    # Por ahora, el usuario selecciona todo y luego se carga la info.
    empresa = forms.ModelChoiceField(
        queryset=Empresa.objects.filter(activo=True).order_by('nombre_razon_social'),
        label="Empresa",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    establecimiento = forms.ModelChoiceField(
        # Queryset vacío inicialmente, se poblará con JS/htmx o se filtrará en la vista post-submit
        queryset=Establecimiento.objects.none(),
        label="Establecimiento",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    lote = forms.ModelChoiceField(
        # Queryset vacío inicialmente
        queryset=Lote.objects.none(),
        label="Lote",
        required=True, # Planificaremos por lote
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    año_zafra = forms.IntegerField(
        label="Año Inicio Zafra",
        initial=datetime.date.today().year,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 2020, 'max': 2050})
    )
    tipo_zafra = forms.ChoiceField(
        label="Tipo de Zafra",
        choices=UsoDeSuelo.ZAFRA_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # Para simplificar la carga inicial, podríamos obtener los establecimientos
    # basados en la empresa seleccionada en el POST de la vista.
    def __init__(self, *args, **kwargs):
        empresa_seleccionada = kwargs.pop('empresa', None)
        establecimiento_seleccionado = kwargs.pop('establecimiento', None)
        super().__init__(*args, **kwargs)

        if empresa_seleccionada:
            self.fields['establecimiento'].queryset = Establecimiento.objects.filter(
                empresa=empresa_seleccionada, activo=True
            ).order_by('nombre')
            # Si queremos preseleccionar
            # self.initial['establecimiento'] = establecimiento_seleccionado_id

        if establecimiento_seleccionado:
             self.fields['lote'].queryset = Lote.objects.filter(
                 establecimiento=establecimiento_seleccionado,
                 estado_version='VIGENTE',
                 estado_workflow='ACTIVO' # Solo lotes listos
             ).order_by('nombre')
            # self.initial['lote'] = lote_seleccionado_id



# Formulario base para editar/crear un UsoDeSuelo
class UsoDeSueloForm(forms.ModelForm):
    class Meta:
        model = UsoDeSuelo
        # Campos a editar en la tabla/formset
        fields = ['tipo_uso'] # El agrónomo principalmente define el cultivo
        # Podrías añadir más campos aquí si los agregaste al modelo:
        # fields = ['tipo_uso', 'variedad_hibrido', 'fecha_siembra_estimada', 'rendimiento_objetivo']

    # Hacemos el campo requerido
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_uso'].required = True
        self.fields['tipo_uso'].widget.attrs.update({'placeholder': 'Ej: Soja 1ra, Maíz'})


# Formset para manejar múltiples UsoDeSuelo (uno por ambiente)
UsoDeSueloFormSet = forms.modelformset_factory(
    UsoDeSuelo,
    form=UsoDeSueloForm,
    extra=0, # No mostrar formularios extra vacíos
    can_delete=False # No permitir borrar desde aquí (se maneja si no se asigna uso?)
)

# Formulario para seleccionar Lote y Zafra
class SeleccionPlanificacionForm(forms.Form):
    # Podrías usar ModelChoiceField para seleccionar Empresa->Establecimiento->Lote
    # O simplemente un campo para Lote si la navegación ya te lleva a un Establecimiento
    lote = forms.ModelChoiceField(
        queryset=Lote.objects.filter(estado_version='VIGENTE', estado_workflow='ACTIVO'), # Solo lotes activos
        label="Seleccionar Lote",
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    año_zafra = forms.IntegerField(
        label="Año Inicio Zafra",
        initial=datetime.date.today().year, # Sugerir año actual
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 2020, 'max': 2050})
    )
    tipo_zafra = forms.ChoiceField(
        label="Tipo de Zafra",
        choices=UsoDeSuelo.ZAFRA_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )