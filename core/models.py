import uuid # Para id_entidad_conceptual
from django.db import models
from django.contrib.gis.db import models as gis_models # Para campos geométricos
from django.conf import settings # Para FK a User en Tarea
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

# Modelo: Empresa
class Empresa(models.Model):
    nombre_razon_social = models.CharField(max_length=255, verbose_name="Nombre o Razón Social")
    nombre_fantasia = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nombre de Fantasía")
    rut = models.CharField(max_length=12, unique=True, blank=True, null=True, verbose_name="RUT")
    direccion = models.CharField(max_length=300, blank=True, null=True, verbose_name="Dirección Fiscal")
    telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    email_contacto = models.EmailField(max_length=254, blank=True, null=True, verbose_name="Email de Contacto")
    otros_atributos = models.JSONField(blank=True, null=True, verbose_name="Otros Atributos", help_text="JSON para atributos adicionales no estructurados.")
    fecha_alta = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Alta")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    def __str__(self):
        return self.nombre_razon_social

    class Meta:
        verbose_name = "Empresa / Cliente"
        verbose_name_plural = "Empresas / Clientes"
        ordering = ['nombre_razon_social']

# Modelo: Establecimiento
class Establecimiento(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="establecimientos", verbose_name="Empresa Propietaria")
    nombre = models.CharField(max_length=255, verbose_name="Nombre del Establecimiento")
    ubicacion_descriptiva = models.TextField(blank=True, null=True, verbose_name="Ubicación Descriptiva/Cómo Llegar")
    punto_referencia = gis_models.PointField(srid=32721, blank=True, null=True, verbose_name="Punto de Referencia Geográfico", help_text="SRID 32721 para Uruguay.")
    otros_atributos = models.JSONField(blank=True, null=True, verbose_name="Otros Atributos")
    fecha_alta = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Alta")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    def __str__(self):
        return f"{self.nombre} ({self.empresa.nombre_razon_social})"

    class Meta:
        verbose_name = "Establecimiento (Campo)"
        verbose_name_plural = "Establecimientos (Campos)"
        unique_together = [['empresa', 'nombre']]
        ordering = ['empresa', 'nombre']

# Modelo: Lote
class Lote(models.Model):
    # Campos para versionado
    id_entidad_conceptual = models.UUIDField(default=uuid.uuid4, editable=False, help_text="Identificador único para todas las versiones de este lote.")
    version_numero = models.PositiveIntegerField(default=1, editable=False, verbose_name="Número de Versión")
    id_version_anterior = models.OneToOneField('self', on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="version_siguiente_lote", verbose_name="Versión Anterior")
    fecha_version = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación de Versión")
    estado_version = models.CharField(max_length=20, choices=[('VIGENTE', 'Vigente'), ('HISTORICO', 'Histórico'), ('EN_EDICION', 'En Edición')], default='VIGENTE', verbose_name="Estado de la Versión")
    # Atributos del Lote
    establecimiento = models.ForeignKey(Establecimiento, on_delete=models.PROTECT, related_name="lotes", verbose_name="Establecimiento")
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Lote")
    categoria = models.CharField(max_length=50, blank=True, null=True, verbose_name="Categoría del Lote", help_text="Ej: i+d, producción")
    geometria = gis_models.MultiPolygonField(srid=32721, verbose_name="Geometría del Lote", help_text="SRID 32721 para Uruguay.")
    superficie_calculada_has = models.FloatField(blank=True, null=True, editable=False, verbose_name="Superficie Calculada (ha)", help_text="Se calcula automáticamente a partir de la geometría.")
    otros_atributos = models.JSONField(blank=True, null=True, verbose_name="Otros Atributos")
    estado_workflow = models.CharField(max_length=30, default='EN_CARGA_GIS', verbose_name="Estado en Workflow",
                                     choices=[('EN_CARGA_GIS', 'En Carga GIS'),
                                              ('PENDIENTE_VALIDACION_PRODUCTOR', 'Pendiente Validación Productor'),
                                              ('VALIDADO_PRODUCTOR', 'Validado por Productor'),
                                              ('CON_AMBIENTACION_EN_PROCESO', 'Con Ambientación en Proceso'),
                                              ('ACTIVO', 'Activo'),
                                              ('HISTORICO_WF', 'Histórico (Workflow)')])

    def save(self, *args, **kwargs):
        # id_entidad_conceptual se asigna con default=uuid.uuid4
        if self.geometria:
            self.superficie_calculada_has = self.geometria.area / 10000
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} (Est: {self.establecimiento.nombre}) - v{self.version_numero} [{self.estado_version}]"

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        ordering = ['establecimiento', 'nombre', '-version_numero']

