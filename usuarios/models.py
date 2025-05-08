from django.db import models
from django.conf import settings # Para referenciar a settings.AUTH_USER_MODEL
from django.db.models.signals import post_save
from django.dispatch import receiver

# Modelo: Rol
class Rol(models.Model):
    ROL_CLIENTE = 'cliente'
    ROL_GIS = 'area_gis'
    ROL_ING_AGRONOMO = 'area_ing_agronomo'
    ROL_LOGISTICA = 'area_logistica'
    ROL_LABORATORIO = 'area_laboratorio'
    ROL_MUESTREADOR = 'muestreador'
    ROL_ADMINISTRACION = 'area_administracion'
    ROL_GERENCIA = 'area_gerencia'
    ROL_ADMIN_SISTEMA = 'admin_sistema'

    ROLES_CHOICES = [
       (ROL_CLIENTE, 'Cliente/Productor'),
       (ROL_GIS, 'Área GIS'),
       (ROL_ING_AGRONOMO, 'Ingeniero Agrónomo'),
       (ROL_LOGISTICA, 'Área Logística'),
       (ROL_LABORATORIO, 'Área Laboratorio'),
       (ROL_MUESTREADOR, 'Muestreador de Campo'),
       (ROL_ADMINISTRACION, 'Área Administración'),
       (ROL_GERENCIA, 'Área Gerencia'),
       (ROL_ADMIN_SISTEMA, 'Administrador del Sistema'),
    ]

    id_rol = models.CharField(max_length=50, primary_key=True, choices=ROLES_CHOICES, verbose_name="Identificador del Rol")
    nombre_visible = models.CharField(max_length=100, verbose_name="Nombre Visible del Rol")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción del Rol")

    def __str__(self):
        return self.get_id_rol_display()

    class Meta:
        verbose_name = "Rol de Usuario"
        verbose_name_plural = "Roles de Usuario"
        ordering = ['nombre_visible']

    @classmethod
    def asegurar_roles_basicos(cls):
        for id_r, nombre_v in cls.ROLES_CHOICES:
            cls.objects.get_or_create(id_rol=id_r, defaults={'nombre_visible': nombre_v})

# Modelo: PerfilUsuario
class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_pronutrition", verbose_name="Usuario del Sistema")
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Rol en ProNutrition", help_text="Rol principal del usuario en el sistema.")
    telefono_contacto = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono de Contacto Adicional")
    empresa_asociada = models.ForeignKey('core.Empresa', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Empresa Asociada (para rol Cliente)", help_text="Si el usuario es un cliente, a qué empresa representa.")
    activo = models.BooleanField(default=True, verbose_name="Perfil Activo")

    def __str__(self):
        rol_display = self.rol.get_id_rol_display() if self.rol else 'Sin rol asignado'
        return f"Perfil de {self.usuario.username} (Rol: {rol_display})"

    class Meta:
        verbose_name = "Perfil de Usuario ProNutrition"
        verbose_name_plural = "Perfiles de Usuario ProNutrition"

# Signal para crear/actualizar PerfilUsuario automáticamente cuando se crea/actualiza un User
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def crear_o_actualizar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.create(usuario=instance)
    try:
        # Asegurarse de que el perfil exista y guardarlo puede ser útil si se agregan campos al User que afecten al perfil.
        # Sin embargo, si el perfil solo se crea y luego se modifica manualmente, esto podría ser opcional.
        # Por seguridad, para asegurar que el perfil exista:
        if not hasattr(instance, 'perfil_pronutrition'):
             PerfilUsuario.objects.create(usuario=instance)
        else:
            instance.perfil_pronutrition.save()
    except PerfilUsuario.DoesNotExist:
         PerfilUsuario.objects.create(usuario=instance)