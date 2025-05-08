# planificacion/models.py
from django.db import models
from core.models import Lote, Ambiente # Importamos Lote y Ambiente
from django.conf import settings # Para el usuario que planifica

class UsoDeSuelo(models.Model):
    ZAFRA_INV = 'INVIERNO'
    ZAFRA_VER = 'VERANO'
    ZAFRA_CHOICES = [
        (ZAFRA_INV, 'Invierno'),
        (ZAFRA_VER, 'Verano'),
    ]

    # Vinculación: ¿A Lote o a Ambiente?
    # El relevamiento dice "planificación anual a nivel de ambiente" [79]
    # pero el modelo inicial decía "Todos los ambientes de un lote ... tienen un mismo uso" [5]
    # y luego que UsoDeSuelo se relaciona con Lote [31] y Opcionalmente con Ambiente [41].
    # PROPUESTA: Vincularlo principalmente al Ambiente, ya que es la unidad mínima de manejo.
    # Si un lote entero tiene el mismo uso, se asignará a todos sus ambientes.
    ambiente = models.ForeignKey(Ambiente, on_delete=models.CASCADE, related_name="usos_suelo", verbose_name="Ambiente")
    # lote = models.ForeignKey(Lote, on_delete=models.CASCADE, related_name="usos_suelo_lote", verbose_name="Lote") # Podría añadirse si se necesita la relación directa al lote también

    año = models.PositiveIntegerField(verbose_name="Año de Inicio de Zafra") # Ej: 2024 para zafra 24/25
    zafra = models.CharField(max_length=10, choices=ZAFRA_CHOICES, verbose_name="Zafra") # Invierno o Verano

    # Tipo de Uso / Cultivo: Podría ser un CharField simple o un FK a un modelo 'Cultivo'
    tipo_uso = models.CharField(max_length=100, verbose_name="Cultivo / Tipo de Uso") # Ej: Soja, Maíz, Trigo, Descanso, Pastura

    # Otros campos relevantes para la planificación?
    # variedad_hibrido = models.CharField(max_length=100, blank=True, null=True, verbose_name="Variedad / Híbrido")
    # fecha_siembra_estimada = models.DateField(blank=True, null=True, verbose_name="Fecha Siembra Estimada")
    # rendimiento_objetivo = models.FloatField(blank=True, null=True, verbose_name="Rendimiento Objetivo (ton/ha)")

    # Auditoría
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="usos_suelo_creados")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Uso de Suelo Planificado"
        verbose_name_plural = "Usos de Suelo Planificados"
        # Una combinación de ambiente, año y zafra debe ser única
        unique_together = [['ambiente', 'año', 'zafra']]
        ordering = ['ambiente__lote__establecimiento__empresa', 'ambiente__lote', 'ambiente', '-año', 'zafra']

    def __str__(self):
        return f"{self.tipo_uso} ({self.get_zafra_display()} {self.año}/{self.año+1}) - Amb: {self.ambiente.nombre}"
    
    