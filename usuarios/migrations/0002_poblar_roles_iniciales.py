# En el archivo de migración (ej. 0002_poblar_roles_iniciales.py)
from django.db import migrations

def asegurar_roles(apps, schema_editor):
    RolModel = apps.get_model('usuarios', 'Rol')
    # Copia aquí las ROLES_CHOICES o impórtalas si es posible (puede ser complejo en migraciones)
    ROLES_CHOICES = [
        ('cliente', 'Cliente/Productor'),
        ('area_gis', 'Área GIS'),
        # ... todos los roles ...
        ('admin_sistema', 'Administrador del Sistema'),
    ]
    for id_r, nombre_v in ROLES_CHOICES:
        RolModel.objects.get_or_create(id_rol=id_r, defaults={'nombre_visible': nombre_v})

class Migration(migrations.Migration):
    dependencies = [
        ('usuarios', '0001_initial'), # Depende de la migración que creó el modelo Rol
    ]
    operations = [
        migrations.RunPython(asegurar_roles),
    ]