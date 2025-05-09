# Generated by Django 5.2 on 2025-05-08 02:35

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UsoDeSuelo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('año', models.PositiveIntegerField(verbose_name='Año de Inicio de Zafra')),
                ('zafra', models.CharField(choices=[('INVIERNO', 'Invierno'), ('VERANO', 'Verano')], max_length=10, verbose_name='Zafra')),
                ('tipo_uso', models.CharField(max_length=100, verbose_name='Cultivo / Tipo de Uso')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_modificacion', models.DateTimeField(auto_now=True)),
                ('ambiente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usos_suelo', to='core.ambiente', verbose_name='Ambiente')),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='usos_suelo_creados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Uso de Suelo Planificado',
                'verbose_name_plural': 'Usos de Suelo Planificados',
                'ordering': ['ambiente__lote__establecimiento__empresa', 'ambiente__lote', 'ambiente', '-año', 'zafra'],
                'unique_together': {('ambiente', 'año', 'zafra')},
            },
        ),
    ]
