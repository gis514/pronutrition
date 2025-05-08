from django import template

register = template.Library()

@register.filter
def split(value, delimiter):
    """
    Devuelve una lista de subcadenas obtenidas al dividir la cadena de entrada por el delimitador.
    Uso: {{ value|split:"," }}
    """
    return value.split(delimiter)