# Modelo: Ambiente
class Ambiente(models.Model):
    # Campos para versionado
    id_entidad_conceptual = models.UUIDField(default=uuid.uuid4, editable=False, help_text="Identificador único para todas las versiones de este ambiente.")
    version_numero = models.PositiveIntegerField(default=1, editable=False, verbose_name="Número de Versión")
    id_version_anterior = models.OneToOneField('self', on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="version_siguiente_ambiente", verbose_name="Versión Anterior")
    fecha_version = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación de Versión")
    estado_version = models.CharField(max_length=20, choices=[('VIGENTE', 'Vigente'), ('HISTORICO', 'Histórico'), ('EN_EDICION', 'En Edición')], default='VIGENTE', verbose_name="Estado de la Versión")
    # Atributos del Ambiente
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, related_name="ambientes", verbose_name="Lote al que pertenece")
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Ambiente")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")
    categoria = models.CharField(max_length=100, blank=True, null=True, verbose_name="Categoría del Ambiente")
    geometria = gis_models.MultiPolygonField(srid=32721, verbose_name="Geometría del Ambiente", help_text="SRID 32721 para Uruguay.")
    superficie_has = models.FloatField(blank=True, null=True, editable=False, verbose_name="Superficie (ha)", help_text="Se calcula automáticamente a partir de la geometría.")
    
    PRODUCTIVIDAD_CHOICES = [
       ('A', 'Alta'),
       ('D', 'D (Por definir significado exacto)'),
       ('B', 'Baja'),
       ('OTRA', 'Otra (Especificar)'),
    ]
    productividad = models.CharField(max_length=10, choices=PRODUCTIVIDAD_CHOICES, blank=True, null=True, verbose_name="Productividad")
    subindice_productividad = models.CharField(max_length=100, blank=True, null=True, verbose_name="Subíndice Productividad (Texto)")
    relieve = models.CharField(max_length=50, blank=True, null=True, verbose_name="Relieve")
    tipo_suelo_nombre = models.CharField(max_length=100, blank=True, null=True, verbose_name="Tipo de Suelo (Nombre)")
    pendiente_elevada = models.BooleanField(default=False, verbose_name="¿Tiene Pendiente Elevada?")
    erosion_suelo = models.BooleanField(default=False, verbose_name="¿Tiene Erosión de Suelo?")
    otros_atributos = models.JSONField(blank=True, null=True, verbose_name="Otros Atributos")
    estado_workflow = models.CharField(max_length=30, default='EN_CARGA_GIS', verbose_name="Estado en Workflow",
                                     choices=[('EN_CARGA_GIS', 'En Carga GIS'),
                                              ('PENDIENTE_VALIDACION_AGRONOMO', 'Pendiente Validación Agrónomo'),
                                              ('EN_CORRECCION_GIS', 'En Corrección GIS'),
                                              ('ACTIVO', 'Activo'),
                                              ('HISTORICO_WF', 'Histórico (Workflow)')])

    def save(self, *args, **kwargs):
        # id_entidad_conceptual se asigna con default=uuid.uuid4
        if self.geometria:
            self.superficie_has = self.geometria.area / 10000
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} (Lote: {self.lote.nombre}) - v{self.version_numero} [{self.estado_version}]"

    class Meta:
        verbose_name = "Ambiente"
        verbose_name_plural = "Ambientes"
        ordering = ['lote', 'nombre', '-version_numero']

# Modelo: Tarea
class Tarea(models.Model):
    ESTADOS_TAREA = [
       ('PENDIENTE', 'Pendiente'),
       ('ASIGNADA', 'Asignada (a usuario específico)'),
       ('EN_PROGRESO', 'En Progreso'),
       ('COMPLETADA', 'Completada'),
       ('BLOQUEADA', 'Bloqueada'),
       ('REQUIERE_CORRECCION', 'Requiere Corrección'),
       ('CANCELADA', 'Cancelada'),
    ]
    TIPOS_TAREA_CHOICES = [ 
       ('DIGITALIZAR_LOTES', 'Digitalizar Lotes'),
       ('VALIDAR_DIGITALIZACION_LOTES', 'Validar Digitalización Lotes'),
       ('CREAR_ACTUALIZAR_AMBIENTACION', 'Crear/Actualizar Ambientación'),
       ('VALIDAR_ENRIQUECER_AMBIENTACION', 'Validar/Enriquecer Ambientación'),
       ('CORREGIR_GEOMETRIA_AMBIENTE', 'Corregir Geometría Ambiente'),
       ('PLANIFICAR_ORDEN_MUESTREO', 'Planificar Orden de Muestreo'),
       ('EJECUTAR_ORDEN_MUESTREO', 'Ejecutar Orden de Muestreo (Muestreador)'),
       ('PROCESAR_ANALISIS_SUELO', 'Procesar Análisis de Suelo'),
       # Se agregarán más tipos a medida que se detallen otros flujos
    ]

    tipo_tarea = models.CharField(max_length=100, choices=TIPOS_TAREA_CHOICES, verbose_name="Tipo de Tarea")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción Detallada")
    estado_tarea = models.CharField(max_length=30, choices=ESTADOS_TAREA, default='PENDIENTE', verbose_name="Estado de la Tarea")
    
    rol_asignado = models.ForeignKey('usuarios.Rol', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Rol Grupal Asignado", help_text="Rol al que pertenece esta tarea.")
    usuario_asignado_actualmente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_tomadas", verbose_name="Usuario Asignado Actualmente")
    
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_creadas", verbose_name="Creado Por")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_limite = models.DateField(null=True, blank=True, verbose_name="Fecha Límite")
    fecha_finalizacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Finalización")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, verbose_name="Tipo de Entidad Relacionada")
    object_id = models.PositiveIntegerField(verbose_name="ID de Entidad Relacionada")
    entidad_relacionada = GenericForeignKey('content_type', 'object_id')

    comentarios_internos = models.TextField(blank=True, null=True, verbose_name="Comentarios Internos / Bitácora")

    def __str__(self):
        asignacion = str(self.rol_asignado) if self.rol_asignado else "Sin asignar a rol"
        if self.usuario_asignado_actualmente:
            asignacion = str(self.usuario_asignado_actualmente)
        return f"{self.get_tipo_tarea_display()} - {self.get_estado_tarea_display()} (Para: {asignacion})"

    class Meta:
        verbose_name = "Tarea de Workflow"
        verbose_name_plural = "Tareas de Workflow"
        ordering = ['-fecha_creacion']