from django.apps import AppConfig

class UsuariosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'usuarios'

    #def ready(self):
        #import usuarios.signals # Aunque el decorador @receiver usualmente es suficiente
        # Para asegurar que los roles se creen al inicio (opcional, mejor una migración de datos):
        # from .models import Rol
        # Rol.asegurar_roles_basicos()