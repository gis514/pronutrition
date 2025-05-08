from django.db import models

# Create your models here.
from django.contrib import admin
from .models import Rol, PerfilUsuario

admin.site.register(Rol)
admin.site.register(PerfilUsuario)
