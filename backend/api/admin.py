# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group
from .models import WIGOSNodeGroup, WIGOSNodeUser


# Define the inline layout for your extra fields
class WIGOSNodeGroupProfileInline(admin.StackedInline):
    model = WIGOSNodeGroup
    can_delete = False
    issuer_identifier = 'Extra Group Information'


admin.site.unregister(Group)
admin.site.register(WIGOSNodeUser)

@admin.register(Group)
class CustomGroupAdmin(GroupAdmin):
    inlines = [WIGOSNodeGroupProfileInline]