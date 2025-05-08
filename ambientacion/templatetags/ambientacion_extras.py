from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Permite acceder a un elemento de un diccionario en una plantilla"""
    if dictionary is None:
        return None
    
    # Si la key es un string que representa un número, convertirla a int
    if isinstance(key, str) and key.isdigit():
        key = int(key)
        
    return dictionary.get(key, [])
